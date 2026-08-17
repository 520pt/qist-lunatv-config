#!/usr/bin/env python3
"""Convert qist TVBox jsm.json into LunaTV/MoonTVPlus Base58 configs.

Two outputs are generated:
- LunaTV-config.txt: compatible/recommended config with direct MacCMS provide/vod APIs.
- LunaTV-config-all.txt: all TVBox sites preserved in api_site shape for users who explicitly want every entry.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict
from pathlib import Path
from typing import Any

DEFAULT_UPSTREAMS = [
    "https://v6.gh-proxy.org/https://raw.githubusercontent.com/qist/tvbox/master/jsm.json",
    "https://raw.githubusercontent.com/qist/tvbox/master/jsm.json",
]
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def fetch_text(urls: list[str], timeout: int = 30) -> tuple[str, str]:
    last_error: Exception | None = None
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "qist-lunatv-config/1.0",
                    "Accept": "application/json,text/plain,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            return body.decode("utf-8-sig"), url
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"failed to fetch upstream: {last_error}")


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    chars: list[str] = []
    while n:
        n, rem = divmod(n, 58)
        chars.append(BASE58_ALPHABET[rem])
    encoded = "".join(reversed(chars)) or "1"
    leading_zeroes = len(data) - len(data.lstrip(b"\0"))
    return "1" * leading_zeroes + encoded


def clean_name(name: str) -> str:
    name = name or ""
    parts = [part.strip() for part in re.split(r"\s*•\s*", name) if part.strip()]
    if len(parts) > 1 and parts[0] in {"影视", "搜索", "配置", "新片"}:
        name = parts[-1]
    else:
        name = "".join(parts) or name
    name = re.sub(r"[\[【(（].*?(直连|采集).*?[\]】)）]", "", name)
    name = name.strip(" -_·•")
    return f"🎬{name}" if name else "🎬未命名"


def normalize_api_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    path = re.sub(r"/+$", "", parts.path)
    path = re.sub(r"/at/(xml|json)$", "", path, flags=re.IGNORECASE)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def safe_key(raw: str, used: set[str], fallback: str = "site") -> str:
    key = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw or fallback).strip("_") or fallback
    # LunaTV/MoonTVPlus docs prefer simple key names.
    key = key[:80]
    base = key
    i = 2
    while key in used:
        suffix = f"_{i}"
        key = f"{base[:80 - len(suffix)]}{suffix}"
        i += 1
    used.add(key)
    return key


def site_key_from_url(url: str, used: set[str], fallback: str) -> str:
    host = urllib.parse.urlsplit(url).netloc.lower().replace(":", "_")
    return safe_key(host, used, fallback)


def detail_url(api_url: str) -> str:
    parts = urllib.parse.urlsplit(api_url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))


SEARCH_TEST_KEYWORDS = ["斗罗", "凡人", "庆余年", "仙逆"]


def build_lives(tvbox: dict[str, Any]) -> OrderedDict[str, dict[str, Any]]:
    lives: OrderedDict[str, dict[str, Any]] = OrderedDict()
    used_live_keys: set[str] = set()
    for index, live in enumerate(tvbox.get("lives", []), start=1):
        if not isinstance(live, dict):
            continue
        live_key = safe_key(str(live.get("name") or f"live_{index}"), used_live_keys, f"live_{index}")
        lives[live_key] = {
            "name": str(live.get("name") or live_key),
            "url": str(live.get("url") or ""),
            "ua": live.get("ua"),
            "epg": live.get("epg"),
        }
    return lives


def candidate_compatible_sites(tvbox: dict[str, Any]) -> OrderedDict[str, dict[str, str]]:
    api_site: OrderedDict[str, dict[str, str]] = OrderedDict()
    used_keys: set[str] = set()
    used_apis: set[str] = set()

    for site in tvbox.get("sites", []):
        if not isinstance(site, dict):
            continue
        api = site.get("api")
        if not isinstance(api, str):
            continue
        if "://" not in api or "provide/vod" not in api:
            continue

        normalized_api = normalize_api_url(api)
        if normalized_api in used_apis:
            continue
        used_apis.add(normalized_api)

        key = site_key_from_url(normalized_api, used_keys, str(site.get("key") or "site"))
        api_site[key] = {
            "name": clean_name(str(site.get("name") or site.get("key") or key)),
            "api": normalized_api,
            "detail": detail_url(normalized_api),
        }

    return api_site


def validate_one_site(key: str, site: dict[str, str], timeout: int = 10) -> tuple[str, bool, dict[str, Any]]:
    """Validate exactly like MoonTVPlus search: api + ?ac=videolist&wd=keyword.

    MoonTVPlus filters search results without .m3u8 episodes, so a source is marked
    supported only when at least one tested keyword returns JSON list items containing
    playable .m3u8 URLs.
    """
    last_error = "no tested keyword returned playable m3u8 results"
    for keyword in SEARCH_TEST_KEYWORDS:
        url = site["api"] + "?ac=videolist&wd=" + urllib.parse.quote(keyword)
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json,text/plain,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(2 * 1024 * 1024).decode("utf-8-sig", "replace")
            data = json.loads(body)
            items = data.get("list") if isinstance(data, dict) else None
            if not isinstance(items, list):
                last_error = f"{keyword}: response has no list array"
                continue
            playable = sum(
                1
                for item in items
                if isinstance(item, dict) and ".m3u8" in str(item.get("vod_play_url", ""))
            )
            if playable > 0:
                return key, True, {
                    "name": site["name"],
                    "api": site["api"],
                    "keyword": keyword,
                    "results": len(items),
                    "playable": playable,
                }
            last_error = f"{keyword}: list={len(items)}, playable_m3u8=0"
        except Exception as exc:
            last_error = f"{keyword}: {type(exc).__name__}: {str(exc)[:160]}"
    return key, False, {"name": site["name"], "api": site["api"], "error": last_error}


def validate_compatible_sites(api_site: OrderedDict[str, dict[str, str]]) -> tuple[OrderedDict[str, dict[str, str]], dict[str, Any]]:
    supported: OrderedDict[str, dict[str, str]] = OrderedDict()
    report: dict[str, Any] = {"tested_keywords": SEARCH_TEST_KEYWORDS, "supported": [], "unsupported": []}

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(validate_one_site, key, site) for key, site in api_site.items()]
        results = {future.result()[0]: future.result() for future in as_completed(futures)}

    for key, site in api_site.items():
        _, ok, info = results[key]
        if ok:
            supported[key] = site
            report["supported"].append({"key": key, **info})
        else:
            report["unsupported"].append({"key": key, **info})

    return supported, report


def convert_compatible(tvbox: dict[str, Any], cache_time: int = 7200, validate: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = candidate_compatible_sites(tvbox)
    if validate:
        api_site, report = validate_compatible_sites(candidates)
    else:
        api_site = candidates
        report = {"tested_keywords": [], "supported": [], "unsupported": [], "validation_skipped": True}
    config: dict[str, Any] = {"cache_time": cache_time, "api_site": api_site, "lives": build_lives(tvbox)}
    report["candidate_count"] = len(candidates)
    report["supported_count"] = len(api_site)
    report["live_count"] = len(config["lives"])
    return config, report


def first_http_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value if value.startswith(("http://", "https://")) else None
    if isinstance(value, list):
        for item in value:
            found = first_http_value(item)
            if found:
                return found
    if isinstance(value, dict):
        # Prefer likely endpoint fields first, then any URL.
        for key in ("url", "host", "site", "分类url", "主页url", "搜索url"):
            found = first_http_value(value.get(key))
            if found:
                return found
        for item in value.values():
            found = first_http_value(item)
            if found:
                return found
    return None


def convert_all_preserved(tvbox: dict[str, Any], cache_time: int = 7200) -> dict[str, Any]:
    """Preserve every TVBox site in LunaTV api_site shape.

    This intentionally includes non-MacCMS TVBox entries. LunaTV/MoonTVPlus can load the
    config, but only entries backed by a real Apple CMS V10 endpoint are expected to work.
    The original TVBox fields are kept under _tvbox for traceability.
    """
    api_site: OrderedDict[str, dict[str, Any]] = OrderedDict()
    used_keys: set[str] = set()

    for index, site in enumerate(tvbox.get("sites", []), start=1):
        if not isinstance(site, dict):
            continue
        raw_key = str(site.get("key") or f"site_{index}")
        key = safe_key(raw_key, used_keys, f"site_{index}")
        api = site.get("api")
        ext = site.get("ext")

        if isinstance(api, str) and api.startswith(("http://", "https://")):
            preserved_api = normalize_api_url(api) if "provide/vod" in api else api
        else:
            preserved_api = first_http_value(ext) or str(api or "")

        entry: dict[str, Any] = {
            "name": clean_name(str(site.get("name") or site.get("key") or key)),
            "api": preserved_api,
            "detail": detail_url(preserved_api) if preserved_api.startswith(("http://", "https://")) else "",
            "_tvbox": {
                "key": site.get("key"),
                "name": site.get("name"),
                "type": site.get("type"),
                "api": site.get("api"),
                "ext": site.get("ext"),
                "compatible": isinstance(preserved_api, str) and "provide/vod" in preserved_api,
            },
        }
        api_site[key] = entry

    return {
        "cache_time": cache_time,
        "api_site": api_site,
        "lives": build_lives(tvbox),
        "_note": "全量保留版：包含 TVBox 的全部 sites；LunaTV/MoonTVPlus 原生只支持标准苹果 CMS V10 API，非 provide/vod 条目可能只能加载，不能搜索播放。",
    }


def write_config(data: dict[str, Any], json_output: str, encoded_output: str) -> None:
    json_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    encoded = b58encode(json_text.encode("utf-8"))
    Path(json_output).write_text(json_text, encoding="utf-8", newline="\n")
    Path(encoded_output).write_text(encoded, encoding="utf-8", newline="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", action="append", help="TVBox jsm.json URL. Can be used multiple times.")
    parser.add_argument("--cache-time", type=int, default=7200)
    parser.add_argument("--skip-validation", action="store_true", help="Do not probe candidate APIs before writing compatible config.")
    args = parser.parse_args()

    urls = args.upstream or DEFAULT_UPSTREAMS
    text, used_url = fetch_text(urls)
    tvbox = json.loads(text)

    compatible, validation_report = convert_compatible(
        tvbox, cache_time=args.cache_time, validate=not args.skip_validation
    )
    all_preserved = convert_all_preserved(tvbox, cache_time=args.cache_time)

    if not compatible["api_site"]:
        raise RuntimeError("no validated playable provide/vod sites found in upstream")
    if len(all_preserved["api_site"]) != len(tvbox.get("sites", [])):
        raise RuntimeError("all-sites output did not preserve every TVBox site")

    write_config(compatible, "LunaTV-config.json", "LunaTV-config.txt")
    write_config(all_preserved, "LunaTV-config-all.json", "LunaTV-config-all.txt")

    Path("tvbox-jsm.json").write_text(json.dumps(tvbox, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    Path("validation-report.json").write_text(json.dumps(validation_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    print(f"upstream={used_url}")
    print(f"candidate_sites={validation_report.get('candidate_count')}")
    print(f"validated_supported_sites={len(compatible['api_site'])}")
    print(f"all_sites={len(all_preserved['api_site'])}")
    print(f"lives={len(all_preserved.get('lives', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
