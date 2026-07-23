"""
tasks.py — concurrent task handling + live-change tracking.

TaskManager:
    - runs agent jobs on worker threads, bounded pool
    - one global MUTATION_LOCK serializes patch applies / fs mutations so
      two tasks can plan+generate in parallel but never write concurrently
    - task registry with status/steps/result for polling from the UI

ChangeFeed:
    - monotonically increasing revision, bumped on every mutation
    - GET /api/workspace/changes?since=N returns events after N, so the
      frontend polls cheaply and refreshes only when something changed
      (poll-based: works on serverless where websockets don't)
"""

import threading
import time
import uuid
from collections import deque
from typing import Callable, Dict, List, Optional

MAX_WORKERS = 3
MAX_EVENTS = 200

# Global write lock — Patcher.apply/FsOps mutations run under this.
MUTATION_LOCK = threading.Lock()


class ChangeFeed:
    def __init__(self):
        self._lock = threading.Lock()
        self._rev = 0
        self._events: deque = deque(maxlen=MAX_EVENTS)

    def emit(self, kind: str, detail: Dict) -> int:
        with self._lock:
            self._rev += 1
            self._events.append({"rev": self._rev, "ts": time.time(),
                                 "kind": kind, **detail})
            return self._rev

    def since(self, rev: int) -> Dict:
        with self._lock:
            events = [e for e in self._events if e["rev"] > rev]
            return {"rev": self._rev, "events": events}


class TaskManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: Dict[str, Dict] = {}
        self._semaphore = threading.Semaphore(MAX_WORKERS)

    def submit(self, title: str, fn: Callable[[Callable[[str, Dict], None]], Dict]) -> str:
        """fn receives an on_step(name, data) callback; runs on a worker thread."""
        task_id = uuid.uuid4().hex[:10]
        task = {
            "id": task_id, "title": title, "status": "queued",
            "created": time.time(), "steps": [], "result": None, "error": None,
        }
        with self._lock:
            self._tasks[task_id] = task
            # keep registry bounded
            if len(self._tasks) > 100:
                for old_id in sorted(self._tasks, key=lambda t: self._tasks[t]["created"])[:20]:
                    if self._tasks[old_id]["status"] in ("done", "failed"):
                        del self._tasks[old_id]

        def on_step(name: str, data: Dict):
            with self._lock:
                task["steps"].append({"step": name, "ts": time.time(), **data})

        def worker():
            with self._semaphore:
                with self._lock:
                    task["status"] = "running"
                try:
                    result = fn(on_step)
                    with self._lock:
                        task["status"], task["result"] = "done", result
                except Exception as e:
                    with self._lock:
                        task["status"], task["error"] = "failed", str(e)

        threading.Thread(target=worker, daemon=True).start()
        return task_id

    def get(self, task_id: str) -> Optional[Dict]:
        with self._lock:
            t = self._tasks.get(task_id)
            return dict(t) if t else None

    def list(self) -> List[Dict]:
        with self._lock:
            return [
                {k: t[k] for k in ("id", "title", "status", "created", "error")}
                for t in sorted(self._tasks.values(), key=lambda t: -t["created"])
            ]
