"""Postgres persistence layer for orders (Vercel has no writable local disk,
so SQLite is out — use Vercel Postgres / Neon / Supabase via DATABASE_URL).
"""
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL", "postgres://user:pass@host:5432/dbname")


@contextmanager
def get_conn():
    # Serverless: open per-invocation, no long-lived pool across cold starts.
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    amount_cents INTEGER NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    status TEXT NOT NULL
                )
            """)
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_id TEXT")


def create_order(order_id: str, amount_cents: int, created_at: str, status: str = "pending_clearance",
                  user_id: str = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (order_id, user_id, amount_cents, created_at, status) VALUES (%s, %s, %s, %s, %s)",
                (order_id, user_id, amount_cents, created_at, status),
            )


def get_order(order_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_mature_pending_orders(cutoff_iso: str):
    """Orders still pending clearance, created before the cutoff timestamp."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM orders WHERE status = 'pending_clearance' AND created_at <= %s",
                (cutoff_iso,),
            )
            return [dict(r) for r in cur.fetchall()]


def update_status(order_id: str, status: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE orders SET status = %s WHERE order_id = %s", (status, order_id))
