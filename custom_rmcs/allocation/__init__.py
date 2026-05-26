"""Externally managed SSP catalog + discount allocation.

This package implements the *relative SSP* allocation method used by ASC 606 /
IFRS 15 revenue recognition. RMCS would normally do this on its own, but
because the OM price-component split obscures the list price, we run it here
and feed RMCS pre-allocated amounts.
"""

from .ssp_catalog import SSPCatalog, JSONFileSSPCatalog, StaticSSPCatalog
from .allocator import allocate, collapse_to_revenue_lines

__all__ = [
    "SSPCatalog",
    "JSONFileSSPCatalog",
    "StaticSSPCatalog",
    "allocate",
    "collapse_to_revenue_lines",
]
