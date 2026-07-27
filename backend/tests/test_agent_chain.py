"""Chain composition + passive token budget. No credentials, no network."""

import pytest

import agent_chain as ac
import token_budget as tb


# ── validation ────────────────────────────────────
def test_default_chain_is_valid():
    assert ac.validate_chain(ac.DEFAULT_CHAIN) == list(ac.DEFAULT_CHAIN)


def test_critical_agents_cannot_be_removed():
    for critical in ac.CRITICAL_STAGES:
        chain = [s for s in ac.DEFAULT_CHAIN if s != critical]
        with pytest.raises(ac.ChainError):
            ac.validate_chain(chain)


def test_max_20_agents():
    parts = list(ac.BUILTIN_STAGES.keys())
    roles = ["role:" + r["id"] for r in ac.get_all_roles()]
    big   = (parts + roles)[:21]
    assert len(big) == 21
    with pytest.raises(ac.ChainError):
        ac.validate_chain(big)
    assert len(ac.validate_chain(big[:20])) == 20


def test_role_slot_replaces_validator():
    chain = ["architect", "operator", "role:business_analyst", "compiler"]
    assert ac.validate_chain(chain) == chain
    assert "validator" not in chain


def test_unknown_and_duplicate_rejected():
    with pytest.raises(ac.ChainError):
        ac.validate_chain(["architect", "operator", "nope"])
    with pytest.raises(ac.ChainError):
        ac.validate_chain(["architect", "operator", "role:not_a_role"])
    with pytest.raises(ac.ChainError):
        ac.validate_chain(["architect", "operator", "critic", "critic"])
    with pytest.raises(ac.ChainError):
        ac.validate_chain([])


def test_dict_slots_normalized():
    chain = [{"id": "architect"}, {"id": "operator"}]
    assert ac.validate_chain(chain) == ["architect", "operator"]


def test_describe_and_parts():
    d = ac.describe_slot("role:teacher")
    assert d["kind"] == "role" and d["role_id"] == "teacher" and not d["critical"]
    assert ac.describe_slot("architect")["critical"] is True
    parts = ac.available_parts()
    assert parts["max_agents"] == 20
    assert len(parts["roles"]) >= 7


# ── budget ────────────────────────────────────────
def test_small_chain_gets_base_pct():
    plan = tb.plan_budget(1_000_000, ["architect", "operator", "critic"])
    assert all(p["pct"] == pytest.approx(0.03) for p in plan.values())
    assert plan["architect"]["allowance"] == 30_000


def test_long_chain_scales_everyone_down():
    slots = [f"a{i}" for i in range(20)]
    plan  = tb.plan_budget(1_000_000, slots)
    pct   = plan["a0"]["pct"]
    assert pct < tb.BASE_PCT
    total = sum(p["pct"] for p in plan.values())
    assert total == pytest.approx(tb.MAX_TOTAL_PCT, abs=1e-3)


def test_overrun_lowers_remaining_agents():
    rb = tb.RunBudget(1_000_000, ["architect", "critic", "operator"])
    before = rb.allowance("critic")
    rb.record("architect", 60_000)          # 2x its 30k allowance
    assert rb.allowance("critic") < before
    assert rb.report()["overrun_any"] is True
    assert rb.report()["agents"][0]["over"] == 30_000


def test_no_overrun_leaves_others_untouched():
    rb = tb.RunBudget(1_000_000, ["architect", "critic"])
    before = rb.allowance("critic")
    rb.record("architect", 100)
    assert rb.allowance("critic") == before
    assert rb.report()["overrun_any"] is False


def test_allowance_never_below_floor():
    rb = tb.RunBudget(100, ["architect", "operator"])
    assert rb.allowance("architect") == tb.MIN_ALLOWANCE
    rb.record("architect", 999_999)
    assert rb.allowance("operator") >= tb.MIN_ALLOWANCE


def test_zero_remaining_is_safe():
    assert tb.plan_budget(0, []) == {}
    rb = tb.RunBudget(0, ["architect"])
    assert rb.allowance("architect") == tb.MIN_ALLOWANCE
    assert rb.report()["total_used"] == 0


def test_note_usage_without_active_budget_is_noop():
    tb.set_active_budget(None)
    tb.note_usage("architect", 500)   # must not raise


def test_active_budget_receives_usage():
    rb = tb.RunBudget(1_000_000, ["architect"])
    tb.set_active_budget(rb)
    try:
        tb.note_usage("architect", 1234)
        assert rb.total_spent() == 1234
        assert rb.should_throttle("architect") is False
    finally:
        tb.set_active_budget(None)
