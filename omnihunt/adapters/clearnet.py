"""Clearnet search engines."""
from __future__ import annotations

import re
from typing import List
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit

from bs4 import BeautifulSoup

from ..models import Result, unwrap_redirect
from ..net import FetchError
from .base import Adapter


def _ddg_target(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href:
        qs = parse_qs(urlsplit(href).query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return href


class DuckDuckGoAdapter(Adapter):
    kind = "web"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
        soup = BeautifulSoup(self.client.get(url, tag=self.name), "lxml")
        out: List[Result] = []
        for div in soup.select("div.result"):
            a = div.select_one("a.result__a")
            if a is None:
                continue
            target = _ddg_target(a.get("href", ""))
            if not target.startswith(("http://", "https://")):
                continue
            snip = div.select_one(".result__snippet")
            out.append(self._result(a.get_text(" ", strip=True), target, snip.get_text(" ") if snip else ""))
            if len(out) >= limit:
                break
        return out


class DuckDuckGoLiteAdapter(Adapter):
    """Fallback endpoint; survives when the HTML endpoint is rate-limited."""

    kind = "web"
    weight = 0.9

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://lite.duckduckgo.com/lite/?q=" + quote_plus(query)
        soup = BeautifulSoup(self.client.get(url, tag=self.name), "lxml")
        out: List[Result] = []
        rows = soup.select("table tr")
        pending: dict[str, str] = {}
        for tr in rows:
            link = tr.select_one("a.result-link")
            if link is not None:
                target = _ddg_target(link.get("href", ""))
                if target.startswith(("http://", "https://")):
                    pending[target] = link.get_text(" ", strip=True)
                continue
            td = tr.select_one("td.result-snippet")
            if td is not None and pending:
                target, title = pending.popitem()
                out.append(self._result(title, target, td.get_text(" ", strip=True)))
                if len(out) >= limit:
                    break
        for target, title in pending.items():
            if len(out) >= limit:
                break
            out.append(self._result(title, target))
        return out


class BingAdapter(Adapter):
    kind = "web"
    weight = 0.95

    def search(self, query: str, limit: int) -> List[Result]:
        url = (
            "https://www.bing.com/search?q=" + quote_plus(query)
            + "&count=30&setlang=en&mkt=en-US&ensearch=1"
        )
        soup = BeautifulSoup(self.client.get(url, tag=self.name), "lxml")
        out: List[Result] = []
        for li in soup.select("li.b_algo"):
            a = li.select_one("h2 a") or li.select_one("a")
            if a is None:
                continue
            target = unwrap_redirect(a.get("href", ""))
            if not target.startswith(("http://", "https://")):
                continue
            snip = li.select_one("p") or li.select_one(".b_caption")
            out.append(self._result(a.get_text(" ", strip=True), target, snip.get_text(" ") if snip else ""))
            if len(out) >= limit:
                break
        return out


class MojeekAdapter(Adapter):
    kind = "web"
    weight = 0.85

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://www.mojeek.com/search?q=" + quote_plus(query)
        page = self.client.get(url, tag=self.name)
        if "results-standard" not in page:
            raise FetchError("mojeek returned a JS challenge instead of results")
        soup = BeautifulSoup(page, "lxml")
        out: List[Result] = []
        for a in soup.select("ul.results-standard li a.title, ul.results-standard li h2 a"):
            target = a.get("href", "")
            if not target.startswith(("http://", "https://")):
                continue
            li = a.find_parent("li")
            snip = li.select_one("p.s") if li else None
            out.append(self._result(a.get_text(" ", strip=True), target, snip.get_text(" ") if snip else ""))
            if len(out) >= limit:
                break
        return out


class BaiduAdapter(Adapter):
    """baidu.com — the reachable default on mainland networks.

    The desktop endpoint now answers with a captcha page for cookie-less
    clients, so this adapter uses the mobile endpoint and falls back to the
    desktop one when the mobile page comes back without result nodes.
    """

    kind = "web"
    weight = 0.9

    ENDPOINTS = (
        "https://m.baidu.com/s?word={q}&sa=tb&ts=0",
        "https://www.baidu.com/s?wd={q}&rn=20&ie=utf-8",
    )

    def search(self, query: str, limit: int) -> List[Result]:
        if not getattr(self, "_primed", False):
            # One homepage hit per process buys the BAIDUID cookie that keeps the
            # search endpoint out of its captcha branch for a while.
            if not self.client.offline:
                try:
                    self.client.get("https://m.baidu.com/", tag=self.name)
                except FetchError:
                    pass
            self._primed = True

        q = quote_plus(query)
        last_error: Exception | None = None
        for template in self.ENDPOINTS:
            try:
                page = self.client.get(template.format(q=q), tag=self.name)
            except FetchError as exc:
                last_error = exc
                continue
            out = self._parse(page, limit)
            if out:
                return out
        if last_error is not None:
            raise last_error
        raise FetchError("baidu returned no parsable results (captcha or layout change)")

    def _parse(self, page: str, limit: int) -> List[Result]:
        soup = BeautifulSoup(page, "lxml")
        out: List[Result] = []
        seen: set[str] = set()
        for node in soup.select("div.result, div.result-op, div.c-container, div.c-result"):
            target = self._real_url(node)
            if not target or target in seen:
                continue
            host = (urlsplit(target).hostname or "").lower()
            if host.endswith("baidu.com"):
                continue  # internal recommendation cards, not results
            seen.add(target)
            heading = node.select_one("h3")
            title = heading.get_text(" ", strip=True) if heading else (node.get("aria-label") or target)
            snip = node.select_one(
                "div.c-abstract, .c-span-last, .content-right_8Zs40, [class*=abstract], [class*=summary]"
            )
            out.append(
                self._result(
                    title,
                    target,
                    snip.get_text(" ", strip=True) if snip else "",
                    source_site=host,
                )
            )
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _real_url(node) -> str:
        # Mobile results carry the destination in data-log JSON: {"mu": "https://..."}
        blob = node.get("data-log") or ""
        if blob:
            try:
                import json

                mu = json.loads(blob).get("mu")
                if isinstance(mu, str) and mu.startswith(("http://", "https://")):
                    return mu
            except ValueError:
                m = re.search(r'"mu"\s*:\s*"([^"]+)"', blob)
                if m:
                    return m.group(1)
        a = node.select_one("h3 a[mu]") or node.select_one("a[mu]")
        if a is not None:
            return a.get("mu", "")
        return ""


class So360Adapter(Adapter):
    """so.com (360 搜索) — second CN fallback when Baidu shows a captcha."""

    kind = "web"
    weight = 0.85

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://www.so.com/s?q=" + quote_plus(query)
        soup = BeautifulSoup(self.client.get(url, tag=self.name), "lxml")
        out: List[Result] = []
        seen: set[str] = set()
        for li in soup.select("li.res-list, li.result"):
            a = li.select_one("h3 a[data-mdurl], h3 a[href], a[data-mdurl]")
            if a is None:
                continue
            target = a.get("data-mdurl") or a.get("href") or ""
            if not target.startswith(("http://", "https://")) or target in seen:
                continue
            if (urlsplit(target).hostname or "").endswith("so.com"):
                continue  # unresolved redirect wrapper
            seen.add(target)
            desc = li.select_one(".res-desc, p.res-desc, p")
            out.append(
                self._result(
                    a.get_text(" ", strip=True),
                    target,
                    desc.get_text(" ", strip=True) if desc else "",
                )
            )
            if len(out) >= limit:
                break
        return out


class SearxNGAdapter(Adapter):
    """Any SearXNG instance with the JSON API enabled."""

    kind = "web"
    weight = 0.9

    def search(self, query: str, limit: int) -> List[Result]:
        base = str(self.spec.get("base", "")).rstrip("/")
        if not base:
            raise RuntimeError("searx engine needs 'base'")
        url = f"{base}/search?q={quote_plus(query)}&format=json&safesearch=0&language=all"
        payload = self.client.get_json(url, tag=self.name)
        out: List[Result] = []
        for item in (payload or {}).get("results", []):
            target = item.get("url") or ""
            if not target.startswith(("http://", "https://")):
                continue
            out.append(self._result(item.get("title", ""), target, item.get("content", "")))
            if len(out) >= limit:
                break
        return out
