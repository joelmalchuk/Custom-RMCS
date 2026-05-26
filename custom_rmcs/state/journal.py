"""Load-state journal: state of every emitted RMCS source-document line.

Used for:

- daily AR-vs-RMCS reconciliation (which OM lines are accepted / rejected
  by RMCS),
- period-close exception list (open `PENDING` or `REJECTED` entries),
- replay / retry decisions (do not re-emit `LOADED` lines).

Lifecycle:

```
            +-------+
   emit --> |PENDING| --(ESS success)----> LOADED
            +-------+ \\
                       \\-(ESS partial)---> PARTIAL
                       \\-(ESS failure)---> REJECTED
```

Only *integration* state is here. The OM/AR business relationship lives on
the AR invoice / credit-memo line DFFs.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path


class LoadState(str, Enum):
    PENDING = "PENDING"
    LOADED = "LOADED"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class LoadStateEntry:
    source_document_number: str
    source_document_line_number: str
    om_order_number: str
    om_line_number: str
    state: LoadState
    last_run_id: str
    last_error: str | None = None
    loaded_at: str | None = None
    """ISO 8601 timestamp set when the entry transitions to LOADED."""


class LoadStateJournal(ABC):
    @abstractmethod
    def upsert(self, entry: LoadStateEntry) -> None: ...

    @abstractmethod
    def get(
        self, source_document_number: str, source_document_line_number: str
    ) -> LoadStateEntry | None: ...

    @abstractmethod
    def all(self) -> list[LoadStateEntry]: ...

    @abstractmethod
    def by_state(self, state: LoadState) -> list[LoadStateEntry]: ...

    def record_emitted(
        self,
        source_document_number: str,
        source_document_line_number: str,
        om_order_number: str,
        om_line_number: str,
        run_id: str,
    ) -> None:
        """Mark an entry `PENDING` after it has been written into the FBDI
        ZIP. Idempotent: an existing `LOADED` entry is left alone (we do
        not regress LOADED rows) but `REJECTED` rows are reset to PENDING
        so a corrective re-emit can be re-attempted."""
        existing = self.get(source_document_number, source_document_line_number)
        if existing and existing.state == LoadState.LOADED:
            return
        self.upsert(
            LoadStateEntry(
                source_document_number=source_document_number,
                source_document_line_number=source_document_line_number,
                om_order_number=om_order_number,
                om_line_number=om_line_number,
                state=LoadState.PENDING,
                last_run_id=run_id,
                last_error=None,
                loaded_at=None,
            )
        )

    def record_load_result(
        self,
        source_document_number: str,
        source_document_line_number: str,
        state: LoadState,
        run_id: str,
        error: str | None = None,
        loaded_at: datetime | None = None,
    ) -> None:
        """Called by OIC's post-ESS-job feedback step.

        ``state`` is one of LOADED / REJECTED / PARTIAL.
        """
        existing = self.get(source_document_number, source_document_line_number)
        if existing is None:
            raise KeyError(
                f"No PENDING entry for "
                f"{source_document_number}/{source_document_line_number}; "
                f"OIC must call record_emitted before record_load_result."
            )
        self.upsert(
            replace(
                existing,
                state=state,
                last_run_id=run_id,
                last_error=error,
                loaded_at=(
                    loaded_at.isoformat()
                    if loaded_at is not None
                    else existing.loaded_at
                ),
            )
        )


@dataclass
class _InMemoryStore:
    rows: dict[tuple[str, str], LoadStateEntry] = field(default_factory=dict)


class JSONLoadStateJournal(LoadStateJournal):
    """Reference impl persisting the journal as a JSON file. Swap for a
    DB-backed implementation in production by subclassing `LoadStateJournal`."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._store = _InMemoryStore()
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        for r in raw.get("entries", []):
            entry = LoadStateEntry(
                source_document_number=r["source_document_number"],
                source_document_line_number=r["source_document_line_number"],
                om_order_number=r["om_order_number"],
                om_line_number=r["om_line_number"],
                state=LoadState(r["state"]),
                last_run_id=r["last_run_id"],
                last_error=r.get("last_error"),
                loaded_at=r.get("loaded_at"),
            )
            self._store.rows[
                (entry.source_document_number, entry.source_document_line_number)
            ] = entry

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "entries": [
                {**asdict(e), "state": e.state.value}
                for e in self._store.rows.values()
            ]
        }
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)

    def upsert(self, entry: LoadStateEntry) -> None:
        self._store.rows[
            (entry.source_document_number, entry.source_document_line_number)
        ] = entry
        self._flush()

    def get(
        self, source_document_number: str, source_document_line_number: str
    ) -> LoadStateEntry | None:
        return self._store.rows.get(
            (source_document_number, source_document_line_number)
        )

    def all(self) -> list[LoadStateEntry]:
        return sorted(
            self._store.rows.values(),
            key=lambda e: (
                e.source_document_number,
                e.source_document_line_number,
            ),
        )

    def by_state(self, state: LoadState) -> list[LoadStateEntry]:
        return [e for e in self.all() if e.state == state]
