"""Errors the Settings feature's own services raise (today: just the
go-live cleanup) -- each maps 1:1 to an Arabic UI message.
"""
from __future__ import annotations


class ConfirmationWordMismatchError(Exception):
    pass
