"""
token_budget.py — Passive per-agent token budgeting

Each slot in a user's agent chain gets a small share of the tokens the user
has *left* (not of their whole plan), so long chains stay cheap and budgets
shrink naturally as the pool drains.

Model:
  * base share per agent = BASE_PCT (3%), floored at MIN_PCT (2%)
  * total allocation is capped at MAX_TOTAL_PCT of remaining tokens
  * if the chain is long enough that base shares exceed the cap, every
    agent's percentage is scaled down proportionally (that is the
    "if the limit is passed, other agents' percentage lowers" behaviour)
  * an agent that overruns its allowance has the overrun re-charged against
    the remaining agents: their percentages drop for the rest of the run

This is passive: it computes and records allowances, and reports overruns.
It never blocks a call, and it does not change llm.py routing or
subscription_manager accounting — those stay the single source of truth for
real usage. Enforcement, if ever wanted, reads should_throttle().
"""

import logging
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_PCT      = 0.03   # 3% of remaining tokens per agent
MIN_PCT       = 0.02   # never advertise less than 2% per agent
MAX_TOTAL_PCT = 0.45   # a single run never plans to spend >45% of what's left
MIN_ALLOWANCE = 256    # tokens; below this a budget is meaningless


def plan_budget(remaining_tokens: int, slots: List[str]) -> Dict[str, dict]:
    """
    Pure function: chain → per-slot allowance.
    Returns {slot_id: {"pct": float, "allowance": int}}.
    """
    n = len(slots)
    if n == 0:
        return {}

    remaining = max(int(remaining_tokens or 0), 0)

    pct = BASE_PCT
    if pct * n > MAX_TOTAL_PCT:
        pct = MAX_TOTAL_PCT / n          # scale everyone down proportionally
    pct = max(pct, MIN_PCT) if BASE_PCT * n <= MAX_TOTAL_PCT else pct

    plan = {}
    for sid in slots:
        allowance = int(remaining * pct)
        plan[sid] = {
            "pct":       round(pct, 4),
            "allowance": allowance if allowance >= MIN_ALLOWANCE else MIN_ALLOWANCE,
        }
    return plan


class RunBudget:
    """
    Per-execution budget tracker. Thread-safe: agents may run concurrently.

    Usage:
        rb = RunBudget(remaining_tokens, slots)
        rb.allowance("architect")        -> int
        rb.record("architect", 1420)     -> redistributes any overrun
        rb.report()                      -> summary dict for the API/UI
    """

    def __init__(self, remaining_tokens: int, slots: List[str]):
        self.slots      = list(slots)
        self.remaining  = max(int(remaining_tokens or 0), 0)
        self.pool       = int(self.remaining * MAX_TOTAL_PCT)
        self.plan       = plan_budget(self.remaining, self.slots)
        self.spent      = {s: 0 for s in self.slots}
        self.overruns   = {}
        self._done      = set()
        self._lock      = threading.Lock()

    # ─────────────────────────────────────────────
    def allowance(self, slot_id: str) -> int:
        with self._lock:
            entry = self.plan.get(slot_id)
            return entry["allowance"] if entry else MIN_ALLOWANCE

    def pct(self, slot_id: str) -> float:
        entry = self.plan.get(slot_id)
        return entry["pct"] if entry else 0.0

    # ─────────────────────────────────────────────
    def record(self, slot_id: str, tokens_used: int) -> dict:
        """
        Log actual spend for a finished agent. If it exceeded its allowance,
        the excess is subtracted from the shared pool and the *unfinished*
        agents' percentages are lowered proportionally.
        """
        tokens_used = max(int(tokens_used or 0), 0)
        with self._lock:
            if slot_id not in self.spent:
                self.slots.append(slot_id)
                self.plan.setdefault(slot_id, {"pct": MIN_PCT, "allowance": MIN_ALLOWANCE})
                self.spent[slot_id] = 0

            self.spent[slot_id] += tokens_used
            self._done.add(slot_id)

            allowed = self.plan[slot_id]["allowance"]
            over    = self.spent[slot_id] - allowed
            if over > 0:
                self.overruns[slot_id] = over
                self._redistribute(over)
                logger.info(
                    f"[TokenBudget] {slot_id} over by {over} tokens — "
                    f"rebalanced {len(self._pending())} remaining agents"
                )
            return {"slot": slot_id, "used": self.spent[slot_id],
                    "allowance": allowed, "over": max(over, 0)}

    # ─────────────────────────────────────────────
    def _pending(self) -> List[str]:
        return [s for s in self.slots if s not in self._done]

    def _redistribute(self, deficit: int) -> None:
        """Caller holds the lock."""
        pending = self._pending()
        if not pending:
            return
        share = deficit // len(pending)
        for sid in pending:
            entry = self.plan[sid]
            new_allowance = max(entry["allowance"] - share, MIN_ALLOWANCE)
            entry["allowance"] = new_allowance
            entry["pct"] = round(
                (new_allowance / self.remaining) if self.remaining else 0.0, 4
            )

    # ─────────────────────────────────────────────
    def should_throttle(self, slot_id: str) -> bool:
        """True when this agent has already spent its (rebalanced) allowance."""
        with self._lock:
            return self.spent.get(slot_id, 0) >= self.plan.get(
                slot_id, {"allowance": MIN_ALLOWANCE})["allowance"]

    def total_spent(self) -> int:
        with self._lock:
            return sum(self.spent.values())

    def report(self) -> dict:
        with self._lock:
            return {
                "remaining_at_start": self.remaining,
                "run_pool":           self.pool,
                "agents":             [
                    {
                        "slot":      sid,
                        "pct":       self.plan.get(sid, {}).get("pct", 0.0),
                        "allowance": self.plan.get(sid, {}).get("allowance", 0),
                        "used":      self.spent.get(sid, 0),
                        "over":      self.overruns.get(sid, 0),
                    }
                    for sid in self.slots
                ],
                "total_used":  sum(self.spent.values()),
                "overrun_any": bool(self.overruns),
            }


# ═══════════════════════════════════════════════════
# CONVENIENCE
# ═══════════════════════════════════════════════════

_active_budget: "contextvars.ContextVar" = None


def _budget_var():
    global _active_budget
    if _active_budget is None:
        import contextvars
        _active_budget = contextvars.ContextVar("xoltra_run_budget", default=None)
    return _active_budget


def set_active_budget(budget: Optional["RunBudget"]) -> None:
    """Attach a RunBudget to the current thread/task so llm.py can feed it."""
    _budget_var().set(budget)


def get_active_budget() -> Optional["RunBudget"]:
    return _budget_var().get()


def note_usage(slot_id: str, tokens: int) -> None:
    """Called from llm._record_usage — never raises."""
    try:
        rb = get_active_budget()
        if rb is not None:
            rb.record(slot_id, tokens)
    except Exception:
        pass


def budget_for_user(user_id: str, slots: Optional[List[str]] = None) -> RunBudget:
    """
    Builds a RunBudget from live plan state. Degrades gracefully: if usage
    lookup fails we assume a generous pool rather than starving the run.
    """
    if slots is None:
        try:
            import agent_chain
            slots = agent_chain.get_chain(user_id)
        except Exception:
            slots = []

    remaining = 0
    try:
        import subscription_manager as sm
        remaining = sm.get_remaining_tokens(user_id) or 0
    except Exception as e:
        logger.warning(f"[TokenBudget] remaining-token lookup failed: {e}")
        remaining = 0

    return RunBudget(remaining, slots)
