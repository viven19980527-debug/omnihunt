"""Data model + URL canonicalisation for OmniHunt."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "hsa_", "ref_")
TRACKING_KEYS = {
    "ref", "referrer", "fbclid", "gclid", "dclid", "msclkid", "mc_cid",
    "mc_eid", "igshid", "spm", "scm", "_ga", "_gl", "yclid", "s_kwcid",
}

_SCHEME_PORTS = {"http": 80, "https": 443}


def unwrap_redirect(url: str) -> str:
    """Unwrap the common search-engine redirect wrappers."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    host = parts.netloc.lower()
    qs = dict(parse_qsl(parts.query))
    if host.endswith("duckduckgo.com") and "/l/" in parts.path:
        for key in ("uddg", "u", "url"):
            if key in qs:
                return unquote(qs[key])
    if host.endswith("bing.com") and parts.path.startswith("/ck/"):
        if "u" in qs:
            raw = qs["u"]
            if raw.startswith("a1"):
                import base64

                raw = raw[2:]
                pad = "=" * (-len(raw) % 4)
                try:
                    return base64.urlsafe_b64decode(raw + pad).decode("utf-8", "replace")
                except Exception:
                    return url
    if host.endswith("google.com") and parts.path == "/url":
        if "q" in qs:
            return qs["q"]
    return url


def canonical_url(url: str) -> str:
    """Stable key used for de-duplication."""
    if not url:
        return ""
    url = unwrap_redirect(url.strip())
    if url.startswith("//"):
        url = "https:" + url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.lower()

    scheme = (parts.scheme or "http").lower()
    host = (parts.hostname or "").lower().strip(".")
    if not host:
        return url.lower()

    port = parts.port
    netloc = host
    if port and port != _SCHEME_PORTS.get(scheme):
        netloc = f"{host}:{port}"

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        low = key.lower()
        if low in TRACKING_KEYS or low.startswith(TRACKING_PREFIXES):
            continue
        kept.append((key, value))
    kept.sort()
    query = urlencode(kept)

    return urlunsplit((scheme, netloc, path, query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8", "replace")).hexdigest()


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def is_onion(url: str) -> bool:
    return host_of(url).endswith(".onion")


@dataclass
class Result:
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    kind: str = "web"          # web | onion | adult | torrent | pattern
    position: int = 0
    weight: float = 1.0
    score: float = 0.0
    sources: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = re.sub(r"\s+", " ", (self.title or "")).strip()
        self.snippet = re.sub(r"\s+", " ", (self.snippet or "")).strip()
        self.url = unwrap_redirect((self.url or "").strip())
        if not self.sources and self.source:
            self.sources = [self.source]

    @property
    def key(self) -> str:
        return canonical_url(self.url)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["score"] = round(self.score, 4)
        return data


@dataclass
class EngineError:
    engine: str
    message: str


@dataclass
class SearchResponse:
    query: str
    results: List[Result] = field(default_factory=list)
    errors: List[EngineError] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    took_ms: int = 0
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "took_ms": self.took_ms,
            "cached": self.cached,
            "count": len(self.results),
            "stats": self.stats,
            "errors": [asdict(e) for e in self.errors],
            "results": [r.to_dict() for r in self.results],
        }
