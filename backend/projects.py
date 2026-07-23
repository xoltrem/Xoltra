"""
projects.py — Xoltra Projects Feature

Mirrors workflow_store.py's SQLite pattern + knowledge_db.py's per-tenant
ChromaDB collection pattern, scoped per-project instead of per-user.

Tables (shared SQLite db via kdb._get_conn()):
  projects            — id, user_id, name, goals, created_at, updated_at
  project_sources      — id, project_id, type(github|upload), ref, status, content_hash
  project_cache        — project_id PK, structure_summary, key_docs_summary,
                          conversation_digests (json list), updated_at

Vector storage: one Chroma collection per project ("proj_<id>"), same
embedding calls as knowledge_db.py (llm.generate_embedding / query).
Namespace checked against knowledge_db.py's "knowledge_<user_id>" prefix —
no collision.

Collision checks performed against the rest of the repo before writing this:
  - SQLite table names (projects, project_sources, project_cache) don't
    exist anywhere else (checked against nodes/edges/insights, workflows,
    workflow_runs, personalization_*, subscriptions, usage_*, users,
    login_events, onedrive_tokens, workflow_templates, moderation_*).
  - Blueprint name "projects" and url_prefix /api/projects are unused.
  - This module never touches memory_router.py's L1/L2 pipeline-pause
    state — that's a separate concern (paused execution state, not
    project knowledge) and is left untouched.
  - Only requires stdlib + already-installed deps (chromadb, requests via
    llm.py) — no new line needed in any requirements*.txt.

Deploy placement: per DEPLOYMENT.md, only frontend/ + the two Node
services (secure-api, auth-service) run on Vercel. This Flask module rides
on app.py, which (like knowledge_db.py's SQLite file and unity_bridge's
websocket thread) requires a persistent host, not a Vercel serverless
function — consistent with the existing architecture, not a new
requirement. Because ANY host's /tmp may still be ephemeral/size-capped
(true on Vercel, often true on containers too), ingestion never relies on
the cloned/uploaded files surviving past the request that indexed them:
every clone/upload lands in a tempfile.mkdtemp() dir that is always
removed in a finally block once chunks are embedded into Chroma + the
SQLite cache. Nothing is read back from disk on later requests.

Endpoints (Blueprint, mounted at /api/projects):
  POST   /api/projects                        create
  GET    /api/projects                        list
  GET    /api/projects/<id>                    get + cache summaries
  DELETE /api/projects/<id>                    delete (cascades sources+vectors)
  POST   /api/projects/<id>/sources/github      clone + ingest
  POST   /api/projects/<id>/sources/upload      upload + ingest (multipart)
  GET    /api/projects/<id>/bootstrap           session-start context payload
  POST   /api/projects/<id>/digest              append a conversation digest
"""

import os
import re
import json
import uuid
import shutil
import hashlib
import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Optional, List, Dict

from flask import Blueprint, request, jsonify

import knowledge_db as kdb
from auth import require_auth, get_current_user_id
import subscription_manager as sm

logger = logging.getLogger(__name__)

projects_bp = Blueprint("projects", __name__, url_prefix="/api/projects")

MAX_FILE_BYTES   = 2_000_000
MAX_FILES_PER_INGEST = 500
SKIP_DIRS   = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
TEXT_EXT    = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".json", ".yml", ".yaml",
    ".txt", ".toml", ".cfg", ".ini", ".java", ".go", ".rb", ".rs", ".c",
    ".cpp", ".h", ".hpp", ".cs", ".php", ".sql", ".css", ".html", ".sh",
}
# Base dir for scratch clones/uploads ONLY — every ingestion cleans up
# after itself (see finally blocks below), so this never needs to be a
# persistent volume. Defaults to the platform tempdir (respects Vercel's
# writable-/tmp-only rule and any container's TMPDIR).
SCRATCH_ROOT = os.environ.get("PROJECTS_SCRATCH_DIR") or tempfile.gettempdir()
GIT_BIN = shutil.which("git")

_tables_created = False


# ═══════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════

