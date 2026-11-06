"""De-duplication and ranking.

Ranking is deliberately transparent: engine weight * position decay + lexical
match bonus + kind bonus + cross-engine corroboration bonus. No ML, no
black box - every weight is a constant you can tune.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence

from .models import Result, canonical_url

KIND_PRIORITY = {"onion": 0, "image": 1, "video": 2, "web": 3, "adult": 4, "torrent": 5, "pattern": 6}
KIND_BONUS = {"onion": 0.18, "image": 0.10, "video": 0.10, "torrent": 0.12, "adult": 0.08, "web": 0.0, "pattern": -0.05}

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_WORD = re.compile(r"[a-z0-9_]+")


def tokenize(query: str) -> List[str]:
    q = (query or "").lower()
    tokens = _WORD.findall(q)
    cjk = _CJK.findall(q)
    if cjk:
        # CJK has no spaces: each char plus bigrams approximates match coverage.
        tokens.extend(cjk)
        tokens.extend("".join(cjk[i : i + 2]) for i in range(len(cjk) - 1))
    return list(dict.fromkeys(t for t in tokens if t))


def _match_ratio(tokens: Sequence[str], text: str) -> float:
    if not tokens or not text:
        return 0.0
    low = text.lower()
    hits = sum(1 for t in tokens if t in low)
    return hits / len(tokens)


def _merge(group: Iterable[Result]) -> Result:
    items = list(group)
    items.sort(key=lambda r: (-r.weight, r.position, r.kind != "onion"))
    head = items[0]
    best = Result(
        title=head.title,
        url=head.url,
        snippet=max((r.snippet for r in items), key=len, default=""),
        source=head.source,
        kind=head.kind,
        weight=max(r.weight for r in items),
        position=min(r.position for r in items),
        sources=[],
        extra=dict(head.extra),
    )
    # Result.__post_init__ seeds sources from source; rebuild it explicitly.
    best.sources = []
    seen_sources = set()
    for r in items:
        for s in r.sources or [r.source]:
            if s and s not in seen_sources:
                seen_sources.add(s)
                best.sources.append(s)
        if r.extra.get("magnet") and not best.extra.get("magnet"):
            best.extra["magnet"] = r.extra["magnet"]
    return best


def merge_and_rank(
    results: Iterable[Result],
    query: str,
    *,
    limit: int = 40,
    kind_filter: Optional[Sequence[str]] = None,
) -> List[Result]:
    groups: Dict[str, List[Result]] = {}
    for r in results:
        if not r.url:
            continue
        if kind_filter and r.kind not in kind_filter:
            continue
        key = canonical_url(r.url) or r.url
        groups.setdefault(key, []).append(r)

    tokens = tokenize(query)
    merged: List[Result] = []
    for group in groups.values():
        r = _merge(group)
        pos_decay = 1.0 / (1.0 + 0.08 * max(0, r.position))
        is_direct = bool(r.extra.get("direct"))
        generated = is_direct or r.kind == "pattern"

        # Direct-link and generated entries carry the query in their own title,
        # so their lexical bonus is scaled down: it is not independent evidence.
        base = r.weight * (0.55 + 0.45 * pos_decay) * (0.70 if is_direct else 1.0)
        title_w = 0.30 if generated else 1.05
        snip_w = 0.15 if generated else 0.35
        score = base
        score += title_w * _match_ratio(tokens, r.title)
        score += snip_w * _match_ratio(tokens, r.snippet)
        score += KIND_BONUS.get(r.kind, 0.0)
        score += 0.10 * (len(r.sources) - 1)
        r.score = score
        merged.append(r)

    merged.sort(key=lambda r: (-r.score, KIND_PRIORITY.get(r.kind, 9), r.title.lower()))

    # Diversity guard: link-directory entries must not crowd out organic hits.
    direct_cap = max(6, int(limit * 0.55)) if limit > 8 else limit
    out: List[Result] = []
    direct_used = 0
    for r in merged:
        if r.extra.get("direct"):
            if direct_used >= direct_cap:
                continue
            direct_used += 1
        out.append(r)
        if len(out) >= limit:
            break
    return out
