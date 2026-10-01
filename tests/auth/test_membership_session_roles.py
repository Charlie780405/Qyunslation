# SPDX-License-Identifier: MPL-2.0
from qyunslation.auth.bff import merge_membership_session_roles


def test_local_admin_survives_oidc_login_without_admin_claim():
    roles = merge_membership_session_roles(["workbench_v2"], "admin")
    assert "admin" in roles
    assert "workbench_v2" in roles


def test_member_membership_does_not_add_a_review_role():
    assert merge_membership_session_roles(["workbench_v2"], "member") == ["workbench_v2"]
