"""Errors the supplies service raises -- each maps 1:1 to an Arabic UI
message, same pattern as derby/features/expenses/exceptions.py.
"""
from __future__ import annotations


class SupplyError(Exception):
    """Base class for every supplies-service error."""


class SupplyNameRequiredError(SupplyError):
    pass


class InvalidCostError(SupplyError):
    pass


class SupplyNotBoughtError(SupplyError):
    """Only a bought item can be converted into an expense."""
