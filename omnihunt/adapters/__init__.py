"""Adapter registry."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..net import Client
from .base import Adapter, absolutize, clean_text
from .catalog import CatalogAdapter
from .clearnet import (
    BaiduAdapter,
    BingAdapter,
    DuckDuckGoAdapter,
    DuckDuckGoLiteAdapter,
    MojeekAdapter,
    SearxNGAdapter,
    So360Adapter,
)
from .onion import AhmiaAdapter, OnionIndexAdapter, OnionSearchEngineAdapter
from .regex import RegexAdapter
from .torrent import MagnetPageAdapter, NyaaAdapter

ADAPTER_TYPES = {
    "duckduckgo": DuckDuckGoAdapter,
    "ddg_lite": DuckDuckGoLiteAdapter,
    "bing": BingAdapter,
    "baidu": BaiduAdapter,
    "so360": So360Adapter,
    "mojeek": MojeekAdapter,
    "searx": SearxNGAdapter,
    "ahmia": AhmiaAdapter,
    "onionsearchengine": OnionSearchEngineAdapter,
    "onion_index": OnionIndexAdapter,
    "regex": RegexAdapter,
    "catalog": CatalogAdapter,
    "nyaa": NyaaAdapter,
    "magnet": MagnetPageAdapter,
}

__all__ = [
    "ADAPTER_TYPES",
    "Adapter",
    "build_adapters",
    "absolutize",
    "clean_text",
]


def build_adapters(specs: List[Dict[str, Any]], client: Client, root: Path) -> List[Adapter]:
    adapters: List[Adapter] = []
    for spec in specs or []:
        if not spec.get("enabled", True):
            continue
        kind = str(spec.get("type") or "").strip().lower()
        cls = ADAPTER_TYPES.get(kind)
        if cls is None:
            raise ValueError(f"unknown engine type: {kind!r} (engine {spec.get('name')!r})")
        adapters.append(cls(spec, client, root))
    return adapters
