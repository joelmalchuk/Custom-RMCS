"""Pipeline orchestrator.

Wires together: feeders -> lineage -> collapse -> allocate -> transform ->
RMA -> FBDI emit. Pure function over its inputs; the only side effects are
the lineage store write and the FBDI ZIP write.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .allocation import SSPCatalog, allocate, collapse_to_revenue_lines
from .fbdi import write_fbdi_package
from .feeders import ARFeeder, OMFeeder
from .lineage import LineageStore, build_lineage
from .rma import build_adjustments
from .transform import build_source_documents


@dataclass(frozen=True)
class PipelineResult:
    fbdi_zip: Path
    source_document_count: int
    adjustment_document_count: int
    revenue_line_count: int


def run(
    *,
    om_feeder: OMFeeder,
    ar_feeder: ARFeeder,
    ssp_catalog: SSPCatalog,
    lineage_store: LineageStore,
    output_zip: str | Path,
    source_system_code: str = "CUSTOM_OMG",
    fbdi_properties: dict[str, str] | None = None,
) -> PipelineResult:
    om_orders = list(om_feeder.orders())
    ar_invoices = list(ar_feeder.invoices())
    credit_memos = list(ar_feeder.credit_memos())

    lineage = lineage_store.load()
    lineage = build_lineage(om_orders, ar_invoices, lineage)

    revenue_lines = collapse_to_revenue_lines(
        om_orders, ar_invoices, ssp_catalog, lineage
    )
    revenue_lines = allocate(revenue_lines)

    documents = build_source_documents(
        om_orders, revenue_lines, source_system_code=source_system_code
    )
    adjustments = build_adjustments(
        credit_memos, lineage, source_system_code=source_system_code
    )

    fbdi_path = write_fbdi_package(
        documents,
        adjustments,
        output_path=output_zip,
        properties=fbdi_properties,
    )

    lineage_store.save(lineage)

    return PipelineResult(
        fbdi_zip=Path(fbdi_path),
        source_document_count=len(documents),
        adjustment_document_count=len(adjustments),
        revenue_line_count=len(revenue_lines),
    )
