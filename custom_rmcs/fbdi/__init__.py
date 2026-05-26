"""FBDI (file-based data import) emitter for RMCS.

This package projects canonical `RMCSSourceDocument` / `RMCSAdjustmentDocument`
objects onto the columnar CSV schema expected by the RMCS *Import Customer
Contract Source Data* FBDI template, then packages them into a ZIP that OIC
uploads to UCM.
"""

from .package import write_fbdi_package
from .schema import (
    SOURCE_DOCUMENTS_COLUMNS,
    SOURCE_DOC_LINES_COLUMNS,
    SOURCE_DOC_SUB_LINES_COLUMNS,
)

__all__ = [
    "write_fbdi_package",
    "SOURCE_DOCUMENTS_COLUMNS",
    "SOURCE_DOC_LINES_COLUMNS",
    "SOURCE_DOC_SUB_LINES_COLUMNS",
]
