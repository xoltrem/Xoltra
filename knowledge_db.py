"""
knowledge_db.py — XoltaOS Knowledge Engine Storage
SQLite (graph + metadata) + ChromaDB (vectors)

Key fixes from v1:
- init_storage() must be called explicitly — never runs on import
- Thread-local SQLite connections — safe under Flask concurrency
- Correct cosine similarity math (ChromaDB distance is in [0,1])
- Indexes on edges table for performance
- get_node() accepts update_access param
- get_node_edges() accepts edge_type filter
- Relevance boost capped at 1.0
- Multi-tenant data isolation via user_id
"""

import sqlite3
import json
import uuid
import threading
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DB_PATH     = "xoltaos_knowledge.db"
VECTOR_PATH = "./chroma_db"

# Thread-local storage for SQLite connections
_local          = threading.local()
_chroma_client     = None
_initialized       = False


# ═══════════════════════════════════════════════════
# INITIALIZATION — called explicitly, never on import
# ═══════════════════════════════════════════════════

def init_storage():
    """
    Initialize SQLite schema and ChromaDB.
    Safe to call multiple times — idempotent.
    Must be called before any other function.
    """
    global _chroma_client, _initialized

    if _initialized:
        return

    # Create tables using a fresh connection on this thread
    conn = _get_conn()
    _create_tables(conn)

    # ChromaDB
    try:
        import chromadb
        _chroma_client = chromadb.PersistentClient(path=VECTOR_PATH)
        logger.info("[Knowledge] ChromaDB initialized")
    except Exception as e:
        logger.warning(f"[Knowledge] ChromaDB unavailable: {e} — vector search disabled")
        _chroma_client = None

    _initialized = True
    logger.info("[Knowledge] Storage initialized")


def _get_conn() -> sqlite3.Connection:
    """
    Get thread-local SQLite connection.
    Each thread gets its own connection — safe for concurrent use.
    """
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn


def _add_column_if_not_exists(cursor, table, column, definition):
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise

