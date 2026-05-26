"""Accounts Receivable (AR) canonical models.

AR is the *downstream* of the OM price-component split: each OM line that has
billing-split components produces multiple AR invoice lines. The lineage
back to the originating OM line is carried by ``om_order_number`` and
``om_line_number``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence


@dataclass(frozen=True)
class ARInvoiceLine:
    """One AR invoice line.

    Because of the OM price-component split, a single OM line typically
    produces *two* AR lines: one for ``CUSTOMER_PAY`` and one for
    ``INSURANCE_PAY``. The ``price_component_code`` is what tells us which.
    """

    invoice_line_number: str
    om_order_number: str
    om_line_number: str
    price_component_code: str
    item_number: str
    quantity: Decimal
    amount: Decimal


@dataclass(frozen=True)
class ARInvoice:
    invoice_number: str
    customer_number: str
    business_unit: str
    invoice_date: date
    currency_code: str
    lines: Sequence[ARInvoiceLine]


@dataclass(frozen=True)
class ARCreditMemoLine:
    """One credit-memo line. Credits the originating AR invoice line and,
    transitively, the originating OM line."""

    credit_line_number: str
    credited_invoice_number: str
    credited_invoice_line_number: str
    om_order_number: str
    om_line_number: str
    price_component_code: str
    quantity: Decimal
    amount: Decimal


@dataclass(frozen=True)
class ARCreditMemo:
    credit_memo_number: str
    customer_number: str
    business_unit: str
    credit_memo_date: date
    currency_code: str
    lines: Sequence[ARCreditMemoLine]
    reason_code: str = "RMA"
