"""Lineage map: OM order line <-> AR invoice line <-> RMCS performance obligation.

The lineage map is the **single source of truth** for routing AR-side events
(invoices, credit memos, RMAs) back to the OM line that drives revenue. RMCS
performance obligations are keyed off the OM line, not the AR line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class LineageEntry:
    om_order_number: str
    om_line_number: str
    ar_invoice_number: str
    ar_invoice_line_number: str
    price_component_code: str
    is_billing_split: bool
    revenue_line_id: str
    """Stable id of the synthetic single revenue line we emit to RMCS for
    this OM line. Same value across all AR splits of the same OM line."""


@dataclass
class LineageMap:
    """Mutable lineage store. The reference implementation is in-memory; swap
    in a database-backed implementation for production by reusing the same
    interface."""

    entries: list[LineageEntry] = field(default_factory=list)

    def add(self, entry: LineageEntry) -> None:
        self.entries.append(entry)

    def extend(self, entries: Iterable[LineageEntry]) -> None:
        self.entries.extend(entries)

    def for_ar_line(
        self, invoice_number: str, invoice_line_number: str
    ) -> LineageEntry | None:
        for e in self.entries:
            if (
                e.ar_invoice_number == invoice_number
                and e.ar_invoice_line_number == invoice_line_number
            ):
                return e
        return None

    def for_om_line(
        self, om_order_number: str, om_line_number: str
    ) -> list[LineageEntry]:
        return [
            e
            for e in self.entries
            if e.om_order_number == om_order_number
            and e.om_line_number == om_line_number
        ]

    def revenue_line_id_for(
        self, om_order_number: str, om_line_number: str
    ) -> str:
        """Deterministic synthetic id for the RMCS revenue line of an OM line.

        Using a deterministic id makes the emitted FBDI rows idempotent: a
        replay of the same OM line produces the same source_document_number
        and RMCS will deduplicate on its side.
        """
        return f"REV-{om_order_number}-{om_line_number}"
