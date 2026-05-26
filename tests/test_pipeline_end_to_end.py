"""End-to-end: feed JSON extracts through the CLI and inspect the FBDI ZIP."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from custom_rmcs.__main__ import main


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_cli_produces_fbdi_zip(tmp_path: Path, capsys) -> None:
    om_extract = tmp_path / "in" / "om.json"
    ar_extract = tmp_path / "in" / "ar.json"
    ssp = tmp_path / "in" / "ssp.json"
    journal = tmp_path / "state" / "load_state.json"
    out = tmp_path / "out" / "rmcs_fbdi.zip"

    _write_json(
        om_extract,
        {
            "orders": [
                {
                    "order_number": "OM-1001",
                    "customer_number": "C-42",
                    "business_unit": "US-OPS",
                    "ordered_date": "2026-05-01",
                    "currency_code": "USD",
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
                                {"component_code": "INSURANCE_PAY", "amount": "800.00"},
                            ],
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        ar_extract,
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
                            "amount": "200.00",
                        },
                        {
                            "invoice_line_number": "2",
                            "om_order_number": "OM-1001",
                            "om_line_number": "1",
                            "price_component_code": "INSURANCE_PAY",
                            "item_number": "RX-100",
                            "quantity": "1",
                            "amount": "800.00",
                        },
                    ],
                }
            ],
            "credit_memos": [],
        },
    )
    _write_json(ssp, {"by_item": {"RX-100": "1000.00"}})

    rc = main(
        [
            "--om-extract", str(om_extract),
            "--ar-extract", str(ar_extract),
            "--ssp-catalog", str(ssp),
            "--state-journal", str(journal),
            "--out", str(out),
            "--run-id", "RUN-2026-05-26-A",
        ]
    )
    assert rc == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["source_document_count"] == 1
    assert summary["adjustment_document_count"] == 0
    assert summary["revenue_line_count"] == 1
    assert summary["run_id"] == "RUN-2026-05-26-A"

    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert {
            "VRM_SOURCE_DOCUMENTS_INT.csv",
            "VRM_SOURCE_DOC_LINES_INT.csv",
            "VRM_SOURCE_DOC_SUB_LINES_INT.csv",
            "VrmExtImportTemplate.properties",
        } <= names

        lines_csv = zf.read("VRM_SOURCE_DOC_LINES_INT.csv").decode()
        # the single revenue line carries the full 1000.00 allocated amount
        assert "1000.00" in lines_csv
        assert "OM-1001" in lines_csv

        sub_lines_csv = zf.read("VRM_SOURCE_DOC_SUB_LINES_INT.csv").decode()
        # billing split preserved at sub-line granularity
        assert "CUSTOMER_PAY" in sub_lines_csv
        assert "INSURANCE_PAY" in sub_lines_csv

    # state journal records one PENDING entry per emitted source-doc line,
    # tagged with the OIC run id for downstream feedback correlation
    assert journal.exists()
    persisted = json.loads(journal.read_text())
    assert len(persisted["entries"]) == 1
    entry = persisted["entries"][0]
    assert entry["state"] == "PENDING"
    assert entry["last_run_id"] == "RUN-2026-05-26-A"
    assert entry["om_order_number"] == "OM-1001"
    assert entry["om_line_number"] == "1"
