#!/usr/bin/env python3
"""Generate LunaTV config that points every TVBox site to tvbox_luna_bridge."""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from collections import OrderedDict
from pathlib import Path
from typing import Any

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ROOT = Path(__file__).resolve().parents[1]


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    chars: list[str] = []
    while n:
        n, rem = divmod(n, 58)
        chars.append(BASE58_ALPHABET[rem])
    encoded = "".join(reversed(chars)) or "1"
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + encoded


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tvbox", type=Path, default=ROOT / "tvbox-jsm.json")
    parser.add_argument("--base-url", required=True, help="Public bridge base URL, e.g. https://bridge.example.com")
    parser.add_argument("--output", default="LunaTV-config-bridge.txt")
    parser.add_argument("--json-output", default="LunaTV-config-bridge.json")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    tvbox = json.loads(args.tvbox.read_text(encoding="utf-8"))
    used: set[str] = set()
    api_site: OrderedDict[str, dict[str, str]] = OrderedDict()
    for idx, site in enumerate(tvbox.get("sites", []), 1):
        if not isinstance(site, dict):
            continue
        key = safe_key(str(site.get("key") or f"site_{idx}"), used, f"site_{idx}")
        api_site[key] = {
            "name": clean_name(str(site.get("name") or site.get("key") or key)),
            "api": f"{base}/api/{urllib.parse.quote(key)}/api.php/provide/vod",
            "detail": f"{base}/api/{urllib.parse.quote(key)}",
        }

    cfg: dict[str, Any] = {"cache_time": 7200, "api_site": api_site}
    json_text = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"
    Path(args.json_output).write_text(json_text, encoding="utf-8", newline="\n")
    Path(args.output).write_text(b58encode(json_text.encode("utf-8")), encoding="utf-8", newline="")
    print(f"sites={len(api_site)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
