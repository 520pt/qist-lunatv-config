#!/usr/bin/env python3
"""Tiny TVBox -> LunaTV/MoonTVPlus bridge.

It exposes Apple CMS-like endpoints for TVBox sites:
  /api/<site_key>/api.php/provide/vod?ac=videolist&wd=keyword
  /api/<site_key>/api.php/provide/vod?ac=videolist&ids=123

Supported today: direct MacCMS/provide/vod TVBox sites.
Unsupported TVBox engines return a clear JSON error instead of pretending to work.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TVBOX = ROOT / "tvbox-jsm.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

SITES: dict[str, dict[str, Any]] = {}


def safe_key(raw: str, used: set[str], fallback: str = "site") -> str:
    key = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw or fallback).strip("_") or fallback
    key = key[:80]
    base = key
    i = 2
    while key in used:
        suffix = f"_{i}"
        key = f"{base[:80 - len(suffix)]}{suffix}"
        i += 1
    used.add(key)
    return key


def normalize_maccms_api(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    path = re.sub(r"/+$", "", parts.path)
    path = re.sub(r"/at/(xml|json)$", "", path, flags=re.I)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def load_sites(path: Path) -> dict[str, dict[str, Any]]:
    tvbox = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    for idx, site in enumerate(tvbox.get("sites", []), 1):
        if not isinstance(site, dict):
            continue
        key = safe_key(str(site.get("key") or f"site_{idx}"), used, f"site_{idx}")
        api = site.get("api")
        engine = "maccms" if isinstance(api, str) and "provide/vod" in api and api.startswith(("http://", "https://")) else "unsupported"
        out[key] = {
            "key": key,
            "name": site.get("name") or site.get("key") or key,
            "engine": engine,
            "api": normalize_maccms_api(api) if engine == "maccms" else api,
            "raw": site,
        }
    return out


def fetch_json(url: str) -> tuple[int, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read(4 * 1024 * 1024)
        status = resp.status
    return status, json.loads(body.decode("utf-8-sig", "replace"))


def maccms_url(base: str, params: dict[str, list[str]]) -> str:
    query: dict[str, str] = {}
    if params.get("ac"):
        query["ac"] = params["ac"][0]
    if params.get("wd"):
        query["wd"] = params["wd"][0]
    if params.get("ids"):
        query["ids"] = params["ids"][0]
    if params.get("pg"):
        query["pg"] = params["pg"][0]
    if not query:
        query["ac"] = "list"
    return base + "?" + urllib.parse.urlencode(query)


class Handler(BaseHTTPRequestHandler):
    server_version = "TVBoxLunaBridge/0.1"

    def send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/health":
            return self.send_json({"ok": True, "sites": len(SITES), "supported": sum(1 for s in SITES.values() if s["engine"] == "maccms")})
        if parsed.path == "/sites":
            return self.send_json({"list": [{k: v for k, v in s.items() if k != "raw"} for s in SITES.values()]})

        match = re.match(r"^/api/([^/]+)/api\.php/provide/vod/?$", parsed.path)
        if not match:
            return self.send_json({"code": 0, "msg": "not found"}, 404)

        key = urllib.parse.unquote(match.group(1))
        site = SITES.get(key)
        if not site:
            return self.send_json({"code": 0, "msg": f"unknown site: {key}", "list": []}, 404)
        if site["engine"] != "maccms":
            return self.send_json({"code": 0, "msg": f"unsupported TVBox engine: {site.get('api')}", "list": []}, 501)

        try:
            params = urllib.parse.parse_qs(parsed.query)
            _, data = fetch_json(maccms_url(site["api"], params))
            return self.send_json(data)
        except Exception as exc:
            return self.send_json({"code": 0, "msg": f"upstream error: {type(exc).__name__}: {str(exc)[:200]}", "list": []}, 502)

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tvbox", type=Path, default=DEFAULT_TVBOX)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    global SITES
    SITES = load_sites(args.tvbox)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"bridge listening on http://{args.host}:{args.port}")
    print(f"sites={len(SITES)} supported={sum(1 for s in SITES.values() if s['engine'] == 'maccms')}")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
