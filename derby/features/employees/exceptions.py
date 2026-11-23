from __future__ import annotations


class EmployeeError(Exception):
    pass


class NameRequiredError(EmployeeError):
    pass


class AlreadyClockedInError(EmployeeError):
    pass


class NotClockedInError(EmployeeError):
    pass


class CorrectionReasonRequiredError(EmployeeError):
    pass