def init_project_tables():
    global _tables_created
    if _tables_created:
        return
    conn = kdb._get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            name        TEXT NOT NULL,
            goals       TEXT DEFAULT '',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_sources (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            type          TEXT NOT NULL,
            ref           TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'pending',
            content_hash  TEXT,
            file_count    INTEGER DEFAULT 0,
            created_at    TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_cache (
            project_id             TEXT PRIMARY KEY,
            structure_summary      TEXT DEFAULT '',
            key_docs_summary       TEXT DEFAULT '',
            conversation_digests   TEXT NOT NULL DEFAULT '[]',
            updated_at             TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_proj_user ON projects(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_src_project ON project_sources(project_id)")
    conn.commit()
    _tables_created = True
    logger.info("[Projects] Tables initialized")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


def _ok(data: dict):
    return jsonify({"success": True, **data})


def _own_project(user_id: str, project_id: str) -> Optional[dict]:
    conn = kdb._get_conn()
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)
    ).fetchone()
    return dict(row) if row else None


# ═══════════════════════════════════════════════════
# PER-PROJECT VECTOR STORE (mirrors kdb._get_user_collection)
# ═══════════════════════════════════════════════════

def _get_project_collection(project_id: str):
    if kdb._chroma_client is None:
        return None
    safe = "".join(c for c in project_id if c.isalnum() or c in "-_")
    return kdb._chroma_client.get_or_create_collection(
        name=f"proj_{safe}", metadata={"hnsw:space": "cosine"}
    )


def _embed_and_store(project_id: str, source_id: str, chunks: List[Dict]):
    """chunks: [{id, text, meta}]"""
    collection = _get_project_collection(project_id)
    if collection is None or not chunks:
        return
    from llm import generate_embedding
    ids, embeds, docs, metas = [], [], [], []
    for c in chunks[:2000]:
        vec = generate_embedding(c["text"][:4000])
        if not vec:
            continue
        ids.append(c["id"])
        embeds.append(vec)
        docs.append(c["text"][:4000])
        metas.append({**c["meta"], "source_id": source_id})
    if ids:
        collection.add(ids=ids, embeddings=embeds, documents=docs, metadatas=metas)


def _query_project(project_id: str, query: str, top_k: int = 6) -> List[Dict]:
    collection = _get_project_collection(project_id)
    if collection is None:
        return []
    from llm import generate_query_embedding
    vec = generate_query_embedding(query)
    if not vec:
        return []
    try:
        res = collection.query(query_embeddings=[vec], n_results=min(top_k, max(1, collection.count())))
    except Exception as e:
        logger.warning(f"[Projects] query failed: {e}")
        return []
    if not res or not res.get("ids"):
        return []
    out = []
    for i, doc_id in enumerate(res["ids"][0]):
        out.append({
            "id": doc_id,
            "text": res["documents"][0][i],
            "meta": res["metadatas"][0][i],
            "distance": res["distances"][0][i],
        })
    return out


# ═══════════════════════════════════════════════════
# INGESTION HELPERS
# ═══════════════════════════════════════════════════

def _walk_text_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXT:
                continue
            full = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue
            rel = os.path.relpath(full, root)
            yield rel, text


def _chunk_file(rel_path: str, text: str, chunk_chars: int = 3000) -> List[Dict]:
    chunks = []
    for i in range(0, max(len(text), 1), chunk_chars):
        piece = text[i:i + chunk_chars]
        if not piece.strip():
            continue
        chunks.append({
            "id": str(uuid.uuid4()),
            "text": f"# {rel_path}\n\n{piece}",
            "meta": {"path": rel_path, "offset": i},
        })
    return chunks


def _structure_pass(files: List[str]) -> str:
    """Cheap, deterministic structure summary — no LLM call needed for the
    skeleton; languages/entrypoints/deps inferred from filenames."""
    langs = {}
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext:
            langs[ext] = langs.get(ext, 0) + 1
    top_langs = sorted(langs.items(), key=lambda x: -x[1])[:8]
    manifest_files = [f for f in files if os.path.basename(f) in (
        "package.json", "requirements.txt", "pyproject.toml", "Cargo.toml", "go.mod"
    )]
    lines = [
        f"{len(files)} files indexed.",
        "Languages: " + ", ".join(f"{ext}({n})" for ext, n in top_langs) if top_langs else "Languages: none detected",
        "Manifests: " + ", ".join(manifest_files) if manifest_files else "Manifests: none found",
    ]
    return "\n".join(lines)


def _docs_summary(root: str, files: List[str]) -> str:
    doc_names = [f for f in files if os.path.basename(f).lower() in
                 ("readme.md", "architecture.md", "contributing.md")]
    parts = []
    for f in doc_names[:5]:
        try:
            with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as fh:
                parts.append(f"## {f}\n{fh.read()[:1500]}")
        except Exception:
            continue
    return "\n\n".join(parts)


def _update_cache_structure(project_id: str, root: str, files: List[str]):
    init_project_tables()
    conn = kdb._get_conn()
    cur = conn.cursor()
    struct = _structure_pass(files)
    docs   = _docs_summary(root, files)
    cur.execute("""
        INSERT INTO project_cache (project_id, structure_summary, key_docs_summary, conversation_digests, updated_at)
        VALUES (?, ?, ?, '[]', ?)
        ON CONFLICT(project_id) DO UPDATE SET
            structure_summary = excluded.structure_summary,
            key_docs_summary  = excluded.key_docs_summary,
            updated_at = excluded.updated_at
    """, (project_id, struct, docs, _now()))
    conn.commit()


# ═══════════════════════════════════════════════════
# ROUTES — CRUD
# ═══════════════════════════════════════════════════

@projects_bp.route("", methods=["POST"])
@require_auth
def create_project():
    init_project_tables()
    user_id = get_current_user_id()
    if not sm.check_permission(user_id, "workflow_builder"):
        return _err("Projects require an active plan", 403)

    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return _err("name is required")

    pid, now = str(uuid.uuid4()), _now()
    conn = kdb._get_conn()
    conn.execute(
        "INSERT INTO projects (id, user_id, name, goals, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (pid, user_id, name, (body.get("goals") or "").strip(), now, now)
    )
    conn.commit()
    return _ok({"project": {"id": pid, "name": name, "goals": body.get("goals", ""), "created_at": now}}), 201


@projects_bp.route("", methods=["GET"])
@require_auth
def list_projects():
    init_project_tables()
    user_id = get_current_user_id()
    rows = kdb._get_conn().execute(
        "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
    ).fetchall()
    return _ok({"projects": [dict(r) for r in rows]})


@projects_bp.route("/<project_id>", methods=["GET"])
@require_auth
def get_project(project_id: str):
    init_project_tables()
    user_id = get_current_user_id()
    proj = _own_project(user_id, project_id)
    if not proj:
        return _err("Project not found", 404)

    conn = kdb._get_conn()
    sources = [dict(r) for r in conn.execute(
        "SELECT id, type, ref, status, file_count, created_at FROM project_sources WHERE project_id = ?",
        (project_id,)
    ).fetchall()]
    cache_row = conn.execute(
        "SELECT structure_summary, key_docs_summary, updated_at FROM project_cache WHERE project_id = ?",
        (project_id,)
    ).fetchone()
    cache = dict(cache_row) if cache_row else None
    return _ok({"project": proj, "sources": sources, "cache": cache})


@projects_bp.route("/<project_id>", methods=["DELETE"])
@require_auth
def delete_project(project_id: str):
    init_project_tables()
    user_id = get_current_user_id()
    if not _own_project(user_id, project_id):
        return _err("Project not found", 404)

    conn = kdb._get_conn()
    conn.execute("DELETE FROM project_sources WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM project_cache WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()

    if kdb._chroma_client is not None:
        try:
            safe = "".join(c for c in project_id if c.isalnum() or c in "-_")
            kdb._chroma_client.delete_collection(f"proj_{safe}")
        except Exception:
            pass

    # No disk cleanup needed — ingestion never leaves files behind past
    # the request that indexed them (see module docstring).
    return _ok({"deleted": project_id})


# ═══════════════════════════════════════════════════
# ROUTES — INGESTION
# ═══════════════════════════════════════════════════

_GITHUB_URL_RE = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+(\.git)?/?$")


@projects_bp.route("/<project_id>/sources/github", methods=["POST"])
@require_auth
def add_github_source(project_id: str):
    init_project_tables()
    user_id = get_current_user_id()
    if not _own_project(user_id, project_id):
        return _err("Project not found", 404)

    body = request.get_json(silent=True) or {}
    url = (body.get("repo_url") or "").strip()
    if not _GITHUB_URL_RE.match(url):
        return _err("repo_url must be a valid https://github.com/<owner>/<repo> URL")

    if GIT_BIN is None:
        return _err("git is not installed on this host — cannot clone repositories", 501)

    source_id = str(uuid.uuid4())
    conn = kdb._get_conn()
    conn.execute(
        "INSERT INTO project_sources (id, project_id, type, ref, status, created_at) VALUES (?, ?, 'github', ?, 'pending', ?)",
        (source_id, project_id, url, _now())
    )
    conn.commit()

    # Scratch-only: created fresh, always removed below. Nothing here is
    # ever read again after this request — safe on ephemeral /tmp.
    scratch = tempfile.mkdtemp(prefix=f"xoltra-proj-{source_id}-", dir=SCRATCH_ROOT)
    dest = os.path.join(scratch, "repo")
    try:
        try:
            subprocess.run(
                [GIT_BIN, "clone", "--depth", "1", url, dest],
                check=True, timeout=120, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            conn.execute("UPDATE project_sources SET status = 'error' WHERE id = ?", (source_id,))
            conn.commit()
            return _err(f"Clone failed: {e.stderr[:300]}", 502)
        except subprocess.TimeoutExpired:
            conn.execute("UPDATE project_sources SET status = 'error' WHERE id = ?", (source_id,))
            conn.commit()
            return _err("Clone timed out", 504)

        files, all_chunks = [], []
        for rel, text in _walk_text_files(dest):
            files.append(rel)
            all_chunks.extend(_chunk_file(rel, text))
            if len(files) >= MAX_FILES_PER_INGEST:
                break

        _embed_and_store(project_id, source_id, all_chunks)
        _update_cache_structure(project_id, dest, files)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    conn.execute(
        "UPDATE project_sources SET status = 'indexed', file_count = ? WHERE id = ?",
        (len(files), source_id)
    )
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), project_id))
    conn.commit()

    return _ok({"source_id": source_id, "status": "indexed", "file_count": len(files)}), 201


