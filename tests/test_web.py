"""HTTP surface tests: PWA routes, JSON API, 404 handling (offline engine)."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import ThreadingHTTPServer

import requests

from omnihunt.engine import SearchEngine
from omnihunt.web import Handler


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = SearchEngine(config_path="config/engines.yaml", offline=True)
        Handler.engine = cls.engine
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.httpd.daemon_threads = True
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.engine.close()

    def test_health(self) -> None:
        resp = requests.get(self.base + "/health", timeout=10)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_manifest(self) -> None:
        resp = requests.get(self.base + "/manifest.webmanifest", timeout=10)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("manifest+json", resp.headers["Content-Type"])
        data = resp.json()
        self.assertEqual(data["display"], "standalone")
        self.assertTrue(any(icon["sizes"] == "512x512" for icon in data["icons"]))

    def test_service_worker(self) -> None:
        resp = requests.get(self.base + "/sw.js", timeout=10)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Service-Worker-Allowed"), "/")
        self.assertIn("javascript", resp.headers["Content-Type"])
        self.assertIn("omnihunt-shell", resp.text)

    def test_icon(self) -> None:
        resp = requests.get(self.base + "/assets/icons/icon-192.png", timeout=10)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["Content-Type"], "image/png")
        self.assertGreater(len(resp.content), 1000)

    def test_index_has_pwa_head(self) -> None:
        html = requests.get(self.base + "/", timeout=10).text
        self.assertIn('rel="manifest"', html)
        self.assertIn("apple-mobile-web-app-capable", html)
        self.assertIn('viewport-fit=cover', html)

    def test_search_api(self) -> None:
        resp = requests.get(
            self.base + "/api/search",
            params={"q": "demo", "kinds": "onion", "limit": 5},
            timeout=20,
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertGreater(payload["count"], 0)
        self.assertTrue(all(item["kind"] == "onion" for item in payload["results"]))

    def test_search_requires_query(self) -> None:
        resp = requests.get(self.base + "/api/search", timeout=10)
        self.assertEqual(resp.status_code, 400)

    def test_unknown_route(self) -> None:
        resp = requests.get(self.base + "/nope", timeout=10)
        self.assertEqual(resp.status_code, 404)

    def test_asset_traversal_blocked(self) -> None:
        resp = requests.get(self.base + "/assets/..%2f..%2fomnihunt%2fengine.py", timeout=10)
        self.assertIn(resp.status_code, (403, 404))


if __name__ == "__main__":
    unittest.main(verbosity=2)
