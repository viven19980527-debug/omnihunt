"""暗面适配器：真正抓内容，而不只是给跳转链接。

- Nyaa / Sukebei RSS：直接拿 magnet + 体积 + 做种数（普通引擎搜不到）
- Booru JSON API：rule34 / danbooru / e621 / gelbooru，直接出图
- JavBus / MissAV：番号站搜索页 HTML，出封面 + 标题
- Ahmia clearnet 索引：.onion 结果（无需 Tor）
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.parse import quote, quote_plus

from bs4 import BeautifulSoup

from ..models import Result
from .base import Adapter, absolutize, clean_text

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15")


class _Net:
    def _get(self, url: str, headers: Dict[str, str] | None = None) -> str:
        h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
        if headers:
            h.update(headers)
        try:
            return self.client.get(url, tag=self.name, headers=h)
        except TypeError:
            return self.client.get(url, tag=self.name)


# ---------------------------------------------------------------- 磁力（RSS）

class NyaaRSSAdapter(_Net, Adapter):
    """nyaa.si / sukebei RSS：真实 magnet，含体积与做种数。"""

    kind = "torrent"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        base = str(self.spec.get("base") or "https://nyaa.si")
        url = f"{base}/?page=rss&c=0_0&f=0&q={quote_plus(query)}"
        xml = self._get(url)
        out: List[Result] = []
        for item in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]:
            def pick(tag: str) -> str:
                m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", item, re.S)
                return clean_text(m.group(1), 400) if m else ""
            title = pick("title")
            magnet = ""
            m = re.search(r'(magnet:\?xt=urn:btih:[^"<\s]+)', item)
            if m:
                magnet = m.group(1)
            link = pick("link")
            size = pick("nyaa:size")
            seeders = pick("nyaa:seeders")
            out.append(self._result(
                title or "torrent", link or magnet, f"{size} · 做种 {seeders}",
                magnet=magnet, size=size, seeders=seeders,
                page=link,
            ))
        return out


class SukebeiRSSAdapter(NyaaRSSAdapter):
    """sukebei：成人向磁力索引。"""

    kind = "torrent"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        base = str(self.spec.get("base") or "https://sukebei.nyaa.si")
        url = f"{base}/?page=rss&c=0_0&f=0&q={quote_plus(query)}"
        xml = self._get(url)
        out: List[Result] = []
        for item in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]:
            def pick(tag: str) -> str:
                m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", item, re.S)
                return clean_text(m.group(1), 400) if m else ""
            m = re.search(r'(magnet:\?xt=urn:btih:[^"<\s]+)', item)
            out.append(self._result(
                pick("title") or "torrent", pick("link") or (m.group(1) if m else ""),
                f"{pick('nyaa:size')} · 做种 {pick('nyaa:seeders')}",
                magnet=(m.group(1) if m else ""), size=pick("nyaa:size"),
                seeders=pick("nyaa:seeders"), page=pick("link"),
            ))
        return out


# ---------------------------------------------------------------- Booru 图站

class BooruAdapter(_Net, Adapter):
    """rule34 / danbooru / e621 / gelbooru：JSON API 直接出图。"""

    kind = "image"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        api = str(self.spec.get("api") or "").strip()
        tags = quote_plus(query.replace(" ", "_"))
        url = api.replace("{q}", tags).replace("{limit}", str(min(limit, 20)))
        raw = self._get(url)
        try:
            data = json.loads(raw)
        except Exception:
            return []

        posts: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            posts = data.get("post") or data.get("posts") or []
        elif isinstance(data, list):
            posts = data

        out: List[Result] = []
        for p in posts[:limit]:
            if not isinstance(p, dict):
                continue
            file_url = (p.get("file_url") or p.get("large_file_url")
                        or p.get("sample_url") or p.get("url")
                        or (p.get("file") or {}).get("url") or "")
            thumb = (p.get("preview_url") or p.get("sample_url")
                     or p.get("preview_file_url") or file_url)
            page = p.get("post_url") or p.get("page_url") or ""
            if page and page.startswith("/"):
                page = "https://" + (self.spec.get("host") or "danbooru.donmai.us") + page
            title = (p.get("tag_string") or p.get("tags") or "").split(" ")[:6]
            title_text = " ".join(title) if isinstance(title, list) else str(title)[:60]
            if not file_url and not thumb:
                continue
            out.append(self._result(
                title_text or "图片",
                page or file_url or thumb,
                "", thumb=thumb, full=file_url,
                width=p.get("image_width") or p.get("width"),
                height=p.get("image_height") or p.get("height"),
                score=p.get("score"),
            ))
        return out


# ---------------------------------------------------------------- 番号站

class JavPageAdapter(_Net, Adapter):
    """JavBus / MissAV 搜索页：封面 + 番号 + 标题。"""

    kind = "video"
    weight = 0.95

    def search(self, query: str, limit: int) -> List[Result]:
        template = str(self.spec.get("search") or "https://www.javbus.com/search/{q}")
        url = template.replace("{q}", quote(query))
        host = str(self.spec.get("host") or "https://www.javbus.com")
        soup = BeautifulSoup(self._get(url), "lxml")
        out: List[Result] = []
        for a in soup.select("a.movie-box, a[href*='/'], .grid-item a, .thumbnail group a"):
            href = absolutize(host, a.get("href", ""))
            if not href.startswith("http"):
                continue
            img = a.select_one("img")
            thumb = ""
            if img is not None:
                thumb = img.get("src") or img.get("data-src") or ""
                if thumb.startswith("//"):
                    thumb = "https:" + thumb
            date = a.select_one(".meta, .date, date")
            title = (img.get("title") if img is not None else "") or a.get_text(" ", strip=True)
            out.append(self._result(
                str(title)[:120], href,
                date.get_text(" ", strip=True) if date is not None else "",
                thumb=thumb,
            ))
            if len(out) >= limit:
                break
        return out


# ---------------------------------------------------------------- 暗网（clearnet 索引）

class AhmiaClearnetAdapter(_Net, Adapter):
    """ahmia.fi 的 clearnet 端点：直接返回 .onion 结果，不需要 Tor。"""

    kind = "onion"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://ahmia.fi/search/?q=" + quote_plus(query)
        soup = BeautifulSoup(self._get(url), "lxml")
        out: List[Result] = []
        for li in soup.select("li.result, ol.searchResults li"):
            a = li.select_one("h4 a, a[href*='.onion']")
            if a is None:
                continue
            href = a.get("href", "")
            if href.startswith("/"):
                href = "https://ahmia.fi" + href
            desc = li.select_one("p, .description")
            out.append(self._result(
                a.get_text(" ", strip=True), href,
                desc.get_text(" ", strip=True) if desc is not None else "",
            ))
            if len(out) >= limit:
                break
        return out