@projects_bp.route("/<project_id>/sources/upload", methods=["POST"])
@require_auth
def add_upload_source(project_id: str):
    init_project_tables()
    user_id = get_current_user_id()
    if not _own_project(user_id, project_id):
        return _err("Project not found", 404)

    files_in = request.files.getlist("files")
    if not files_in:
        return _err("No files provided")

    source_id = str(uuid.uuid4())
    conn = kdb._get_conn()
    conn.execute(
        "INSERT INTO project_sources (id, project_id, type, ref, status, created_at) VALUES (?, ?, 'upload', ?, 'pending', ?)",
        (source_id, project_id, f"{len(files_in)} file(s)", _now())
    )
    conn.commit()

    # Scratch-only, same as the GitHub path — removed in finally, never
    # read back after this request.
    scratch = tempfile.mkdtemp(prefix=f"xoltra-proj-{source_id}-", dir=SCRATCH_ROOT)
    rel_names, all_chunks = [], []
    try:
        for f in files_in[:MAX_FILES_PER_INGEST]:
            filename = os.path.basename(f.filename or "")
            ext = os.path.splitext(filename)[1].lower()
            if not filename or ext not in TEXT_EXT:
                continue
            content = f.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES:
                continue
            text = content.decode("utf-8", errors="ignore")
            with open(os.path.join(scratch, filename), "w", encoding="utf-8") as out:
                out.write(text)
            rel_names.append(filename)
            all_chunks.extend(_chunk_file(filename, text))

        _embed_and_store(project_id, source_id, all_chunks)
        _update_cache_structure(project_id, scratch, rel_names)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    conn.execute(
        "UPDATE project_sources SET status = 'indexed', file_count = ? WHERE id = ?",
        (len(rel_names), source_id)
    )
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), project_id))
    conn.commit()

    return _ok({"source_id": source_id, "status": "indexed", "file_count": len(rel_names)}), 201


