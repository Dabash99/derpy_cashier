from __future__ import annotations

from derby.core.utils.single_instance import SingleInstanceGuard


def test_second_guard_cannot_acquire_the_same_lock(tmp_path):
    lock_path = tmp_path / "derby.lock"

    first = SingleInstanceGuard(lock_path)
    assert first.try_acquire() is True

    second = SingleInstanceGuard(lock_path)
    assert second.try_acquire() is False

    first.release()
    third = SingleInstanceGuard(lock_path)
    assert third.try_acquire() is True
    third.release()
