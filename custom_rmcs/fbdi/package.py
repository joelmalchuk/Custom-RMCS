"""Write an RMCS FBDI ZIP from canonical source/adjustment documents."""

from __future__ import annotations

import csv
import io
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from ..models import (
    RMCSAdjustmentDocument,
    RMCSSourceDocument,
    RMCSSourceDocumentLine,
)
from .schema import (
    SOURCE_DOCUMENTS_COLUMNS,
    SOURCE_DOC_LINES_COLUMNS,
    SOURCE_DOC_SUB_LINES_COLUMNS,
)


_SOURCE_DOCUMENT_TYPE_ORIGINAL = "ORIGINAL"
_SOURCE_DOCUMENT_TYPE_MODIFICATION = "MODIFICATION"
_SOURCE_DOCUMENT_TYPE_ADJUSTMENT = "ADJUSTMENT"


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _write_csv(columns: tuple[str, ...], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow([f"# {c}" for c in columns])
    for row in rows:
        writer.writerow([_fmt(row.get(c, "")) for c in columns])
    return buf.getvalue().encode("utf-8")


def _header_row(doc: RMCSSourceDocument, doc_type: str) -> dict:
    return {
        "SOURCE_SYSTEM_CODE": doc.source_system_code,
        "SOURCE_DOCUMENT_TYPE_CODE": doc_type,
        "SOURCE_DOCUMENT_NUMBER": doc.source_document_number,
        "CONTRACT_IDENTIFIER": doc.contract_identifier,
        "CUSTOMER_ACCOUNT_NUMBER": doc.customer_number,
        "BUSINESS_UNIT_NAME": doc.business_unit,
        "DOCUMENT_DATE": doc.document_date.isoformat(),
        "CURRENCY_CODE": doc.currency_code,
        "IS_CONTRACT_MODIFICATION_FLAG": doc.is_modification,
        "MODIFIES_SOURCE_DOCUMENT_NUMBER": doc.modifies_document_number or "",
    }


def _line_row(
    doc: RMCSSourceDocument, line: RMCSSourceDocumentLine
) -> dict:
    pob = line.performance_obligation
    return {
        "SOURCE_SYSTEM_CODE": doc.source_system_code,
        "SOURCE_DOCUMENT_NUMBER": doc.source_document_number,
        "SOURCE_DOCUMENT_LINE_NUMBER": line.source_document_line_number,
        "ITEM_NUMBER": pob.item_number,
        "ITEM_CLASS": pob.item_class,
        "QUANTITY": pob.quantity,
        "LIST_PRICE": pob.list_price,
        "SSP_PER_UNIT": pob.ssp_unit,
        "ALLOCATED_AMOUNT": pob.allocated_amount,
        "FULFILLMENT_DATE": pob.fulfillment_date.isoformat(),
        "OM_ORDER_NUMBER": pob.om_order_number,
        "OM_LINE_NUMBER": pob.om_line_number,
        "CUSTOMER_PAY_AMOUNT": pob.customer_amount,
        "INSURANCE_PAY_AMOUNT": pob.insurance_amount,
    }


def _sub_line_rows(
    doc: RMCSSourceDocument, line: RMCSSourceDocumentLine
) -> list[dict]:
    """Emit one sub-line per billing party so downstream reconciliation in
    AR can be joined back to RMCS. RMCS does not use sub-lines for
    recognition; they are persisted as reference data."""
    pob = line.performance_obligation
    rows: list[dict] = []
    if pob.customer_amount:
        rows.append(
            {
                "SOURCE_SYSTEM_CODE": doc.source_system_code,
                "SOURCE_DOCUMENT_NUMBER": doc.source_document_number,
                "SOURCE_DOCUMENT_LINE_NUMBER": line.source_document_line_number,
                "SUB_LINE_NUMBER": "1",
                "BILLING_PARTY_TYPE": "CUSTOMER_PAY",
                "AMOUNT": pob.customer_amount,
            }
        )
    if pob.insurance_amount:
        rows.append(
            {
                "SOURCE_SYSTEM_CODE": doc.source_system_code,
                "SOURCE_DOCUMENT_NUMBER": doc.source_document_number,
                "SOURCE_DOCUMENT_LINE_NUMBER": line.source_document_line_number,
                "SUB_LINE_NUMBER": "2",
                "BILLING_PARTY_TYPE": "INSURANCE_PAY",
                "AMOUNT": pob.insurance_amount,
            }
        )
    return rows


def write_fbdi_package(
    source_documents: Iterable[RMCSSourceDocument],
    adjustment_documents: Iterable[RMCSAdjustmentDocument] = (),
    *,
    output_path: str | Path,
    properties: dict[str, str] | None = None,
) -> Path:
    """Build the FBDI ZIP at ``output_path`` and return the path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header_rows: list[dict] = []
    line_rows: list[dict] = []
    sub_line_rows: list[dict] = []

    for doc in source_documents:
        header_rows.append(
            _header_row(
                doc,
                _SOURCE_DOCUMENT_TYPE_MODIFICATION
                if doc.is_modification
                else _SOURCE_DOCUMENT_TYPE_ORIGINAL,
            )
        )
        for line in doc.lines:
            line_rows.append(_line_row(doc, line))
            sub_line_rows.extend(_sub_line_rows(doc, line))

    for adj in adjustment_documents:
        # Adjustments use the same header/line schema with negative amounts
        # and SOURCE_DOCUMENT_TYPE_CODE = ADJUSTMENT.
        synthetic_doc = RMCSSourceDocument(
            source_document_number=adj.adjustment_document_number,
            source_system_code=adj.source_system_code,
            contract_identifier=adj.adjusts_document_number,
            customer_number="",
            business_unit="",
            document_date=adj.document_date,
            currency_code=adj.currency_code,
            lines=adj.lines,
            is_modification=False,
            modifies_document_number=adj.adjusts_document_number,
        )
        header_rows.append(
            _header_row(synthetic_doc, _SOURCE_DOCUMENT_TYPE_ADJUSTMENT)
        )
        for line in adj.lines:
            line_rows.append(_line_row(synthetic_doc, line))
            sub_line_rows.extend(_sub_line_rows(synthetic_doc, line))

    headers_csv = _write_csv(SOURCE_DOCUMENTS_COLUMNS, header_rows)
    lines_csv = _write_csv(SOURCE_DOC_LINES_COLUMNS, line_rows)
    sub_lines_csv = _write_csv(SOURCE_DOC_SUB_LINES_COLUMNS, sub_line_rows)

    properties = properties or {}
    properties_text = "\n".join(
        f"{k}={v}" for k, v in sorted(properties.items())
    )

    with zipfile.ZipFile(
        output_path, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        zf.writestr("VRM_SOURCE_DOCUMENTS_INT.csv", headers_csv)
        zf.writestr("VRM_SOURCE_DOC_LINES_INT.csv", lines_csv)
        zf.writestr("VRM_SOURCE_DOC_SUB_LINES_INT.csv", sub_lines_csv)
        zf.writestr("VrmExtImportTemplate.properties", properties_text)
    return output_path
