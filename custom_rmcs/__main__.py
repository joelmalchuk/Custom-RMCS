"""CLI entrypoint invoked by OIC.

Usage::

    python -m custom_rmcs \\
        --om-extract ./extracts/om.json \\
        --ar-extract ./extracts/ar.json \\
        --ssp-catalog ./extracts/ssp.json \\
        --state-journal ./state/load_state.json \\
        --out ./out/rmcs_fbdi.zip \\
        --run-id 2026-05-26T18-00Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .allocation import JSONFileSSPCatalog
from .feeders import JSONFileARFeeder, JSONFileOMFeeder
from .pipeline import run
from .state import JSONLoadStateJournal


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="custom_rmcs",
        description=(
            "Build an RMCS FBDI ZIP from OIC-staged OM and AR extracts. "
            "The OM <-> AR relationship is read directly from AR DFFs; only "
            "integration load state is persisted (in --state-journal)."
        ),
    )
    p.add_argument("--om-extract", required=True, type=Path)
    p.add_argument("--ar-extract", required=True, type=Path)
    p.add_argument("--ssp-catalog", required=True, type=Path)
    p.add_argument(
        "--state-journal",
        required=True,
        type=Path,
        help="Path to the load-state journal JSON file (created if missing).",
    )
    p.add_argument("--out", required=True, type=Path)
    p.add_argument(
        "--source-system-code",
        default="CUSTOM_OMG",
        help="Value written to SOURCE_SYSTEM_CODE in the FBDI rows.",
    )
    p.add_argument(
        "--run-id",
        default=None,
        help=(
            "Stable run identifier from OIC. Recorded against every emitted "
            "row so OIC's post-ESS-job feedback can correlate results."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run(
        om_feeder=JSONFileOMFeeder(args.om_extract),
        ar_feeder=JSONFileARFeeder(args.ar_extract),
        ssp_catalog=JSONFileSSPCatalog(args.ssp_catalog),
        state_journal=JSONLoadStateJournal(args.state_journal),
        output_zip=args.out,
        source_system_code=args.source_system_code,
        run_id=args.run_id,
    )
    summary = {
        "run_id": result.run_id,
        "fbdi_zip": str(result.fbdi_zip),
        "source_document_count": result.source_document_count,
        "adjustment_document_count": result.adjustment_document_count,
        "revenue_line_count": result.revenue_line_count,
    }
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
