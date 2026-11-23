from __future__ import annotations


class CustomerError(Exception):
    pass


class NameRequiredError(CustomerError):
    pass


class InvalidAmountError(CustomerError):
    pass
