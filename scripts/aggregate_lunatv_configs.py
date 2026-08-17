#!/usr/bin/env python3
"""Aggregate maintained LunaTV/MoonTVPlus configs into two outputs.

Outputs:
- aggregated.json / aggregated.txt: normal sources only
- aggregated-plus18.json / aggregated-plus18.txt: normal + 18+ sources
"""
from __future__ import annotations

import json
import re
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Any

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

NORMAL_SOURCES = [
    "https://raw.githubusercontent.com/hafrey1/LunaTV-config/main/LunaTV-config.txt",
    "https://raw.githubusercontent.com/qianqikun/LunaTV-config/main/LunaTV-config.txt",
    "https://raw.githubusercontent.com/netput-web/LunaTV-config/main/LunaTV-config.txt",
    "https://raw.githubusercontent.com/smallmain/moontv-aggr-config/main/full.txt",
]

PLUS18_SOURCES = NORMAL_SOURCES + [
    "https://raw.githubusercontent.com/hafrey1/LunaTV-config/main/jin18.txt",
    "https://raw.githubusercontent.com/qianqikun/LunaTV-config/main/jin18.txt",
    "https://raw.githubusercontent.com/netput-web/LunaTV-config/main/jin18.txt",
    "https://raw.githubusercontent.com/smallmain/moontv-aggr-config/main/full-plus18.txt",
]


def b58decode(text: str) -> bytes:
    n = 0
    for ch in text.strip():
        n = n * 58 + BASE58_ALPHABET.index(ch)
    data = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\0" * (len(text.strip()) - len(text.strip().lstrip("1"))) + data


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    chars: list[str] = []
    while n:
        n, rem = divmod(n, 58)
        chars.append(BASE58_ALPHABET[rem])
    encoded = "".join(reversed(chars)) or "1"
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + encoded


def fetch_config(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "qist-lunatv-aggregator/1.0"})
    body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8-sig").strip()
    if body.startswith("{"):
        return json.loads(body)
    return json.loads(b58decode(body).decode("utf-8-sig"))


def safe_key(raw: str, used: set[str], fallback: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw or fallback).strip("_") or fallback
    key = key[:80]
    base = key
    i = 2
    while key in used:
        suffix = f"_{i}"
        key = f"{base[:80-len(suffix)]}{suffix}"
        i += 1
    used.add(key)
    return key


def api_identity(site: dict[str, Any]) -> str:
    api = str(site.get("api") or "").strip().rstrip("/")
    detail = str(site.get("detail") or "").strip().rstrip("/")
    return api.lower() or detail.lower()


def aggregate(urls: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    api_site: OrderedDict[str, dict[str, Any]] = OrderedDict()
    lives: OrderedDict[str, dict[str, Any]] = OrderedDict()
    seen_api: set[str] = set()
    used_keys: set[str] = set()
    used_live_keys: set[str] = set()
    report: dict[str, Any] = {"sources": [], "skipped_duplicates": 0, "failed": []}

    for url in urls:
        try:
            cfg = fetch_config(url)
        except Exception as exc:
            report["failed"].append({"url": url, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue

        added = 0
        duplicated = 0
        for raw_key, site in (cfg.get("api_site") or {}).items():
            if not isinstance(site, dict):
                continue
            ident = api_identity(site)
            if not ident or ident in seen_api:
                duplicated += 1
                continue
            seen_api.add(ident)
            key = safe_key(str(raw_key), used_keys, f"site_{len(api_site)+1}")
            clean_site = {"name": site.get("name") or key, "api": site.get("api") or ""}
            if site.get("detail"):
                clean_site["detail"] = site.get("detail")
            api_site[key] = clean_site
            added += 1

        for raw_key, live in (cfg.get("lives") or {}).items():
            if not isinstance(live, dict):
                continue
            key = safe_key(str(raw_key), used_live_keys, f"live_{len(lives)+1}")
            lives[key] = live

        report["sources"].append({"url": url, "api_site": len(cfg.get("api_site") or {}), "added": added, "duplicates": duplicated})
        report["skipped_duplicates"] += duplicated

    out: dict[str, Any] = {"cache_time": 7200, "api_site": api_site}
    if lives:
        out["lives"] = lives
    report["total_api_site"] = len(api_site)
    report["total_lives"] = len(lives)
    return out, report


def write(name: str, cfg: dict[str, Any]) -> None:
    text = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"
    Path(f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
    Path(f"{name}.txt").write_text(b58encode(text.encode("utf-8")), encoding="utf-8", newline="")


def main() -> int:
    normal, normal_report = aggregate(NORMAL_SOURCES)
    plus18, plus18_report = aggregate(PLUS18_SOURCES)
    write("aggregated", normal)
    write("aggregated-plus18", plus18)
    Path("aggregation-report.json").write_text(json.dumps({"normal": normal_report, "plus18": plus18_report}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("normal", normal_report["total_api_site"], "plus18", plus18_report["total_api_site"])
    if normal_report["failed"] or plus18_report["failed"]:
        print("failed sources exist, see aggregation-report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
