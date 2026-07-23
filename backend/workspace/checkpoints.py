"""
checkpoints.py — snapshot/rollback journal.

Before any mutation transaction, CheckpointStore.snapshot() copies the
about-to-change files into .xoltra_checkpoints/<id>/ with a manifest.
rollback(id) restores them exactly (including re-deleting files the
transaction created). JSON manifest — no DB dependency, works on any host
with a writable disk; on read-only serverless the store degrades to
in-memory (checkpoints survive the request, not the instance — documented
limitation, git history is the durable layer there).
"""

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from workspace.security import WorkspaceSecurity

CHECKPOINT_DIR = ".xoltra_checkpoints"
MAX_CHECKPOINTS = 30


class CheckpointStore:
    def __init__(self, security: WorkspaceSecurity):
        self.sec = security
        self.dir = self.sec.root / CHECKPOINT_DIR
        self._memory: Dict[str, Dict] = {}
        try:
            self.dir.mkdir(exist_ok=True)
            self.persistent = True
        except OSError:
            self.persistent = False

    # ── create ─────────────────────────────────────────────

    def snapshot(self, rel_paths: List[str], label: str = "") -> str:
        """Snapshot current state of rel_paths. Missing files recorded as 'absent'
        (rollback deletes them if the transaction created them)."""
        cp_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        manifest = {"id": cp_id, "label": label, "created": time.time(), "files": []}
        blobs: Dict[str, str] = {}
        for rel in rel_paths:
            p = self.sec.resolve(rel)
            if p.is_file():
                content = p.read_text(encoding="utf-8", errors="replace")
                manifest["files"].append({"path": rel, "state": "present"})
                blobs[rel] = content
            else:
                manifest["files"].append({"path": rel, "state": "absent"})
        if self.persistent:
            cp_path = self.dir / cp_id
            cp_path.mkdir(parents=True)
            (cp_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            for rel, content in blobs.items():
                blob = cp_path / "blobs" / rel
                blob.parent.mkdir(parents=True, exist_ok=True)
                blob.write_text(content, encoding="utf-8")
            self._prune()
        else:
            self._memory[cp_id] = {"manifest": manifest, "blobs": blobs}
        return cp_id

    # ── restore ────────────────────────────────────────────

    def rollback(self, cp_id: str) -> Dict:
        data = self._load(cp_id)
        if not data:
            raise KeyError(f"Checkpoint not found: {cp_id}")
        manifest, blobs = data["manifest"], data["blobs"]
        restored, deleted = [], []
        for f in manifest["files"]:
            rel, state = f["path"], f["state"]
            target = self.sec.resolve(rel, for_write=True)
            if state == "present":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(blobs[rel], encoding="utf-8")
                restored.append(rel)
            else:  # file didn't exist pre-transaction — remove it
                if target.exists():
                    target.unlink()
                    deleted.append(rel)
        return {"id": cp_id, "restored": restored, "deleted": deleted}

    # ── list / load ────────────────────────────────────────

    def list(self) -> List[Dict]:
        out = []
        if self.persistent:
            for d in sorted(self.dir.iterdir(), reverse=True):
                mf = d / "manifest.json"
                if mf.is_file():
                    try:
                        m = json.loads(mf.read_text(encoding="utf-8"))
                        out.append({"id": m["id"], "label": m["label"],
                                    "created": m["created"], "files": len(m["files"])})
                    except (json.JSONDecodeError, KeyError):
                        continue
        for m in self._memory.values():
            mf = m["manifest"]
            out.append({"id": mf["id"], "label": mf["label"],
                        "created": mf["created"], "files": len(mf["files"])})
        out.sort(key=lambda c: c["created"], reverse=True)
        return out

    def _load(self, cp_id: str) -> Optional[Dict]:
        if cp_id in self._memory:
            return self._memory[cp_id]
        cp_path = self.dir / cp_id
        mf = cp_path / "manifest.json"
        if not mf.is_file():
            return None
        manifest = json.loads(mf.read_text(encoding="utf-8"))
        blobs = {}
        for f in manifest["files"]:
            if f["state"] == "present":
                blobs[f["path"]] = (cp_path / "blobs" / f["path"]).read_text(encoding="utf-8")
        return {"manifest": manifest, "blobs": blobs}

    def _prune(self) -> None:
        dirs = sorted(d for d in self.dir.iterdir() if d.is_dir())
        while len(dirs) > MAX_CHECKPOINTS:
            shutil.rmtree(dirs.pop(0), ignore_errors=True)
