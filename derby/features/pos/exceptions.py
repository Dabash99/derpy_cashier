"""Errors the orders service raises. Each maps 1:1 to an Arabic message the
UI shows -- kept as plain small classes (no error codes/metaprogramming)
so the mapping in the UI layer is a simple except/if chain.
"""
from __future__ import annotations


class OrderError(Exception):
    """Base class for every orders-service error."""


class InvalidTransitionError(OrderError):
    """The order isn't in the right status for this action."""


class TableBusyError(OrderError):
    """The target table already has an open order."""


class DiscountExceedsSubtotalError(OrderError):
    pass


class DiscountReasonRequiredError(OrderError):
    pass


class AddonSelectionError(OrderError):
    """A required add-on group was skipped, or too many/few were picked."""


class QuantityOutOfRangeError(OrderError):
    pass


class WrongApprovalPinError(OrderError):
    pass


class ApprovalLockedOutError(OrderError):
    """Reuses the existing global login lockout -- too many wrong PINs."""


class PermissionDeniedError(OrderError):
    pass


class VoidReasonRequiredError(OrderError):
    pass
