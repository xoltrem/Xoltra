"""
crypto_utils.py, Field-level encryption for secrets stored in SQLite.

The SQLite database (knowledge_db.py) has no encryption at rest at all,
plain sqlite3.connect(), no SQLCipher, nothing. Swapping the whole DB
engine for SQLCipher is a real infrastructure decision (new dependency,
migration path for existing data, performance/deployment implications)
that isn't this module's call to make unilaterally.

What IS a safe, contained fix: encrypt specific highly-sensitive columns
before they ever reach disk, decrypt on read. First (and currently only)
use: onedrive_routes.py's access_token/refresh_token, a refresh_token is
a long-lived credential to a user's actual Microsoft account; storing it
in plaintext in a file that a backup, a misconfigured permission, or a
SQL-injection bug could expose is a real severity finding, not a
theoretical one.

Uses Fernet (AES-128-CBC + HMAC, from the `cryptography` package) rather
than hand-rolled crypto, this is the standard, boring, correct choice for
"encrypt a field with a server-held key," which is exactly what this is.
"""

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")
_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    if not _FIELD_ENCRYPTION_KEY:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "and set it as an env var before storing any encrypted field. "
            "There's no safe default for this one, unlike the other config "
            "placeholders in this codebase."
        )
    try:
        _fernet = Fernet(_FIELD_ENCRYPTION_KEY.encode())
    except Exception as e:
        raise RuntimeError(f"FIELD_ENCRYPTION_KEY is not a valid Fernet key: {e}")
    return _fernet


def encrypt_secret(plaintext: str) -> str:
    """Returns a versioned, base64-safe ciphertext string, storable as TEXT."""
    if plaintext is None:
        return None
    token = _get_fernet().encrypt(plaintext.encode())
    return "enc:v1:" + token.decode()


def decrypt_secret(value: str) -> str:
    """
    Decrypts a value written by encrypt_secret(). If the value doesn't
    have the "enc:v1:" prefix, it predates this module (written before
    field encryption existed, or FIELD_ENCRYPTION_KEY wasn't set yet),
    returned as-is rather than raising, the same "don't break existing
    data" choice made for the audit log's pre-scoping entries and the
    referral system's pre-existing signups. Logged once as a warning so
    it's visible, not silent.
    """
    if value is None:
        return None
    if not value.startswith("enc:v1:"):
        logger.warning("[Crypto] read an unencrypted legacy value, will be encrypted on next write")
        return value
    try:
        return _get_fernet().decrypt(value[len("enc:v1:"):].encode()).decode()
    except InvalidToken:
        logger.error("[Crypto] decryption failed, wrong FIELD_ENCRYPTION_KEY or corrupted data")
        raise
