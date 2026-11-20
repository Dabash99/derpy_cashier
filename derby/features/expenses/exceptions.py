"""Errors the expenses service raises. Each maps 1:1 to an Arabic UI
message, same small-classes pattern as derby/features/pos/exceptions.py.
"""
from __future__ import annotations


class ExpenseError(Exception):
    """Base class for every expenses-service error."""


class InvalidAmountError(ExpenseError):
    pass


class FutureDateError(ExpenseError):
    pass


class VoidReasonRequiredError(ExpenseError):
    pass


class InvalidReceiptImageError(ExpenseError):
    pass
