"""CORS origin parsing.

Regression cover for a deploy failure: `cors_origins` is a list, so
pydantic-settings JSON-decoded it at the source *before* any validator ran. A
value that was not valid JSON — including an empty one — raised SettingsError
while the module was still importing, so the process exited before it could
log anything explaining why.

Hosting dashboards are full of plain-text fields, so this must accept whatever
a person reasonably types, and must never be the reason a service fails to
boot.
"""

from __future__ import annotations

import pytest

from agent_pm.core.config import Settings

DEFAULT = ["http://localhost:5173"]


def origins(value: str | None) -> list[str]:
    if value is None:
        return Settings().cors_origins
    return Settings(cors_origins=value).cors_origins  # type: ignore[arg-type]


def test_json_array() -> None:
    assert origins('["https://a.app","https://b.app"]') == [
        "https://a.app",
        "https://b.app",
    ]


def test_single_origin_unquoted() -> None:
    assert origins("https://agent-pm.vercel.app") == ["https://agent-pm.vercel.app"]


def test_comma_separated() -> None:
    assert origins("https://a.app,https://b.app") == ["https://a.app", "https://b.app"]


def test_comma_separated_with_spaces() -> None:
    assert origins("https://a.app , https://b.app") == [
        "https://a.app",
        "https://b.app",
    ]


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_falls_back_to_the_default(blank: str) -> None:
    """The exact case that took the service down: an empty dashboard field."""
    assert origins(blank) == DEFAULT


def test_unset_uses_the_default() -> None:
    assert origins(None) == DEFAULT


def test_malformed_json_is_salvaged_not_fatal() -> None:
    """Better a working service with imperfect CORS than no service at all."""
    assert origins('["https://a.app", "https://b.app"') == [
        "https://a.app",
        "https://b.app",
    ]


def test_a_real_list_passes_through() -> None:
    assert Settings(cors_origins=["https://a.app"]).cors_origins == ["https://a.app"]


def test_no_input_shape_can_stop_the_app_booting() -> None:
    """The property that actually matters."""
    for value in ["", "  ", "[]", "[", "]", "a,,b", '"https://a.app"', "https://a.app"]:
        assert isinstance(origins(value), list)
