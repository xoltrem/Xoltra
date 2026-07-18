"""
digest.py, Weekly "what happened" email per user.

Not triggered by anything automatically, Flask isn't on Vercel (see
docs/DEPLOYMENT.md's accuracy note), so there's no built-in cron here the
way stripe_main.py has for nightly-split. Whoever hosts backend/ needs a
system cron (or any external scheduler) doing roughly:

    curl -X POST https://<flask-host>/api/cron/weekly-digest \
         -H "Authorization: Bearer $CRON_SECRET"

once a week. Reuses config.CRON_SECRET, the same one stripe_main.py's
nightly-split cron already relies on, rather than adding a second secret
nobody will remember to set.

Design choices:
- Skips users with zero workflow activity that week, an empty "you did
  nothing this week" email is a deliverability/trust problem, not a
  feature.
- "Minutes saved" is a disclosed estimate (config.DIGEST_EST_MINUTES_
  SAVED_PER_RUN * successful runs), labeled as an estimate in the email
  itself. Never presented as a measured fact, there's no real baseline
  for "how long this would've taken by hand" to measure against.
- Reuses subscription_manager.get_usage_summary() rather than
  re-querying usage_weekly directly, so this can never drift out of sync
  with what the billing UI itself shows.
"""

import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import config
import knowledge_db as kdb
import subscription_manager as sm
import workflow_engine

logger = logging.getLogger(__name__)


def _active_users() -> list:
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email FROM users WHERE is_active = 1 AND tos_status = 'accepted'")
    return [dict(r) for r in cursor.fetchall()]


def _week_window() -> tuple:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=7)).isoformat(), now.isoformat()


def _run_stats(user_id: str, start_iso: str, end_iso: str) -> dict:
    conn = kdb._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, COUNT(*) as n FROM workflow_runs "
        "WHERE user_id = ? AND started_at >= ? AND started_at <= ? GROUP BY status",
        (user_id, start_iso, end_iso)
    )
    counts = {row["status"]: row["n"] for row in cursor.fetchall()}
    # workflow_engine.py's finalization logic (verified directly) only ever
    # sets: "success", "failed", or "partial" (some nodes ok, some not) as
    # a run's final status, "running"/"skipped" are per-node, not final.
    succeeded = counts.get("success", 0)
    needs_attention = counts.get("failed", 0) + counts.get("partial", 0)
    total     = sum(counts.values())
    return {"total_runs": total, "succeeded": succeeded, "needs_attention": needs_attention, "by_status": counts}


