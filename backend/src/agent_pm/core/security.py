"""Supabase JWT verification.

The SPA authenticates against Supabase (Google OAuth or email OTP) and sends
the resulting access token as ``Authorization: Bearer <jwt>``. This module is
the only place that trusts a token.

Two signing schemes are supported:

* **Asymmetric (preferred).** Supabase publishes a JWKS; keys rotate without
  redeploying us. Used when ``SUPABASE_JWT_SECRET`` is empty.
* **Legacy shared secret (HS256).** Used when ``SUPABASE_JWT_SECRET`` is set.

Verification is deliberately strict: signature, expiry, audience and issuer are
all checked. A token that merely decodes is not a token that is valid.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from jwt import PyJWKClient
from pydantic import BaseModel, Field

from agent_pm.core.config import Settings, get_settings
from agent_pm.core.errors import AuthenticationError
from agent_pm.core.logging import get_logger

logger = get_logger(__name__)

_ASYMMETRIC_ALGORITHMS = ["RS256", "ES256"]
_SYMMETRIC_ALGORITHMS = ["HS256"]
REQUIRED_CLAIMS = ["exp", "sub", "aud"]


class TokenClaims(BaseModel):
    """The subset of Supabase's claims this application relies on."""

    sub: UUID
    email: str | None = None
    aud: str
    exp: datetime
    iss: str | None = None
    session_id: str | None = None
    app_metadata: dict[str, Any] = Field(default_factory=dict)
    user_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def user_id(self) -> UUID:
        return self.sub

    @property
    def provider(self) -> str:
        """'google' for OAuth sign-in, 'email' for OTP."""
        provider = self.app_metadata.get("provider")
        return str(provider) if provider else "unknown"

    @property
    def display_name(self) -> str | None:
        for key in ("full_name", "name", "user_name"):
            value = self.user_metadata.get(key)
            if value:
                return str(value)
        return None

    @property
    def avatar_url(self) -> str | None:
        value = self.user_metadata.get("avatar_url") or self.user_metadata.get("picture")
        return str(value) if value else None


@lru_cache
def _jwks_client(jwks_url: str) -> PyJWKClient:
    """Cached per URL. PyJWKClient caches fetched keys internally."""
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


def _decode(token: str, settings: Settings) -> dict[str, Any]:
    # REQUIRED_CLAIMS must be present, not merely valid when present: a token
    # without an expiry or an audience is not one we accept. The option dict is
    # written inline at each call so it types as PyJWT's Options TypedDict.
    if settings.supabase_jwt_secret:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=_SYMMETRIC_ALGORITHMS,
            audience=settings.supabase_jwt_audience,
            issuer=settings.supabase_jwt_issuer or None,
            options={"require": REQUIRED_CLAIMS},
        )
        return claims

    if not settings.supabase_url:
        raise AuthenticationError("Auth is not configured on this server")

    signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
    verified: dict[str, Any] = jwt.decode(
        token,
        signing_key.key,
        algorithms=_ASYMMETRIC_ALGORITHMS,
        audience=settings.supabase_jwt_audience,
        issuer=settings.supabase_jwt_issuer,
        options={"require": REQUIRED_CLAIMS},
    )
    return verified


def verify_token_sync(token: str, settings: Settings | None = None) -> TokenClaims:
    """Verify and parse an access token. Raises ``AuthenticationError``.

    Blocking: the first call may fetch the JWKS document. Prefer
    :func:`verify_token` from async code.
    """
    settings = settings or get_settings()
    try:
        raw = _decode(token, settings)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthenticationError("Access token has the wrong audience") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthenticationError("Access token was issued by an unknown issuer") from exc
    except jwt.PyJWKClientError as exc:
        # Key fetch failed — infrastructure, not the caller's fault, but we
        # still cannot authenticate them.
        logger.warning("jwks_fetch_failed", extra={"error": str(exc)})
        raise AuthenticationError("Unable to verify access token") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Access token is invalid") from exc

    try:
        return TokenClaims.model_validate(raw)
    except Exception as exc:  # pragma: no cover - malformed provider payload
        raise AuthenticationError("Access token claims are malformed") from exc


async def verify_token(token: str, settings: Settings | None = None) -> TokenClaims:
    """Async wrapper: key fetching and RSA verification run off the event loop."""
    return await asyncio.to_thread(verify_token_sync, token, settings)


def extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise AuthenticationError("Missing Authorization header")
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Authorization header must be 'Bearer <token>'")
    return token.strip()


def is_expired(claims: TokenClaims) -> bool:
    return claims.exp <= datetime.now(UTC)