def _create_tables(conn: sqlite3.Connection):
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS nodes (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL DEFAULT 'default',
        type            TEXT NOT NULL,
        content         TEXT NOT NULL,
        metadata        TEXT NOT NULL DEFAULT '{}',
        execution_state TEXT,
        created_at      TEXT NOT NULL,
        last_accessed   TEXT NOT NULL,
        access_count    INTEGER DEFAULT 0,
        status          TEXT DEFAULT 'active'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS edges (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL DEFAULT 'default',
        from_node   TEXT NOT NULL,
        to_node     TEXT NOT NULL,
        edge_type   TEXT NOT NULL,
        strength    REAL DEFAULT 1.0,
        reason      TEXT,
        created_at  TEXT NOT NULL,
        FOREIGN KEY (from_node) REFERENCES nodes(id),
        FOREIGN KEY (to_node)   REFERENCES nodes(id),
        UNIQUE(from_node, to_node, edge_type)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS insights (
        id             TEXT PRIMARY KEY,
        user_id        TEXT NOT NULL DEFAULT 'default',
        pattern        TEXT NOT NULL,
        confidence     REAL NOT NULL,
        actionable     INTEGER DEFAULT 0,
        created_at     TEXT NOT NULL,
        surfaced_count INTEGER DEFAULT 0
    )
    """)
    
    # Migrations for existing DBs
    _add_column_if_not_exists(cursor, "nodes", "user_id", "TEXT NOT NULL DEFAULT 'default'")
    _add_column_if_not_exists(cursor, "edges", "user_id", "TEXT NOT NULL DEFAULT 'default'")
    _add_column_if_not_exists(cursor, "insights", "user_id", "TEXT NOT NULL DEFAULT 'default'")

    # Indexes for performance — critical once edges table grows
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_from   ON edges(from_node)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_to     ON edges(to_node)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_type   ON edges(edge_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type   ON nodes(type, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status)")
    
    # New multi-tenant indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_user   ON nodes(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_user   ON edges(user_id)")

    conn.commit()


def _require_init():
    if not _initialized:
        raise RuntimeError(
            "Knowledge Engine not initialized. Call kdb.init_storage() first."
        )

def _get_user_collection(user_id: str):
    """Get or create a ChromaDB collection specifically for this user."""
    if _chroma_client is None:
        return None
    # Sanitize user_id for collection name (must be alphanumeric/underscore/hyphen, 3-63 chars)
    safe_user_id = "".join(c for c in user_id if c.isalnum() or c in "-_")
    collection_name = f"knowledge_{safe_user_id}"
    return _chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )


# ═══════════════════════════════════════════════════
# NODE OPERATIONS
# ═══════════════════════════════════════════════════

def create_node(
    user_id: str,
    node_type: str,
    content: dict,
    metadata: dict = None,
    execution_state: dict = None
) -> str:
    """
    Create a knowledge node in SQLite + ChromaDB.
    Returns node_id (UUID string).
    """
    _require_init()

    node_id = str(uuid.uuid4())
    now     = datetime.utcnow().isoformat()
    meta    = metadata or {}

    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO nodes
            (id, user_id, type, content, metadata, execution_state, created_at, last_accessed, access_count, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        node_id, user_id, node_type,
        json.dumps(content), json.dumps(meta),
        json.dumps(execution_state) if execution_state else None,
        now, now, 0, "active"
    ))
    conn.commit()

    # Store embedding in ChromaDB if available
    collection = _get_user_collection(user_id)
    if collection is not None:
        try:
            from llm import generate_embedding
            text      = _prepare_embedding_text(node_type, content)
            embedding = generate_embedding(user_id, text)
            if embedding:
                collection.add(
                    ids=[node_id],
                    embeddings=[embedding],
                    metadatas=[{"type": node_type, "created_at": now}],
                    documents=[text]
                )
        except Exception as e:
            logger.warning(f"[Knowledge] Embedding failed for {node_id}: {e}")

    logger.debug(f"[Knowledge] Created {node_type} node: {node_id[:8]} for user: {user_id}")
    return node_id


def _prepare_embedding_text(node_type: str, content: dict) -> str:
    if node_type == "goal":
        return f"{content.get('original_input', '')} {content.get('clarified_goal', '')}"
    elif node_type == "workflow":
        phases = " ".join(p.get("phase_name", "") for p in content.get("phases", []))
        return f"{content.get('goal_summary', '')} {phases}"
    elif node_type == "document":
        return content.get("extracted_goal", "")
    elif node_type == "insight":
        return content.get("pattern", "")
    else:
        return json.dumps(content)[:500]


def get_node(user_id: str, node_id: str, update_access: bool = True) -> Optional[Dict]:
    """
    Retrieve node by ID.
    update_access=False for internal reads that shouldn't count as user access.
    """
    _require_init()

    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nodes WHERE id = ? AND user_id = ?", (node_id, user_id))
    row = cursor.fetchone()

    if not row:
        return None

    if update_access:
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            UPDATE nodes
            SET last_accessed = ?, access_count = access_count + 1
            WHERE id = ? AND user_id = ?
        """, (now, node_id, user_id))
        conn.commit()

    return {
        "id":              row["id"],
        "user_id":         row["user_id"],
        "type":            row["type"],
        "content":         json.loads(row["content"]),
        "metadata":        json.loads(row["metadata"]),
        "execution_state": json.loads(row["execution_state"]) if row["execution_state"] else None,
        "created_at":      row["created_at"],
        "last_accessed":   row["last_accessed"],
        "access_count":    row["access_count"],
        "status":          row["status"],
    }


def update_node(user_id: str, node_id: str, updates: dict) -> bool:
    _require_init()

    conn   = _get_conn()
    cursor = conn.cursor()

    set_clauses, values = [], []
    for field in ["content", "metadata", "execution_state", "status"]:
        if field in updates:
            set_clauses.append(f"{field} = ?")
            val = updates[field]
            values.append(json.dumps(val) if isinstance(val, dict) else val)

    if not set_clauses:
        return False

    values.extend([node_id, user_id])
    cursor.execute(
        f"UPDATE nodes SET {', '.join(set_clauses)} WHERE id = ? AND user_id = ?",
        values
    )
    conn.commit()
    return cursor.rowcount > 0


def get_nodes_by_type(user_id: str, node_type: str, status: str = "active") -> List[Dict]:
    """Public function — no direct _local access from outside this module."""
    _require_init()

    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM nodes WHERE type = ? AND status = ? AND user_id = ?",
        (node_type, status, user_id)
    )
    rows = cursor.fetchall()
    return [
        {
            "id":           row["id"],
            "type":         row["type"],
            "content":      json.loads(row["content"]),
            "created_at":   row["created_at"],
            "access_count": row["access_count"],
            "status":       row["status"],
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════
# EDGE OPERATIONS
# ═══════════════════════════════════════════════════

def create_edge(
    user_id:   str,
    from_node: str,
    to_node:   str,
    edge_type: str,
    strength:  float = 1.0,
    reason:    str   = None
) -> Optional[str]:
    """
    Create edge between nodes. Returns edge_id or None if duplicate.
    UNIQUE constraint silently ignores duplicates.
    """
    _require_init()

    edge_id = str(uuid.uuid4())
    now     = datetime.utcnow().isoformat()

    conn   = _get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO edges
                (id, user_id, from_node, to_node, edge_type, strength, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (edge_id, user_id, from_node, to_node, edge_type, strength, reason, now))
        conn.commit()
        return edge_id if cursor.rowcount > 0 else None
    except Exception as e:
        logger.warning(f"[Knowledge] create_edge failed: {e}")
        return None


def get_node_edges(
    user_id:   str,
    node_id:   str,
    direction: str = "both",
    edge_type: str = None
) -> List[Dict]:
    """
    Get edges for a node with optional direction and type filtering.
    direction: "outgoing" | "incoming" | "both"
    edge_type: optional filter e.g. "derives_from"
    """
    _require_init()

    conn   = _get_conn()
    cursor = conn.cursor()

    if direction == "outgoing":
        base = "SELECT * FROM edges WHERE from_node = ? AND user_id = ?"
        params = [node_id, user_id]
    elif direction == "incoming":
        base = "SELECT * FROM edges WHERE to_node = ? AND user_id = ?"
        params = [node_id, user_id]
    else:
        base = "SELECT * FROM edges WHERE (from_node = ? OR to_node = ?) AND user_id = ?"
        params = [node_id, node_id, user_id]

    if edge_type:
        base += " AND edge_type = ?"
        params.append(edge_type)

    cursor.execute(base, params)
    return [dict(row) for row in cursor.fetchall()]


# ═══════════════════════════════════════════════════
# SEMANTIC SEARCH
# ═══════════════════════════════════════════════════

def semantic_search(
    user_id:        str,
    query:          str,
    top_k:          int       = 5,
    node_types:     List[str] = None,
    min_similarity: float     = 0.7
) -> List[Dict]:
    """
    Find similar nodes by vector similarity.

    ChromaDB cosine distance is in [0, 1] where:
      0.0 = identical
      1.0 = completely opposite
    So similarity = 1 - distance (both in [0,1]).
    """
    collection = _get_user_collection(user_id)
    if collection is None:
        logger.debug("[Knowledge] Vector search unavailable — ChromaDB not initialized")
        return []

    try:
        from llm import generate_query_embedding
        query_embedding = generate_query_embedding(user_id, query)
    except Exception as e:
        logger.warning(f"[Knowledge] Query embedding failed: {e}")
        return []

    if not query_embedding:
        return []

    where = {"type": {"$in": node_types}} if node_types else None

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(1, collection.count())),
            where=where
        )
    except Exception as e:
        logger.warning(f"[Knowledge] ChromaDB query failed: {e}")
        return []

    if not results or not results.get("ids"):
        return []

    enriched = []
    for i, node_id in enumerate(results["ids"][0]):
        # ChromaDB cosine distance ∈ [0, 1] → similarity = 1 - distance
        distance   = results["distances"][0][i]
        similarity = 1.0 - distance

        if similarity < min_similarity:
            continue

        node = get_node(user_id, node_id, update_access=False)
        if node:
            node["relevance"] = round(similarity, 4)
            enriched.append(node)

    enriched.sort(key=lambda x: x["relevance"], reverse=True)
    return enriched


