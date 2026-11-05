"""Catalog adapters: turn a JSON catalog of sites into deep search links.

Two flavours share one implementation:
  * adult catalog  (kind: adult)
  * onion directory (kind: onion)
  * magnet indexes  (kind: torrent)
  * plain web engines (kind: web)

The result URL is the site's own search URL for the query, so the click lands
inside the target site with the query already applied. No page is fetched,
which keeps the adapter working when a site is JS-only or behind a login.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus

from ..models import Result
from .base import Adapter


class CatalogAdapter(Adapter):
    direct = True

    def _sites(self) -> List[Dict[str, Any]]:
        spec = self.spec
        sites = spec.get("sites")
        if sites:
            return list(sites)
        path = spec.get("catalog")
        if not path:
            return []
        target = Path(path)
        if not target.is_absolute():
            target = self.root / path
        if not target.exists():
            raise FileNotFoundError(f"catalog not found: {target}")
        data = json.loads(target.read_text(encoding="utf-8"))
        return list(data.get("sites", data if isinstance(data, list) else []))

    def search(self, query: str, limit: int) -> List[Result]:
        q = quote_plus(query)
        out: List[Result] = []
        max_sites = int(self.spec.get("max_sites", 40))
        for site in self._sites()[:max_sites]:
            if not site.get("enabled", True):
                continue
            template = site.get("search") or site.get("url") or ""
            if not template:
                continue
            url = template.replace("{q}", q)
            name = site.get("name") or template
            note = site.get("note") or ""
            kind = site.get("kind") or self.kind
            out.append(
                Result(
                    title=f"{name} · {query}",
                    url=url,
                    snippet=note,
                    source=f"{self.name}:{name}",
                    kind=kind,
                    weight=self.weight,
                    extra={
                        "direct": True,
                        "site": name,
                        "tags": site.get("tags", []),
                        "region": site.get("region", ""),
                        "onion": bool(site.get("onion")),
                    },
                )
            )
            if len(out) >= limit:
                break
        return out
