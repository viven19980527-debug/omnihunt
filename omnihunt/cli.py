"""Command line interface for OmniHunt."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engine import SearchEngine
from .patterns import build_patterns

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "engines.yaml"

KIND_COLOR = {"web": "36", "onion": "35", "adult": "95", "torrent": "33", "pattern": "90"}


def _tty() -> bool:
    return sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def paint(text: str, color: str) -> str:
    return f"\x1b[{color}m{text}\x1b[0m" if _tty() else text


def bold(text: str) -> str:
    return f"\x1b[1m{text}\x1b[0m" if _tty() else text


def dim(text: str) -> str:
    return f"\x1b[2m{text}\x1b[0m" if _tty() else text


def render(results, show_sources: bool = True) -> str:
    lines: List[str] = []
    for i, r in enumerate(results, 1):
        badge = paint(f"[{r.kind}]", KIND_COLOR.get(r.kind, "37"))
        title = r.title or r.url
        lines.append(f"{i:>3}. {badge} {bold(title)}")
        lines.append(f"     {paint(r.url, '34')}")
        if r.snippet:
            snippet = r.snippet if len(r.snippet) <= 220 else r.snippet[:217] + "..."
            lines.append(f"     {snippet}")
        if show_sources and r.sources:
            lines.append("     " + dim("sources: " + ", ".join(r.sources) + f"  score={r.score:.2f}"))
        lines.append("")
    return "\n".join(lines)


def to_markdown(query: str, response: Dict[str, Any]) -> str:
    rows = [
        f"# OmniHunt · {query}",
        "",
        f"- 结果: {response['count']} / 去重后",
        f"- 耗时: {response['took_ms']} ms",
        f"- 引擎: {', '.join(e['name'] for e in response['stats'].get('engines', [])) or '-'}",
        "",
        "| # | 类型 | 标题 | 链接 |",
        "|---|------|------|------|",
    ]
    for i, r in enumerate(response["results"], 1):
        title = (r["title"] or "").replace("|", "\\|")
        rows.append(f"| {i} | {r['kind']} | {title} | {r['url']} |")
    if response["errors"]:
        rows += ["", "## 错误", ""]
        rows += [f"- `{e['engine']}`: {e['message']}" for e in response["errors"]]
    return "\n".join(rows) + "\n"


def cmd_search(args: argparse.Namespace) -> int:
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()] if args.kinds else None
    engines = [e.strip() for e in args.engines.split(",") if e.strip()] if args.engines else None

    with SearchEngine(
        config_path=args.config,
        offline=args.offline,
        use_cache=not args.no_cache,
    ) as engine:
        proxy = (getattr(args, "proxy", None) or "").strip()
        if proxy:
            if proxy.startswith("socks"):
                engine.client.tor_proxy = proxy
                engine.client.force_tor = True
            else:
                engine.client.http_proxy = proxy
        if args.tor_all:
            engine.client.force_tor = True
        response = engine.search(
            args.query,
            kinds=kinds,
            engines=engines,
            limit=args.limit,
            per_engine=args.per_engine,
            include_patterns=args.patterns,
            timeout=args.timeout,
        )
        payload = response.to_dict()

    if args.json == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print()
    print(bold(f"OmniHunt · {payload['query']}"))
    print(
        dim(
            f"{payload['count']} 条 · {payload['took_ms']} ms"
            f"{' · cache' if payload['cached'] else ''}"
            f" · 引擎 {len(payload['stats'].get('engines', []))}"
        )
    )
    print()
    if payload["results"]:
        print(render(response.results))
    else:
        print(dim("没有结果。试试 --kinds web,onion,adult,torrent 或 --patterns。"))
        print()

    if payload["errors"]:
        print(paint("引擎错误", "31"))
        for err in payload["errors"]:
            print(f"  - {err['engine']}: {dim(err['message'][:200])}")
        print()

    if args.json and args.json != "-":
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(dim(f"JSON -> {out}"))

    if args.md:
        out = Path(args.md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(to_markdown(payload["query"], payload), encoding="utf-8")
        print(dim(f"Markdown -> {out}"))
    return 0


def cmd_engines(args: argparse.Namespace) -> int:
    with SearchEngine(config_path=args.config) as engine:
        infos = engine.engines_info()
        summary = engine.catalog_summary()
    print(bold(f"{'name':<16}{'kind':<10}{'weight':<8}{'via':<10}{'direct':<8}enabled"))
    for info in infos:
        print(
            f"{info['name']:<16}{info['kind']:<10}{info['weight']:<8.2f}"
            f"{info['via']:<10}{str(info['direct']):<8}{info['enabled']}"
        )
    print()
    for name, data in summary.items():
        if "error" in data:
            print(paint(f"{name}: {data['error']}", "31"))
        else:
            print(dim(f"{name}: {data['count']} sites ({', '.join(data['kinds'])})"))
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    files = {
        "adult": ROOT / "catalog" / "adult_sites.json",
        "onion": ROOT / "catalog" / "onion_index.json",
        "magnet": ROOT / "catalog" / "magnet_sources.json",
    }
    picks = [args.name] if args.name else list(files)
    for key in picks:
        path = files.get(key)
        if not path or not path.exists():
            print(paint(f"unknown catalog: {key}", "31"))
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        print(bold(f"\n{key} · {len(data.get('sites', []))} sites"))
        for site in data.get("sites", []):
            flag = "" if site.get("enabled", True) else dim(" (disabled)")
            tags = ",".join(site.get("tags", []))
            print(f"  {site.get('name'):<14} {site.get('search')}{flag}")
            if tags:
                print(dim(f"                 tags: {tags}"))
    print()
    return 0


def cmd_patterns(args: argparse.Namespace) -> int:
    patterns = build_patterns(args.query)
    print(bold(f"\n查询模式 · {args.query}\n"))
    for item in patterns:
        print(f"  {paint('[' + item['label'] + ']', '36')}  {item['query']}")
        print(dim(f"      {item['note']}"))
    if args.json:
        Path(args.json).write_text(json.dumps(patterns, ensure_ascii=False, indent=2), encoding="utf-8")
        print(dim(f"\nJSON -> {args.json}"))
    print()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .web import serve

    serve(
        host=args.host,
        port=args.port,
        config_path=args.config,
        offline=args.offline,
        proxy=getattr(args, "proxy", None),
    )
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    with SearchEngine(config_path=args.config) as engine:
        if args.action == "purge":
            removed = engine.cache.purge()
            print(f"purged {removed} expired rows")
        else:
            path = engine.cache.path
            size = path.stat().st_size if path.exists() else 0
            print(f"cache: {path} ({size} bytes, ttl={engine.cache.ttl}s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="omnihunt", description="OmniHunt · 多源聚合搜索（clearnet / onion / 成人目录 / 磁力）")
    p.add_argument("--config", default=str(DEFAULT_CONFIG), help="引擎配置 yaml")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="执行聚合搜索")
    s.add_argument("query")
    s.add_argument("--kinds", help="web,onion,adult,torrent,pattern")
    s.add_argument("--engines", help="按引擎名过滤，逗号分隔")
    s.add_argument("--limit", type=int, default=40)
    s.add_argument("--per-engine", type=int, default=10)
    s.add_argument("--timeout", type=float, default=25)
    s.add_argument("--patterns", action="store_true", help="附带查询模式结果")
    s.add_argument("--json", help="导出 JSON 路径，'-' 表示打印到 stdout")
    s.add_argument("--md", help="导出 Markdown 报告")
    s.add_argument("--offline", action="store_true", help="离线 fixtures 模式")
    s.add_argument("--no-cache", action="store_true")
    s.add_argument("--tor-all", action="store_true", help="全部流量走 Tor SOCKS5")
    s.add_argument("--proxy", default=None,
                   help="HTTP/SOCKS5 代理：http://127.0.0.1:7890 或 socks5h://127.0.0.1:7890")
    s.set_defaults(func=cmd_search)

    e = sub.add_parser("engines", help="列出引擎")
    e.set_defaults(func=cmd_engines)

    c = sub.add_parser("catalog", help="查看站点目录")
    c.add_argument("name", nargs="?", choices=["adult", "onion", "magnet"])
    c.set_defaults(func=cmd_catalog)

    pt = sub.add_parser("patterns", help="生成查询模式")
    pt.add_argument("query")
    pt.add_argument("--json")
    pt.set_defaults(func=cmd_patterns)

    sv = sub.add_parser("serve", help="启动 Web UI")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=7860)
    sv.add_argument("--offline", action="store_true")
    sv.add_argument("--proxy", default=None, help="HTTP/SOCKS5 代理，透传给所有适配器")
    sv.set_defaults(func=cmd_serve)

    ch = sub.add_parser("cache", help="缓存维护")
    ch.add_argument("action", nargs="?", default="info", choices=["info", "purge"])
    ch.set_defaults(func=cmd_cache)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(paint(f"{type(exc).__name__}: {exc}", "31"), file=sys.stderr)
        return 1