# ═══════════════════════════════════════════════════
# ROUTES — SESSION BOOTSTRAP + DIGESTS
# ═══════════════════════════════════════════════════

@projects_bp.route("/<project_id>/bootstrap", methods=["GET"])
@require_auth
def bootstrap_session(project_id: str):
    """Called when a new chat starts inside a project. Returns everything
    that should be injected into the system context: fixed structure/docs
    summaries + most-relevant conversation digests + (once a first message
    exists) top-k retrieved chunks via ?query=."""
    init_project_tables()
    user_id = get_current_user_id()
    proj = _own_project(user_id, project_id)
    if not proj:
        return _err("Project not found", 404)

    conn = kdb._get_conn()
    cache_row = conn.execute(
        "SELECT structure_summary, key_docs_summary, conversation_digests FROM project_cache WHERE project_id = ?",
        (project_id,)
    ).fetchone()

    structure = cache_row["structure_summary"] if cache_row else ""
    docs      = cache_row["key_docs_summary"] if cache_row else ""
    digests   = json.loads(cache_row["conversation_digests"]) if cache_row else []

    query = (request.args.get("query") or "").strip()
    relevant_digests = digests[-5:]
    retrieved_chunks = []
    if query:
        retrieved_chunks = _query_project(project_id, query, top_k=6)
        if digests:
            # cheap relevance: keyword overlap fallback, no extra LLM call
            q_words = set(query.lower().split())
            scored = sorted(
                digests,
                key=lambda d: len(q_words & set(d.get("summary", "").lower().split())),
                reverse=True,
            )
            relevant_digests = scored[:5]

    return _ok({
        "project": {"id": proj["id"], "name": proj["name"], "goals": proj["goals"]},
        "structure_summary": structure,
        "key_docs_summary": docs,
        "conversation_digests": relevant_digests,
        "retrieved_chunks": retrieved_chunks,
    })


