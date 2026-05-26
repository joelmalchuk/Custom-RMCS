"""Shared fixtures and helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from custom_rmcs.models import (
    ARCreditMemo,
    ARCreditMemoLine,
    ARInvoice,
    ARInvoiceLine,
    OMOrder,
    OMOrderLine,
    OMPriceComponent,
)
from custom_rmcs.models.om import CUSTOMER_PAY, INSURANCE_PAY, LIST_PRICE


@pytest.fixture
def simple_om_order() -> OMOrder:
    """One order, one line, split 20/80 customer/insurance against a $1000 list."""
    return OMOrder(
        order_number="OM-1001",
        customer_number="C-42",
        business_unit="US-OPS",
        ordered_date=date(2026, 5, 1),
        currency_code="USD",
        lines=(
            OMOrderLine(
                line_number="1",
                item_number="RX-100",
                item_class="DRUG",
                quantity=Decimal("1"),
                unit_of_measure="Ea",
                fulfillment_date=date(2026, 5, 2),
                price_components=(
                    OMPriceComponent(LIST_PRICE, Decimal("1000.00")),
                    OMPriceComponent(CUSTOMER_PAY, Decimal("200.00")),
                    OMPriceComponent(INSURANCE_PAY, Decimal("800.00")),
                ),
            ),
        ),
    )


@pytest.fixture
def simple_ar_invoice() -> ARInvoice:
    return ARInvoice(
        invoice_number="AR-9001",
        customer_number="C-42",
        business_unit="US-OPS",
        invoice_date=date(2026, 5, 3),
        currency_code="USD",
        lines=(
            ARInvoiceLine(
                invoice_line_number="1",
                om_order_number="OM-1001",
                om_line_number="1",
                price_component_code=CUSTOMER_PAY,
                item_number="RX-100",
                quantity=Decimal("1"),
                amount=Decimal("200.00"),
            ),
            ARInvoiceLine(
                invoice_line_number="2",
                om_order_number="OM-1001",
                om_line_number="1",
                price_component_code=INSURANCE_PAY,
                item_number="RX-100",
                quantity=Decimal("1"),
                amount=Decimal("800.00"),
            ),
        ),
    )


@pytest.fixture
def simple_credit_memo() -> ARCreditMemo:
    """Full reversal: customer-pay and insurance-pay both credited."""
    return ARCreditMemo(
        credit_memo_number="CM-7001",
        customer_number="C-42",
        business_unit="US-OPS",
        credit_memo_date=date(2026, 6, 1),
        currency_code="USD",
        reason_code="RMA",
        lines=(
            ARCreditMemoLine(
                credit_line_number="1",
                credited_invoice_number="AR-9001",
                credited_invoice_line_number="1",
                om_order_number="OM-1001",
                om_line_number="1",
                price_component_code=CUSTOMER_PAY,
                quantity=Decimal("1"),
                amount=Decimal("200.00"),
            ),
            ARCreditMemoLine(
                credit_line_number="2",
                credited_invoice_number="AR-9001",
                credited_invoice_line_number="2",
                om_order_number="OM-1001",
                om_line_number="1",
                price_component_code=INSURANCE_PAY,
                quantity=Decimal("1"),
                amount=Decimal("800.00"),
            ),
        ),
    )
