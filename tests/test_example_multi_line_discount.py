"""Pin down the cent-precise relative-SSP allocation for the
3-line-with-discount example. Failing this test means the canonical
example in `examples/multi_line_with_discount/` no longer behaves the
way the README claims."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from custom_rmcs.__main__ import main


REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "multi_line_with_discount"


def _row_by_line(lines_csv: str) -> dict[str, dict[str, str]]:
    reader = csv.reader(io.StringIO(lines_csv))
    headers = [h.lstrip("# ").strip() for h in next(reader)]
    return {
        row[headers.index("OM_LINE_NUMBER")]: dict(zip(headers, row))
        for row in reader
    }


def test_multi_line_with_discount_allocation(tmp_path: Path, capsys) -> None:
    journal = tmp_path / "state.json"
    out = tmp_path / "rmcs_fbdi.zip"

    rc = main(
        [
            "--om-extract", str(EXAMPLE / "om.json"),
            "--ar-extract", str(EXAMPLE / "ar.json"),
            "--ssp-catalog", str(EXAMPLE / "ssp.json"),
            "--state-journal", str(journal),
            "--out", str(out),
            "--run-id", "RUN-DEMO-1",
        ]
    )
    assert rc == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["source_document_count"] == 1
    assert summary["revenue_line_count"] == 3
    assert summary["adjustment_document_count"] == 0

    with zipfile.ZipFile(out) as zf:
        lines_csv = zf.read("VRM_SOURCE_DOC_LINES_INT.csv").decode()
        sub_lines_csv = zf.read("VRM_SOURCE_DOC_SUB_LINES_INT.csv").decode()

    rows = _row_by_line(lines_csv)
    assert set(rows.keys()) == {"1", "2", "3"}

    # Cent-precise relative-SSP allocation of the $734 transaction price.
    # Math: 734 * (gross/810), with last-line residual correction.
    assert rows["1"]["ITEM_NUMBER"] == "OPT-PROG"
    assert rows["1"]["ALLOCATED_AMOUNT"] == "389.65"
    assert rows["1"]["LIST_PRICE"] == "430.00"
    assert rows["1"]["SSP_PER_UNIT"] == "430.00"

    assert rows["2"]["ITEM_NUMBER"] == "SUN-SV"
    assert rows["2"]["ALLOCATED_AMOUNT"] == "212.95"
    assert rows["2"]["LIST_PRICE"] == "235.00"

    assert rows["3"]["ITEM_NUMBER"] == "OPT-SV"
    assert rows["3"]["ALLOCATED_AMOUNT"] == "131.40"
    assert rows["3"]["LIST_PRICE"] == "145.00"

    total_allocated = sum(
        float(rows[k]["ALLOCATED_AMOUNT"]) for k in rows
    )
    assert round(total_allocated, 2) == 734.00

    # Whole-dollar Finance presentation also ties:
    rounded = sum(round(float(rows[k]["ALLOCATED_AMOUNT"])) for k in rows)
    assert rounded == 734  # 390 + 213 + 131

    # Sub-lines preserve the customer/insurance billing split per OM line
    sub_reader = list(csv.reader(io.StringIO(sub_lines_csv)))
    headers = [h.lstrip("# ").strip() for h in sub_reader[0]]
    sub_rows = [dict(zip(headers, r)) for r in sub_reader[1:]]
    # 3 OM lines * 2 billing parties = 6 sub-lines
    assert len(sub_rows) == 6
    customer_total = sum(
        float(r["AMOUNT"]) for r in sub_rows
        if r["BILLING_PARTY_TYPE"] == "CUSTOMER_PAY"
    )
    insurance_total = sum(
        float(r["AMOUNT"]) for r in sub_rows
        if r["BILLING_PARTY_TYPE"] == "INSURANCE_PAY"
    )
    assert round(customer_total, 2) == 183.50  # 107.50 + 47.00 + 29.00
    assert round(insurance_total, 2) == 550.50  # 322.50 + 141.00 + 87.00
    assert round(customer_total + insurance_total, 2) == 734.00

    # State journal records 3 PENDING entries (one per emitted POB line)
    persisted = json.loads(journal.read_text())
    assert len(persisted["entries"]) == 3
    assert {e["state"] for e in persisted["entries"]} == {"PENDING"}
    assert {e["om_line_number"] for e in persisted["entries"]} == {"1", "2", "3"}
