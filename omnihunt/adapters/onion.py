"""Darknet index adapters (clearnet mirrors + .onion endpoints)."""
from __future__ import annotations

from typing import List

from bs4 import BeautifulSoup

from ..models import Result
from ..net import FetchError
from .base import Adapter


class AhmiaAdapter(Adapter):
    """ahmia.fi indexes .onion services; reachable from clearnet."""

    kind = "onion"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        url = self._search_url(query)
        page = self.client.get(url, tag=self.name)
        soup = BeautifulSoup(page, "lxml")
        out: List[Result] = []
        nodes = soup.select("li.result") or soup.select("div.result")
        for li in nodes:
            a = li.select_one("h4 a") or li.select_one("a[href]")
            if a is None:
                continue
            target = a.get("href", "")
            if not target.startswith(("http://", "https://")):
                continue
            p = li.select_one("p")
            out.append(self._result(a.get_text(" ", strip=True), target, p.get_text(" ") if p else "", onion=True))
            if len(out) >= limit:
                break
        if not out and "li.result" not in page and "No results" not in page:
            # Ahmia redirects /search/ to the homepage when the endpoint is
            # rate-limited or disabled; surface it instead of "0 results".
            raise FetchError("ahmia returned no result markup (search endpoint unavailable or rate-limited)")
        return out


class OnionSearchEngineAdapter(Adapter):
    """onionsearchengine.com — a clearnet front-end with live .onion results.

    Markup: ``ul.results-list > li.result-item > h3.result-title > a[href]``
    plus ``p.result-snippet``.
    """

    kind = "onion"
    weight = 0.95

    def search(self, query: str, limit: int) -> List[Result]:
        url = self._search_url(query)
        page = self.client.get(url, tag=self.name)
        soup = BeautifulSoup(page, "lxml")
        out: List[Result] = []
        seen: set[str] = set()
        for li in soup.select("li.result-item, li.result"):
            a = li.select_one("h3.result-title a[href], h3 a[href], a[href]")
            if a is None:
                continue
            target = a.get("href", "").strip()
            if not target.startswith(("http://", "https://")) or target in seen:
                continue
            seen.add(target)
            snip = li.select_one("p.result-snippet, .result-snippet, p")
            snippet = snip.get_text(" ", strip=True) if snip else ""
            host = (target.split("//", 1)[-1].split("/", 1)[0] or "").lower()
            if snippet.strip().lower() in {host, target.lower(), host.rstrip(".")}:
                snippet = ""  # the index repeats the domain as "snippet"
            out.append(
                self._result(
                    a.get_text(" ", strip=True),
                    target,
                    snippet,
                    onion=".onion" in target,
                    live_index=True,
                )
            )
            if len(out) >= limit:
                break
        if not out:
            # A real "0 hits" page still contains the results container; a block
            # page or a layout change does not. Chinese queries routinely hit 0.
            if ("results-container" in page or "results-list" in page or "No results" in page):
                return []
            raise FetchError("onionsearchengine returned no result markup (layout change or block page)")
        return out


class OnionIndexAdapter(Adapter):
    """Config-driven index page for .onion search engines.

    Supports two layouts without code changes:
      * ``json``: {"results": [{title,url,snippet}]}
      * HTML: uses ``item`` / ``link`` / ``title`` / ``snippet`` CSS selectors.
    """

    kind = "onion"
    weight = 0.9

    def search(self, query: str, limit: int) -> List[Result]:
        url = self._search_url(query)
        if self.spec.get("format") == "json":
            payload = self.client.get_json(url, tag=self.name, via=self.via)
            out = []
            for item in (payload or {}).get("results", []):
                target = item.get("url") or item.get("link") or ""
                if not target.startswith(("http://", "https://")):
                    continue
                out.append(self._result(item.get("title", ""), target, item.get("snippet", item.get("content", "")), onion=True))
                if len(out) >= limit:
                    break
            return out

        soup = BeautifulSoup(self.client.get(url, tag=self.name, via=self.via), "lxml")
        item_sel = self.spec.get("item") or "li"
        link_sel = self.spec.get("link") or "a[href]"
        title_sel = self.spec.get("title")
        snippet_sel = self.spec.get("snippet")
        out: List[Result] = []
        for node in soup.select(item_sel):
            a = node.select_one(link_sel)
            if a is None or not a.get("href"):
                continue
            target = a.get("href", "")
            if not target.startswith(("http://", "https://")):
                continue
            title_node = node.select_one(title_sel) if title_sel else a
            snip_node = node.select_one(snippet_sel) if snippet_sel else None
            out.append(
                self._result(
                    title_node.get_text(" ", strip=True) if title_node else "",
                    target,
                    snip_node.get_text(" ", strip=True) if snip_node else "",
                    onion=True,
                )
            )
            if len(out) >= limit:
                break
        return out
