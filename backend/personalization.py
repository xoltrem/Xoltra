"""
personalization.py — Xoltra AI Personalization Engine

Backend counterpart to xoltra-ai.js. The JS module previously called
Anthropic directly from the browser with no key and stored state in
`window.storage`, which is not a real browser API — nothing ever
persisted and every request would fail. This moves everything server
side: per-user (multi-tenant) storage in the shared SQLite DB, Cohere
via the existing llm.py (so usage tracking + tier gating apply the
same as every other call), JWT auth via auth.require_auth.

6 learned traits (unchanged shape from xoltra-ai.js):
    vocabulary, reasoning, communication, tone, interests, expertise

Extraction runs every EXTRACT_EVERY user messages, same as before.

Public API:
    init_personalization_tables()
    get_profile(user_id) -> {traits, settings}
    chat(user_id, message) -> {reply, extracting}
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, request, jsonify

import knowledge_db as kdb
import subscription_manager as sm
from llm import call_llm, safe_json_parse
from auth import require_auth, get_current_user_id

logger = logging.getLogger(__name__)

personalization_bp = Blueprint("personalization", __name__, url_prefix="/api/personalization")

EXTRACT_EVERY = 4
MAX_HISTORY   = 20

DEFAULT_SETTINGS = {"mode": "adaptive", "customPrompt": ""}

_tables_created = False


# ═══════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════

def init_personalization_tables():
    global _tables_created
    if _tables_created:
        return

    conn   = kdb._get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personalization_profiles (
            user_id     TEXT PRIMARY KEY,
            traits      TEXT,
            settings    TEXT NOT NULL,
            msg_count   INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personalization_history (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pers_hist_user ON personalization_history(user_id, created_at)"
    )
    conn.commit()
    _tables_created = True
    logger.info("[Personalization] Tables initialized")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════
# SYSTEM PROMPT BUILDER — mirrors xoltra-ai.js buildSystemPrompt
# ═══════════════════════════════════════════════════

def _build_preamble(traits: Optional[dict], settings: dict) -> str:
    mode = settings.get("mode", "adaptive")

    if mode == "off":
        return "You are a helpful AI assistant."

    if mode == "custom" and settings.get("customPrompt", "").strip():
        return settings["customPrompt"].strip()

    if not traits:
        return (
            "You are a helpful AI. Pay close attention to how this user communicates "
            "and naturally adapt your style, vocabulary and tone to match theirs. "
            "Never acknowledge you are doing this."
        )

    lines = [
        "You are a personalised AI assistant. Adapt every response precisely to this user's profile.",
        f"Vocabulary: {traits.get('vocabulary', 'intermediate')} — match their word complexity exactly.",
        f"Style: {traits.get('communication', 'conversational')}. Tone: {traits.get('tone', 'casual')}.",
        f"Reasoning: {traits.get('reasoning', 'practical')} — mirror their thinking structure.",
    ]
    if traits.get("interests"):
        lines.append(f"Interests: {', '.join(traits['interests'])} — weave in naturally when relevant.")
    if traits.get("expertise"):
        lines.append(f"Expertise: {', '.join(traits['expertise'])} — skip over-explaining in these areas.")
    lines.append("Never acknowledge you are adapting. Just be that version of yourself.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════
# STORAGE HELPERS
# ═══════════════════════════════════════════════════

def _get_profile_row(user_id: str) -> dict:
    init_personalization_tables()
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM personalization_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        now = _now()
        cursor.execute("""
            INSERT INTO personalization_profiles (user_id, traits, settings, msg_count, updated_at)
            VALUES (?, NULL, ?, 0, ?)
        """, (user_id, json.dumps(DEFAULT_SETTINGS), now))
        conn.commit()
        return {"user_id": user_id, "traits": None, "settings": DEFAULT_SETTINGS, "msg_count": 0}

    return {
        "user_id":   row["user_id"],
        "traits":    json.loads(row["traits"]) if row["traits"] else None,
        "settings":  json.loads(row["settings"]),
        "msg_count": row["msg_count"],
    }


def _save_traits(user_id: str, traits: dict):
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE personalization_profiles SET traits = ?, updated_at = ? WHERE user_id = ?
    """, (json.dumps(traits), _now(), user_id))
    conn.commit()


def _save_settings(user_id: str, settings: dict):
    _get_profile_row(user_id)  # ensures row exists
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE personalization_profiles SET settings = ?, updated_at = ? WHERE user_id = ?
    """, (json.dumps(settings), _now(), user_id))
    conn.commit()


def _reset_msg_count(user_id: str):
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE personalization_profiles SET msg_count = 0 WHERE user_id = ?", (user_id,))
    conn.commit()


def _increment_msg_count(user_id: str) -> int:
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE personalization_profiles SET msg_count = msg_count + 1 WHERE user_id = ?
    """, (user_id,))
    conn.commit()
    cursor.execute("SELECT msg_count FROM personalization_profiles WHERE user_id = ?", (user_id,))
    return cursor.fetchone()["msg_count"]


