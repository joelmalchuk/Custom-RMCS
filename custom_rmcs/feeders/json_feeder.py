"""JSON-file feeder implementations.

OIC's extract step (BICC or REST) stages data as JSON in UCM or on the OIC
file system. This feeder reads that JSON and builds canonical models.

Expected OM extract shape (one object, ``orders`` is required):

.. code-block:: json

    {
      "orders": [
        {
          "order_number": "OM-1001",
          "customer_number": "C-42",
          "business_unit": "US-OPS",
          "ordered_date": "2026-05-01",
          "currency_code": "USD",
          "contract_modification_of": null,
          "lines": [
            {
              "line_number": "1",
              "item_number": "RX-100",
              "item_class": "DRUG",
              "quantity": "1",
              "unit_of_measure": "Ea",
              "fulfillment_date": "2026-05-02",
              "price_components": [
                {"component_code": "LIST", "amount": "1000.00"},
                {"component_code": "CUSTOMER_PAY", "amount": "200.00"},
                {"component_code": "INSURANCE_PAY", "amount": "800.00"}
              ]
            }
          ]
        }
      ]
    }

Expected AR extract shape:

.. code-block:: json

    {
      "invoices": [
        {
          "invoice_number": "AR-9001",
          "customer_number": "C-42",
          "business_unit": "US-OPS",
          "invoice_date": "2026-05-03",
          "currency_code": "USD",
          "lines": [
            {
              "invoice_line_number": "1",
              "om_order_number": "OM-1001",
              "om_line_number": "1",
              "price_component_code": "CUSTOMER_PAY",
              "item_number": "RX-100",
              "quantity": "1",
              "amount": "200.00"
            }
          ]
        }
      ],
      "credit_memos": []
    }
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from ..models import (
    ARCreditMemo,
    ARCreditMemoLine,
    ARInvoice,
    ARInvoiceLine,
    OMOrder,
    OMOrderLine,
    OMPriceComponent,
)
from .base import ARFeeder, OMFeeder


def _d(value) -> Decimal:
    return Decimal(str(value))


def _date(value: str) -> date:
    return date.fromisoformat(value)


class JSONFileOMFeeder(OMFeeder):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def orders(self) -> Iterable[OMOrder]:
        with self._path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        for raw in payload.get("orders", []):
            yield OMOrder(
                order_number=raw["order_number"],
                customer_number=raw["customer_number"],
                business_unit=raw["business_unit"],
                ordered_date=_date(raw["ordered_date"]),
                currency_code=raw["currency_code"],
                contract_modification_of=raw.get("contract_modification_of"),
                lines=tuple(
                    OMOrderLine(
                        line_number=l["line_number"],
                        item_number=l["item_number"],
                        item_class=l["item_class"],
                        quantity=_d(l["quantity"]),
                        unit_of_measure=l["unit_of_measure"],
                        fulfillment_date=_date(l["fulfillment_date"]),
                        price_components=tuple(
                            OMPriceComponent(
                                component_code=pc["component_code"],
                                amount=_d(pc["amount"]),
                                charge_currency_code=pc.get(
                                    "charge_currency_code",
                                    raw["currency_code"],
                                ),
                            )
                            for pc in l.get("price_components", [])
                        ),
                    )
                    for l in raw.get("lines", [])
                ),
            )


class JSONFileARFeeder(ARFeeder):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def _payload(self) -> dict:
        with self._path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def invoices(self) -> Iterable[ARInvoice]:
        for raw in self._payload().get("invoices", []):
            yield ARInvoice(
                invoice_number=raw["invoice_number"],
                customer_number=raw["customer_number"],
                business_unit=raw["business_unit"],
                invoice_date=_date(raw["invoice_date"]),
                currency_code=raw["currency_code"],
                lines=tuple(
                    ARInvoiceLine(
                        invoice_line_number=l["invoice_line_number"],
                        om_order_number=l["om_order_number"],
                        om_line_number=l["om_line_number"],
                        price_component_code=l["price_component_code"],
                        item_number=l["item_number"],
                        quantity=_d(l["quantity"]),
                        amount=_d(l["amount"]),
                    )
                    for l in raw.get("lines", [])
                ),
            )

    def credit_memos(self) -> Iterable[ARCreditMemo]:
        for raw in self._payload().get("credit_memos", []):
            yield ARCreditMemo(
                credit_memo_number=raw["credit_memo_number"],
                customer_number=raw["customer_number"],
                business_unit=raw["business_unit"],
                credit_memo_date=_date(raw["credit_memo_date"]),
                currency_code=raw["currency_code"],
                reason_code=raw.get("reason_code", "RMA"),
                lines=tuple(
                    ARCreditMemoLine(
                        credit_line_number=l["credit_line_number"],
                        credited_invoice_number=l["credited_invoice_number"],
                        credited_invoice_line_number=l[
                            "credited_invoice_line_number"
                        ],
                        om_order_number=l["om_order_number"],
                        om_line_number=l["om_line_number"],
                        price_component_code=l["price_component_code"],
                        quantity=_d(l["quantity"]),
                        amount=_d(l["amount"]),
                    )
                    for l in raw.get("lines", [])
                ),
            )
