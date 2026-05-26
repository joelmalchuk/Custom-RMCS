"""CLI entrypoint invoked by OIC.

Usage::

    python -m custom_rmcs \\
        --om-extract ./extracts/om.json \\
        --ar-extract ./extracts/ar.json \\
        --ssp-catalog ./extracts/ssp.json \\
        --lineage-store ./state/lineage.json \\
        --out ./out/rmcs_fbdi.zip
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .allocation import JSONFileSSPCatalog
from .feeders import JSONFileARFeeder, JSONFileOMFeeder
from .lineage import JSONLineageStore
from .pipeline import run


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="custom_rmcs",
        description=(
            "Build an RMCS FBDI ZIP from OIC-staged OM and AR extracts."
        ),
    )
    p.add_argument("--om-extract", required=True, type=Path)
    p.add_argument("--ar-extract", required=True, type=Path)
    p.add_argument("--ssp-catalog", required=True, type=Path)
    p.add_argument("--lineage-store", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument(
        "--source-system-code",
        default="CUSTOM_OMG",
        help="Value written to SOURCE_SYSTEM_CODE in the FBDI rows.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run(
        om_feeder=JSONFileOMFeeder(args.om_extract),
        ar_feeder=JSONFileARFeeder(args.ar_extract),
        ssp_catalog=JSONFileSSPCatalog(args.ssp_catalog),
        lineage_store=JSONLineageStore(args.lineage_store),
        output_zip=args.out,
        source_system_code=args.source_system_code,
    )
    summary = {
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
