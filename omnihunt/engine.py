"""Orchestrator: fan out to engines, cache, merge, rank."""
from __future__ import annotations

import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from .adapters import build_adapters
from .cache import Cache
from .models import EngineError, Result, SearchResponse
from .net import Client, env_override
from .patterns import build_results
from .rank import merge_and_rank

DEFAULT_CONFIG: Dict[str, Any] = {
    "http": {
        "timeout": 15,
        "retries": 1,
        "rate_per_sec": 1.5,
        "max_bytes": 3_000_000,
        "tor_socks": "127.0.0.1:9050",
        "http_proxy": "",
    },
    "cache": {"enabled": True, "path": "data/cache.sqlite", "ttl_seconds": 1800},
    "search": {"limit": 40, "per_engine": 10, "timeout": 25},
    "engines": [
        {"name": "duckduckgo", "type": "duckduckgo", "kind": "web", "weight": 1.0},
        {"name": "ahmia", "type": "ahmia", "kind": "onion", "weight": 1.0,
         "base": "https://ahmia.fi", "path": "/search/?q={q}"},
        {"name": "adult_catalog", "type": "catalog", "kind": "adult", "weight": 0.8,
         "catalog": "catalog/adult_sites.json"},
        {"name": "magnet_catalog", "type": "catalog", "kind": "torrent", "weight": 0.7,
         "catalog": "catalog/magnet_sources.json"},
    ],
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path:
        p = Path(path)
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            cfg = deep_merge(cfg, data)
    return cfg


class SearchEngine:
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        root: str | Path | None = None,
        offline: bool = False,
        use_cache: bool = True,
        config_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root) if root else Path(__file__).resolve().parent.parent
        base = load_config(config_path) if config is None else deep_merge(DEFAULT_CONFIG, config)
        self.config = env_override(base)
        self.offline = offline

        http_cfg = self.config.get("http", {})
        self.client = Client(http_cfg, offline=offline, root=self.root)
        self.adapters = build_adapters(self.config.get("engines", []), self.client, self.root)

        cache_cfg = self.config.get("cache", {})
        cache_path = Path(str(cache_cfg.get("path", "data/cache.sqlite")))
        if not cache_path.is_absolute():
            cache_path = self.root / cache_path
        self.cache = Cache(
            cache_path,
            ttl_seconds=int(cache_cfg.get("ttl_seconds", 1800)),
            enabled=bool(cache_cfg.get("enabled", True)) and use_cache,
        )
        self.use_cache = use_cache

    # ------------------------------------------------------------------ info
    def engines_info(self) -> List[Dict[str, Any]]:
        return [a.describe() for a in self.adapters]

    def catalog_summary(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for adapter in self.adapters:
            if getattr(adapter, "direct", False):
                try:
                    sites = adapter._sites()  # noqa: SLF001 - intentional introspection
                except Exception as exc:  # noqa: BLE001
                    out[adapter.name] = {"error": str(exc)}
                    continue
                out[adapter.name] = {
                    "count": len(sites),
                    "kinds": sorted({s.get("kind", adapter.kind) for s in sites}),
                    "sites": [s.get("name") for s in sites],
                }
        return out

    # ---------------------------------------------------------------- search
    def search(
        self,
        query: str,
        *,
        kinds: Optional[Sequence[str]] = None,
        engines: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
        per_engine: Optional[int] = None,
        include_patterns: bool = False,
        timeout: Optional[float] = None,
        use_cache: Optional[bool] = None,
    ) -> SearchResponse:
        query = (query or "").strip()
        if not query:
            raise ValueError("empty query")

        search_cfg = self.config.get("search", {})
        limit = int(limit or search_cfg.get("limit", 40))
        per_engine = int(per_engine or search_cfg.get("per_engine", 10))
        timeout = float(timeout or search_cfg.get("timeout", 25))
        cache_on = self.use_cache if use_cache is None else bool(use_cache)
        kind_set = set(kinds) if kinds else None
        engine_set = set(engines) if engines else None

        selected = [
            a for a in self.adapters
            if (kind_set is None or a.kind in kind_set) and (engine_set is None or a.name in engine_set)
        ]
        started = time.perf_counter()
        results: List[Result] = []
        errors: List[EngineError] = []
        stats: Dict[str, Any] = {"engines": [], "raw": 0, "cached_engines": 0}

        if selected:
            # 目录型适配器（catalog / magnet / onion 直链）不发网络请求，
            # 先在主线程跑完。否则它们会排在 8 个网络任务后面被整轮超时吃掉。
            direct_adapter = [a for a in selected if getattr(a, "direct", False)]
            net_adapter = [a for a in selected if not getattr(a, "direct", False)]
            for adapter in direct_adapter:
                t0 = time.perf_counter()
                try:
                    got = adapter.search(query, max(1, min(per_engine, 50))) or []
                    for pos, item in enumerate(got):
                        item.position = pos
                        if not item.weight:
                            item.weight = adapter.weight
                        if not item.source:
                            item.source = adapter.name
                        if not item.sources:
                            item.sources = [item.source]
                    results.extend(got)
                    stats["engines"].append({
                        "name": adapter.name, "kind": adapter.kind,
                        "count": len(got),
                        "ms": int((time.perf_counter() - t0) * 1000), "cached": False,
                    })
                except Exception as exc:  # noqa: BLE001
                    errors.append(EngineError(adapter.name, f"{type(exc).__name__}: {exc}"))
                    stats["engines"].append({
                        "name": adapter.name, "kind": adapter.kind, "count": 0, "error": str(exc),
                    })

            selected = net_adapter

        if selected:
            # Bound each socket by the search budget so a dead network cannot
            # hold the worker pool far past the wall-clock deadline. Retries
            # share the same budget instead of doubling it.
            attempts = max(1, int(self.client.retries) + 1)
            self.client.timeout = max(2.5, min(float(self.client.timeout), timeout / attempts))
            max_workers = max(1, min(8, len(selected)))
            pool = ThreadPoolExecutor(max_workers=max_workers)
            futures = {
                pool.submit(self._run_one, adapter, query, per_engine, cache_on): adapter
                for adapter in selected
            }
            try:
                for fut in as_completed(futures, timeout=timeout):
                    adapter = futures[fut]
                    try:
                        got, ms, cached = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        errors.append(EngineError(adapter.name, f"{type(exc).__name__}: {exc}"))
                        stats["engines"].append(
                            {"name": adapter.name, "kind": adapter.kind, "count": 0, "error": str(exc)}
                        )
                        continue
                    results.extend(got)
                    stats["engines"].append(
                        {
                            "name": adapter.name,
                            "kind": adapter.kind,
                            "count": len(got),
                            "ms": ms,
                            "cached": cached,
                        }
                    )
                    stats["cached_engines"] += 1 if cached else 0
            except TimeoutError:
                pending = {a.name for f, a in futures.items() if not f.done()}
                for name in pending:
                    errors.append(EngineError(name, f"timeout after {timeout:.0f}s"))
                    stats["engines"].append({"name": name, "kind": "", "count": 0, "error": "timeout"})
                for fut in futures:
                    fut.cancel()
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

        pattern_results: List[Result] = []
        if include_patterns:
            reserved = min(12, max(3, limit // 3))
            pattern_results = build_results(query, limit=reserved)
            if kind_set is not None:
                pattern_results = [r for r in pattern_results if r.kind in kind_set]
            for p in pattern_results:
                p.score = 0.5
            natural = merge_and_rank(results, query, limit=max(0, limit - len(pattern_results)), kind_filter=kinds)
            ranked = natural + pattern_results[: max(0, limit - len(natural))]
        else:
            if kind_set is None:
                ranked = self._rank_with_quotas(results, query, limit)
            else:
                ranked = merge_and_rank(results, query, limit=limit, kind_filter=kinds)

        stats["raw"] = len(results) + len(pattern_results)
        stats["unique"] = len(ranked)
        stats["engines"].sort(key=lambda e: e["name"])

        return SearchResponse(
            query=query,
            results=ranked,
            errors=errors,
            stats=stats,
            took_ms=int((time.perf_counter() - started) * 1000),
            cached=bool(selected) and stats["cached_engines"] == len(selected),
        )

    # ---------------------------------------------------------------- quotas
    # 「全部」模式下普通网页引擎会占满名额，把磁力/暗网/图片/视频挤掉。
    # 这里给非 web 类别保留固定份额，保证暗面内容一定出现在结果中。
    QUOTA_KINDS = ("onion", "torrent", "image", "video", "adult")
    QUOTA_SHARE = {"onion": 0.15, "torrent": 0.15, "image": 0.12, "video": 0.10, "adult": 0.10}

    def _rank_with_quotas(self, results, query: str, limit: int):
        ranked = merge_and_rank(results, query, limit=max(limit * 3, 60))
        buckets = {k: [] for k in self.QUOTA_KINDS}
        rest = []
        for r in ranked:
            if r.kind in buckets:
                buckets[r.kind].append(r)
            else:
                rest.append(r)

        out = []
        used = set()
        for kind, share in self.QUOTA_SHARE.items():
            take = max(1, int(limit * share))
            for r in buckets[kind][:take]:
                out.append(r)
                used.add(id(r))
        for r in rest:
            if len(out) >= limit:
                break
            out.append(r)
            used.add(id(r))
        if len(out) < limit:
            for r in ranked:
                if len(out) >= limit:
                    break
                if id(r) not in used:
                    out.append(r)
                    used.add(id(r))
        return out[:limit]


    # --------------------------------------------------------------- internal
    def _run_one(self, adapter, query: str, per_engine: int, cache_on: bool):
        n = max(1, min(per_engine, 50))
        net = self.client.http_proxy or self.client.tor_proxy or "direct"
        key = Cache.key("v3", query.lower(), adapter.name, n, net)
        if cache_on:
            cached = self.cache.get(key)
            if cached is not None:
                return [Result(**row) for row in cached], 0, True

        t0 = time.perf_counter()
        try:
            items = adapter.search(query, n) or []
        except Exception:
            # 失败不写缓存，下次还能重试（以前会把失败当空结果缓存 30 分钟）
            raise
        for pos, item in enumerate(items):
            item.position = pos
            if not item.weight:
                item.weight = adapter.weight
            if not item.source:
                item.source = adapter.name
            if not item.sources:
                item.sources = [item.source]
        ms = int((time.perf_counter() - t0) * 1000)
        if cache_on:
            self.cache.set(key, [r.to_dict() for r in items])
        return items, ms, False

    def close(self) -> None:
        self.cache.close()

    def __enter__(self) -> "SearchEngine":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def quick_search(query: str, **kwargs: Any) -> Dict[str, Any]:
    """Convenience helper for scripts: returns the JSON-ready dict."""
    kwargs.pop("config", None)
    with SearchEngine(**kwargs) as engine:
        return engine.search(query).to_dict()
