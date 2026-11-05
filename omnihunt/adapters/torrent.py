"""Torrent / magnet search adapters."""
from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ..models import Result
from .base import Adapter

BTIH_RE = re.compile(r"urn:btih:([A-Za-z0-9]{32,40})", re.I)


class NyaaAdapter(Adapter):
    """nyaa.si / sukebei.nyaa.si share one table layout."""

    kind = "torrent"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        url = self._search_url(query)
        soup = BeautifulSoup(self.client.get(url, tag=self.name), "lxml")
        out: List[Result] = []
        rows = soup.select("table.torrent-list tbody tr") or soup.select("table tbody tr")
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            link = tr.select_one("a[href^='/view/']") or tr.select_one("td:nth-of-type(2) a")
            magnet = tr.select_one("a[href^='magnet:']")
            if link is None:
                continue
            title = link.get_text(" ", strip=True)
            view = link.get("href", "")
            if view.startswith("/"):
                view = self.spec.get("base", "https://nyaa.si").rstrip("/") + view
            magnet_url = magnet.get("href", "") if magnet else ""
            size = tds[3].get_text(" ", strip=True) if len(tds) > 3 else ""
            seeds = tds[5].get_text(" ", strip=True) if len(tds) > 5 else ""
            target = magnet_url or view
            if not target:
                continue
            m = BTIH_RE.search(magnet_url)
            out.append(
                self._result(
                    title,
                    target,
                    f"size={size} seeds={seeds}".strip(),
                    magnet=magnet_url,
                    view=view,
                    btih=m.group(1) if m else "",
                )
            )
            if len(out) >= limit:
                break
        return out


class MagnetPageAdapter(Adapter):
    """Generic magnet harvester: regex the page, group by btih.

    ``item`` splits the page, ``title`` names the row, and any magnet link is
    attached. Works for most DHT index front-ends.
    """

    kind = "torrent"
    weight = 0.8

    def search(self, query: str, limit: int) -> List[Result]:
        url = self._search_url(query)
        page = self.client.get(url, tag=self.name, via=self.via)
        item_pat = self.spec.get("item")
        blocks = re.split(item_pat, page, flags=re.S | re.I) if item_pat else [page]
        title_re = re.compile(self.spec.get("title") or r"<h3[^>]*>(.*?)</h3>", re.S | re.I)
        out: List[Result] = []
        seen: set[str] = set()
        for block in blocks:
            m = re.search(r'href="(magnet:\?[^"]+)"', block, re.I)
            if not m:
                continue
            magnet = m.group(1)
            btih = BTIH_RE.search(magnet)
            if btih and btih.group(1).lower() in seen:
                continue
            if btih:
                seen.add(btih.group(1).lower())
            tm = title_re.search(block)
            title = (tm.group(1) if tm else "").strip()
            title = re.sub(r"<[^>]+>", " ", title)
            title = re.sub(r"\s+", " ", title).strip() or (btih.group(1) if btih else magnet[:60])
            out.append(self._result(title, magnet, "", magnet=magnet, btih=btih.group(1) if btih else ""))
            if len(out) >= limit:
                break
        return out
