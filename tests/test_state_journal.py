"""LoadStateJournal lifecycle tests."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from custom_rmcs.state import (
    JSONLoadStateJournal,
    LoadState,
    LoadStateEntry,
)


def _journal(tmp_path: Path) -> JSONLoadStateJournal:
    return JSONLoadStateJournal(tmp_path / "state.json")


def test_record_emitted_starts_pending(tmp_path):
    j = _journal(tmp_path)
    j.record_emitted(
        source_document_number="SD-OM-1",
        source_document_line_number="REV-OM-1-1",
        om_order_number="OM-1",
        om_line_number="1",
        run_id="RUN-A",
    )
    entry = j.get("SD-OM-1", "REV-OM-1-1")
    assert entry is not None
    assert entry.state == LoadState.PENDING
    assert entry.last_run_id == "RUN-A"


def test_load_result_transitions_pending_to_loaded(tmp_path):
    j = _journal(tmp_path)
    j.record_emitted("SD-OM-1", "REV-OM-1-1", "OM-1", "1", "RUN-A")
    when = datetime(2026, 5, 26, 18, 0, tzinfo=timezone.utc)
    j.record_load_result(
        "SD-OM-1", "REV-OM-1-1",
        state=LoadState.LOADED, run_id="RUN-A", loaded_at=when,
    )
    entry = j.get("SD-OM-1", "REV-OM-1-1")
    assert entry.state == LoadState.LOADED
    assert entry.loaded_at == when.isoformat()


def test_re_emit_preserves_loaded(tmp_path):
    """A subsequent run must not regress LOADED entries to PENDING."""
    j = _journal(tmp_path)
    j.record_emitted("SD-OM-1", "REV-OM-1-1", "OM-1", "1", "RUN-A")
    j.record_load_result(
        "SD-OM-1", "REV-OM-1-1",
        state=LoadState.LOADED, run_id="RUN-A",
        loaded_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )
    j.record_emitted("SD-OM-1", "REV-OM-1-1", "OM-1", "1", "RUN-B")
    entry = j.get("SD-OM-1", "REV-OM-1-1")
    assert entry.state == LoadState.LOADED
    assert entry.last_run_id == "RUN-A"  # untouched


def test_re_emit_resets_rejected_to_pending(tmp_path):
    j = _journal(tmp_path)
    j.record_emitted("SD-OM-1", "REV-OM-1-1", "OM-1", "1", "RUN-A")
    j.record_load_result(
        "SD-OM-1", "REV-OM-1-1",
        state=LoadState.REJECTED, run_id="RUN-A",
        error="VRM-12345: missing customer",
    )
    j.record_emitted("SD-OM-1", "REV-OM-1-1", "OM-1", "1", "RUN-B")
    entry = j.get("SD-OM-1", "REV-OM-1-1")
    assert entry.state == LoadState.PENDING
    assert entry.last_run_id == "RUN-B"


def test_load_result_on_unknown_entry_raises(tmp_path):
    j = _journal(tmp_path)
    with pytest.raises(KeyError):
        j.record_load_result(
            "SD-NONE", "REV-NONE",
            state=LoadState.LOADED, run_id="RUN-A",
        )


def test_by_state_filters_correctly(tmp_path):
    j = _journal(tmp_path)
    j.record_emitted("SD-OM-1", "REV-OM-1-1", "OM-1", "1", "RUN-A")
    j.record_emitted("SD-OM-2", "REV-OM-2-1", "OM-2", "1", "RUN-A")
    j.record_load_result(
        "SD-OM-1", "REV-OM-1-1",
        state=LoadState.LOADED, run_id="RUN-A",
        loaded_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )
    pending = j.by_state(LoadState.PENDING)
    loaded = j.by_state(LoadState.LOADED)
    assert {e.source_document_number for e in pending} == {"SD-OM-2"}
    assert {e.source_document_number for e in loaded} == {"SD-OM-1"}


def test_journal_persists_across_instances(tmp_path):
    path = tmp_path / "state.json"
    j1 = JSONLoadStateJournal(path)
    j1.record_emitted("SD-OM-1", "REV-OM-1-1", "OM-1", "1", "RUN-A")
    j2 = JSONLoadStateJournal(path)
    assert j2.get("SD-OM-1", "REV-OM-1-1") is not None
