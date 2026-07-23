"""
dep_graph.py — import parsing + dependency graph + reference rewriting.

Graph: file -> set of files it imports (workspace-relative, resolved).
Used for:
    - impact analysis before a patch ("what breaks if X changes")
    - automatic import rewriting on move/rename
    - broken-reference detection after a patch

Python imports via ast; TS/JS via regex on import/require specifiers.
Only relative + workspace-alias ("@/") specifiers are resolved; package
imports are recorded as external.
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from workspace.security import WorkspaceSecurity
from workspace.indexer import RepoIndexer

_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w${},*\s]+\s+from\s+)?|export\s+(?:[\w${},*\s]+\s+from\s+)?|require\()\s*['"]([^'"]+)['"]""",
)

_JS_RESOLVE_SUFFIXES = ["", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js"]


class DependencyGraph:
    def __init__(self, security: WorkspaceSecurity, indexer: RepoIndexer):
        self.sec = security
        self.indexer = indexer
        self.imports: Dict[str, Set[str]] = {}     # file -> resolved workspace files
        self.external: Dict[str, Set[str]] = {}    # file -> package names
        self.specifiers: Dict[str, List[Tuple[str, str]]] = {}  # file -> [(raw_spec, resolved)]

    # ── build ──────────────────────────────────────────────

    def build(self) -> Dict:
        self.imports.clear(); self.external.clear(); self.specifiers.clear()
        for rel, entry in self.indexer.files.items():
            lang = entry["language"]
            if lang not in ("python", "typescript", "javascript"):
                continue
            try:
                src = (self.sec.root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if lang == "python":
                self._parse_python(rel, src)
            else:
                self._parse_js(rel, src)
        return {"files": len(self.imports),
                "edges": sum(len(v) for v in self.imports.values())}

    def _parse_python(self, rel: str, src: str) -> None:
        deps, ext, specs = set(), set(), []
        try:
            tree = ast.parse(src)
        except SyntaxError:
            return
        base = Path(rel).parent
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                # backend modules import each other flat (import auth, import llm)
                candidate = base / (name.replace(".", "/") + ".py")
                pkg_init = base / name.replace(".", "/") / "__init__.py"
                resolved = None
                for c in (candidate, pkg_init):
                    if c.as_posix() in self.indexer.files:
                        resolved = c.as_posix()
                        break
                if resolved:
                    deps.add(resolved); specs.append((name, resolved))
                else:
                    ext.add(name.split(".")[0])
        self.imports[rel], self.external[rel], self.specifiers[rel] = deps, ext, specs

    def _parse_js(self, rel: str, src: str) -> None:
        deps, ext, specs = set(), set(), []
        base = Path(rel).parent
        for m in _JS_IMPORT_RE.finditer(src):
            spec = m.group(1)
            resolved = self._resolve_js(spec, base, rel)
            if resolved:
                deps.add(resolved); specs.append((spec, resolved))
            else:
                ext.add(spec.split("/")[0])
        self.imports[rel], self.external[rel], self.specifiers[rel] = deps, ext, specs

    def _resolve_js(self, spec: str, base: Path, importer: str) -> Optional[str]:
        if spec.startswith("@/"):
            # Next.js alias -> <app-root>/src. Importer decides which src tree.
            root_prefix = importer.split("src/")[0] if "src/" in importer else ""
            target = root_prefix + "src/" + spec[2:]
        elif spec.startswith("."):
            target = (base / spec).as_posix()
            # normalize ../
            target = Path(target).as_posix()
            parts = []
            for p in target.split("/"):
                if p == "..":
                    if parts: parts.pop()
                elif p != ".":
                    parts.append(p)
            target = "/".join(parts)
        else:
            return None
        for suf in _JS_RESOLVE_SUFFIXES:
            cand = target + suf
            if cand in self.indexer.files:
                return cand
        return None

    # ── queries ────────────────────────────────────────────

    def dependents_of(self, rel_path: str) -> List[str]:
        """Files that import rel_path — the blast radius of a change."""
        return sorted(f for f, deps in self.imports.items() if rel_path in deps)

    def graph_json(self) -> Dict:
        return {
            "nodes": sorted(self.imports.keys()),
            "edges": [{"from": f, "to": t} for f, deps in sorted(self.imports.items()) for t in sorted(deps)],
        }

    # ── import rewriting on move/rename ────────────────────

    def rewrite_imports_for_move(self, old_rel: str, new_rel: str) -> Dict[str, str]:
        """
        Return {file_path: new_content} for every file whose import
        specifiers must change because old_rel moved to new_rel.
        Caller applies via Patcher (so it's diffed + checkpointed).
        """
        changes: Dict[str, str] = {}
        for importer in self.dependents_of(old_rel):
            try:
                src = (self.sec.root / importer).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            new_src = src
            for raw_spec, resolved in self.specifiers.get(importer, []):
                if resolved != old_rel:
                    continue
                new_spec = self._respecify(importer, raw_spec, new_rel)
                if new_spec and new_spec != raw_spec:
                    new_src = re.sub(
                        r"(['\"])" + re.escape(raw_spec) + r"(['\"])",
                        lambda m: m.group(1) + new_spec + m.group(2),
                        new_src,
                    )
            if new_src != src:
                changes[importer] = new_src
        return changes

    def _respecify(self, importer: str, raw_spec: str, new_rel: str) -> Optional[str]:
        new_p = Path(new_rel)
        if raw_spec.startswith("@/"):
            if "src/" in new_rel:
                inner = new_rel.split("src/", 1)[1]
                return "@/" + re.sub(r"\.(tsx?|jsx?)$", "", inner)
            return None
        if raw_spec.startswith("."):
            rel = Path(new_rel)
            imp_dir = Path(importer).parent
            try:
                import os
                spec = os.path.relpath(rel.as_posix(), imp_dir.as_posix()).replace("\\", "/")
            except ValueError:
                return None
            spec = re.sub(r"\.(tsx?|jsx?)$", "", spec)
            if not spec.startswith("."):
                spec = "./" + spec
            return spec
        # python flat module name
        if importer.endswith(".py") and new_p.suffix == ".py":
            return new_p.stem
        return None
