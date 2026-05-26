"""Deterministic identifier functions.

These are the only things we used to need a lineage map for. They are pure
functions of business keys carried on the OM order line (and replicated on
every AR line via DFF), so no separate index needs to be persisted.

Stability is contractual: changing any of these breaks idempotency for
in-flight OM orders. If you must change the format, version the function
and route old vs. new orders through the appropriate version.
"""

from __future__ import annotations


def revenue_line_id(om_order_number: str, om_line_number: str) -> str:
    """Stable id for the synthetic single revenue line that represents an
    OM line in RMCS, across all of its AR price-component splits."""
    return f"REV-{om_order_number}-{om_line_number}"


def source_document_number(om_order_number: str) -> str:
    """Stable RMCS source-document number for an OM order."""
    return f"SD-{om_order_number}"


def adjustment_document_number(credit_memo_number: str) -> str:
    """Stable RMCS adjustment-document number for an AR credit memo."""
    return f"ADJ-{credit_memo_number}"
