"""Pure discount math -- no DB, no Qt, so it's trivially unit-testable."""
from __future__ import annotations

DISCOUNT_KIND_FIXED = "fixed"
DISCOUNT_KIND_PERCENT = "percent"


def compute_discount_piasters(kind: str, amount: int, subtotal_piasters: int) -> int:
    """kind="fixed": amount is already piasters. kind="percent": amount is an
    integer 1-100, converted to piasters with round-half-up integer math.
    """
    if kind == DISCOUNT_KIND_FIXED:
        return amount
    if kind == DISCOUNT_KIND_PERCENT:
        if not (1 <= amount <= 100):
            raise ValueError("percent must be between 1 and 100")
        quotient, remainder = divmod(subtotal_piasters * amount, 100)
        if remainder * 2 >= 100:
            quotient += 1
        return quotient
    raise ValueError("unknown discount kind: {0!r}".format(kind))
