#!/usr/bin/env python3
"""Convert qist TVBox jsm.json into LunaTV/MoonTVPlus Base58 config."""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
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
        except Exception as exc:  # fallback to the next mirror
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


def site_key(url: str, used: set[str], fallback: str) -> str:
    host = urllib.parse.urlsplit(url).netloc.lower()
    key = re.sub(r"[^a-z0-9.-]+", "-", host).strip(".-") or fallback or "site"
    base = key
    i = 2
    while key in used:
        key = f"{base}-{i}"
        i += 1
    used.add(key)
    return key


def detail_url(api_url: str) -> str:
    parts = urllib.parse.urlsplit(api_url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def convert_tvbox_to_lunatv(tvbox: dict[str, Any], cache_time: int = 7200) -> dict[str, Any]:
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

        key = site_key(normalized_api, used_keys, str(site.get("key") or "site"))
        api_site[key] = {
            "name": clean_name(str(site.get("name") or site.get("key") or key)),
            "api": normalized_api,
            "detail": detail_url(normalized_api),
        }

    return {"cache_time": cache_time, "api_site": api_site}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", action="append", help="TVBox jsm.json URL. Can be used multiple times.")
    parser.add_argument("--output", default="LunaTV-config.txt", help="Base58 LunaTV output path.")
    parser.add_argument("--json-output", default="LunaTV-config.json", help="Decoded JSON output path for inspection.")
    parser.add_argument("--cache-time", type=int, default=7200)
    args = parser.parse_args()

    urls = args.upstream or DEFAULT_UPSTREAMS
    text, used_url = fetch_text(urls)
    tvbox = json.loads(text)
    lunatv = convert_tvbox_to_lunatv(tvbox, cache_time=args.cache_time)

    if not lunatv["api_site"]:
        raise RuntimeError("no compatible provide/vod sites found in upstream")

    json_text = json.dumps(lunatv, ensure_ascii=False, indent=2) + "\n"
    encoded = b58encode(json_text.encode("utf-8"))

    Path(args.json_output).write_text(json_text, encoding="utf-8", newline="\n")
    Path(args.output).write_text(encoded, encoding="utf-8", newline="")

    print(f"upstream={used_url}")
    print(f"sites={len(lunatv['api_site'])}")
    print(f"json={args.json_output}")
    print(f"encoded={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
