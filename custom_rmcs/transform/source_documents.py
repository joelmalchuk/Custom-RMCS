"""Project allocated revenue lines into canonical RMCS source documents."""

from __future__ import annotations

from typing import Iterable

from ..identifiers import source_document_number
from ..models import (
    AllocatedRevenueLine,
    OMOrder,
    PerformanceObligation,
    RMCSSourceDocument,
    RMCSSourceDocumentLine,
)


DEFAULT_SOURCE_SYSTEM_CODE = "CUSTOM_OMG"


def build_source_documents(
    om_orders: Iterable[OMOrder],
    revenue_lines: Iterable[AllocatedRevenueLine],
    *,
    source_system_code: str = DEFAULT_SOURCE_SYSTEM_CODE,
) -> list[RMCSSourceDocument]:
    """Group revenue lines by their originating OM order and emit one
    `RMCSSourceDocument` per order. Each OM line becomes one POB."""
    orders_by_number = {o.order_number: o for o in om_orders}

    revenue_by_order: dict[str, list[AllocatedRevenueLine]] = {}
    for rl in revenue_lines:
        revenue_by_order.setdefault(rl.om_order_number, []).append(rl)

    documents: list[RMCSSourceDocument] = []
    for order_number, lines in revenue_by_order.items():
        order = orders_by_number[order_number]
        om_line_index = {l.line_number: l for l in order.lines}

        doc_lines: list[RMCSSourceDocumentLine] = []
        for rl in lines:
            om_line = om_line_index[rl.om_line_number]
            doc_lines.append(
                RMCSSourceDocumentLine(
                    source_document_line_number=rl.revenue_line_id,
                    performance_obligation=PerformanceObligation(
                        line_id=rl.revenue_line_id,
                        item_number=rl.item_number,
                        item_class=rl.item_class,
                        quantity=rl.quantity,
                        list_price=rl.list_price,
                        ssp_unit=rl.ssp_unit,
                        allocated_amount=rl.allocated_amount,
                        fulfillment_date=om_line.fulfillment_date,
                        om_order_number=rl.om_order_number,
                        om_line_number=rl.om_line_number,
                        customer_amount=rl.billing_split.customer_amount,
                        insurance_amount=rl.billing_split.insurance_amount,
                    ),
                )
            )

        documents.append(
            RMCSSourceDocument(
                source_document_number=source_document_number(order.order_number),
                source_system_code=source_system_code,
                contract_identifier=order.order_number,
                customer_number=order.customer_number,
                business_unit=order.business_unit,
                document_date=order.ordered_date,
                currency_code=order.currency_code,
                lines=tuple(doc_lines),
                is_modification=order.contract_modification_of is not None,
                modifies_document_number=(
                    source_document_number(order.contract_modification_of)
                    if order.contract_modification_of
                    else None
                ),
            )
        )
    return documents