@projects_bp.route("/<project_id>/digest", methods=["POST"])
@require_auth
def append_digest(project_id: str):
    """Append a conversation summary to the project's rolling cache.
    Called when a chat ends / every N turns. Body: {summary, conversation_id}."""
    init_project_tables()
    user_id = get_current_user_id()
    if not _own_project(user_id, project_id):
        return _err("Project not found", 404)

    body = request.get_json(silent=True) or {}
    summary = (body.get("summary") or "").strip()
    if not summary:
        return _err("summary is required")

    conn = kdb._get_conn()
    row = conn.execute(
        "SELECT conversation_digests FROM project_cache WHERE project_id = ?", (project_id,)
    ).fetchone()
    digests = json.loads(row["conversation_digests"]) if row else []
    digests.append({
        "conversation_id": body.get("conversation_id"),
        "summary": summary[:1000],
        "created_at": _now(),
    })
    digests = digests[-50:]  # rotate — bounded growth

    conn.execute("""
        INSERT INTO project_cache (project_id, structure_summary, key_docs_summary, conversation_digests, updated_at)
        VALUES (?, '', '', ?, ?)
        ON CONFLICT(project_id) DO UPDATE SET
            conversation_digests = excluded.conversation_digests,
            updated_at = excluded.updated_at
    """, (project_id, json.dumps(digests), _now()))
    conn.commit()
    return _ok({"digest_count": len(digests)})


def register_project_routes(app):
    app.register_blueprint(projects_bp)
    logger.info("[Projects] Routes registered under /api/projects")
