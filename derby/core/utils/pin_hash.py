"""PIN hashing: PBKDF2-HMAC-SHA256 with a per-user random salt.

PINs are short (4-6 digits) so a slow, salted hash with many iterations is
essential — a fast hash would make offline brute-forcing trivial. The
iteration count is tuned to stay well under ~300ms on modest hardware;
see tests/test_pin_hash.py for the measured time on the dev machine.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 150_000
SALT_BYTES = 16


def generate_salt() -> bytes:
    return secrets.token_bytes(SALT_BYTES)


def hash_pin(pin: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)


def verify_pin(pin: str, salt: bytes, expected_hash: bytes, iterations: int = PBKDF2_ITERATIONS) -> bool:
    candidate = hash_pin(pin, salt, iterations)
    return hmac.compare_digest(candidate, expected_hash)


def is_valid_pin_format(pin: str) -> bool:
    return pin.isdigit() and 4 <= len(pin) <= 6
