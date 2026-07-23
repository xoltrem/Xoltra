"""
test_digest.py, weekly digest stats. No external credentials needed, SMTP
sending itself is skipped gracefully when unconfigured (tested here too),
not mocked, since digest.py already degrades to a safe no-op by design.
"""

import uuid
from datetime import datetime, timezone

import digest
import subscription_manager as sm
import workflow_engine
import workflow_store


def _add_run(cursor, user_id, workflow_id, status):
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO workflow_runs (run_id, user_id, workflow_id, status, started_at, finished_at, result) "
        "VALUES (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), user_id, workflow_id, status, now, now, "{}")
    )


def test_run_stats_counts_correctly(db, make_user):
    workflow_engine._init_runs_table()
    alice = make_user("alice@example.com")
    wf_id = workflow_store.save_workflow(alice, {"name": "WF", "status": "draft", "graph": {"nodes": [], "edges": []}})

    cursor = db.cursor()
    for status in ["success", "success", "failed", "partial"]:
        _add_run(cursor, alice, wf_id, status)
    db.commit()

    start_iso, end_iso = digest._week_window()
    stats = digest._run_stats(alice, start_iso, end_iso)

    assert stats["total_runs"] == 4
    assert stats["succeeded"] == 2
    assert stats["needs_attention"] == 2  # 1 failed + 1 partial


def test_zero_activity_user_is_skipped_by_full_run(db, make_user):
    workflow_engine._init_runs_table()
    make_user("bob@example.com")  # no runs at all

    result = digest.run_weekly_digest()
    assert result["skipped_no_activity"] == 1
    assert result["sent"] == 0


def test_full_pipeline_handles_missing_smtp_config_gracefully(db, make_user, monkeypatch):
    workflow_engine._init_runs_table()
    alice = make_user("alice@example.com")
    wf_id = workflow_store.save_workflow(alice, {"name": "WF", "status": "draft", "graph": {"nodes": [], "edges": []}})
    cursor = db.cursor()
    _add_run(cursor, alice, wf_id, "success")
    db.commit()

    import config
    monkeypatch.setattr(config, "DIGEST_SMTP_HOST", "")  # explicitly unconfigured

    result = digest.run_weekly_digest()
    assert result["failed"] == 1  # attempted, but no SMTP host means send fails, not crashes
    assert result["skipped_no_activity"] == 0


def test_render_includes_disclosed_estimate_language(db, make_user):
    alice = make_user("alice@example.com")
    sm.activate_trial(alice)
    stats = {"total_runs": 3, "succeeded": 3, "needs_attention": 0}
    usage = sm.get_usage_summary(alice)
    subject, html, text = digest._render("alice@example.com", stats, usage)
    assert "estimated" in text.lower()
    assert "estimated" in html.lower()