# ═══════════════════════════════════════════════════
# DUPLICATE DETECTION
# ═══════════════════════════════════════════════════

def check_duplicate(user_id: str, goal_text: str, threshold: float = 0.85) -> Optional[Dict]:
    """Returns match info if a very similar goal exists, else None."""
    similar = semantic_search(
        user_id=user_id,
        query=goal_text,
        top_k=3,
        node_types=["goal"],
        min_similarity=threshold
    )
    if similar:
        return {
            "is_duplicate": True,
            "match":        similar[0],
            "similarity":   similar[0]["relevance"]
        }
    return None


# ═══════════════════════════════════════════════════
# CONTEXT RETRIEVAL FOR PIPELINE
# ═══════════════════════════════════════════════════

def get_relevant_context(user_id: str, user_input: str, top_k: int = 3) -> List[Dict]:
    """Main retrieval function used by the pipeline."""
    results = semantic_search(
        user_id=user_id,
        query=user_input,
        top_k=top_k,
        min_similarity=0.75
    )

    # Cap relevance at 1.0 after any boosting
    for r in results:
        r["relevance"] = min(r["relevance"], 1.0)

    results.sort(key=lambda x: x["relevance"], reverse=True)
    return results[:top_k]


# ═══════════════════════════════════════════════════
# ARCHIVING
# ═══════════════════════════════════════════════════

def archive_old_nodes(user_id: str, days_threshold: int = 30) -> int:
    _require_init()

    cutoff = (datetime.utcnow() - timedelta(days=days_threshold)).isoformat()
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE nodes
        SET status = 'archived'
        WHERE last_accessed < ? AND access_count < 2 AND status = 'active' AND user_id = ?
    """, (cutoff, user_id))
    conn.commit()
    archived = cursor.rowcount
    logger.info(f"[Knowledge] Archived {archived} old nodes for {user_id}")
    return archived


# ═══════════════════════════════════════════════════
# STATISTICS
# ═══════════════════════════════════════════════════

def get_stats(user_id: str) -> Dict:
    _require_init()

    conn   = _get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT type, COUNT(*) as count FROM nodes WHERE status = 'active' AND user_id = ? GROUP BY type", (user_id,))
    type_counts = {row["type"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("SELECT COUNT(*) as total FROM nodes WHERE status = 'active' AND user_id = ?", (user_id,))
    total_nodes = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM edges WHERE user_id = ?", (user_id,))
    total_edges = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM nodes WHERE status = 'archived' AND user_id = ?", (user_id,))
    archived = cursor.fetchone()["total"]

    vector_count = 0
    collection = _get_user_collection(user_id)
    if collection:
        try:
            vector_count = collection.count()
        except Exception:
            pass

    return {
        "total_nodes":   total_nodes,
        "total_edges":   total_edges,
        "archived_nodes": archived,
        "nodes_by_type": type_counts,
        "vector_count":  vector_count,
    }

