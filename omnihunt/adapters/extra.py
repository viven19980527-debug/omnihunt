"""按需扩展的搜索引擎适配器：更多引擎 + 图片/视频垂类（无广告、无跳转）。

设计原则：
- 只用「无广告/无弹窗」的端点：官方 HTML 结果页、公开 JSON API。
- 返回 Result(kind="web"/"image"/"video")，iOS 端按 kind 分栏展示。
- 图片/视频给 extra 带上缩略图与时长，App 内直接看，不跳外站。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.parse import quote, quote_plus, unquote, urlsplit, parse_qs

from bs4 import BeautifulSoup

from ..models import Result
from html import unescape as html_unescape
from .base import Adapter, absolutize, clean_text

UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
UA_DESKTOP = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


class _HeadersMixin:
    """部分引擎必须带浏览器 UA / Accept-Language 才不返回挑战页。"""

    headers: Dict[str, str] = {}

    def _get(self, url: str) -> str:
        try:
            return self.client.get(url, tag=self.name, headers=self.headers)
        except TypeError:
            return self.client.get(url, tag=self.name)


# ---------------------------------------------------------------- 通用 HTML 引擎

class YandexAdapter(_HeadersMixin, Adapter):
    kind = "web"
    weight = 0.95

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://yandex.com/search/?text=" + quote_plus(query) + "&lr=87"
        soup = _soup(self._get(url))
        out: List[Result] = []
        for li in soup.select("li.serp-item, .serp-item"):
            a = li.select_one("a.OrganicTitle-Link, a.Link_theme_normal, h2 a")
            if not a:
                continue
            href = absolutize("https://yandex.com", a.get("href", ""))
            if not href.startswith("http"):
                continue
            snip = li.select_one(".Organic-ContentWrapper, .TextContainer")
            out.append(self._result(a.get_text(" ", strip=True), href,
                                    snip.get_text(" ", strip=True) if snip else ""))
            if len(out) >= limit:
                break
        return out


class BraveAdapter(_HeadersMixin, Adapter):
    kind = "web"
    weight = 0.9

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://search.brave.com/search?q=" + quote_plus(query) + "&source=web"
        soup = _soup(self._get(url))
        out: List[Result] = []
        for block in soup.select("div.snippet, .snippet[data-type='web']"):
            a = block.select_one("a[href^='http']")
            if not a:
                continue
            snip = block.select_one(".snippet-description, .snippet-content")
            out.append(self._result(a.get_text(" ", strip=True), a["href"],
                                    snip.get_text(" ", strip=True) if snip else ""))
            if len(out) >= limit:
                break
        return out


class StartpageAdapter(_HeadersMixin, Adapter):
    kind = "web"
    weight = 0.85

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://www.startpage.com/sp/search?query=" + quote_plus(query)
        soup = _soup(self._get(url))
        out: List[Result] = []
        for li in soup.select(".w-gl__result, .result"):
            a = li.select_one("a.w-gl__result-title, a.result-link, a[href^='http']")
            if not a:
                continue
            snip = li.select_one(".w-gl__description, .description")
            out.append(self._result(a.get_text(" ", strip=True), a.get("href", ""),
                                    snip.get_text(" ", strip=True) if snip else ""))
            if len(out) >= limit:
                break
        return out


class EcosiaAdapter(_HeadersMixin, Adapter):
    kind = "web"
    weight = 0.8

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://www.ecosia.org/search?q=" + quote_plus(query)
        soup = _soup(self._get(url))
        out: List[Result] = []
        for art in soup.select("article.result, .result"):
            a = art.select_one("a.result__link, h2 a, a[href^='http']")
            if not a:
                continue
            snip = art.select_one(".result__description, p")
            out.append(self._result(a.get_text(" ", strip=True), a.get("href", ""),
                                    snip.get_text(" ", strip=True) if snip else ""))
            if len(out) >= limit:
                break
        return out


class SogouAdapter(_HeadersMixin, Adapter):
    kind = "web"
    weight = 0.8

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://www.sogou.com/web?query=" + quote_plus(query)
        soup = _soup(self._get(url))
        out: List[Result] = []
        for div in soup.select("div.vrwrap, div.rb"):
            a = div.select_one("h3 a")
            if not a:
                continue
            href = a.get("href", "")
            # sogou 的跳转链接：/link?url=...
            if href.startswith("/"):
                href = "https://www.sogou.com" + href
            snip = div.select_one(".str-text-info, .space-txt, .ft")
            out.append(self._result(a.get_text(" ", strip=True), href,
                                    snip.get_text(" ", strip=True) if snip else ""))
            if len(out) >= limit:
                break
        return out


class MarginaliaAdapter(_HeadersMixin, Adapter):
    kind = "web"
    weight = 0.7

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://search.marginalia.nu/search?query=" + quote_plus(query)
        soup = _soup(self._get(url))
        out: List[Result] = []
        for a in soup.select("a[href^='http']"):
            href = a.get("href", "")
            title = a.get_text(" ", strip=True)
            if len(title) < 6:
                continue
            out.append(self._result(title, href))
            if len(out) >= limit:
                break
        return out


class SearxPoolAdapter(_HeadersMixin, Adapter):
    """多个公共 SearXNG 实例轮询，任一可用即返回。"""

    kind = "web"
    weight = 1.0

    DEFAULT_POOL = [
        "https://searx.be", "https://search.bus-hit.me", "https://searx.tiekoetter.com",
        "https://opnxng.com", "https://priv.au", "https://search.inetol.net",
    ]

    def search(self, query: str, limit: int) -> List[Result]:
        pool = self.spec.get("pool") or self.DEFAULT_POOL
        for base in pool:
            try:
                url = f"{base.rstrip('/')}/search?q={quote_plus(query)}&format=json"
                raw = self._get(url)
                data = json.loads(raw)
                out: List[Result] = []
                for item in (data.get("results") or [])[:limit]:
                    out.append(self._result(item.get("title", ""), item.get("url", ""),
                                            item.get("content", "")))
                if out:
                    return out
            except Exception:
                continue
        return []


# ---------------------------------------------------------------- 图片垂类

class OpenverseAdapter(_HeadersMixin, Adapter):
    """Openverse（原 CC Search）：免费开放 API，无 key，无广告。"""

    kind = "image"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        url = ("https://api.openverse.org/v1/images/?q=" + quote_plus(query)
               + f"&page_size={min(limit, 20)}")
        data = json.loads(self._get(url))
        out: List[Result] = []
        for it in (data.get("results") or [])[:limit]:
            out.append(self._result(
                it.get("title") or "图片",
                it.get("foreign_landing_url") or it.get("url", ""),
                ", ".join(filter(None, [it.get("creator"), it.get("license")])),
                thumb=it.get("thumbnail") or it.get("url", ""),
                full=it.get("url", ""),
                width=it.get("width"), height=it.get("height"),
            ))
        return out


class WikimediaAdapter(_HeadersMixin, Adapter):
    """维基共享资源：图片/视频，公开 API。"""

    kind = "image"
    weight = 0.9

    def search(self, query: str, limit: int) -> List[Result]:
        url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
               "&generator=search&gsrsearch=" + quote_plus(query)
               + f"&gsrlimit={min(limit, 20)}&gsrnamespace=6"
               "&prop=imageinfo&iiprop=url|size|mime&iiurlwidth=480")
        data = json.loads(self._get(url))
        pages = ((data.get("query") or {}).get("pages") or {})
        out: List[Result] = []
        for p in pages.values():
            info = (p.get("imageinfo") or [{}])[0]
            mime = info.get("mime", "")
            kind = "video" if mime.startswith("video") else "image"
            out.append(self._result(
                p.get("title", "").replace("File:", ""),
                info.get("descriptionurl", ""), mime,
                thumb=info.get("thumburl", ""), full=info.get("url", ""),
                width=info.get("width"), height=info.get("height"), kind_hint=kind,
            ))
        return out


class BingImagesAdapter(_HeadersMixin, Adapter):
    """Bing 图片：结果页里内嵌 m JSON，直接解析，App 内看缩略图。"""

    kind = "image"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        url = ("https://www.bing.com/images/search?q=" + quote_plus(query)
               + "&form=HDRSC2&first=1")
        html = self._get(url)
        out: List[Result] = []
        for m in re.finditer(r'm="(\{[^"]{20,4000}\})"', html):
            try:
                meta = json.loads(m.group(1).replace("&quot;", '"'))
            except Exception:
                continue
            murl = meta.get("murl", "")
            if not murl:
                continue
            out.append(self._result(
                meta.get("t", "") or "图片", meta.get("purl") or murl,
                meta.get("t", ""),
                thumb=html_unescape(meta.get("turl", "")), full=murl,
                width=meta.get("mw"), height=meta.get("mh"),
            ))
            if len(out) >= limit:
                break
        return out


class YandexImagesAdapter(_HeadersMixin, Adapter):
    kind = "image"
    weight = 0.9

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://yandex.com/images/search?text=" + quote_plus(query)
        html = self._get(url)
        out: List[Result] = []
        for m in re.finditer(r'"origUrl":"(.*?)".*?"thumb":\{"url":"(.*?)"', html):
            full = m.group(1).encode().decode("unicode_escape", "ignore")
            thumb = m.group(2).encode().decode("unicode_escape", "ignore")
            if not full.startswith("http"):
                continue
            out.append(self._result("图片", full, "", thumb=thumb, full=full))
            if len(out) >= limit:
                break
        return out


# ---------------------------------------------------------------- 视频垂类

class BilibiliVideoAdapter(_HeadersMixin, Adapter):
    """B站搜索页 HTML：视频结果，带封面与时长，App 内直接播。"""

    kind = "video"
    weight = 1.0

    def search(self, query: str, limit: int) -> List[Result]:
        url = "https://search.bilibili.com/all?keyword=" + quote_plus(query)
        soup = _soup(self._get(url))
        out: List[Result] = []
        for card in soup.select("li.video-item, .video-list-item, .bili-video-card"):
            a = card.select_one("a[href*='/video/']")
            if not a:
                continue
            href = absolutize("https://www.bilibili.com", a.get("href", ""))

            img = card.select_one("img")
            thumb = ""
            if img is not None:
                thumb = img.get("data-src") or img.get("src") or ""
                if thumb.startswith("//"):
                    thumb = "https:" + thumb

            # 标题：B站把标题放在封面 alt 上，a 的文本是播放量/时长
            title = (img.get("alt") if img is not None else "") or ""
            if not title.strip():
                node = card.select_one(".bili-video-card__info--tit") or card.select_one("h3")
                if node is not None:
                    title = node.get_text(" ", strip=True)
            if not title.strip():
                title = a.get("title", "") or "视频"
            title = re.sub(r"\s+", " ", str(title)).strip()

            dur_node = card.select_one(".length, .bili-video-card__stats__duration")
            duration = dur_node.get_text(strip=True) if dur_node is not None else ""

            out.append(self._result(title, href, "", thumb=thumb, duration=duration))
            if len(out) >= limit:
                break
        return out


class InvidiousAdapter(_HeadersMixin, Adapter):
    """YouTube 经 Invidious 公共实例，无广告、无推荐流。"""

    kind = "video"
    weight = 0.9

    DEFAULT_POOL = [
        "https://inv.nadeko.net", "https://invidious.nerdvpn.de",
        "https://yewtu.be", "https://invidious.privacyredirect.com",
    ]

    def search(self, query: str, limit: int) -> List[Result]:
        pool = self.spec.get("pool") or self.DEFAULT_POOL
        for base in pool:
            try:
                url = (f"{base.rstrip('/')}/api/v1/search?q={quote_plus(query)}"
                       f"&type=video&region=US")
                data = json.loads(self._get(url))
                out: List[Result] = []
                for it in (data or [])[:limit]:
                    vid = it.get("videoId")
                    if not vid:
                        continue
                    thumbs = (it.get("videoThumbnails") or [{}])
                    thumb = thumbs[0].get("url", "") if thumbs else ""
                    if thumb.startswith("/"):
                        thumb = base.rstrip("/") + thumb
                    out.append(self._result(
                        it.get("title", ""), f"https://yewtu.be/watch?v={vid}",
                        it.get("author", ""),
                        thumb=thumb, duration=str(it.get("lengthSeconds", "")),
                        video_id=vid,
                    ))
                if out:
                    return out
            except Exception:
                continue
        return []


class PexelsLikeAdapter(_HeadersMixin, Adapter):
    """免费素材站（Pexels/Pixabay 的公开搜索页），无 key、无广告。"""

    kind = "video"
    weight = 0.7

    def search(self, query: str, limit: int) -> List[Result]:
        base = str(self.spec.get("base") or "https://www.pexels.com")
        url = f"{base}/search/videos/{quote(query)}/"
        soup = _soup(self._get(url))
        out: List[Result] = []
        for a in soup.select("a[href*='/video/']"):
            href = absolutize(base, a.get("href", ""))
            img = a.select_one("img")
            thumb = (img.get("src") or "") if img else ""
            out.append(self._result(a.get("title") or "视频", href, "", thumb=thumb))
            if len(out) >= limit:
                break
        return out
