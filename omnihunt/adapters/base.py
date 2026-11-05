"""Adapter base class and shared helpers."""
from __future__ import annotations

import html as html_mod
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus, urljoin

from ..models import Result
from ..net import Client

TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value: str, limit: int = 400) -> str:
    if not value:
        return ""
    value = TAG_RE.sub(" ", str(value))
    value = html_mod.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def absolutize(base: str, href: str) -> str:
    if not href:
        return ""
    href = html_mod.unescape(href.strip())
    if href.startswith(("javascript:", "data:", "#", "mailto:")):
        return ""
    if href.startswith("//"):
        return "https:" + href
    if base and href.startswith("/"):
        return urljoin(base, href)
    if base and not re.match(r"^[a-z][a-z0-9+.\-]*://", href, re.I):
        return urljoin(base, href)
    return href


class Adapter:
    kind = "web"
    weight = 1.0
    direct = False  # True => catalog/deep-link adapter (no page fetch)

    def __init__(self, spec: Dict[str, Any], client: Client, root: Path) -> None:
        self.spec = spec or {}
        self.name = str(self.spec.get("name") or self.__class__.__name__.lower())
        self.client = client
        self.root = root
        self.kind = str(self.spec.get("kind") or self.kind)
        self.weight = float(self.spec.get("weight", self.weight))
        self.limit = int(self.spec.get("per_engine", 10))
        self.via = str(self.spec.get("via") or "clearnet")

    # ------------------------------------------------------------------ helpers
    def _search_url(self, query: str) -> str:
        base = str(self.spec.get("base", "")).rstrip("/")
        path = str(self.spec.get("path") or "/search?q={q}")
        return base + path.replace("{q}", quote_plus(query))

    def _result(self, title: str, url: str, snippet: str = "", **extra: Any) -> Result:
        return Result(
            title=clean_text(title, 300),
            url=url,
            snippet=clean_text(snippet, 500),
            source=self.name,
            kind=self.kind,
            weight=self.weight,
            extra=extra,
        )

    # -------------------------------------------------------------------- API
    def search(self, query: str, limit: int) -> List[Result]:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "weight": self.weight,
            "via": self.via,
            "direct": self.direct,
            "enabled": bool(self.spec.get("enabled", True)),
        }
