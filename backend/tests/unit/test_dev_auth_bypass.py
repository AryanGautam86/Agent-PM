"""The local-only authentication bypass.

The bypass exists so the UI is usable before Supabase is configured. It is
also the single most dangerous setting in the codebase, so its guard rails get
their own tests: it must be impossible to enable outside local development,
and start-up must fail loudly rather than silently serving every request as
one user.
"""

from __future__ import annotations

import pytest

from agent_pm.core.config import Settings

BYPASS = "dev@example.com"


def test_bypass_is_active_in_local() -> None:
    settings = Settings(environment="local", dev_auth_bypass_email=BYPASS)

    assert settings.dev_auth_bypass_active


def test_bypass_is_off_when_unset() -> None:
    assert not Settings(environment="local").dev_auth_bypass_active


@pytest.mark.parametrize("environment", ["dev", "staging", "prod"])
def test_startup_fails_if_the_bypass_is_set_outside_local(environment: str) -> None:
    """A misconfigured deploy must crash on boot, not accept traffic."""
    with pytest.raises(ValueError, match="only permitted when ENVIRONMENT=local"):
        Settings(environment=environment, dev_auth_bypass_email=BYPASS)


@pytest.mark.parametrize("environment", ["dev", "staging", "prod"])
def test_non_local_environments_start_fine_without_it(environment: str) -> None:
    settings = Settings(environment=environment)

    assert not settings.dev_auth_bypass_active


def test_dev_claims_are_stable_for_the_same_email() -> None:
    """The synthetic id is derived from the email, so a developer keeps the
    same row — and their memberships — across restarts."""
    from agent_pm.api.deps import _dev_claims

    settings = Settings(environment="local", dev_auth_bypass_email=BYPASS)
    first = _dev_claims(settings)
    second = _dev_claims(settings)

    assert first.sub == second.sub
    assert first.email == BYPASS
    assert first.provider == "dev-bypass"


def test_dev_claims_differ_between_developers() -> None:
    from agent_pm.api.deps import _dev_claims

    one = _dev_claims(Settings(environment="local", dev_auth_bypass_email="a@x.com"))
    two = _dev_claims(Settings(environment="local", dev_auth_bypass_email="b@x.com"))

    assert one.sub != two.sub
