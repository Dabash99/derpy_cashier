from __future__ import annotations


class ShiftError(Exception):
    pass


class ShiftAlreadyOpenError(ShiftError):
    pass


class NoOpenShiftError(ShiftError):
    pass
