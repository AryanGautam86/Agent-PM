"""Shared machinery for outbound adapters.

Every integration is a ``typing.Protocol`` with two implementations: a real one
and a fixture one. ``integrations/registry.py`` chooses between them based on
whether credentials are configured, which is what lets the whole system run
offline with deterministic data.

Rules for adapters:

* Translate foreign errors into :class:`IntegrationError` — no ``httpx``
  exception escapes this package.
* Return typed DTOs, never raw JSON.
* Read methods are free to run unprompted; write methods are only ever called
  from an approved payload.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent_pm.core.errors import IntegrationError, RateLimitedError
from agent_pm.core.logging import get_logger

logger = get_logger(__name__)

RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class HttpIntegration:
    """Base for HTTP-backed adapters: one client, uniform errors, retries."""

    name: str = "http"

    def __init__(
        self,
        base_url: str = "",
        *,
        headers: dict[str, str] | None = None,
        auth: httpx.Auth | tuple[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers or {},
            auth=auth,
            timeout=timeout or DEFAULT_TIMEOUT,
            follow_redirects=True,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RateLimitedError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        try:
            response = await self._client.request(method, url, params=params, json=json)
        except httpx.TransportError as exc:
            raise IntegrationError(self.name, f"network error calling {url}: {exc}") from exc

        if response.status_code in RETRYABLE_STATUS:
            # Raised so tenacity retries; escapes as itself if attempts run out.
            raise RateLimitedError(
                f"{self.name} returned {response.status_code}",
                details={"url": url, "status": response.status_code},
            )

        if response.status_code >= 400:
            raise IntegrationError(
                self.name,
                f"{method} {url} failed with {response.status_code}",
                details={"status": response.status_code, "body": response.text[:500]},
            )

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    async def get(self, url: str, **kwargs: Any) -> Any:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Any:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> Any:
        return await self.request("PUT", url, **kwargs)
