"""Lineage persistence.

The reference implementation persists the lineage map as a JSON file so OIC
can mount it on a known path. Swap in a database-backed implementation for
production by subclassing `LineageStore`.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path

from ..models import LineageEntry, LineageMap


class LineageStore(ABC):
    @abstractmethod
    def load(self) -> LineageMap:
        ...

    @abstractmethod
    def save(self, lineage: LineageMap) -> None:
        ...


class JSONLineageStore(LineageStore):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> LineageMap:
        if not self._path.exists():
            return LineageMap()
        with self._path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return LineageMap(
            entries=[LineageEntry(**e) for e in raw.get("entries", [])]
        )

    def save(self, lineage: LineageMap) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": [asdict(e) for e in lineage.entries]}
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
