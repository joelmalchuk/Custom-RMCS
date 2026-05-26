"""RMA / credit-memo handling.

Translates AR credit memos into RMCS adjustment documents that reference
the original performance obligation (i.e. the OM line), regardless of which
price-component AR line the credit was actually issued against.
"""

from .builder import build_adjustments

__all__ = ["build_adjustments"]
