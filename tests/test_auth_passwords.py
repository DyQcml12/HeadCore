from __future__ import annotations

import pytest

from app.auth.passwords import PasswordPolicyError, hash_password, validate_password, verify_password


def test_password_policy_rejects_short_or_weak_passwords() -> None:
    with pytest.raises(PasswordPolicyError, match="at least 12"):
        validate_password("Short1!pass")
    with pytest.raises(PasswordPolicyError, match="uppercase"):
        validate_password("lowercase-only-password1!")


def test_argon2_password_hash_verifies_without_exposing_plaintext() -> None:
    password = "SafePassword!2026"

    encoded = hash_password(password)

    assert encoded.startswith("$argon2id$")
    assert password not in encoded
    assert verify_password(encoded, password) is True
    assert verify_password(encoded, "IncorrectPassword!2026") is False
