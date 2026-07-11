"""
backup_service.py — Periodic snapshot backup for the knowledge base.

Removes the single-point-of-failure risk of xoltaos_knowledge.db being one
local SQLite file: every N minutes, copies it to S3-compatible storage
(works with AWS S3, Cloudflare R2, Backblaze B2 — anything speaking the S3
API). Restore pulls the latest snapshot back down.

Turso (real-time replicated SQLite) is the natural next upgrade once there
are real users; this is the fast-to-build interim per the planning doc.

ENV required:
  BACKUP_S3_BUCKET
  BACKUP_S3_ENDPOINT_URL   (omit for real AWS S3)
  BACKUP_S3_ACCESS_KEY
  BACKUP_S3_SECRET_KEY
  BACKUP_INTERVAL_MINUTES  (default 15)

Usage (in app.py, after kdb.init_storage()):
    from backup_service import start_backup_scheduler
    start_backup_scheduler()
"""

import os
import logging
import shutil
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = "xoltaos_knowledge.db"
_scheduler = None


def _get_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("BACKUP_S3_ENDPOINT_URL") or None,
        aws_access_key_id=os.environ["BACKUP_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["BACKUP_S3_SECRET_KEY"],
    )


def run_snapshot() -> bool:
    """Copy the current DB file to S3-compatible storage. Never raises."""
    bucket = os.environ.get("BACKUP_S3_BUCKET")
    if not bucket:
        logger.debug("[Backup] BACKUP_S3_BUCKET not set — skipping snapshot")
        return False

    if not os.path.exists(DB_PATH):
        logger.debug("[Backup] %s does not exist yet — skipping snapshot", DB_PATH)
        return False

    tmp_copy = f"{DB_PATH}.snapshot"
    try:
        # Copy first so we never upload a file mid-write from another thread
        shutil.copyfile(DB_PATH, tmp_copy)

        ts  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        key = f"knowledge-snapshots/{ts}.db"

        client = _get_client()
        client.upload_file(tmp_copy, bucket, key)
        client.upload_file(tmp_copy, bucket, "knowledge-snapshots/latest.db")  # rolling pointer

        logger.info("[Backup] Snapshot uploaded: s3://%s/%s", bucket, key)
        return True
    except Exception as exc:
        logger.error("[Backup] Snapshot failed: %s", exc)
        return False
    finally:
        if os.path.exists(tmp_copy):
            os.remove(tmp_copy)


def restore_latest(dest_path: str = DB_PATH) -> bool:
    """Pull the most recent snapshot down, e.g. after the primary file corrupts."""
    bucket = os.environ.get("BACKUP_S3_BUCKET")
    if not bucket:
        logger.error("[Backup] BACKUP_S3_BUCKET not set — cannot restore")
        return False
    try:
        client = _get_client()
        client.download_file(bucket, "knowledge-snapshots/latest.db", dest_path)
        logger.info("[Backup] Restored %s from latest snapshot", dest_path)
        return True
    except Exception as exc:
        logger.error("[Backup] Restore failed: %s", exc)
        return False


def start_backup_scheduler():
    """Starts a background job that snapshots the DB every N minutes."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    interval = int(os.environ.get("BACKUP_INTERVAL_MINUTES", 15))
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("[Backup] apscheduler not installed — periodic backups disabled")
        return None

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(run_snapshot, "interval", minutes=interval, id="knowledge_backup")
    _scheduler.start()
    logger.info("[Backup] Scheduler started — snapshot every %d minute(s)", interval)
    return _scheduler
