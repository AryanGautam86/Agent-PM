"""Typed application settings.

One source of truth for configuration. Nothing else in the codebase reads
``os.environ`` — if a value is needed, it gets a field here so that it is
typed, documented, and validated at start-up rather than at first use.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from agent_pm.core.enums import Environment


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Application ----------
    app_name: str = "agent-pm"
    environment: Environment = Environment.LOCAL
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    # NoDecode is essential. Without it pydantic-settings JSON-decodes any
    # complex type at the source, *before* validators run — so a value that is
    # not valid JSON raises SettingsError during import and the process exits
    # before logging anything useful. Hosting dashboards are full of values
    # typed as plain text, so this field has to accept them.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # ---------- Supabase ----------
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    # ---------- Database ----------
    database_url: str = ""
    alembic_database_url: str = ""
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 1800

    # ---------- Anthropic ----------
    anthropic_api_key: str = ""
    anthropic_model_structured: str = "claude-sonnet-5"
    anthropic_model_narrative: str = "claude-opus-5"
    anthropic_max_tokens: int = 4096
    anthropic_timeout_seconds: float = 120.0

    # ---------- Jira ----------
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    # ---------- GitHub ----------
    github_token: str = ""

    # ---------- Teams ----------
    teams_webhook_url: str = ""
    teams_tenant_id: str = ""
    teams_client_id: str = ""
    teams_client_secret: str = ""

    # ---------- Agent policy ----------
    scheduler_enabled: bool = False
    scheduler_tick_seconds: int = 60
    grounding_min_citation_ratio: float = Field(default=0.9, ge=0.0, le=1.0)
    approval_expiry_hours: int = Field(default=24, gt=0)
    max_nudges_per_person_per_day: int = Field(default=3, ge=0)
    blocker_age_days_before_risk: int = Field(default=2, gt=0)
    nudge_lead_time_hours: int = Field(default=24, gt=0)

    # ---------- Onboarding ----------
    auto_join_new_users: bool = Field(
        default=True,
        description="Give anyone who signs in immediate access to a workspace. "
        "Without this a new account belongs to no engagement, so every page "
        "renders with a null engagement id and every action fails.",
    )
    default_engagement_slug: str = Field(
        default="",
        description="Engagement new users join. Blank means the first active "
        "one; if none exists, a workspace is created so the app is never empty.",
    )

    # ---------- A2A ----------
    meeting_agent_webhook_secret: str = ""

    # ---------- Local development only ----------
    dev_auth_bypass_email: str = Field(
        default="",
        description="When set AND environment is local, every request is "
        "treated as this user and no token is required. Lets the UI be used "
        "before Supabase is configured. Start-up fails if this is set in any "
        "other environment, so it cannot reach a deployed service.",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept every form somebody might reasonably type.

            ["https://a.app","https://b.app"]   JSON array
            https://a.app,https://b.app         comma separated
            https://a.app                       a single origin
            (blank)                             falls back to the default

        A misconfigured CORS value should degrade to the default, never stop
        the service from booting.
        """
        if not isinstance(value, str):
            return value

        text = value.strip()
        if not text:
            return ["http://localhost:5173"]

        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                # Malformed JSON: salvage what looks like origins rather than
                # crashing the process.
                text = text.strip("[]")
            else:
                return [str(origin).strip() for origin in parsed if str(origin).strip()]

        return [
            origin.strip().strip('"').strip("'")
            for origin in text.split(",")
            if origin.strip().strip('"').strip("'")
        ]

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _dev_bypass_is_local_only(self) -> Settings:
        """Refuse to start rather than serve unauthenticated traffic.

        This is the single guarantee that makes the bypass safe to have in the
        codebase at all: a misconfigured deploy crashes on boot instead of
        quietly accepting every request as one user.
        """
        if self.dev_auth_bypass_email and self.environment is not Environment.LOCAL:
            raise ValueError(
                "DEV_AUTH_BYPASS_EMAIL is set but ENVIRONMENT is "
                f"{self.environment.value!r}. It is only permitted when "
                "ENVIRONMENT=local. Unset it."
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.environment in {Environment.STAGING, Environment.PROD}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supabase_jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def migration_database_url(self) -> str:
        return self.alembic_database_url or self.database_url

    # ---- capability flags -------------------------------------------------
    # Each integration falls back to a deterministic fixture when unconfigured,
    # so the whole system runs offline. These flags are the switch.

    @computed_field  # type: ignore[prop-decorator]
    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jira_configured(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def github_configured(self) -> bool:
        return bool(self.github_token)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def teams_configured(self) -> bool:
        return bool(self.teams_webhook_url)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dev_auth_bypass_active(self) -> bool:
        """The environment check is repeated here deliberately — belt and
        braces around the one setting that can disable authentication."""
        return bool(
            self.dev_auth_bypass_email and self.environment is Environment.LOCAL
        )


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Cached so that FastAPI dependencies and module-level consumers observe the
    same object. Tests clear the cache via ``get_settings.cache_clear()``.
    """
    return Settings()
