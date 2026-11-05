"""Config-driven regex adapter: any site, zero code.

Config example (config/engines.yaml)::

  - name: my_index
    type: regex
    kind: onion
    base: http://INDEX_HOST
    path: "/search?q={q}"
    via: tor
    item: '<li class="res">'
    link: '<a[^>]+href="([^"]+)"'
    title: '<a[^>]*>(.*?)</a>'
    snippet: '<p[^>]*>(.*?)</p>'
"""
from __future__ import annotations

import html as html_mod
import re
from typing import List

from ..models import Result
from ..net import FetchError
from .base import Adapter, absolutize, clean_text


class RegexAdapter(Adapter):
    def search(self, query: str, limit: int) -> List[Result]:
        url = self._search_url(query)
        page = self.client.get(url, tag=self.name, via=self.via)

        link_re = re.compile(self.spec.get("link") or r'href="([^"]+)"', re.S | re.I)
        title_re = re.compile(self.spec.get("title") or r">([^<]{2,200})<", re.S | re.I)
        snip_re = re.compile(self.spec["snippet"], re.S | re.I) if self.spec.get("snippet") else None
        item_pat = self.spec.get("item")
        blocks = re.split(item_pat, page, flags=re.S | re.I) if item_pat else [page]

        out: List[Result] = []
        seen: set[str] = set()
        for block in blocks:
            m = link_re.search(block)
            if not m:
                continue
            target = absolutize(url, m.group(1))
            if not target.startswith(("http://", "https://")) or target in seen:
                continue
            seen.add(target)
            tm = title_re.search(block)
            title = clean_text(tm.group(1), 200) if tm else ""
            sm = snip_re.search(block) if snip_re else None
            snippet = clean_text(sm.group(1), 400) if sm else ""
            if not title:
                title = target
            out.append(self._result(title, target, snippet))
            if len(out) >= limit:
                break
        return out
