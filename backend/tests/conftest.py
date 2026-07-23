"""
conftest.py, shared fixtures for the credential-free part of the test suite.

Everything here runs against a real, throwaway SQLite file per test, no
Cohere/Stripe/Google/Microsoft credentials involved anywhere. That's a
deliberate scope: this suite covers business logic (RBAC, referrals,
templates, workflow-import parsing/compilation, digest stats, field
encryption, audit scoping) that never leaves the database. Anything that
calls an external API (LLM calls, Stripe checkout, Google OAuth, OneDrive)
needs a second, separate suite built around mocking those calls, not
attempted here, and flagged rather than faked.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.fernet import Fernet
os.environ.setdefault("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())

import knowledge_db as kdb


@pytest.fixture
def db():
    """
    A fresh, isolated SQLite file for a single test. Auto-cleaned up after.

    Two layers of process-lifetime caching have to be reset for real
    per-test isolation, not just one:

    1. knowledge_db._get_conn() caches a thread-local connection object,
       reassigning DB_PATH alone isn't enough, or _get_conn() keeps
       returning the previous test's already-closed connection.

    2. Nearly every module in this codebase (auth, referrals, teams,
       templates, workflow_engine, workflow_store, subscription_manager,
       onedrive_routes, personalization, projects, moderation) guards its
       own init_*_tables() with a module-level "already ran once" boolean.
       That's correct for a real long-running server, but means a second
       test in the same process silently skips table creation entirely
       against its brand-new (table-less) database, because the flag from
       test 1 is still True. Every one of those flags has to be reset too.
    """
    tmpdb = tempfile.mktemp(suffix=".db")
    kdb.DB_PATH = tmpdb
    kdb._local.conn = None

    import auth, referrals, teams, templates, workflow_engine, workflow_store
    import subscription_manager, onedrive_routes, personalization, projects, moderation
    for module, flag in [
        (auth, "_auth_tables_created"), (referrals, "_tables_created"),
        (teams, "_tables_created"), (templates, "_tables_created"),
        (workflow_engine, "_runs_table_created"), (workflow_store, "_tables_created"),
        (subscription_manager, "_subs_tables_created"), (onedrive_routes, "_tables_created"),
        (personalization, "_tables_created"), (projects, "_tables_created"),
        (moderation, "_tables_created"),
    ]:
        setattr(module, flag, False)

    kdb._create_tables(kdb._get_conn())
    auth.init_auth_tables()

    yield kdb._get_conn()

    kdb._local.conn = None
    try:
        os.remove(tmpdb)
    except OSError:
        pass


@pytest.fixture
def make_user(db):
    """Factory fixture: make_user('alice@example.com') -> user_id."""
    import uuid
    from datetime import datetime, timezone
    import auth

    def _make(email: str, tos_status: str = "accepted") -> str:
        uid = str(uuid.uuid4())
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO users (id, email, password_hash, created_at, is_active, tos_status, tos_version) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, email, "x", datetime.now(timezone.utc).isoformat(), 1, tos_status, auth.CURRENT_POLICY_VERSION)
        )
        db.commit()
        return uid

    return _make


@pytest.fixture
def flask_app():
    """
    A minimal Flask app for route-level tests, registers only the
    blueprint(s) a given test file needs, not the full app.py (which pulls
    in Cohere/ChromaDB/etc. at import time). Blueprints are registered by
    each test module via app.register_blueprint(...) in its own fixture
    override, or tests can import this directly and register what they need.
    """
    from flask import Flask
    app = Flask(__name__)
    app.testing = True
    return app


@pytest.fixture
def auth_headers(make_user):
    """auth_headers('alice@example.com') -> (user_id, {"Authorization": "Bearer ..."})"""
    import auth

    def _make(email: str):
        user_id = make_user(email)
        token = auth.generate_token(user_id)
        return user_id, {"Authorization": f"Bearer {token}"}

    return _make
