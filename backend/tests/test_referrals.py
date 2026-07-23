"""
test_referrals.py, referral codes and attribution. No external credentials needed.
"""

import referrals


def test_code_is_stable(db, make_user):
    alice = make_user("alice@example.com")
    code_1 = referrals.get_or_create_code(alice)
    code_2 = referrals.get_or_create_code(alice)
    assert code_1 == code_2
    assert len(code_1) == 7


def test_signup_attribution(db, make_user):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    code = referrals.get_or_create_code(alice)

    assert referrals.record_signup(code, bob) is True
    assert referrals.get_referral_stats(alice)["signup_count"] == 1


def test_double_attribution_is_a_no_op(db, make_user):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    code = referrals.get_or_create_code(alice)

    referrals.record_signup(code, bob)
    second_attempt = referrals.record_signup(code, bob)

    assert second_attempt is False
    assert referrals.get_referral_stats(alice)["signup_count"] == 1


def test_self_referral_is_rejected(db, make_user):
    alice = make_user("alice@example.com")
    code = referrals.get_or_create_code(alice)
    assert referrals.record_signup(code, alice) is False


def test_unknown_code_does_not_crash(db, make_user):
    carol = make_user("carol@example.com")
    assert referrals.record_signup("BADCODE", carol) is False


def test_no_code_is_a_no_op(db, make_user):
    dave = make_user("dave@example.com")
    assert referrals.record_signup(None, dave) is False
