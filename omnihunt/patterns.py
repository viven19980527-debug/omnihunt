"""Search-operator playbook, exposed as data.

Every pattern is a ready-to-run query string plus a launch URL, so the CLI,
the web UI and any downstream tool share one definition.
"""
from __future__ import annotations

from typing import Dict, Iterable, List
from urllib.parse import quote_plus

from .models import Result

DDG = "https://duckduckgo.com/?q={q}"
AHMIA = "https://ahmia.fi/search/?q={q}"
BT4G = "https://bt4gprx.com/search?q={q}"

# (label, template, engine, note)
PATTERNS = [
    # --- general discovery -------------------------------------------------
    ("精确短语", '"{q}"', DDG, "引号锁定完整短语，压掉分词噪声"),
    ("标题命中", 'intitle:"{q}"', DDG, "标题包含关键词，通常是索引页/专题页"),
    ("URL 命中", 'inurl:{q}', DDG, "URL 里出现关键词，如 /tag/{q}"),
    ("目录列表", 'intitle:"index of" "{q}"', DDG, "开放目录直链，常见于媒体/归档站"),
    ("文件类型", '{q} filetype:mp4 OR filetype:mkv', DDG, "限定媒体容器格式"),
    ("归档格式", '{q} (filetype:zip OR filetype:rar OR filetype:7z)', DDG, "打包归档，多为合集"),
    ("粘贴站", '{q} site:pastebin.com OR site:ghostbin.com', DDG, "泄露文本/凭据的常见落点"),
    # --- darknet -----------------------------------------------------------
    ("暗网域名", '{q} site:onion', AHMIA, "Ahmia 索引下的 .onion 结果"),
    ("暗网标题", 'intitle:"{q}" site:onion', AHMIA, "只在标题命中的暗网页面"),
    ("暗网镜像", '"{q}" onion mirror', DDG, "clearnet 上的 .onion 镜像与入口说明"),
    ("目录站", '"{q}" onion directory list', DDG, "目录站通常给出最新可用入口"),
    # --- torrent / magnet --------------------------------------------------
    ("磁力关键词", '{q} magnet', DDG, "页面里出现 magnet 链接的索引页"),
    ("哈希前缀", '"{q}" "urn:btih"', DDG, "直接命中 infohash 文本"),
    ("DHT 索引", '{q}', BT4G, "BT4G 聚合 DHT 索引，按 infohash 去重"),
    # --- adult catalog -----------------------------------------------------
    ("标签路径", '{q} inurl:tag OR inurl:tags OR inurl:category', DDG, "成人站的标签/分类路径"),
    ("站内搜索", 'site:pornhub.com "{q}" OR site:xvideos.com "{q}"', DDG, "主流 tube 站内检索"),
    ("图库索引", '{q} site:rule34.xxx OR site:gelbooru.com OR site:danbooru.donmai.us', DDG, "图库/同人站"),
    ("漫画索引", '{q} site:nhentai.net OR site:e-hentai.org', DDG, "同人志与画廊"),
]


def build_patterns(query: str) -> List[Dict[str, str]]:
    q = quote_plus(query)
    out: List[Dict[str, str]] = []
    for label, template, engine, note in PATTERNS:
        pattern = template.format(q=query)
        out.append(
            {
                "label": label,
                "query": pattern,
                "url": engine.format(q=quote_plus(pattern)),
                "note": note,
            }
        )
    return out


def build_results(query: str, limit: int = 12) -> List[Result]:
    out: List[Result] = []
    for item in build_patterns(query)[:limit]:
        out.append(
            Result(
                title=f"[{item['label']}] {item['query']}",
                url=item["url"],
                snippet=item["note"],
                source="patterns",
                kind="pattern",
                weight=0.45,
                extra={"pattern": True, "label": item["label"]},
            )
        )
    return out
