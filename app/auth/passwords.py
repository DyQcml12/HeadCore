from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class PasswordPolicyError(ValueError):
    """Raised when a registration password cannot meet the public policy."""


_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=2)


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise PasswordPolicyError("password must contain at least 12 characters")
    if not any(character.islower() for character in password):
        raise PasswordPolicyError("password must contain a lowercase letter")
    if not any(character.isupper() for character in password):
        raise PasswordPolicyError("password must contain an uppercase letter")
    if not any(character.isdigit() for character in password):
        raise PasswordPolicyError("password must contain a number")
    if not any(not character.isalnum() and not character.isspace() for character in password):
        raise PasswordPolicyError("password must contain a symbol")


def hash_password(password: str) -> str:
    validate_password(password)
    return _PASSWORD_HASHER.hash(password)


def verify_password(encoded_hash: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(encoded_hash, password)
    except (InvalidHashError, VerificationError):
        return False
