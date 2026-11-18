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


class DeviceBusyError(OrderError):
    """The target PlayStation device already has an open order."""


class DeviceRateNotSetError(OrderError):
    """Starting a session on a device whose rate for this mode is 0 (unconfigured)."""


class SessionRunningError(OrderError):
    """A running PlayStation session blocks this action (pay, move, disable, ...)."""
