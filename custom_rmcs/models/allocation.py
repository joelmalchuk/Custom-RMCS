"""Models produced by the allocation stage."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BillingSplit:
    """The customer/insurance split for a revenue line.

    This is *billing-only* information carried for traceability and for
    downstream reconciliation against AR. It is **not** used by RMCS for
    revenue recognition -- RMCS sees the full allocated amount as the
    transaction price for the performance obligation.
    """

    customer_amount: Decimal
    insurance_amount: Decimal

    @property
    def total(self) -> Decimal:
        return self.customer_amount + self.insurance_amount


@dataclass(frozen=True)
class AllocatedRevenueLine:
    """A revenue line that has been collapsed from N AR lines back to a single
    OM line and had its transaction price allocated against the SSP catalog."""

    revenue_line_id: str
    om_order_number: str
    om_line_number: str
    item_number: str
    item_class: str
    quantity: Decimal
    list_price: Decimal
    """Original OM list price before any order-level discount."""
    ssp_unit: Decimal
    """Standalone selling price per unit from the externally managed catalog."""
    allocated_amount: Decimal
    """The transaction price allocated to this performance obligation."""
    billing_split: BillingSplit
