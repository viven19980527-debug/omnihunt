"""Offline test suite: parsing, dedupe, ranking, end-to-end search."""
from __future__ import annotations

import base64
import unittest

from omnihunt.engine import SearchEngine
from omnihunt.models import Result, canonical_url, unwrap_redirect
from omnihunt.patterns import build_patterns
from omnihunt.rank import merge_and_rank


class UrlTests(unittest.TestCase):
    def test_tracking_stripped(self):
        a = canonical_url("https://Example.com/Path/?utm_source=x&id=7#frag")
        b = canonical_url("http://example.com/Path?id=7")
        # scheme is part of the key, but host/path/tracking normalisation is not
        self.assertEqual(a, "https://example.com/Path?id=7")
        self.assertNotIn("utm", a)
        self.assertNotEqual(a, b)

    def test_query_sorted(self):
        self.assertEqual(
            canonical_url("https://e.com/s?b=2&a=1"),
            canonical_url("https://e.com/s?a=1&b=2"),
        )

    def test_ddg_redirect(self):
        wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fx&rut=1"
        self.assertEqual(unwrap_redirect(wrapped), "https://example.org/x")

    def test_bing_redirect(self):
        inner = base64.urlsafe_b64encode(b"https://example.net/y").decode().rstrip("=")
        wrapped = f"https://www.bing.com/ck/a?!&&p=1&u=a1{inner}&ntb=1"
        self.assertEqual(unwrap_redirect(wrapped), "https://example.net/y")


class RankTests(unittest.TestCase):
    def test_dedupe_merges_sources(self):
        rows = [
            Result(title="Alpha", url="https://e.com/a?utm_source=x", source="duckduckgo", kind="web", weight=1.0),
            Result(title="Alpha", url="https://e.com/a", source="bing", kind="web", weight=0.95),
        ]
        merged = merge_and_rank(rows, "alpha")
        self.assertEqual(len(merged), 1)
        self.assertEqual(sorted(merged[0].sources), ["bing", "duckduckgo"])
        self.assertGreaterEqual(len(merged[0].sources), 2)

    def test_organic_beats_catalog_flood(self):
        rows = [
            Result(title="Real page about cats", url="https://real.example/cats", source="ddg", kind="web", weight=1.0, snippet="cats"),
            Result(title="Site A · cats", url="https://a.example/search?q=cats", source="cat", kind="adult",
                   weight=0.85, extra={"direct": True}),
            Result(title="Site B · cats", url="https://b.example/search?q=cats", source="cat", kind="adult",
                   weight=0.85, extra={"direct": True}),
        ]
        ranked = merge_and_rank(rows, "cats", limit=10)
        self.assertEqual(ranked[0].url, "https://real.example/cats")

    def test_direct_cap(self):
        rows = [Result(title=f"S{i} · q", url=f"https://s{i}.example/?q=q", source="cat", kind="adult",
                       weight=0.85, extra={"direct": True}) for i in range(30)]
        ranked = merge_and_rank(rows, "q", limit=10)
        self.assertLessEqual(len(ranked), 10)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = SearchEngine(config_path="config/engines.yaml", offline=True)

    @classmethod
    def tearDownClass(cls):
        cls.engine.close()

    def test_offline_search_all_kinds(self):
        resp = self.engine.search("demo", limit=40, use_cache=False)
        self.assertTrue(resp.results)
        kinds = {r.kind for r in resp.results}
        self.assertIn("onion", kinds)
        self.assertIn("web", kinds)
        self.assertIn("adult", kinds)
        self.assertIn("torrent", kinds)
        self.assertFalse(resp.errors, [e.message for e in resp.errors])

    def test_onion_first_and_scores_desc(self):
        resp = self.engine.search("demo", limit=20, use_cache=False)
        scores = [r.score for r in resp.results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(any(r.kind == "onion" for r in resp.results))
        self.assertIn(resp.results[0].kind, {"onion", "web"})

    def test_kind_filter(self):
        resp = self.engine.search("demo", kinds=["torrent"], limit=10, use_cache=False)
        self.assertTrue(resp.results)
        self.assertTrue(all(r.kind == "torrent" for r in resp.results))

    def test_patterns_appended(self):
        resp = self.engine.search("demo", limit=60, include_patterns=True, use_cache=False)
        self.assertTrue(any(r.kind == "pattern" for r in resp.results))
        self.assertIsNot(resp.results[0].kind, "pattern")

    def test_engine_subset(self):
        resp = self.engine.search("demo", engines=["ahmia"], limit=10, use_cache=False)
        self.assertTrue(resp.results)
        self.assertTrue(all("ahmia" in r.sources for r in resp.results))

    def test_cache_roundtrip(self):
        self.engine.search("cache-me", limit=8, use_cache=True)
        again = self.engine.search("cache-me", limit=8, use_cache=True)
        self.assertTrue(again.cached)

    def test_engines_info_and_catalog(self):
        info = {e["name"]: e for e in self.engine.engines_info()}
        self.assertIn("bing", info)
        self.assertIn("baidu", info)
        self.assertIn("onion_catalog", info)
        summary = self.engine.catalog_summary()
        self.assertGreaterEqual(summary["adult_catalog"]["count"], 20)
        self.assertGreaterEqual(summary["onion_catalog"]["count"], 5)


class PatternTests(unittest.TestCase):
    def test_patterns_built(self):
        items = build_patterns("q")
        self.assertGreaterEqual(len(items), 12)
        self.assertTrue(all({"label", "query", "url", "note"} <= set(i) for i in items))
        self.assertTrue(any("site:onion" in i["query"] for i in items))


if __name__ == "__main__":
    unittest.main(verbosity=2)
