"""
test_crypto_utils.py, field encryption for secrets like OneDrive tokens.
Uses a real Fernet key generated in conftest.py's env setup, no external
service needed (this is local symmetric crypto, not a KMS call).
"""

import pytest

import crypto_utils


def test_encrypt_then_decrypt_roundtrips():
    secret = "M.C123_super_secret_refresh_token"  # audit-ok: dummy test fixture, not a real credential
    encrypted = crypto_utils.encrypt_secret(secret)
    assert encrypted != secret
    assert encrypted.startswith("enc:v1:")
    assert crypto_utils.decrypt_secret(encrypted) == secret


def test_legacy_plaintext_value_passes_through():
    # Simulates a row written before field encryption existed.
    legacy_value = "plain_old_unencrypted_token"
    assert crypto_utils.decrypt_secret(legacy_value) == legacy_value


def test_none_passes_through_both_directions():
    assert crypto_utils.encrypt_secret(None) is None
    assert crypto_utils.decrypt_secret(None) is None


def test_wrong_key_fails_to_decrypt():
    from cryptography.fernet import Fernet, InvalidToken
    key_a, key_b = Fernet.generate_key(), Fernet.generate_key()
    encrypted = Fernet(key_a).encrypt(b"secret").decode()
    with pytest.raises(InvalidToken):
        Fernet(key_b).decrypt(encrypted.encode())
