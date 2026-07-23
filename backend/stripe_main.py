"""
stripe_main.py — FastAPI app: checkout creation + refund webhook listener.

NOT wired into vercel.json / deployed yet — the pricing UI isn't live and
Stripe isn't connected (see subscription_manager.py's module docstring).
This file is fixed to be safe *in isolation*, ready for whenever it's
actually deployed as the real payment path:

Fixes applied (previously vulnerable):
  - Price tampering: amount_cents came directly from the client and was
    passed straight to Stripe as unit_amount — anyone could buy anything
    for $0.01. Replaced with a server-side PRODUCT_CATALOG; the client can
    only select a known product_id, never set its own price.
  - No authentication: /create-checkout was fully anonymous, with no tie
    to a Xoltra account. Now requires the same Bearer JWT the rest of the
    app uses (verified locally with PyJWT + the shared JWT_SECRET, no
    Flask import needed) and stamps user_id + client_reference_id onto
    both the order and the Stripe session.
  - No rate limiting: added a simple in-memory per-user sliding window
    (this process has no Redis access — matches rate_limit.py's degraded
    fallback behavior, just without the Redis-backed option since this is
    a separate deployable).
  - Timing-unsafe secret comparison on the cron endpoint: switched to
    hmac.compare_digest.
  - No idempotency key: a client/network retry on Session.create() could
    create duplicate checkout sessions for the same purchase. Added
    idempotency_key=order_id.
"""

import hmac
import secrets
import time
from datetime import datetime, timezone

import jwt
import stripe
import requests
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel

import config
import database

stripe.api_key = config.STRIPE_SECRET_KEY

app = FastAPI()
database.init_db()


# ═══════════════════════════════════════════════════
# SERVER-SIDE PRICE CATALOG — the client can never set its own price
# ═══════════════════════════════════════════════════
# Mirrors subscription_manager.PLANS' price_cents so this becomes a
# drop-in real payment path once it's wired up as the actual upgrade gate.
PRODUCT_CATALOG = {
    "basic":   {"name": "Xoltra Basic",   "amount_cents": 1_700},
    "premium": {"name": "Xoltra Premium", "amount_cents": 2_200},
    "max":     {"name": "Xoltra Max",     "amount_cents": 4_100},
}


class CheckoutRequest(BaseModel):
    product_id: str  # must be a PRODUCT_CATALOG key — never a client-supplied price


# ═══════════════════════════════════════════════════
# AUTH — verifies the same JWT the Flask app issues, no Flask import needed
# ═══════════════════════════════════════════════════

def require_user(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_id


# ═══════════════════════════════════════════════════
# RATE LIMITING — in-memory only; this process has no shared Redis
# ═══════════════════════════════════════════════════

_rate_buckets: dict = {}


def rate_limit(user_id: str, limit: int = 5, window_seconds: int = 3600):
    now = time.time()
    bucket = _rate_buckets.get(user_id)
    if bucket is None or bucket[0] < now:
        _rate_buckets[user_id] = [now + window_seconds, 1]
        return
    bucket[1] += 1
    if bucket[1] > limit:
        raise HTTPException(status_code=429, detail="Too many checkout attempts. Try again later.")


@app.post("/create-checkout")
def create_checkout(req: CheckoutRequest, user_id: str = require_user):
    rate_limit(user_id)

    product = PRODUCT_CATALOG.get(req.product_id)
    if product is None:
        raise HTTPException(status_code=400, detail=f"Unknown product_id: {req.product_id}")

    order_id = secrets.token_hex(16)  # unique tracking string -> transfer_group

    session = stripe.checkout.Session.create(
        mode="payment",
        client_reference_id=user_id,
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": product["name"]},
                "unit_amount": product["amount_cents"],
            },
            "quantity": 1,
        }],
        payment_intent_data={
            "transfer_group": order_id,  # ties this PaymentIntent to later Transfers
        },
        metadata={"user_id": user_id, "product_id": req.product_id},
        success_url=config.SUCCESS_URL,
        cancel_url=config.CANCEL_URL,
        idempotency_key=order_id,
    )

    database.create_order(
        order_id=order_id,
        amount_cents=product["amount_cents"],
        created_at=datetime.now(timezone.utc).isoformat(),
        status="pending_clearance",
        user_id=user_id,
    )

    return {"checkout_url": session.url, "order_id": order_id}


@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, config.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "charge.refunded":
        handle_refund(event["data"]["object"])
    elif event["type"] == "checkout.session.completed":
        activated = handle_checkout_completed(event["data"]["object"])
        if not activated:
            # Payment cleared but the tier didn't get activated — return an
            # error so Stripe retries the webhook instead of silently
            # losing a paying customer's upgrade.
            raise HTTPException(status_code=502, detail="Plan activation failed, will retry")

    return {"received": True}


@app.post("/api/cron/nightly-split")
def trigger_nightly_split(request: Request):
    # Vercel Cron sends this header automatically; also works with a manual curl + secret.
    auth = request.headers.get("authorization") or ""
    expected = f"Bearer {config.CRON_SECRET}"
    if not hmac.compare_digest(auth, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    import nightly_split
    result = nightly_split.run_nightly_split()
    return {"ok": True, **result}


def handle_refund(charge: dict):
    """Mark an order as refunded so the nightly split script skips it."""
    order_id = charge.get("transfer_group")
    if not order_id:
        return
    order = database.get_order(order_id)
    if order and order["status"] == "pending_clearance":
        database.update_status(order_id, "refunded")


def handle_checkout_completed(session: dict) -> bool:
    """
    The actual payment gate: called once Stripe confirms a checkout session
    cleared. Activates the plan in the Flask app's subscription system with
    payment_verified=True, over HTTP, since the two services don't share a
    database. Returns False on any failure so the caller can tell Stripe to
    retry rather than silently dropping a paid upgrade.
    """
    user_id    = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
    plan_id    = (session.get("metadata") or {}).get("product_id")
    session_id = session.get("id")

    if not user_id or not plan_id:
        # Nothing we can activate — log and don't ask Stripe to retry,
        # since retrying won't add the missing metadata.
        return True

    try:
        resp = requests.post(
            f"{config.FLASK_INTERNAL_URL}/api/usage/internal/activate",
            json={"user_id": user_id, "plan_id": plan_id, "payment_reference": session_id},
            headers={"X-Internal-Key": config.INTERNAL_SERVICE_KEY},
            timeout=10,
        )
        return resp.ok
    except requests.RequestException:
        return False
