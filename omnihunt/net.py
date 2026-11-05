"""Transport layer: HTTP(S) fetch over clearnet or Tor SOCKS5, with
per-host rate limiting, simple retries, byte caps and an offline fixture mode.
"""
from __future__ import annotations

import os
import random
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter

try:  # requests[socks]
    import socks  # noqa: F401  (PySocks; enables socks5h:// proxies)
    _SOCKS_OK = True
except Exception:  # pragma: no cover
    _SOCKS_OK = False


UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]


class FetchError(RuntimeError):
    """Any failure that should be attributed to one engine, not the whole run."""


class RateLimiter:
    """Token-free spacing limiter: one request every 1/rate seconds per host."""

    def __init__(self, rate: float = 1.5) -> None:
        self.rate = max(0.1, float(rate))
        self._lock = threading.Lock()
        self._next: Dict[str, float] = {}

    def wait(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            ready = self._next.get(host, 0.0)
            delay = max(0.0, ready - now)
            self._next[host] = max(now, ready) + 1.0 / self.rate
        if delay > 0:
            time.sleep(delay)


class Client:
    def __init__(self, cfg: Dict[str, Any], offline: bool = False, root: Optional[Path] = None) -> None:
        self.cfg = cfg or {}
        self.offline = offline
        self.root = root or Path.cwd()
        self.timeout = float(self.cfg.get("timeout", 15))
        self.retries = int(self.cfg.get("retries", 1))
        self.max_bytes = int(self.cfg.get("max_bytes", 3_000_000))
        self.limiter = RateLimiter(self.cfg.get("rate_per_sec", 1.5))

        tor = str(self.cfg.get("tor_socks", "127.0.0.1:9050")).strip()
        self.tor_proxy = f"socks5h://{tor}" if tor else ""
        self.http_proxy = str(self.cfg.get("http_proxy", "")).strip()
        self.force_tor = bool(self.cfg.get("force_tor", False))

        self._local = threading.local()

    # One requests.Session per worker thread: adapters run in a thread pool.
    @property
    def session(self) -> requests.Session:
        sess = getattr(self._local, "session", None)
        if sess is not None:
            return sess

        sess = requests.Session()
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
        sess.mount("http://", adapter)
        sess.mount("https://", adapter)
        sess.headers.update(
            {
                "User-Agent": random.choice(UA_POOL),
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "Cache-Control": "no-cache",
            }
        )
        self._local.session = sess
        return sess

    # ------------------------------------------------------------------ offline
    def _fixture(self, tag: str, suffix: str = "html") -> str:
        path = self.root / "fixtures" / "pages" / f"{tag}.{suffix}"
        if not path.exists():
            raise FetchError(f"offline: no fixture for engine '{tag}' ({path.name})")
        return path.read_text(encoding="utf-8", errors="replace")

    # ------------------------------------------------------------------- public
    def get(
        self,
        url: str,
        *,
        tag: str = "generic",
        via: str = "clearnet",
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        fixtures: bool = True,
    ) -> str:
        if self.offline:
            if not fixtures:
                raise FetchError("offline: network disabled")
            return self._fixture(tag)

        host = (url.split("//", 1)[-1].split("/", 1)[0] or "").lower()
        if self.force_tor:
            via = "tor"
        if host.endswith(".onion") and via != "tor":
            via = "tor"
        if via == "tor" and not self.tor_proxy:
            raise FetchError("onion target but tor_socks is not configured")
        if via == "tor" and not _SOCKS_OK:
            raise FetchError("PySocks is required for SOCKS5/Tor (pip install pysocks)")

        proxies = None
        if via == "tor":
            proxies = {"http": self.tor_proxy, "https": self.tor_proxy}
        elif self.http_proxy:
            proxies = {"http": self.http_proxy, "https": self.http_proxy}

        last: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            self.limiter.wait(host)
            try:
                resp = self.session.get(
                    url,
                    timeout=timeout or self.timeout,
                    proxies=proxies,
                    headers=headers,
                    stream=True,
                    allow_redirects=True,
                )
                try:
                    chunks, total = [], 0
                    for chunk in resp.iter_content(16_384):
                        chunks.append(chunk)
                        total += len(chunk)
                        if total >= self.max_bytes:
                            break
                    raw = b"".join(chunks)
                finally:
                    resp.close()

                if resp.status_code >= 400:
                    raise FetchError(f"HTTP {resp.status_code} for {url}")

                ctype = resp.headers.get("Content-Type", "")
                if ctype and not any(t in ctype.lower() for t in ("html", "json", "xml", "text")):
                    raise FetchError(f"unsupported content-type {ctype!r}")

                encoding = resp.encoding
                if not encoding or encoding.lower() == "iso-8859-1":
                    encoding = self._sniff_charset(raw, ctype)
                return raw.decode(encoding or "utf-8", "replace")
            except FetchError:
                raise
            except Exception as exc:  # noqa: BLE001 - network layer
                last = exc
                if attempt < self.retries:
                    time.sleep(0.4 + 0.6 * attempt + random.random() * 0.3)
        raise FetchError(f"{type(last).__name__}: {last}")

    def get_json(self, url: str, **kw: Any) -> Any:
        text = self.get(url, **kw)
        import json

        try:
            return json.loads(text)
        except ValueError as exc:
            raise FetchError(f"invalid JSON from {url}: {exc}") from exc

    @staticmethod
    def _sniff_charset(raw: bytes, ctype: str) -> str:
        import re

        m = re.search(r"charset=([\w\-]+)", ctype or "", re.I)
        if m:
            return m.group(1)
        head = raw[:4096].decode("ascii", "ignore")
        m = re.search(r'charset=["\']?([\w\-]+)', head, re.I)
        return m.group(1) if m else "utf-8"


def env_override(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Environment switches keep test runs and CLI use from editing YAML."""
    out = dict(cfg or {})
    http = dict(out.get("http") or {})
    if os.getenv("OMNI_TOR_SOCKS"):
        http["tor_socks"] = os.environ["OMNI_TOR_SOCKS"]
    if os.getenv("OMNI_HTTP_PROXY"):
        http["http_proxy"] = os.environ["OMNI_HTTP_PROXY"]
    if os.getenv("OMNI_TIMEOUT"):
        http["timeout"] = float(os.environ["OMNI_TIMEOUT"])
    out["http"] = http
    return out
