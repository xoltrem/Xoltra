"""
memory_router.py — XoltaOS Session State Persistence

Two-tier architecture:
  L1 (hot):  in-process dict  — microsecond reads, lost on process restart
  L2 (warm): Upstash Redis    — survives restarts, written only on WAITING_FOR_USER

Flow:
  save_temporary_session()
    → always writes L1
    → if status == 'WAITING_FOR_USER', also serialises + pushes to L2 (24h TTL)

  resume_session()
    → L1 hit  → return immediately            (same process, still running)
    → L1 miss → pull L2, warm L1, return     (server restarted / user returned later)
    → L2 miss → return None                  (genuinely new session)

Integrates with agents.py — drop in alongside it, import where needed.

ENV required:
  UPSTASH_REDIS_REST_URL
  UPSTASH_REDIS_REST_TOKEN
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from upstash_redis import Redis

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "xoltra:session:"
_SESSION_TTL  = 86_400          # 24 hours — how long Redis holds a paused session
_WAITING      = "WAITING_FOR_USER"


class MemoryRouter:
    """
    Singleton-safe: _local_cache is class-level so all instances share one dict.
    Thread-safe: all dict mutations go through _lock.

    State data contract (what state_data should contain):
    {
        "status":                  "RUNNING | WAITING_FOR_USER | COMPLETE | ERROR",
        "stage":                   "routing | clarifying | building | reviewing | ...",
        "goal":                    str,
        "mode":                    "default | coach",
        "complexity":              "simple | medium | complex",
        "pipeline_depth":          "minimal | standard | full",
        "role_preamble":           str | None,
        "clarification_questions": list | None,   # set when WAITING_FOR_USER
        "clarification_answers":   dict | None,   # set when user responds
        "blueprint":               dict | None,
        "output":                  str  | None,
        "context_nodes":           list | None,
    }
    thread_id, created_at, updated_at are injected automatically.
    """

    _local_cache: dict = {}
    _lock = threading.Lock()

    def __init__(self):
        self._redis = Redis(
            url=os.environ["UPSTASH_REDIS_REST_URL"],
            token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
        )

    # ── public API ───────────────────────────────────────────────────────────

    def save_temporary_session(self, thread_id: str, state_data: dict) -> None:
        """
        Always writes to L1.
        If status == WAITING_FOR_USER, also pushes serialised payload to L2.
        Never raises — a Redis failure is logged but will not crash the agent.
        """
        payload = self._stamp(thread_id, state_data)

        with self._lock:
            self._local_cache[thread_id] = payload

        if state_data.get("status") == _WAITING:
            self._push_to_redis(thread_id, payload)
            logger.info(
                "[MemoryRouter] thread=%s paused → pushed to Redis (WAITING_FOR_USER)",
                thread_id,
            )
        else:
            logger.debug(
                "[MemoryRouter] thread=%s saved to L1 (status=%s)",
                thread_id, state_data.get("status"),
            )

    def resume_session(self, thread_id: str) -> Optional[dict]:
        """
        Called whenever the user activates the platform or sends a message.
        Transparently reconstructs state with no user involvement:
          - If process is still running → returns from L1 instantly
          - If server restarted / user returned later → fetches from Redis,
            warms L1, returns — the caller just checks state['status'] and continues
          - If no session found → returns None (start fresh)
        """
        # L1 — same process, still running
        with self._lock:
            local = self._local_cache.get(thread_id)
        if local is not None:
            logger.debug("[MemoryRouter] thread=%s resumed from L1", thread_id)
            return local

        # L2 — server restarted or user returned after a break
        remote = self._pull_from_redis(thread_id)
        if remote is not None:
            with self._lock:
                self._local_cache[thread_id] = remote      # warm L1 for next call
            logger.info(
                "[MemoryRouter] thread=%s resumed from Redis "
                "(was in status=%s, stage=%s)",
                thread_id,
                remote.get("status"),
                remote.get("stage"),
            )
            return remote

        logger.debug("[MemoryRouter] thread=%s — no session found, starting fresh", thread_id)
        return None

    def complete_session(self, thread_id: str) -> None:
        """
        Call when pipeline reaches COMPLETE or ERROR.
        Evicts from both tiers so memory doesn't accumulate.
        """
        with self._lock:
            self._local_cache.pop(thread_id, None)
        try:
            self._redis.delete(_REDIS_PREFIX + thread_id)
            logger.debug("[MemoryRouter] thread=%s evicted from both tiers", thread_id)
        except Exception as exc:
            logger.warning("[MemoryRouter] Redis evict failed for %s: %s", thread_id, exc)

    def session_exists(self, thread_id: str) -> bool:
        """Quick existence check before resuming."""
        with self._lock:
            if thread_id in self._local_cache:
                return True
        try:
            return bool(self._redis.exists(_REDIS_PREFIX + thread_id))
        except Exception:
            return False

    def get_status(self, thread_id: str) -> Optional[str]:
        """Returns just the status string without full resume overhead."""
        session = self.resume_session(thread_id)
        return session.get("status") if session else None

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _stamp(thread_id: str, state_data: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            **state_data,
            "thread_id":  thread_id,
            "updated_at": now,
            "created_at": state_data.get("created_at", now),
        }

    def _push_to_redis(self, thread_id: str, payload: dict) -> None:
        try:
            self._redis.set(
                _REDIS_PREFIX + thread_id,
                json.dumps(payload, default=str),
                ex=_SESSION_TTL,
            )
        except Exception as exc:
            # Non-fatal: L1 still has the data, session continues
            logger.error(
                "[MemoryRouter] Redis write failed for thread=%s: %s — "
                "session lives in L1 only until process restart",
                thread_id, exc,
            )

    def _pull_from_redis(self, thread_id: str) -> Optional[dict]:
        try:
            raw = self._redis.get(_REDIS_PREFIX + thread_id)
            if not raw:
                return None
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            logger.error(
                "[MemoryRouter] Redis read failed for thread=%s: %s",
                thread_id, exc,
            )
            return None


# ── singleton ────────────────────────────────────────────────────────────────
# Import this anywhere: from memory_router import memory_router
memory_router = MemoryRouter()


# ── usage example (how llm.py / pipeline calls this) ────────────────────────
"""
from memory_router import memory_router

# ① After RouterAgent decides clarification is needed:
memory_router.save_temporary_session(thread_id, {
    "status":                  "WAITING_FOR_USER",
    "stage":                   "clarifying",
    "goal":                    user_input,
    "mode":                    route["mode"],
    "complexity":              route["complexity"],
    "pipeline_depth":          route["pipeline_depth"],
    "role_preamble":           role_preamble,
    "clarification_questions": clarifier_result["questions"],
})
# → L1 written, L2 written (status is WAITING_FOR_USER)
# → return questions to frontend, wait for user

# ② User returns (same session or after restart) and sends answers:
state = memory_router.resume_session(thread_id)
# → if state is None: session expired, ask user to restart
# → if state["status"] == "WAITING_FOR_USER": perfect, continue below

state["clarification_answers"] = user_answers
state["status"] = "RUNNING"
state["stage"]  = "building"
memory_router.save_temporary_session(thread_id, state)
# → L1 updated, L2 NOT written (status is RUNNING, not WAITING_FOR_USER)

# ③ Pipeline completes:
memory_router.complete_session(thread_id)
# → evicted from L1 + L2
"""