def _render(user_email: str, run_stats: dict, usage: dict) -> tuple:
    est_minutes = run_stats["succeeded"] * config.DIGEST_EST_MINUTES_SAVED_PER_RUN
    first_name = user_email.split("@")[0]

    subject = f"Your week on Xoltra: {run_stats['total_runs']} run{'s' if run_stats['total_runs'] != 1 else ''}, {run_stats['succeeded']} succeeded"

    plan_line = f"{usage.get('plan_label', usage.get('plan_id', 'your plan'))}"
    tokens_line = ""
    if usage.get("tokens_limit"):
        tokens_line = f"<p style=\"color:#888;font-size:13px;\">{usage['tokens_used']:,} / {usage['tokens_limit']:,} weekly tokens used on {plan_line}.</p>"

    attention_line = ""
    if run_stats["needs_attention"] > 0:
        attention_line = (
            f"<p style=\"color:#888;font-size:13px;\">{run_stats['needs_attention']} run"
            f"{'s' if run_stats['needs_attention'] != 1 else ''} needed attention, check the audit log for exactly why.</p>"
        )

    html = f"""\
<html><body style="font-family:-apple-system,sans-serif;background:#0a0a0a;color:#eaeaea;padding:24px;">
  <div style="max-width:480px;margin:0 auto;">
    <h2 style="font-weight:600;">Hey {first_name},</h2>
    <p>Here's what ran on Xoltra this week:</p>
    <div style="background:#151515;border:1px solid #2a2a2a;border-radius:8px;padding:16px;margin:16px 0;">
      <p style="font-size:28px;font-weight:600;margin:0;">{run_stats['total_runs']}</p>
      <p style="color:#888;font-size:13px;margin:0 0 12px 0;">workflow run{'s' if run_stats['total_runs'] != 1 else ''}, {run_stats['succeeded']} succeeded</p>
      <p style="color:#888;font-size:13px;margin:0;">~{est_minutes} min saved this week (estimated, not measured, {config.DIGEST_EST_MINUTES_SAVED_PER_RUN} min/successful run)</p>
    </div>
    {attention_line}
    {tokens_line}
    <p style="margin-top:24px;">
      <a href="{config.APP_BASE_URL}/workflows" style="color:#fff;background:#333;padding:8px 16px;border-radius:6px;text-decoration:none;font-size:13px;">Open Xoltra</a>
    </p>
  </div>
</body></html>"""

    text = (
        f"Hey {first_name},\n\n"
        f"This week: {run_stats['total_runs']} workflow runs, {run_stats['succeeded']} succeeded.\n"
        f"~{est_minutes} min saved (estimated, {config.DIGEST_EST_MINUTES_SAVED_PER_RUN} min/successful run).\n"
        + (f"{run_stats['needs_attention']} run(s) needed attention.\n" if run_stats["needs_attention"] else "")
        + f"\nOpen Xoltra: {config.APP_BASE_URL}/workflows"
    )

    return subject, html, text


def _send_email(to_addr: str, subject: str, html: str, text: str) -> bool:
    if not config.DIGEST_SMTP_HOST:
        logger.warning("[Digest] DIGEST_SMTP_HOST not configured, skipping send, logging instead.")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = config.DIGEST_FROM_EMAIL
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(config.DIGEST_SMTP_HOST, config.DIGEST_SMTP_PORT, timeout=30) as server:
            server.ehlo()
            if config.DIGEST_SMTP_PORT == 587:
                server.starttls()
                server.ehlo()
            if config.DIGEST_SMTP_USER and config.DIGEST_SMTP_PASS:
                server.login(config.DIGEST_SMTP_USER, config.DIGEST_SMTP_PASS)
            server.sendmail(config.DIGEST_FROM_EMAIL, [to_addr], msg.as_string())
        return True
    except Exception as e:
        logger.error(f"[Digest] send failed for {to_addr}: {e}")
        return False


def run_weekly_digest() -> dict:
    workflow_engine._init_runs_table()  # idempotent, table may not exist yet on a fresh process
    start_iso, end_iso = _week_window()
    sent, skipped_no_activity, failed = 0, 0, 0

    for user in _active_users():
        try:
            stats = _run_stats(user["id"], start_iso, end_iso)
            if stats["total_runs"] == 0:
                skipped_no_activity += 1
                continue

            usage = sm.get_usage_summary(user["id"])
            subject, html, text = _render(user["email"], stats, usage)

            if _send_email(user["email"], subject, html, text):
                sent += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"[Digest] failed for user {user['id']}: {e}")
            failed += 1

    result = {"sent": sent, "skipped_no_activity": skipped_no_activity, "failed": failed}
    logger.info(f"[Digest] weekly run complete: {result}")
    return result


def register_digest_routes(app):
    from flask import request, jsonify

    @app.route("/api/cron/weekly-digest", methods=["POST"])
    def weekly_digest_cron():
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {config.CRON_SECRET}":
            return jsonify({"success": False, "error": "Forbidden"}), 403
        try:
            result = run_weekly_digest()
            return jsonify({"success": True, **result})
        except Exception as e:
            logger.error(f"[Digest] cron run failed entirely: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    logger.info("[Digest] Route registered: POST /api/cron/weekly-digest")
