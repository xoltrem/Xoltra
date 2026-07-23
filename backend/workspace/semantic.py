"""
semantic.py — embedding-based semantic search over the repo index.

Uses Cohere embeddings through the same client llm.py already configures
(no new dependency). Chunks = file symbols + head of file. Embeddings
cached by file mtime. If no embedding client is available (missing key,
offline), search falls back to the indexer's lexical search transparently.
"""

import logging
import math
from typing import Dict, List, Optional

from workspace.security import WorkspaceSecurity
from workspace.indexer import RepoIndexer

logger = logging.getLogger(__name__)

EMBED_MODEL = "embed-english-v3.0"
CHUNK_CHARS = 1200
MAX_CHUNKS_PER_FILE = 4


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class SemanticSearch:
    def __init__(self, security: WorkspaceSecurity, indexer: RepoIndexer):
        self.sec = security
        self.indexer = indexer
        # rel_path -> {"mtime": float, "chunks": [{"text","line","vec"}]}
        self._cache: Dict[str, Dict] = {}
        self._client = None
        self._client_tried = False

    # ── embedding client (deferred, optional) ──────────────

    def _get_client(self):
        if not self._client_tried:
            self._client_tried = True
            try:
                from llm import _init_cohere  # same client llm.py uses
                self._client = _init_cohere()
            except Exception as e:
                logger.warning(f"[semantic] no embedding client, lexical fallback: {e}")
                self._client = None
        return self._client

    def _embed(self, texts: List[str], input_type: str) -> Optional[List[List[float]]]:
        client = self._get_client()
        if client is None or not texts:
            return None
        try:
            resp = client.embed(texts=texts, model=EMBED_MODEL, input_type=input_type)
            return list(resp.embeddings)
        except Exception as e:
            logger.warning(f"[semantic] embed failed: {e}")
            return None

    # ── chunking ───────────────────────────────────────────

    def _chunks_for(self, rel: str) -> List[Dict]:
        entry = self.indexer.files.get(rel)
        if not entry or entry["language"] == "text":
            return []
        try:
            src = (self.sec.root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        chunks = []
        lines = src.splitlines()
        # one chunk per top-level symbol (code around its line), else file head
        if entry["symbols"]:
            for sym in entry["symbols"][:MAX_CHUNKS_PER_FILE]:
                start = max(0, sym["line"] - 1)
                text = "\n".join(lines[start:start + 40])[:CHUNK_CHARS]
                chunks.append({"text": f"{rel} :: {sym['name']}\n{text}", "line": sym["line"]})
        else:
            chunks.append({"text": f"{rel}\n{src[:CHUNK_CHARS]}", "line": 1})
        return chunks

    def _ensure_embedded(self) -> bool:
        """Embed new/changed files. Returns False if embeddings unavailable."""
        pending: List[Dict] = []
        for rel, entry in self.indexer.files.items():
            cached = self._cache.get(rel)
            if cached and cached["mtime"] == entry["mtime"]:
                continue
            for c in self._chunks_for(rel):
                pending.append({"rel": rel, "mtime": entry["mtime"], **c})
        # drop deleted files
        for gone in set(self._cache) - set(self.indexer.files):
            del self._cache[gone]
        if not pending:
            return bool(self._cache) or self._get_client() is not None
        vecs = self._embed([p["text"] for p in pending], "search_document")
        if vecs is None:
            return False
        by_file: Dict[str, Dict] = {}
        for p, v in zip(pending, vecs):
            slot = by_file.setdefault(p["rel"], {"mtime": p["mtime"], "chunks": []})
            slot["chunks"].append({"text": p["text"], "line": p["line"], "vec": v})
        self._cache.update(by_file)
        return True

    # ── search ─────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> Dict:
        """Semantic search; falls back to lexical when embeddings unavailable.
        Returns {"mode": "semantic"|"lexical", "results": [...]}."""
        if not self.indexer.files:
            self.indexer.build()
        if not self._ensure_embedded():
            return {"mode": "lexical", "results": self.indexer.search(query, limit)}
        qvecs = self._embed([query], "search_query")
        if not qvecs:
            return {"mode": "lexical", "results": self.indexer.search(query, limit)}
        qvec = qvecs[0]
        scored = []
        for rel, entry in self._cache.items():
            for c in entry["chunks"]:
                scored.append({
                    "path": rel, "line": c["line"],
                    "match": c["text"].split("\n", 2)[0],
                    "kind": "semantic",
                    "score": round(_cosine(qvec, c["vec"]), 4),
                })
        scored.sort(key=lambda r: -r["score"])
        # best chunk per file
        seen, results = set(), []
        for r in scored:
            if r["path"] in seen:
                continue
            seen.add(r["path"])
            results.append(r)
            if len(results) >= limit:
                break
        return {"mode": "semantic", "results": results}
