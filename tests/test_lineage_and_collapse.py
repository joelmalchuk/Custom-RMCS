"""The OM <-> AR relationship is read directly from AR DFFs (no lineage map).
These tests pin down the collapse step and the deterministic id function."""

from decimal import Decimal

import pytest

from custom_rmcs.allocation import StaticSSPCatalog, collapse_to_revenue_lines
from custom_rmcs.identifiers import revenue_line_id


def test_split_ar_lines_collapse_to_one_revenue_line(
    simple_om_order, simple_ar_invoice
):
    catalog = StaticSSPCatalog(by_item={"RX-100": Decimal("1000.00")})
    revenue_lines = collapse_to_revenue_lines(
        [simple_om_order], [simple_ar_invoice], catalog
    )

    assert len(revenue_lines) == 1
    rl = revenue_lines[0]
    assert rl.om_order_number == "OM-1001"
    assert rl.om_line_number == "1"
    assert rl.allocated_amount == Decimal("1000.00")
    assert rl.billing_split.customer_amount == Decimal("200.00")
    assert rl.billing_split.insurance_amount == Decimal("800.00")
    assert rl.billing_split.total == Decimal("1000.00")
    assert rl.revenue_line_id == revenue_line_id("OM-1001", "1")


def test_revenue_line_id_is_pure_and_stable():
    assert revenue_line_id("OM-1001", "1") == "REV-OM-1001-1"
    assert revenue_line_id("OM-1001", "1") == revenue_line_id("OM-1001", "1")


def test_collapse_quarantines_ar_with_unknown_om_ref(simple_om_order):
    """An AR line whose OM-ref DFFs point at an unknown OM order must not
    silently produce revenue. Today, `collapse_to_revenue_lines` simply
    yields no revenue line for those AR rows because it iterates OM, not
    AR; the unmatched AR amount surfaces in reconciliation."""
    from datetime import date

    from custom_rmcs.models import ARInvoice, ARInvoiceLine

    bad = ARInvoice(
        invoice_number="AR-OOPS",
        customer_number="C-42",
        business_unit="US-OPS",
        invoice_date=date(2026, 5, 3),
        currency_code="USD",
        lines=(
            ARInvoiceLine(
                invoice_line_number="1",
                om_order_number="OM-DOES-NOT-EXIST",
                om_line_number="1",
                price_component_code="CUSTOMER_PAY",
                item_number="RX-100",
                quantity=Decimal("1"),
                amount=Decimal("100.00"),
            ),
        ),
    )
    catalog = StaticSSPCatalog(by_item={"RX-100": Decimal("1000.00")})
    rl = collapse_to_revenue_lines([simple_om_order], [bad], catalog)
    # one OM line in, one revenue line out; the orphan AR line is not
    # merged into anything (it will appear in reconciliation as a variance)
    assert len(rl) == 1
    assert rl[0].om_order_number == "OM-1001"
    assert rl[0].allocated_amount == Decimal("0")  # nothing matched from AR
