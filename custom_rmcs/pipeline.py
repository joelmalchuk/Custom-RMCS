"""Pipeline orchestrator.

Wires together: feeders -> collapse -> allocate -> transform -> RMA ->
FBDI emit -> state journal write. Pure function over its inputs except for
the state journal write and the FBDI ZIP write.

The OM <-> AR <-> RMCS *relationship* is not a side effect; it is read on
every run from AR DFFs (``om_order_number``, ``om_line_number``,
``price_component_code``) populated by the OM -> AR Autoinvoice flow.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from .allocation import SSPCatalog, allocate, collapse_to_revenue_lines
from .fbdi import write_fbdi_package
from .feeders import ARFeeder, OMFeeder
from .rma import build_adjustments
from .state import LoadStateJournal
from .transform import build_source_documents


@dataclass(frozen=True)
class PipelineResult:
    fbdi_zip: Path
    source_document_count: int
    adjustment_document_count: int
    revenue_line_count: int
    run_id: str


def run(
    *,
    om_feeder: OMFeeder,
    ar_feeder: ARFeeder,
    ssp_catalog: SSPCatalog,
    state_journal: LoadStateJournal,
    output_zip: str | Path,
    source_system_code: str = "CUSTOM_OMG",
    fbdi_properties: dict[str, str] | None = None,
    run_id: str | None = None,
) -> PipelineResult:
    run_id = run_id or uuid.uuid4().hex

    om_orders = list(om_feeder.orders())
    ar_invoices = list(ar_feeder.invoices())
    credit_memos = list(ar_feeder.credit_memos())

    revenue_lines = collapse_to_revenue_lines(
        om_orders, ar_invoices, ssp_catalog
    )
    revenue_lines = allocate(revenue_lines)

    documents = build_source_documents(
        om_orders, revenue_lines, source_system_code=source_system_code
    )
    adjustments = build_adjustments(
        credit_memos, source_system_code=source_system_code
    )

    fbdi_path = write_fbdi_package(
        documents,
        adjustments,
        output_path=output_zip,
        properties=fbdi_properties,
    )

    for doc in documents:
        for line in doc.lines:
            pob = line.performance_obligation
            state_journal.record_emitted(
                source_document_number=doc.source_document_number,
                source_document_line_number=line.source_document_line_number,
                om_order_number=pob.om_order_number,
                om_line_number=pob.om_line_number,
                run_id=run_id,
            )
    for adj in adjustments:
        for line in adj.lines:
            pob = line.performance_obligation
            state_journal.record_emitted(
                source_document_number=adj.adjustment_document_number,
                source_document_line_number=line.source_document_line_number,
                om_order_number=pob.om_order_number,
                om_line_number=pob.om_line_number,
                run_id=run_id,
            )

    return PipelineResult(
        fbdi_zip=Path(fbdi_path),
        source_document_count=len(documents),
        adjustment_document_count=len(adjustments),
        revenue_line_count=len(revenue_lines),
        run_id=run_id,
    )
