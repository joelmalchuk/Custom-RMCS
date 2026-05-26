"""Feeder adapters.

Feeders are thin readers that turn an OIC-staged extract into canonical
models. The abstract interfaces let us swap the transport (JSON files on
disk, an HTTP POST body, a DB table) without touching the rest of the
pipeline.
"""

from .base import OMFeeder, ARFeeder
from .json_feeder import JSONFileOMFeeder, JSONFileARFeeder

__all__ = [
    "OMFeeder",
    "ARFeeder",
    "JSONFileOMFeeder",
    "JSONFileARFeeder",
]
