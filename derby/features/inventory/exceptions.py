from __future__ import annotations


class InventoryError(Exception):
    pass


class InvalidQuantityError(InventoryError):
    pass


class WasteReasonRequiredError(InventoryError):
    pass


class PurchaseAlreadyPaidError(InventoryError):
    pass


class NoteRequiredError(InventoryError):
    pass


class OpeningBalanceRequiredError(InventoryError):
    pass
