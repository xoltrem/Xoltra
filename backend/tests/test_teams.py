"""
test_teams.py, orgs, roles, invites. No external credentials needed.
"""

import teams


def test_personal_org_auto_created(db, make_user):
    alice = make_user("alice@example.com")
    org_id = teams.ensure_personal_org(alice)
    assert teams.get_user_role(org_id, alice) == "owner"


def test_personal_org_is_idempotent(db, make_user):
    alice = make_user("alice@example.com")
    org_id_1 = teams.ensure_personal_org(alice)
    org_id_2 = teams.ensure_personal_org(alice)
    assert org_id_1 == org_id_2


def test_invite_and_join(db, make_user):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    org_id = teams.ensure_personal_org(alice)

    code = teams.create_invite(org_id, "admin", alice)
    joined_org = teams.redeem_invite(code, bob)

    assert joined_org == org_id
    assert teams.get_user_role(org_id, bob) == "admin"


def test_invalid_invite_code_returns_none(db, make_user):
    carol = make_user("carol@example.com")
    assert teams.redeem_invite("NOTAREALCODE", carol) is None


def test_admin_can_also_invite(db, make_user):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    carol = make_user("carol@example.com")
    org_id = teams.ensure_personal_org(alice)

    bob_code = teams.create_invite(org_id, "admin", alice)
    teams.redeem_invite(bob_code, bob)

    carol_code = teams.create_invite(org_id, "member", bob)
    teams.redeem_invite(carol_code, carol)

    assert teams.get_user_role(org_id, carol) == "member"
    assert len(teams.list_members(org_id)) == 3


def test_member_list_includes_email(db, make_user):
    alice = make_user("alice@example.com")
    org_id = teams.ensure_personal_org(alice)
    members = teams.list_members(org_id)
    assert members[0]["email"] == "alice@example.com"
    assert members[0]["role"] == "owner"
