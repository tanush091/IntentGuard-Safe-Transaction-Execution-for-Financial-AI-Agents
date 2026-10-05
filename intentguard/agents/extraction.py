"""
Deterministic extraction of a structured proposal from a support ticket.

Used as the offline agent, and as the offline stand-in for the pre-execution
LLM reviewer baseline. Identifiers are removed before amounts are parsed, so
"C-17" or "ORD-204" can never be mistaken for an amount.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from intentguard.domain import Operation
from intentguard.money import MoneyError, to_minor

ORDER_RE = re.compile(r"\bORD-\d+\b", re.IGNORECASE)
CUSTOMER_RE = re.compile(r"\bC-\d+\b", re.IGNORECASE)
_CUR_PREFIX = {"₹": "INR", "RS": "INR", "RS.": "INR", "INR": "INR", "$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR"}
_CUR_SUFFIX = {"INR": "INR", "RUPEES": "INR", "USD": "USD", "DOLLARS": "USD", "EUR": "EUR", "EUROS": "EUR"}
AMOUNT_PREFIX_RE = re.compile(r"(₹|Rs\.?|INR|\$|USD|€|EUR)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", re.IGNORECASE)
AMOUNT_SUFFIX_RE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(INR|rupees|USD|dollars|EUR|euros)\b", re.IGNORECASE)
AUTH_RE = re.compile(r"\b(authori[sz]e|authori[sz]ation|hold|pre-?auth)\b", re.IGNORECASE)


class ExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class Extracted:
    operation: Operation
    customer_id: str
    order_id: str
    amount_minor: int
    currency: str


def extract(text: str) -> Extracted:
    order = ORDER_RE.search(text)
    customer = CUSTOMER_RE.search(text)
    if not order or not customer:
        raise ExtractionError("ticket must name an order (ORD-…) and a customer (C-…)")
    scrubbed = CUSTOMER_RE.sub(" ", ORDER_RE.sub(" ", text))

    m = AMOUNT_PREFIX_RE.search(scrubbed)
    if m:
        currency, raw = _CUR_PREFIX[m.group(1).upper()], m.group(2)
    else:
        m = AMOUNT_SUFFIX_RE.search(scrubbed)
        if not m:
            raise ExtractionError("no amount with a currency found in the ticket")
        raw, currency = m.group(1), _CUR_SUFFIX[m.group(2).upper()]
    try:
        amount_minor = to_minor(raw.replace(",", ""), currency)
    except MoneyError as exc:
        raise ExtractionError(str(exc)) from exc

    operation = Operation.PAYMENT_AUTHORIZATION if AUTH_RE.search(text) else Operation.REFUND
    return Extracted(operation, customer.group(0).upper(), order.group(0).upper(), amount_minor, currency)
