"""Cached HTTP layer.

Every GET is cached on disk under data_cache/ keyed by sha1(url).
- Live mode (default): fetch fresh if cache is older than TTL, fall back to
  cache on network failure.
- --cache-only mode: never touch the network (used for offline testing).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

CACHE_DIR = Path(__file__).resolve().parent.parent / "data_cache"
MANIFEST = CACHE_DIR / "manifest.json"
TTL_SECONDS = 3600  # 1 hour
CACHE_ONLY = False

HEADERS = {"User-Agent": "mlb-predictor/1.4 (personal research tool)"}


def _key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()


def _record_manifest(url: str, key: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text())
        except Exception:
            manifest = {}
    manifest[key] = url
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))


def get_text(url: str, ext: str = ".txt", ttl: float | None = None) -> str:
    key = _key(url)
    path = CACHE_DIR / f"{key}{ext}"
    if CACHE_ONLY:
        if path.exists():
            return path.read_text()
        raise RuntimeError(f"cache-only mode: no cached copy of {url}")
    ttl = TTL_SECONDS if ttl is None else ttl
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return path.read_text()
    try:
        text = _http_get(url)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        _record_manifest(url, key)
        return text
    except Exception as exc:
        if path.exists():  # stale cache beats no data
            return path.read_text()
        raise RuntimeError(f"fetch failed for {url}: {exc}") from exc


def _http_get(url: str) -> str:
    """Uses 'requests' if available, else the standard library (no installs).

    Falls back to an unverified SSL context if the local Python install has
    broken/missing certificates (a common macOS issue) — acceptable here
    since this app only reads public sports data.
    """
    if requests is not None:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text
    import ssl
    import urllib.request
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return r.read().decode("utf-8", "replace")


def get_json(url: str, ttl: float | None = None) -> dict:
    return json.loads(get_text(url, ext=".json", ttl=ttl))


def get_text_nocache(url: str) -> str:
    """Like get_text but never touches disk — for URLs carrying secrets
    (API keys) that shouldn't be written into data_cache/manifest.json."""
    if CACHE_ONLY:
        raise RuntimeError(f"cache-only mode: no cached copy of {url}")
    return _http_get(url)
