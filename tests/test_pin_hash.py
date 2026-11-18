from __future__ import annotations

import time

from derby.core.utils.pin_hash import (
    PBKDF2_ITERATIONS,
    generate_salt,
    hash_pin,
    is_valid_pin_format,
    verify_pin,
)


def test_hash_and_verify_roundtrip():
    salt = generate_salt()
    hashed = hash_pin("1234", salt)
    assert verify_pin("1234", salt, hashed) is True
    assert verify_pin("4321", salt, hashed) is False


def test_different_salts_produce_different_hashes():
    salt_a = generate_salt()
    salt_b = generate_salt()
    assert salt_a != salt_b
    assert hash_pin("1234", salt_a) != hash_pin("1234", salt_b)


def test_is_valid_pin_format():
    assert is_valid_pin_format("1234") is True
    assert is_valid_pin_format("123456") is True
    assert is_valid_pin_format("123") is False
    assert is_valid_pin_format("1234567") is False
    assert is_valid_pin_format("12a4") is False
    assert is_valid_pin_format("") is False


def test_verification_time_is_under_300ms():
    salt = generate_salt()
    hashed = hash_pin("123456", salt)
    started = time.perf_counter()
    verify_pin("123456", salt, hashed)
    elapsed_ms = (time.perf_counter() - started) * 1000
    print("PBKDF2 verify time at {0} iterations: {1:.1f} ms".format(PBKDF2_ITERATIONS, elapsed_ms))
    assert elapsed_ms < 300
