"""Order Management (OM) canonical models.

Modeled after Oracle Fusion Cloud Order Management's DOO entities, restricted
to the attributes the RMCS reconstruction pipeline needs. Fields use snake_case
and are framework-free so they can be populated from BICC, REST, or a flat
extract without coupling to a transport layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Sequence


CUSTOMER_PAY = "CUSTOMER_PAY"
INSURANCE_PAY = "INSURANCE_PAY"
LIST_PRICE = "LIST"


@dataclass(frozen=True)
class OMPriceComponent:
    """A single price-component row attached to an OM order line.

    The price-component mechanism is what lets a single commercial OM line
    fan out into multiple AR invoice lines (one per component). Components
    classified as ``LIST_PRICE`` carry the original list price that RMCS
    would normally consume; components classified as ``CUSTOMER_PAY`` /
    ``INSURANCE_PAY`` are billing-only splits.
    """

    component_code: str
    amount: Decimal
    charge_currency_code: str = "USD"

    @property
    def is_list_price(self) -> bool:
        return self.component_code == LIST_PRICE

    @property
    def is_billing_split(self) -> bool:
        return self.component_code in (CUSTOMER_PAY, INSURANCE_PAY)


@dataclass(frozen=True)
class OMOrderLine:
    """One OM order line, which is the unit of revenue / performance obligation.

    Even though this line may be split into multiple AR invoice lines through
    price components, RMCS sees it as one performance obligation.
    """

    line_number: str
    item_number: str
    item_class: str
    quantity: Decimal
    unit_of_measure: str
    fulfillment_date: date
    price_components: Sequence[OMPriceComponent] = field(default_factory=tuple)

    def list_price_total(self) -> Decimal:
        """Sum of ``LIST`` component amounts, i.e. the gross commercial price.

        Falls back to the sum of billing-split components when no explicit
        ``LIST`` component is present (some OM configurations only carry the
        split, with ``LIST`` implicit).
        """
        list_components = [c for c in self.price_components if c.is_list_price]
        if list_components:
            return sum((c.amount for c in list_components), Decimal("0"))
        return sum(
            (c.amount for c in self.price_components if c.is_billing_split),
            Decimal("0"),
        )

    def billing_split(self) -> dict[str, Decimal]:
        """Return component_code -> amount for the billing-split components only."""
        return {
            c.component_code: c.amount
            for c in self.price_components
            if c.is_billing_split
        }


@dataclass(frozen=True)
class OMOrder:
    """A DOO sales order from OM."""

    order_number: str
    customer_number: str
    business_unit: str
    ordered_date: date
    currency_code: str
    lines: Sequence[OMOrderLine]
    contract_modification_of: str | None = None
    """If set, this order is a contract modification of the given prior order."""
