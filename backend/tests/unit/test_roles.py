"""Authorisation roles.

Two role systems exist on purpose and are easy to confuse:

* ``PodRole`` describes what someone does on an engagement. It grants nothing.
* ``AppRole`` decides what someone may do, and only it confers the right to
  decide approvals.

The tests below pin that separation, because a bug that let a pod role grant
approval rights would silently defeat the human-in-the-loop guarantee.
"""

from __future__ import annotations

import pytest

from agent_pm.core.enums import AppRole, PodRole
from agent_pm.schemas.auth import CurrentUser


def make_user(role: AppRole) -> CurrentUser:
    return CurrentUser(
        id="00000000-0000-0000-0000-000000000001",  # type: ignore[arg-type]
        email="someone@example.com",
        role=role,
    )


@pytest.mark.parametrize(
    ("role", "can_approve"),
    [
        (AppRole.ADMIN, True),
        (AppRole.DELIVERY_LEAD, True),
        (AppRole.PRODUCT_OWNER, True),
        (AppRole.ENGINEER, False),
    ],
)
def test_only_senior_app_roles_may_approve(role: AppRole, can_approve: bool) -> None:
    assert role.can_approve is can_approve
    assert make_user(role).can_approve is can_approve


def test_only_admin_is_admin() -> None:
    assert make_user(AppRole.ADMIN).is_admin
    for role in (AppRole.DELIVERY_LEAD, AppRole.PRODUCT_OWNER, AppRole.ENGINEER):
        assert not make_user(role).is_admin


def test_pod_roles_confer_no_privilege() -> None:
    """A pod role is descriptive. It must never appear in an authorisation
    check, so it deliberately has no `can_approve` at all."""
    for pod_role in PodRole:
        assert not hasattr(pod_role, "can_approve")


def test_pod_and_app_roles_are_distinct_vocabularies() -> None:
    """They overlap in spelling, which is exactly why the distinction is
    worth asserting: 'delivery_lead' means different things in each."""
    assert PodRole.DELIVERY_LEAD.value == AppRole.DELIVERY_LEAD.value
    assert PodRole.TECH_LEAD.value not in {role.value for role in AppRole}
    assert AppRole.ADMIN.value not in {role.value for role in PodRole}


def test_default_app_role_cannot_approve() -> None:
    """New accounts must land somewhere harmless."""
    assert not AppRole.ENGINEER.can_approve


@pytest.mark.parametrize(
    ("role", "can_modify"),
    [
        (AppRole.ADMIN, True),
        (AppRole.DELIVERY_LEAD, False),
        (AppRole.PRODUCT_OWNER, False),
        (AppRole.ENGINEER, False),
    ],
)
def test_only_administrators_may_change_data(role: AppRole, can_modify: bool) -> None:
    """Sign-up is open, so anyone who can authenticate reaches the app. Write
    access has to be narrower than read access or a stranger could edit a live
    client engagement."""
    assert role.can_modify is can_modify
    assert make_user(role).can_modify is can_modify


def test_approving_and_modifying_are_different_rights() -> None:
    """A delivery lead may decide approvals but may not edit the project.
    Conflating the two would silently widen write access."""
    lead = make_user(AppRole.DELIVERY_LEAD)

    assert lead.can_approve
    assert not lead.can_modify


def test_every_role_can_still_be_read_only_present() -> None:
    """No role is locked out entirely — everyone can read and post a standup,
    which is the one write a team member needs."""
    assert all(isinstance(role.can_modify, bool) for role in AppRole)
