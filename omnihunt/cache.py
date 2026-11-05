"""SQLite result cache (per engine, TTL based)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class Cache:
    def __init__(self, path: str | Path, ttl_seconds: int = 1800, enabled: bool = True) -> None:
        self.enabled = enabled
        self.ttl = int(ttl_seconds)
        self.path = Path(path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            " key TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL)"
        )
        self._conn.commit()

    @staticmethod
    def key(*parts: Any) -> str:
        raw = "\x1f".join(str(p) for p in parts)
        return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()

    def get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        if not self._conn:
            return None
        with self._lock:
            row = self._conn.execute("SELECT payload, created FROM cache WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        payload, created = row
        if time.time() - float(created) > self.ttl:
            return None
        try:
            return json.loads(payload)
        except ValueError:
            return None

    def set(self, key: str, results: List[Dict[str, Any]]) -> None:
        if not self._conn:
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, payload, created) VALUES (?,?,?)",
                (key, json.dumps(results, ensure_ascii=False), time.time()),
            )
            self._conn.commit()

    def purge(self) -> int:
        if not self._conn:
            return 0
        with self._lock:
            cur = self._conn.execute("DELETE FROM cache WHERE created < ?", (time.time() - self.ttl,))
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        if self._conn:
            with self._lock:
                self._conn.close()
            self._conn = None
