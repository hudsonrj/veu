"""Nervos externos do Véu — apps, MCPs, APIs e workspaces."""

from __future__ import annotations

from .notion import NotionAdapter
from .openrag import OpenRAGAdapter
from .registry import Connector, ConnectorKind, Registry, default_registry

__all__ = [
    "Connector",
    "ConnectorKind",
    "Registry",
    "default_registry",
    "NotionAdapter",
    "OpenRAGAdapter",
]
