from __future__ import annotations

from datetime import datetime, timedelta, timezone

from derby.features.auth import lockout


def test_no_lockout_initially(db_conn):
    assert lockout.is_locked(db_conn) is False
    assert lockout.get_lock_remaining(db_conn) is None


def test_five_failed_attempts_lock_for_five_minutes(db_conn):
    fake_now = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    for _ in range(4):
        lockout.record_failed_attempt(db_conn, now=fake_now)
        assert lockout.is_locked(db_conn, now=fake_now) is False

    lockout.record_failed_attempt(db_conn, now=fake_now)
    assert lockout.is_locked(db_conn, now=fake_now) is True

    remaining = lockout.get_lock_remaining(db_conn, now=fake_now)
    assert remaining == timedelta(minutes=5)


def test_lockout_persists_across_a_simulated_restart(db_conn):
    # "Restarting the app" just means a fresh read of `settings` with a
    # later `now` -- there is no in-memory state to lose.
    fake_now = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    for _ in range(5):
        lockout.record_failed_attempt(db_conn, now=fake_now)

    later = fake_now + timedelta(minutes=2)
    assert lockout.is_locked(db_conn, now=later) is True


def test_lockout_expires_after_five_minutes(db_conn):
    fake_now = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    for _ in range(5):
        lockout.record_failed_attempt(db_conn, now=fake_now)

    after_expiry = fake_now + timedelta(minutes=5, seconds=1)
    assert lockout.is_locked(db_conn, now=after_expiry) is False


def test_reset_failed_attempts(db_conn):
    fake_now = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    for _ in range(3):
        lockout.record_failed_attempt(db_conn, now=fake_now)

    lockout.reset_failed_attempts(db_conn)
    assert lockout.is_locked(db_conn, now=fake_now) is False

    # Counter restarted: 4 more failures should not lock (only 4 total since reset).
    for _ in range(4):
        lockout.record_failed_attempt(db_conn, now=fake_now)
    assert lockout.is_locked(db_conn, now=fake_now) is False
