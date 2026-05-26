"""Build RMCS adjustment documents from AR credit memos.

The OM-line reference on each credit-memo line (carried via DFFs populated
by Autoinvoice) is sufficient to route the credit back to the originating
performance obligation. No external lineage map is consulted; we only use
the deterministic identifier function.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from ..identifiers import (
    adjustment_document_number,
    revenue_line_id,
    source_document_number,
)
from ..models import (
    ARCreditMemo,
    PerformanceObligation,
    RMCSAdjustmentDocument,
    RMCSSourceDocumentLine,
)
from ..models.om import CUSTOMER_PAY, INSURANCE_PAY
from ..transform.source_documents import DEFAULT_SOURCE_SYSTEM_CODE


def build_adjustments(
    credit_memos: Iterable[ARCreditMemo],
    *,
    source_system_code: str = DEFAULT_SOURCE_SYSTEM_CODE,
) -> list[RMCSAdjustmentDocument]:
    """For each credit memo, produce one `RMCSAdjustmentDocument` that
    references the originating OM line's performance obligation.

    Multiple credit-memo lines that hit different price components of the
    same OM line are aggregated into a single adjustment line so RMCS sees
    one negative entry per POB, mirroring the way revenue is recognized.
    """
    documents: list[RMCSAdjustmentDocument] = []
    for cm in credit_memos:
        per_om_line: dict[tuple[str, str], dict] = {}
        for cl in cm.lines:
            key = (cl.om_order_number, cl.om_line_number)
            bucket = per_om_line.setdefault(
                key,
                {
                    # Quantity is taken as the max across the price-component
                    # split lines because every split line for the same OM
                    # line carries the same physical quantity -- only the
                    # *amount* is split. Summing would double-count.
                    "quantity": Decimal("0"),
                    "amount": Decimal("0"),
                    "customer": Decimal("0"),
                    "insurance": Decimal("0"),
                },
            )
            if cl.quantity > bucket["quantity"]:
                bucket["quantity"] = cl.quantity
            bucket["amount"] += cl.amount
            if cl.price_component_code == CUSTOMER_PAY:
                bucket["customer"] += cl.amount
            elif cl.price_component_code == INSURANCE_PAY:
                bucket["insurance"] += cl.amount

        lines: list[RMCSSourceDocumentLine] = []
        adjusts_doc_number: str | None = None
        for (om_order, om_line_no), bucket in per_om_line.items():
            line_id = revenue_line_id(om_order, om_line_no)
            adjusts_doc_number = source_document_number(om_order)
            lines.append(
                RMCSSourceDocumentLine(
                    source_document_line_number=line_id,
                    performance_obligation=PerformanceObligation(
                        line_id=line_id,
                        item_number="",
                        item_class="",
                        quantity=-bucket["quantity"],
                        list_price=Decimal("0"),
                        ssp_unit=Decimal("0"),
                        allocated_amount=-bucket["amount"],
                        fulfillment_date=cm.credit_memo_date,
                        om_order_number=om_order,
                        om_line_number=om_line_no,
                        customer_amount=-bucket["customer"],
                        insurance_amount=-bucket["insurance"],
                    ),
                )
            )

        if not lines:
            continue

        documents.append(
            RMCSAdjustmentDocument(
                adjustment_document_number=adjustment_document_number(
                    cm.credit_memo_number
                ),
                source_system_code=source_system_code,
                adjusts_document_number=adjusts_doc_number or "",
                reason_code=cm.reason_code,
                document_date=cm.credit_memo_date,
                currency_code=cm.currency_code,
                lines=tuple(lines),
            )
        )
    return documents
