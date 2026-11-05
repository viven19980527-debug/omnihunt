"""Minimal HTTP UI + JSON API (stdlib only)."""
from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .engine import SearchEngine

ASSETS = Path(__file__).resolve().parent / "assets"
_ENGINE_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "OmniHunt/1.0"
    engine: SearchEngine  # injected by serve()

    # ------------------------------------------------------------- utilities
    def log_message(self, fmt: str, *args: Any) -> None:  # quiet access log
        pass

    def _send(
        self,
        code: int,
        body: bytes,
        ctype: str,
        extra_headers: Optional[Dict[str, str]] = None,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: Any) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    # ------------------------------------------------------------------ GET
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        try:
            if route in ("/", "/index.html"):
                self._serve_asset("index.html")
            elif route == "/health":
                self._json(200, {"ok": True, "engines": len(self.engine.adapters)})
            elif route == "/api/engines":
                self._json(200, {"engines": self.engine.engines_info(), "catalogs": self.engine.catalog_summary()})
            elif route == "/api/catalog":
                self._json(200, self.engine.catalog_summary())
            elif route == "/api/search":
                self._api_search(parse_qs(parsed.query))
            elif route == "/manifest.webmanifest":
                self._serve_asset("manifest.webmanifest", ctype="application/manifest+json; charset=utf-8")
            elif route in ("/sw.js", "/service-worker.js"):
                self._serve_asset(
                    "sw.js",
                    ctype="application/javascript; charset=utf-8",
                    extra_headers={"Service-Worker-Allowed": "/"},
                    cache_control="no-cache",
                )
            elif route in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
                self._serve_asset("icons/icon-180.png", cache_control="public, max-age=86400")
            elif route == "/favicon.ico":
                self._serve_asset("icons/icon-192.png", cache_control="public, max-age=86400")
            elif route.startswith("/assets/"):
                self._serve_asset(route.split("/assets/", 1)[1])
            else:
                self._json(404, {"error": "not found"})
        except BrokenPipeError:
            return
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    # -------------------------------------------------------------- handlers
    def _serve_asset(
        self,
        name: str,
        ctype: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        cache_control: str = "no-store",
    ) -> None:
        target = (ASSETS / name).resolve()
        if ASSETS.resolve() not in target.parents and target != ASSETS.resolve():
            self._json(403, {"error": "path traversal"})
            return
        if not target.exists():
            self._json(404, {"error": f"missing asset {name}"})
            return
        resolved_type = ctype or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype is None and (resolved_type.startswith("text/") or target.suffix in (".js", ".css")):
            resolved_type += "; charset=utf-8"
        self._send(
            200,
            target.read_bytes(),
            resolved_type,
            extra_headers=extra_headers,
            cache_control=cache_control,
        )

    def _api_search(self, qs: Dict[str, list]) -> None:
        def one(key: str, default: str = "") -> str:
            return (qs.get(key) or [default])[0].strip()

        query = one("q")
        if not query:
            self._json(400, {"error": "missing q"})
            return
        kinds = [k for k in one("kinds").split(",") if k] or None
        engines = [e for e in one("engines").split(",") if e] or None
        limit = min(200, max(1, int(one("limit", "40") or 40)))
        per_engine = min(30, max(1, int(one("per_engine", "10") or 10)))
        patterns = one("patterns").lower() in ("1", "true", "yes")

        with _ENGINE_LOCK:
            response = self.engine.search(
                query,
                kinds=kinds,
                engines=engines,
                limit=limit,
                per_engine=per_engine,
                include_patterns=patterns,
            )
        payload = response.to_dict()
        payload["engine_info"] = self.engine.engines_info()
        self._json(200, payload)


def serve(
    host: str = "127.0.0.1",
    port: int = 7860,
    *,
    config_path: Optional[str] = None,
    offline: bool = False,
) -> None:
    engine = SearchEngine(config_path=config_path, offline=offline)
    Handler.engine = engine
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print(f"OmniHunt UI  ->  http://{host}:{port}")
    print(f"engines: {', '.join(a.name for a in engine.adapters)}")
    if offline:
        print("offline mode: 使用 fixtures/pages 回放")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()
        engine.close()
