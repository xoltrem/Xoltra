"""
agent_chain.py — Custom Agentic Chain Composer

Lets a user rebuild the agentic pipeline out of parts: built-in stages
(architect, operator, critic, validator, ...) and role-backed stages
sourced from roles.py (e.g. replace "validator" with "business_analyst").

Rules enforced here:
  * MAX_AGENTS (20) slots per chain
  * CRITICAL_STAGES ("architect", "operator") can never be removed
  * no duplicate slot ids
  * role slots must reference a real role in roles.py

Storage: per-user row in the shared SQLite DB (knowledge_db connection),
so this does not touch llm.TIERS or pipeline defaults — a user with no
saved chain keeps the existing tier behaviour untouched.
"""

import json
import logging
from typing import Optional

import knowledge_db as kdb
from roles import get_all_roles, get_role, is_valid_role

logger = logging.getLogger(__name__)

MAX_AGENTS = 20

CRITICAL_STAGES = ("architect", "operator")

# Canonical built-in stage order. A chain is always executed in list order,
# but these are the pieces available and how they are labelled in the UI.
BUILTIN_STAGES = {
    "router":              "Router",
    "clarifier":           "Clarifier",
    "extractor":           "PDF Extractor",
    "architect":           "Architect",
    "critic":              "Critic",
    "operator":            "Operator",
    "auditor":             "Auditor",
    "validator":           "Validator",
    "compiler":            "Compiler",
    "qa":                  "QA",
    "coding":              "Coding",
    "coach":               "Coach",
    "knowledge_retriever": "Knowledge Retriever",
    "knowledge_linker":    "Knowledge Linker",
    "insight_generator":   "Insight Generator",
    "deduplicator":        "Deduplicator",
}

DEFAULT_CHAIN = [
    "router", "clarifier", "architect", "critic",
    "operator", "validator", "compiler",
]

# Role slots have no engine of their own — they borrow a built-in agent's
# model/temperature config and override the preamble with the role's.
ROLE_ENGINE = "architect"

ROLE_PREFIX = "role:"

_tables_created = False


class ChainError(ValueError):
    """Raised on any invalid chain definition. Surfaced as a 400."""


# ═══════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════

def init_agent_chain_tables():
    global _tables_created
    if _tables_created:
        return
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_chains (
            user_id     TEXT PRIMARY KEY,
            slots_json  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    _tables_created = True
    logger.info("[AgentChain] tables ready")


# ═══════════════════════════════════════════════════
# SLOT HELPERS
# ═══════════════════════════════════════════════════

def is_role_slot(slot_id: str) -> bool:
    return isinstance(slot_id, str) and slot_id.startswith(ROLE_PREFIX)


def role_id_of(slot_id: str) -> Optional[str]:
    return slot_id[len(ROLE_PREFIX):] if is_role_slot(slot_id) else None


def slot_label(slot_id: str) -> str:
    if is_role_slot(slot_id):
        role = get_role(role_id_of(slot_id))
        return role["name"] if role else slot_id
    return BUILTIN_STAGES.get(slot_id, slot_id)


def describe_slot(slot_id: str) -> dict:
    """UI-facing shape for one chain position."""
    return {
        "id":       slot_id,
        "label":    slot_label(slot_id),
        "kind":     "role" if is_role_slot(slot_id) else "builtin",
        "role_id":  role_id_of(slot_id),
        "critical": slot_id in CRITICAL_STAGES,
        "engine":   ROLE_ENGINE if is_role_slot(slot_id) else slot_id,
    }


def available_parts() -> dict:
    """Everything a user can drop into a chain."""
    return {
        "builtin": [
            {"id": sid, "label": label, "kind": "builtin",
             "critical": sid in CRITICAL_STAGES}
            for sid, label in BUILTIN_STAGES.items()
        ],
        "roles": [
            {"id": ROLE_PREFIX + r["id"], "label": r["name"], "kind": "role",
             "role_id": r["id"], "description": r["description"],
             "icon": r["icon"], "critical": False}
            for r in get_all_roles()
        ],
        "max_agents":      MAX_AGENTS,
        "critical_stages": list(CRITICAL_STAGES),
        "default_chain":   list(DEFAULT_CHAIN),
    }


# ═══════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════

def normalize_slots(slots) -> list:
    """Accepts ["architect", {"id": "role:teacher"}, ...] → ["architect", ...]."""
    if not isinstance(slots, (list, tuple)):
        raise ChainError("chain must be a list of agent slots")
    out = []
    for s in slots:
        if isinstance(s, dict):
            s = s.get("id") or s.get("stage")
        if not isinstance(s, str) or not s.strip():
            raise ChainError("each slot must be a non-empty string id")
        out.append(s.strip())
    return out


def validate_chain(slots) -> list:
    slots = normalize_slots(slots)

    if not slots:
        raise ChainError("chain cannot be empty")
    if len(slots) > MAX_AGENTS:
        raise ChainError(f"chain exceeds the {MAX_AGENTS}-agent limit (got {len(slots)})")

    seen = set()
    for sid in slots:
        if sid in seen:
            raise ChainError(f"duplicate agent in chain: {sid}")
        seen.add(sid)
        if is_role_slot(sid):
            rid = role_id_of(sid)
            if not is_valid_role(rid):
                raise ChainError(f"unknown role: {rid}")
        elif sid not in BUILTIN_STAGES:
            raise ChainError(f"unknown agent stage: {sid}")

    for critical in CRITICAL_STAGES:
        if critical not in seen:
            raise ChainError(
                f"'{critical}' is a critical agent and cannot be removed from the chain"
            )

    return slots


# ═══════════════════════════════════════════════════
# PERSISTENCE
# ═══════════════════════════════════════════════════

def save_chain(user_id: str, slots) -> list:
    slots = validate_chain(slots)
    init_agent_chain_tables()
    from datetime import datetime, timezone
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO agent_chains (user_id, slots_json, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               slots_json = excluded.slots_json,
               updated_at = excluded.updated_at""",
        (user_id, json.dumps(slots), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    logger.info(f"[AgentChain] saved {len(slots)} slots for {user_id}")
    return slots


def get_chain(user_id: str) -> list:
    """Returns the user's chain, or DEFAULT_CHAIN when nothing is saved."""
    init_agent_chain_tables()
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT slots_json FROM agent_chains WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return list(DEFAULT_CHAIN)
    try:
        slots = json.loads(row["slots_json"] if isinstance(row, dict) or hasattr(row, "keys") else row[0])
        return validate_chain(slots)
    except Exception as e:
        logger.warning(f"[AgentChain] corrupt chain for {user_id} ({e}) — using default")
        return list(DEFAULT_CHAIN)


def reset_chain(user_id: str) -> list:
    init_agent_chain_tables()
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agent_chains WHERE user_id = ?", (user_id,))
    conn.commit()
    return list(DEFAULT_CHAIN)


def get_chain_detail(user_id: str) -> dict:
    slots = get_chain(user_id)
    return {
        "slots":      [describe_slot(s) for s in slots],
        "count":      len(slots),
        "max_agents": MAX_AGENTS,
        "customized": slots != list(DEFAULT_CHAIN),
    }
