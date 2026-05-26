"""Load-state journal.

Records *only* what this integration did with each emitted RMCS source
document: when it was emitted, the result of the FBDI ESS job, and any
error text. This is the operational store -- it is **not** the system of
record for the OM <-> AR <-> RMCS relationship (that lives on the AR
invoice / credit-memo DFFs populated by the OM -> AR Autoinvoice flow).

Keeping the journal narrow has two functional benefits:

1. There is no custom store that can drift from AR; AR is unambiguously
   the system of record for the business relationship.
2. The journal is what feeds the daily AR-vs-RMCS reconciliation report
   and the period-close exception list, and nothing else.
"""

from .journal import (
    JSONLoadStateJournal,
    LoadState,
    LoadStateEntry,
    LoadStateJournal,
)

__all__ = [
    "JSONLoadStateJournal",
    "LoadState",
    "LoadStateEntry",
    "LoadStateJournal",
]
