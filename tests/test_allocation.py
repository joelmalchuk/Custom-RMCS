from datetime import date
from decimal import Decimal

from custom_rmcs.allocation import (
    StaticSSPCatalog,
    allocate,
    collapse_to_revenue_lines,
)
from custom_rmcs.models import (
    ARInvoice,
    ARInvoiceLine,
    OMOrder,
    OMOrderLine,
    OMPriceComponent,
)
from custom_rmcs.models.om import CUSTOMER_PAY, INSURANCE_PAY, LIST_PRICE


def _order_two_lines() -> OMOrder:
    return OMOrder(
        order_number="OM-2001",
        customer_number="C-9",
        business_unit="US-OPS",
        ordered_date=date(2026, 5, 1),
        currency_code="USD",
        lines=(
            OMOrderLine(
                line_number="1",
                item_number="A",
                item_class="CLASS-X",
                quantity=Decimal("1"),
                unit_of_measure="Ea",
                fulfillment_date=date(2026, 5, 2),
                price_components=(
                    OMPriceComponent(LIST_PRICE, Decimal("600.00")),
                    OMPriceComponent(CUSTOMER_PAY, Decimal("120.00")),
                    OMPriceComponent(INSURANCE_PAY, Decimal("480.00")),
                ),
            ),
            OMOrderLine(
                line_number="2",
                item_number="B",
                item_class="CLASS-X",
                quantity=Decimal("1"),
                unit_of_measure="Ea",
                fulfillment_date=date(2026, 5, 2),
                price_components=(
                    OMPriceComponent(LIST_PRICE, Decimal("400.00")),
                    OMPriceComponent(CUSTOMER_PAY, Decimal("80.00")),
                    OMPriceComponent(INSURANCE_PAY, Decimal("320.00")),
                ),
            ),
        ),
    )


def _invoice_for_order() -> ARInvoice:
    return ARInvoice(
        invoice_number="AR-2001",
        customer_number="C-9",
        business_unit="US-OPS",
        invoice_date=date(2026, 5, 3),
        currency_code="USD",
        lines=(
            ARInvoiceLine("1", "OM-2001", "1", CUSTOMER_PAY, "A",
                          Decimal("1"), Decimal("120.00")),
            ARInvoiceLine("2", "OM-2001", "1", INSURANCE_PAY, "A",
                          Decimal("1"), Decimal("480.00")),
            ARInvoiceLine("3", "OM-2001", "2", CUSTOMER_PAY, "B",
                          Decimal("1"), Decimal("80.00")),
            ARInvoiceLine("4", "OM-2001", "2", INSURANCE_PAY, "B",
                          Decimal("1"), Decimal("320.00")),
        ),
    )


def test_relative_ssp_reallocates_within_contract():
    order = _order_two_lines()
    invoice = _invoice_for_order()

    # SSPs different from the actual transaction price -> RMCS would
    # reallocate. We expect the same outcome from our allocator.
    catalog = StaticSSPCatalog(
        by_item={"A": Decimal("500.00"), "B": Decimal("500.00")},
    )

    rl = collapse_to_revenue_lines([order], [invoice], catalog)
    allocated = allocate(rl)

    # Total transaction price = 600 + 400 = 1000. Allocated 50/50 by SSP.
    total = sum((l.allocated_amount for l in allocated), Decimal("0"))
    assert total == Decimal("1000.00")
    assert allocated[0].allocated_amount == Decimal("500.00")
    assert allocated[1].allocated_amount == Decimal("500.00")

    # Billing split must stay as-billed (revenue allocation does not
    # change who-pays-what).
    assert allocated[0].billing_split.customer_amount == Decimal("120.00")
    assert allocated[0].billing_split.insurance_amount == Decimal("480.00")


def test_allocation_handles_rounding_to_the_cent():
    order = _order_two_lines()
    invoice = _invoice_for_order()

    # Awkward SSP ratio to force rounding.
    catalog = StaticSSPCatalog(
        by_item={"A": Decimal("333.33"), "B": Decimal("666.67")},
    )
    allocated = allocate(
        collapse_to_revenue_lines([order], [invoice], catalog)
    )
    total = sum((l.allocated_amount for l in allocated), Decimal("0"))
    assert total == Decimal("1000.00")  # exact to the cent
