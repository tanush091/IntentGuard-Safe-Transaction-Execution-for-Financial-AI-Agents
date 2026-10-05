"""Money is handled as integer minor units (paise, cents) everywhere inside IntentGuard."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ISO 4217 minor-unit exponents for the currencies the prototype accepts.
CURRENCY_EXPONENT = {"INR": 2, "USD": 2, "EUR": 2, "GBP": 2, "JPY": 0}

SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


class MoneyError(ValueError):
    pass


def exponent(currency: str) -> int:
    try:
        return CURRENCY_EXPONENT[currency.upper()]
    except KeyError as exc:
        raise MoneyError(f"unsupported currency {currency!r}") from exc


def to_minor(amount: Decimal | str | int | float, currency: str) -> int:
    """Convert a major-unit amount ("1500.00") to minor units (150000)."""
    try:
        value = Decimal(str(amount))
    except InvalidOperation as exc:
        raise MoneyError(f"invalid amount {amount!r}") from exc
    scaled = value.scaleb(exponent(currency))
    if scaled != scaled.to_integral_value():
        raise MoneyError(f"{amount} has more precision than {currency} allows")
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_major(amount_minor: int, currency: str) -> Decimal:
    return Decimal(amount_minor).scaleb(-exponent(currency))


def fmt(amount_minor: int, currency: str) -> str:
    exp = exponent(currency)
    major = to_major(amount_minor, currency)
    return f"{SYMBOLS.get(currency.upper(), currency.upper() + ' ')}{major:,.{exp}f}"
