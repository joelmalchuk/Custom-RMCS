"""SSP catalog interfaces.

The SSP catalog is owned outside Oracle (typically a finance-owned reference
data store synced into the integration runtime). It returns the standalone
selling price for an item / item class on a given date.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from pathlib import Path


class SSPCatalog(ABC):
    @abstractmethod
    def ssp_unit(
        self, item_number: str, item_class: str, on: date
    ) -> Decimal:
        """Return the SSP per unit for the given item on the given date."""


class StaticSSPCatalog(SSPCatalog):
    """In-memory SSP catalog. Useful for tests and small deployments.

    The catalog falls back from ``item_number`` to ``item_class`` and then
    to a default, matching the typical SSP governance hierarchy.
    """

    def __init__(
        self,
        by_item: dict[str, Decimal] | None = None,
        by_class: dict[str, Decimal] | None = None,
        default: Decimal | None = None,
    ) -> None:
        self._by_item = by_item or {}
        self._by_class = by_class or {}
        self._default = default

    def ssp_unit(
        self, item_number: str, item_class: str, on: date
    ) -> Decimal:
        if item_number in self._by_item:
            return self._by_item[item_number]
        if item_class in self._by_class:
            return self._by_class[item_class]
        if self._default is not None:
            return self._default
        raise KeyError(
            f"No SSP found for item {item_number!r} / class {item_class!r}"
        )


class JSONFileSSPCatalog(StaticSSPCatalog):
    """Load SSP from a JSON file. Format::

        {
          "by_item": {"RX-100": "1000.00"},
          "by_class": {"DRUG": "950.00"},
          "default": "0.00"
        }
    """

    def __init__(self, path: str | Path) -> None:
        with Path(path).open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        super().__init__(
            by_item={k: Decimal(str(v)) for k, v in raw.get("by_item", {}).items()},
            by_class={k: Decimal(str(v)) for k, v in raw.get("by_class", {}).items()},
            default=(
                Decimal(str(raw["default"])) if "default" in raw else None
            ),
        )
