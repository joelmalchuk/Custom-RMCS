"""Abstract feeder interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from ..models import ARCreditMemo, ARInvoice, OMOrder


class OMFeeder(ABC):
    """Reads OM orders (with their price components) from an OIC extract."""

    @abstractmethod
    def orders(self) -> Iterable[OMOrder]:
        """Yield each OM order in the extract."""


class ARFeeder(ABC):
    """Reads AR invoices and credit memos from an OIC extract."""

    @abstractmethod
    def invoices(self) -> Iterable[ARInvoice]:
        ...

    @abstractmethod
    def credit_memos(self) -> Iterable[ARCreditMemo]:
        ...
