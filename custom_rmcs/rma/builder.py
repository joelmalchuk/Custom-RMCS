"""Build RMCS adjustment documents from AR credit memos."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from ..models import (
    ARCreditMemo,
    LineageMap,
    PerformanceObligation,
    RMCSAdjustmentDocument,
    RMCSSourceDocumentLine,
)
from ..models.om import CUSTOMER_PAY, INSURANCE_PAY
from ..transform.source_documents import DEFAULT_SOURCE_SYSTEM_CODE


def build_adjustments(
    credit_memos: Iterable[ARCreditMemo],
    lineage: LineageMap,
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
        # group by (om_order, om_line)
        per_om_line: dict[tuple[str, str], dict] = {}
        for cl in cm.lines:
            key = (cl.om_order_number, cl.om_line_number)
            bucket = per_om_line.setdefault(
                key,
                {
                    "quantity": Decimal("0"),
                    "amount": Decimal("0"),
                    "customer": Decimal("0"),
                    "insurance": Decimal("0"),
                    "lineage_entry": lineage.for_ar_line(
                        cl.credited_invoice_number,
                        cl.credited_invoice_line_number,
                    ),
                },
            )
            bucket["quantity"] += cl.quantity
            bucket["amount"] += cl.amount
            if cl.price_component_code == CUSTOMER_PAY:
                bucket["customer"] += cl.amount
            elif cl.price_component_code == INSURANCE_PAY:
                bucket["insurance"] += cl.amount

        lines: list[RMCSSourceDocumentLine] = []
        adjusts_doc_number: str | None = None
        for (om_order, om_line_no), bucket in per_om_line.items():
            entry = bucket["lineage_entry"]
            if entry is None:
                raise ValueError(
                    f"Credit memo {cm.credit_memo_number} references AR line "
                    f"that has no lineage entry; rebuild lineage before "
                    f"applying RMAs."
                )
            revenue_line_id = entry.revenue_line_id
            adjusts_doc_number = f"SD-{om_order}"
            lines.append(
                RMCSSourceDocumentLine(
                    source_document_line_number=revenue_line_id,
                    performance_obligation=PerformanceObligation(
                        line_id=revenue_line_id,
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
                adjustment_document_number=f"ADJ-{cm.credit_memo_number}",
                source_system_code=source_system_code,
                adjusts_document_number=adjusts_doc_number or "",
                reason_code=cm.reason_code,
                document_date=cm.credit_memo_date,
                currency_code=cm.currency_code,
                lines=tuple(lines),
            )
        )
    return documents
