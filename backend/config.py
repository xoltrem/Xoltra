"""Placeholder configuration — replace with real values (env vars recommended)."""
import os

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_PLACEHOLDER")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_PLACEHOLDER")

PARTNER_A_ACCOUNT_ID = os.getenv("PARTNER_A_ACCOUNT_ID", "acct_PARTNER_A_ID")
PARTNER_B_ACCOUNT_ID = os.getenv("PARTNER_B_ACCOUNT_ID", "acct_PARTNER_B_ID")

PARTNER_A_SPLIT = 0.60
PARTNER_B_SPLIT = 0.40

STRIPE_PCT_FEE = 0.029
STRIPE_FLAT_FEE_CENTS = 30

HOLDING_PERIOD_DAYS = 30

CRON_SECRET = os.getenv("CRON_SECRET", "PLACEHOLDER_CRON_SECRET")

# Same secret auth.py signs Xoltra JWTs with — this service verifies the
# caller's identity by decoding the same token, without importing Flask.
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-key-do-not-use-in-prod")
JWT_ALGORITHM = "HS256"

SUCCESS_URL = os.getenv("SUCCESS_URL", "https://example.com/success")
CANCEL_URL = os.getenv("CANCEL_URL", "https://example.com/cancel")

# Where the Flask app (subscription_manager.py) lives, this service calls
# it over HTTP after a checkout clears, since they run as separate
# deployables on separate databases (Postgres here, SQLite there).
FLASK_INTERNAL_URL = os.getenv("FLASK_INTERNAL_URL", "http://localhost:5001")
# Same shared secret auth.py's /oauth-issue already uses for service-to-service calls.
INTERNAL_SERVICE_KEY = os.getenv("INTERNAL_SERVICE_KEY", "dev-internal-key-do-not-use-in-prod")

# ═══════════════════════════════════════════════════
# WEEKLY DIGEST (digest.py, Flask-side cron)
# ═══════════════════════════════════════════════════
# Flask isn't on Vercel (see docs/DEPLOYMENT.md) so nothing triggers this
# automatically, whoever hosts backend/ needs a system cron / external
# scheduler hitting POST /api/cron/weekly-digest with this same CRON_SECRET
# stripe_main.py's nightly-split already uses, reused here rather than
# adding a second secret to manage.
DIGEST_SMTP_HOST  = os.getenv("DIGEST_SMTP_HOST", "")
DIGEST_SMTP_PORT  = int(os.getenv("DIGEST_SMTP_PORT", "587"))
DIGEST_SMTP_USER  = os.getenv("DIGEST_SMTP_USER", "")
DIGEST_SMTP_PASS  = os.getenv("DIGEST_SMTP_PASS", "")
DIGEST_FROM_EMAIL = os.getenv("DIGEST_FROM_EMAIL", "digest@xoltra.net")
APP_BASE_URL      = os.getenv("APP_BASE_URL", "https://app.xoltra.net")
# Not a measured number, a disclosed, editable estimate (same practice
# Zapier's own "time saved" dashboard uses). Shown as "~N min, estimated"
# in the email itself, never as a bare fact.
DIGEST_EST_MINUTES_SAVED_PER_RUN = int(os.getenv("DIGEST_EST_MINUTES_SAVED_PER_RUN", "4"))
