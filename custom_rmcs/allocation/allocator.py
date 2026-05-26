"""Collapse AR splits back to one revenue line per OM line, then allocate.

The collapse step is the heart of the integration: it undoes the price-
component fan-out so RMCS sees one performance obligation per OM line. The
allocate step then runs ASC 606 relative-SSP allocation against the
externally managed SSP catalog.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from ..models import (
    AllocatedRevenueLine,
    ARInvoice,
    BillingSplit,
    LineageMap,
    OMOrder,
)
from ..models.om import CUSTOMER_PAY, INSURANCE_PAY
from .ssp_catalog import SSPCatalog


_CENT = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    """Bankers-aware money rounding to cents."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _ar_total_for_om_line(
    invoices: Iterable[ARInvoice],
    om_order_number: str,
    om_line_number: str,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (customer_amount, insurance_amount, total) for an OM line as
    invoiced across all AR lines."""
    customer = Decimal("0")
    insurance = Decimal("0")
    for inv in invoices:
        for line in inv.lines:
            if (
                line.om_order_number != om_order_number
                or line.om_line_number != om_line_number
            ):
                continue
            if line.price_component_code == CUSTOMER_PAY:
                customer += line.amount
            elif line.price_component_code == INSURANCE_PAY:
                insurance += line.amount
    return customer, insurance, customer + insurance


def collapse_to_revenue_lines(
    om_orders: Iterable[OMOrder],
    ar_invoices: Iterable[ARInvoice],
    ssp_catalog: SSPCatalog,
    lineage: LineageMap,
) -> list[AllocatedRevenueLine]:
    """Build one un-allocated `AllocatedRevenueLine` per OM line.

    The ``allocated_amount`` is initialized to the AR-side total (the actual
    transaction price for the line). The `allocate` step refines this with
    contract-level proportional reallocation.
    """
    invoices = list(ar_invoices)
    revenue_lines: list[AllocatedRevenueLine] = []
    for order in om_orders:
        for om_line in order.lines:
            customer_amt, insurance_amt, ar_total = _ar_total_for_om_line(
                invoices, order.order_number, om_line.line_number
            )
            list_price = om_line.list_price_total()
            ssp_unit = ssp_catalog.ssp_unit(
                om_line.item_number,
                om_line.item_class,
                om_line.fulfillment_date,
            )
            revenue_lines.append(
                AllocatedRevenueLine(
                    revenue_line_id=lineage.revenue_line_id_for(
                        order.order_number, om_line.line_number
                    ),
                    om_order_number=order.order_number,
                    om_line_number=om_line.line_number,
                    item_number=om_line.item_number,
                    item_class=om_line.item_class,
                    quantity=om_line.quantity,
                    list_price=list_price,
                    ssp_unit=ssp_unit,
                    allocated_amount=ar_total,
                    billing_split=BillingSplit(
                        customer_amount=customer_amt,
                        insurance_amount=insurance_amt,
                    ),
                )
            )
    return revenue_lines


def allocate(
    revenue_lines: list[AllocatedRevenueLine],
) -> list[AllocatedRevenueLine]:
    """Apply relative-SSP discount allocation within each OM order.

    For each contract (= OM order), if the sum of (qty * SSP) differs from
    the sum of transaction prices (the AR-side totals), reallocate the
    transaction price across performance obligations proportional to
    (qty * SSP). This is exactly what RMCS would do natively, but we run it
    here because RMCS no longer sees the original list price.

    The customer/insurance billing split is **not** reallocated -- it stays
    as billed, because it is a billing concern, not a revenue-recognition
    concern.
    """
    by_contract: dict[str, list[AllocatedRevenueLine]] = {}
    for rl in revenue_lines:
        by_contract.setdefault(rl.om_order_number, []).append(rl)

    out: list[AllocatedRevenueLine] = []
    for contract_lines in by_contract.values():
        ssp_extended_total = sum(
            (rl.quantity * rl.ssp_unit for rl in contract_lines),
            Decimal("0"),
        )
        transaction_total = sum(
            (rl.allocated_amount for rl in contract_lines), Decimal("0")
        )

        if ssp_extended_total == 0:
            # Degenerate: no SSP available, keep as-billed. This will show up
            # in the reconciliation report as an allocation exception.
            out.extend(contract_lines)
            continue

        # Allocate; track residual to land last-line correction so the sum
        # equals the transaction total exactly to the cent.
        running = Decimal("0")
        allocated: list[AllocatedRevenueLine] = []
        for idx, rl in enumerate(contract_lines):
            share = (rl.quantity * rl.ssp_unit) / ssp_extended_total
            if idx < len(contract_lines) - 1:
                amt = _q(transaction_total * share)
                running += amt
            else:
                amt = _q(transaction_total - running)
            allocated.append(
                AllocatedRevenueLine(
                    revenue_line_id=rl.revenue_line_id,
                    om_order_number=rl.om_order_number,
                    om_line_number=rl.om_line_number,
                    item_number=rl.item_number,
                    item_class=rl.item_class,
                    quantity=rl.quantity,
                    list_price=rl.list_price,
                    ssp_unit=rl.ssp_unit,
                    allocated_amount=amt,
                    billing_split=rl.billing_split,
                )
            )
        out.extend(allocated)
    return out