def _get_history(user_id: str) -> list:
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content FROM personalization_history
        WHERE user_id = ? ORDER BY created_at ASC
    """, (user_id,))
    return [{"role": r["role"], "content": r["content"]} for r in cursor.fetchall()]


def _append_history(user_id: str, role: str, content: str):
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO personalization_history (id, user_id, role, content, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), user_id, role, content, _now()))

    # cap at MAX_HISTORY per user
    cursor.execute("""
        DELETE FROM personalization_history WHERE id IN (
            SELECT id FROM personalization_history WHERE user_id = ?
            ORDER BY created_at DESC LIMIT -1 OFFSET ?
        )
    """, (user_id, MAX_HISTORY))
    conn.commit()


def _clear_history(user_id: str):
    conn   = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM personalization_history WHERE user_id = ?", (user_id,))
    conn.commit()
    _reset_msg_count(user_id)


# ═══════════════════════════════════════════════════
# TRAIT EXTRACTION
# ═══════════════════════════════════════════════════

def _extract_traits(user_id: str, history: list, existing: Optional[dict]) -> Optional[dict]:
    user_msgs = [m["content"] for m in history if m["role"] == "user"][-12:]
    if not user_msgs:
        return existing

    prompt = f"""
Analyze these messages and extract the user's key communication traits.

Messages:
{chr(10).join(user_msgs)}
{f"Existing profile to refine (merge, do not discard): {json.dumps(existing)}" if existing else ""}

Return ONLY JSON:
{{"vocabulary":"technical|intermediate|casual","reasoning":"analytical|intuitive|practical|creative","communication":"concise|detailed|conversational","tone":"formal|casual|playful","interests":[],"expertise":[]}}

interests and expertise: max 3 items each, only include if clearly evidenced. Empty [] if unclear.
"""
    try:
        raw  = call_llm(user_id, "clarifier", prompt)
        data = safe_json_parse(raw)
        data["updatedAt"] = _now()
        return data
    except Exception as e:
        logger.warning(f"[Personalization] Trait extraction failed for {user_id[:8]}: {e}")
        return existing


# ═══════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════

def get_profile(user_id: str) -> dict:
    row = _get_profile_row(user_id)
    return {"traits": row["traits"], "settings": row["settings"]}


def chat(user_id: str, message: str) -> dict:
    """Send a message through the personalized assistant. Returns {reply, extracting}."""
    if not message or not message.strip():
        raise ValueError("message is required")

    can_run, reason = sm.can_execute(user_id)
    if not can_run:
        raise PermissionError(reason)

    profile  = _get_profile_row(user_id)
    preamble = _build_preamble(profile["traits"], profile["settings"])

    _append_history(user_id, "user", message.strip())
    history = _get_history(user_id)

    # Cohere has no separate "system" turn like Anthropic — preamble covers it,
    # so we pass the running history as plain conversational context in-prompt.
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-10:])
    reply = call_llm(user_id, "qa", convo, role_preamble=preamble)

    _append_history(user_id, "assistant", reply)

    extracting = False
    if profile["settings"].get("mode", "adaptive") == "adaptive":
        count = _increment_msg_count(user_id)
        if count >= EXTRACT_EVERY:
            _reset_msg_count(user_id)
            extracting = True
            extracted = _extract_traits(user_id, history, profile["traits"])
            if extracted:
                _save_traits(user_id, extracted)

    return {"reply": reply, "extracting": extracting}


# ═══════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════

def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status

def _ok(data: dict):
    return jsonify({"success": True, **data})


@personalization_bp.route("/chat", methods=["POST"])
@require_auth
def route_chat():
    user_id = get_current_user_id()
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()

    if not message:
        return _err("message is required")

    try:
        result = chat(user_id, message)
        return _ok(result)
    except PermissionError as e:
        return _err(str(e), 402)
    except Exception as e:
        logger.error(f"[/personalization/chat] {e}")
        return _err(f"Chat failed: {e}", 500)


@personalization_bp.route("/profile", methods=["GET"])
@require_auth
def route_get_profile():
    user_id = get_current_user_id()
    return _ok(get_profile(user_id))


@personalization_bp.route("/settings", methods=["PUT"])
@require_auth
def route_update_settings():
    user_id = get_current_user_id()
    body    = request.get_json(silent=True) or {}

    mode = body.get("mode")
    if mode and mode not in ("adaptive", "custom", "off"):
        return _err("mode must be 'adaptive', 'custom', or 'off'")

    row      = _get_profile_row(user_id)
    settings = {**row["settings"], **{k: v for k, v in body.items() if k in ("mode", "customPrompt")}}
    _save_settings(user_id, settings)
    return _ok({"settings": settings})


@personalization_bp.route("/traits", methods=["DELETE"])
@require_auth
def route_reset_traits():
    user_id = get_current_user_id()
    _save_traits(user_id, None)
    return _ok({"reset": True})


@personalization_bp.route("/history", methods=["GET"])
@require_auth
def route_get_history():
    user_id = get_current_user_id()
    return _ok({"history": _get_history(user_id)})


@personalization_bp.route("/history", methods=["DELETE"])
@require_auth
def route_clear_history():
    user_id = get_current_user_id()
    _clear_history(user_id)
    return _ok({"cleared": True})
