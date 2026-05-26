from decimal import Decimal

from custom_rmcs.allocation import StaticSSPCatalog, collapse_to_revenue_lines
from custom_rmcs.lineage import build_lineage


def test_split_ar_lines_collapse_to_one_revenue_line(
    simple_om_order, simple_ar_invoice
):
    lineage = build_lineage([simple_om_order], [simple_ar_invoice])
    catalog = StaticSSPCatalog(by_item={"RX-100": Decimal("1000.00")})

    revenue_lines = collapse_to_revenue_lines(
        [simple_om_order], [simple_ar_invoice], catalog, lineage
    )

    assert len(revenue_lines) == 1
    rl = revenue_lines[0]
    assert rl.om_order_number == "OM-1001"
    assert rl.om_line_number == "1"
    assert rl.allocated_amount == Decimal("1000.00")
    assert rl.billing_split.customer_amount == Decimal("200.00")
    assert rl.billing_split.insurance_amount == Decimal("800.00")
    assert rl.billing_split.total == Decimal("1000.00")


def test_lineage_resolves_ar_line_back_to_om_line(
    simple_om_order, simple_ar_invoice
):
    lineage = build_lineage([simple_om_order], [simple_ar_invoice])
    entry = lineage.for_ar_line("AR-9001", "1")
    assert entry is not None
    assert entry.om_order_number == "OM-1001"
    assert entry.is_billing_split is True
    assert entry.revenue_line_id == "REV-OM-1001-1"

    customer_and_insurance = lineage.for_om_line("OM-1001", "1")
    assert {e.price_component_code for e in customer_and_insurance} == {
        "CUSTOMER_PAY",
        "INSURANCE_PAY",
    }


def test_lineage_rejects_unknown_om_line(simple_om_order, simple_ar_invoice):
    bad = type(simple_ar_invoice)(
        invoice_number=simple_ar_invoice.invoice_number,
        customer_number=simple_ar_invoice.customer_number,
        business_unit=simple_ar_invoice.business_unit,
        invoice_date=simple_ar_invoice.invoice_date,
        currency_code=simple_ar_invoice.currency_code,
        lines=(
            simple_ar_invoice.lines[0].__class__(
                invoice_line_number="99",
                om_order_number="OM-DOES-NOT-EXIST",
                om_line_number="1",
                price_component_code="CUSTOMER_PAY",
                item_number="RX-100",
                quantity=Decimal("1"),
                amount=Decimal("100.00"),
            ),
        ),
    )
    import pytest

    with pytest.raises(ValueError):
        build_lineage([simple_om_order], [bad])
