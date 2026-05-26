"""Canonical RMCS source-document models.

These are the **internal** representation. The FBDI emitter
(`custom_rmcs/fbdi/`) projects these structures onto the columnar schema of
the RMCS FBDI CSVs. Keeping the canonical representation separate from the
FBDI columns lets us upgrade the FBDI template (Oracle ships new columns
every few releases) without touching the rest of the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Sequence


@dataclass(frozen=True)
class PerformanceObligation:
    """One revenue performance obligation (POB) within a contract."""

    line_id: str
    item_number: str
    item_class: str
    quantity: Decimal
    list_price: Decimal
    ssp_unit: Decimal
    allocated_amount: Decimal
    fulfillment_date: date
    om_order_number: str
    om_line_number: str
    customer_amount: Decimal
    insurance_amount: Decimal


@dataclass(frozen=True)
class RMCSSourceDocumentLine:
    """An RMCS source-document line, one per performance obligation."""

    source_document_line_number: str
    performance_obligation: PerformanceObligation


@dataclass(frozen=True)
class RMCSSourceDocument:
    """An RMCS source-document header carrying its POB lines.

    ``source_document_number`` is deterministic on the originating OM order
    number so re-running the pipeline on the same input produces the same
    document number, which RMCS deduplicates on.
    """

    source_document_number: str
    source_system_code: str
    contract_identifier: str
    customer_number: str
    business_unit: str
    document_date: date
    currency_code: str
    lines: Sequence[RMCSSourceDocumentLine]
    is_modification: bool = False
    modifies_document_number: str | None = None


@dataclass(frozen=True)
class RMCSAdjustmentDocument:
    """A negative source document emitted in response to an RMA / credit memo.

    Adjustments reference the original `RMCSSourceDocument` and POB lines.
    """

    adjustment_document_number: str
    source_system_code: str
    adjusts_document_number: str
    reason_code: str
    document_date: date
    currency_code: str
    lines: Sequence[RMCSSourceDocumentLine]
