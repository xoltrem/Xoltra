"""
rate_limit.py — Per-IP rate limiting for Flask routes.

Same fraud-protection Layer 3 already live in auth-service/auth.js, but for
the Flask auth routes (/api/auth/register, /api/auth/login) — the path the
frontend actually calls today, which previously had no rate limiting at all.

Uses Upstash Redis if UPSTASH_REDIS_REST_URL/TOKEN are set (shared counters
across multiple server processes); otherwise falls back to an in-process
dict so a single-instance deploy is still protected without any extra infra.
Never raises — a limiter failure must never block a legitimate request.
"""

import os
import time
import logging
import threading
from functools import wraps

from flask import request, jsonify

logger = logging.getLogger(__name__)

try:
    from upstash_redis import Redis
except ImportError:
    Redis = None

_redis = None
if Redis is not None and os.environ.get("UPSTASH_REDIS_REST_URL") and os.environ.get("UPSTASH_REDIS_REST_TOKEN"):
    try:
        _redis = Redis(
            url=os.environ["UPSTASH_REDIS_REST_URL"],
            token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
        )
    except Exception as e:
        logger.warning(f"[RateLimit] Redis init failed, falling back to in-memory: {e}")
        _redis = None

# In-memory fallback: {key: [expiry_ts, count]}
_local_counts: dict = {}
_local_lock = threading.Lock()


def _incr_local(key: str, window_seconds: int) -> int:
    now = time.time()
    with _local_lock:
        entry = _local_counts.get(key)
        if entry is None or entry[0] < now:
            _local_counts[key] = [now + window_seconds, 1]
            return 1
        entry[1] += 1
        return entry[1]


def rate_limit(limit: int, window_seconds: int = 60):
    """
    Decorator: caps requests to `limit` per `window_seconds` per client IP,
    keyed per-route. Degrades to a no-op (logs a warning) rather than ever
    blocking a request if the limiter itself errors.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                ip  = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
                key = f"ratelimit:{request.path}:{ip.split(',')[0].strip()}"

                if _redis is not None:
                    count = _redis.incr(key)
                    if count == 1:
                        _redis.expire(key, window_seconds)
                else:
                    count = _incr_local(key, window_seconds)

                if count > limit:
                    return jsonify({
                        "success": False,
                        "error": "Too many requests. Please slow down and try again shortly.",
                    }), 429
            except Exception as e:
                logger.warning(f"[RateLimit] limiter failed, allowing request through: {e}")

            return fn(*args, **kwargs)
        return wrapped
    return decorator


def rate_limit_user(limit: int, window_seconds: int = 60, category: str = "flood"):
    """
    Same as rate_limit(), but keyed per authenticated user_id instead of IP
    (use on @require_auth routes, after it in the decorator stack), and
    every time the limit is exceeded it also records a ToS violation via
    moderation.record_violation() — repeated flooding of an AI-cost-incurring
    endpoint escalates into an actual account timeout, not just a 429.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                from auth import get_current_user_id
                user_id = get_current_user_id() or "anonymous"
                key = f"ratelimit:user:{request.path}:{user_id}"

                if _redis is not None:
                    count = _redis.incr(key)
                    if count == 1:
                        _redis.expire(key, window_seconds)
                else:
                    count = _incr_local(key, window_seconds)

                if count > limit:
                    try:
                        import moderation
                        moderation.record_violation(
                            user_id, category=category,
                            detail=f"exceeded {limit}/{window_seconds}s on {request.path}",
                        )
                    except Exception as e:
                        logger.warning(f"[RateLimit] violation recording failed: {e}")

                    return jsonify({
                        "success": False,
                        "error": "Too many requests. Repeated abuse of this endpoint may result in a temporary account timeout.",
                    }), 429
            except Exception as e:
                logger.warning(f"[RateLimit] user limiter failed, allowing request through: {e}")

            return fn(*args, **kwargs)
        return wrapped
    return decorator
