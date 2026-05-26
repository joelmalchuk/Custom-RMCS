"""Build a `LineageMap` from OM orders and AR invoices."""

from __future__ import annotations

from typing import Iterable

from ..models import (
    ARInvoice,
    LineageEntry,
    LineageMap,
    OMOrder,
)
from ..models.om import LIST_PRICE


def build_lineage(
    om_orders: Iterable[OMOrder],
    ar_invoices: Iterable[ARInvoice],
    lineage_map: LineageMap | None = None,
) -> LineageMap:
    """Walk each AR line and attach it to its originating OM line.

    Every AR line in this integration carries ``om_order_number`` and
    ``om_line_number`` because OM populates the price-component-driven AR
    rows through DOO with those references. We simply normalize those into a
    persistent `LineageEntry` and assign a deterministic synthetic revenue
    line id.
    """
    lineage_map = lineage_map or LineageMap()
    om_line_index = {
        (o.order_number, l.line_number)
        for o in om_orders
        for l in o.lines
    }

    for invoice in ar_invoices:
        for ar_line in invoice.lines:
            key = (ar_line.om_order_number, ar_line.om_line_number)
            if key not in om_line_index:
                # Defensive: AR contains a line for an OM line we never saw.
                # In the seeded integration this would silently be passed to
                # RMCS and break allocation; here we surface it so OIC can
                # quarantine.
                raise ValueError(
                    f"AR invoice {invoice.invoice_number} line "
                    f"{ar_line.invoice_line_number} references unknown OM "
                    f"line {ar_line.om_order_number}/{ar_line.om_line_number}"
                )
            lineage_map.add(
                LineageEntry(
                    om_order_number=ar_line.om_order_number,
                    om_line_number=ar_line.om_line_number,
                    ar_invoice_number=invoice.invoice_number,
                    ar_invoice_line_number=ar_line.invoice_line_number,
                    price_component_code=ar_line.price_component_code,
                    is_billing_split=ar_line.price_component_code != LIST_PRICE,
                    revenue_line_id=lineage_map.revenue_line_id_for(
                        ar_line.om_order_number, ar_line.om_line_number
                    ),
                )
            )
    return lineage_map
