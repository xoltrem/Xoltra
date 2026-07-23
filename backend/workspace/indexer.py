"""
indexer.py — repository scan + file index.

Builds an in-memory index of every indexable file:
    path, language, size, mtime, symbols (top-level defs/classes/exports)

Symbols come from lightweight parsing:
    - Python: ast module (stdlib, no deps)
    - TS/JS:  regex over export/function/class/const declarations
              (good enough for search + rename detection; no babel needed,
               which keeps this serverless-friendly)

Index rebuilds are incremental via mtime comparison.
"""

import ast
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from workspace.security import WorkspaceSecurity, IGNORED_DIRS

LANG_BY_EXT = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".json": "json", ".css": "css", ".scss": "css",
    ".md": "markdown", ".html": "html", ".yml": "yaml", ".yaml": "yaml",
    ".sql": "sql", ".sh": "shell",
}

_TS_SYMBOL_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_TS_PLAIN_RE = re.compile(
    r"^(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)", re.MULTILINE
)


def _python_symbols(source: str) -> List[Dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append({"name": node.name, "kind": "function", "line": node.lineno})
        elif isinstance(node, ast.ClassDef):
            out.append({"name": node.name, "kind": "class", "line": node.lineno})
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    out.append({"name": t.id, "kind": "constant", "line": node.lineno})
    return out


def _ts_symbols(source: str) -> List[Dict]:
    out, seen = [], set()
    for m in _TS_SYMBOL_RE.finditer(source):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append({"name": name, "kind": "export", "line": source[: m.start()].count("\n") + 1})
    for m in _TS_PLAIN_RE.finditer(source):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append({"name": name, "kind": "declaration", "line": source[: m.start()].count("\n") + 1})
    return out


class RepoIndexer:
    def __init__(self, security: WorkspaceSecurity):
        self.sec = security
        self.files: Dict[str, Dict] = {}   # rel_path -> entry
        self.built_at: Optional[float] = None

    def build(self, force: bool = False) -> Dict:
        """Full or incremental scan. Returns summary stats."""
        seen = set()
        scanned = updated = 0
        stack = [self.sec.root]
        while stack:
            d = stack.pop()
            try:
                entries = list(d.iterdir())
            except OSError:
                continue
            for e in entries:
                if e.is_dir():
                    if e.name not in IGNORED_DIRS:
                        stack.append(e)
                    continue
                if not self.sec.is_indexable(e):
                    continue
                rel = self.sec.relpath(e)
                seen.add(rel)
                scanned += 1
                try:
                    mtime = e.stat().st_mtime
                except OSError:
                    continue
                cached = self.files.get(rel)
                if cached and not force and cached["mtime"] == mtime:
                    continue
                self.files[rel] = self._index_file(e, rel, mtime)
                updated += 1
        # drop deleted files
        for gone in set(self.files) - seen:
            del self.files[gone]
        self.built_at = time.time()
        return {"files": len(self.files), "scanned": scanned, "updated": updated}

    def _index_file(self, p: Path, rel: str, mtime: float) -> Dict:
        lang = LANG_BY_EXT.get(p.suffix.lower(), "text")
        entry = {"path": rel, "language": lang, "mtime": mtime, "size": p.stat().st_size, "symbols": []}
        if lang in ("python", "typescript", "javascript"):
            try:
                src = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return entry
            entry["symbols"] = _python_symbols(src) if lang == "python" else _ts_symbols(src)
        return entry

    def invalidate(self, rel_path: str) -> None:
        self.files.pop(rel_path, None)

    # ── search ─────────────────────────────────────────────

    def search(self, query: str, limit: int = 40) -> List[Dict]:
        """Symbol + path + content search, ranked: symbol > path > content.
        Multi-word queries match if any token matches (best-token score)."""
        tokens = [t for t in query.lower().split() if t] or [query.lower()]

        def hit(text: str) -> bool:
            t = text.lower()
            return any(tok in t for tok in tokens)

        results = []
        for rel, entry in self.files.items():
            for sym in entry["symbols"]:
                if hit(sym["name"]):
                    results.append({"path": rel, "match": sym["name"], "kind": sym["kind"],
                                    "line": sym["line"], "score": 3})
            if hit(rel):
                results.append({"path": rel, "match": rel, "kind": "path", "line": 1, "score": 2})
        if len(results) < limit:
            for rel, entry in self.files.items():
                if entry["language"] == "text" or entry["size"] > 256_000:
                    continue
                try:
                    src = (self.sec.root / rel).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for i, line in enumerate(src.splitlines(), 1):
                    if hit(line):
                        results.append({"path": rel, "match": line.strip()[:160],
                                        "kind": "content", "line": i, "score": 1})
                        break
        results.sort(key=lambda r: -r["score"])
        return results[:limit]

    def project_summary(self, max_files: int = 400) -> str:
        """Compact architecture description fed to the LLM planner."""
        lines = []
        for rel in sorted(self.files)[:max_files]:
            e = self.files[rel]
            syms = ", ".join(s["name"] for s in e["symbols"][:8])
            lines.append(f"{rel} [{e['language']}]" + (f" — {syms}" if syms else ""))
        return "\n".join(lines)
