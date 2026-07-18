"""
nightly_split.py — Splits cleared orders between PARTNER_A/PARTNER_B via
Stripe Transfers. This file didn't exist before; stripe_main.py's cron
endpoint imported it unconditionally and would crash (ModuleNotFoundError)
on every invocation — any real pending transfers would have silently never
executed with no visible error to anyone but the server log.

Runs nightly (Vercel Cron -> POST /api/cron/nightly-split). For each order
still "pending_clearance" and older than HOLDING_PERIOD_DAYS (time to let a
dispute/refund land first):
  1. Deduct Stripe's own fee from the gross amount
  2. Split the net 60/40 (PARTNER_A_SPLIT/PARTNER_B_SPLIT) via two
     stripe.Transfer.create() calls tagged with the order's transfer_group
  3. Mark the order "split" so it's never processed twice

Idempotent and defensive: each order is wrapped in its own try/except so
one bad order can't stop the batch, and orders are only ever touched while
still "pending_clearance" (refunded orders are skipped automatically —
handle_refund() in stripe_main.py already flips their status).
"""

import logging
from datetime import datetime, timedelta, timezone

import stripe

import config
import database

logger = logging.getLogger(__name__)

stripe.api_key = config.STRIPE_SECRET_KEY


def _net_amount_cents(gross_cents: int) -> int:
    """Gross minus Stripe's own percentage + flat fee."""
    fee = round(gross_cents * config.STRIPE_PCT_FEE) + config.STRIPE_FLAT_FEE_CENTS
    return max(0, gross_cents - fee)


def run_nightly_split() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.HOLDING_PERIOD_DAYS)).isoformat()
    orders = database.get_mature_pending_orders(cutoff)

    processed, failed = 0, 0

    for order in orders:
        order_id = order["order_id"]
        try:
            # Re-check status right before transferring — a refund could
            # have landed between the query above and now.
            current = database.get_order(order_id)
            if not current or current["status"] != "pending_clearance":
                continue

            net_cents = _net_amount_cents(order["amount_cents"])
            if net_cents <= 0:
                database.update_status(order_id, "split")  # nothing to transfer, but done
                processed += 1
                continue

            partner_a_cents = round(net_cents * config.PARTNER_A_SPLIT)
            partner_b_cents = net_cents - partner_a_cents  # remainder avoids rounding drift

            if partner_a_cents > 0:
                stripe.Transfer.create(
                    amount=partner_a_cents,
                    currency="usd",
                    destination=config.PARTNER_A_ACCOUNT_ID,
                    transfer_group=order_id,
                    idempotency_key=f"{order_id}-partner-a",
                )
            if partner_b_cents > 0:
                stripe.Transfer.create(
                    amount=partner_b_cents,
                    currency="usd",
                    destination=config.PARTNER_B_ACCOUNT_ID,
                    transfer_group=order_id,
                    idempotency_key=f"{order_id}-partner-b",
                )

            database.update_status(order_id, "split")
            processed += 1
            logger.info(f"[NightlySplit] order={order_id} split: A={partner_a_cents}c B={partner_b_cents}c")

        except Exception as e:
            failed += 1
            logger.error(f"[NightlySplit] order={order_id} failed: {e}")
            # Deliberately NOT marking as failed/skipped — leave it
            # "pending_clearance" so tomorrow's run retries it.

    logger.info(f"[NightlySplit] run complete: {processed} split, {failed} failed, {len(orders)} candidates")
    return {"processed": processed, "failed": failed, "candidates": len(orders)}
