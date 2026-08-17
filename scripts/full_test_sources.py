#!/usr/bin/env python3
"""Full source test for qist TVBox -> LunaTV bridge.

Writes full-test-report.json and full-test-report.md.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TVBOX_PATH = ROOT / "tvbox-jsm.json"
BRIDGE = ROOT / "bridge" / "tvbox_luna_bridge.py"
KEYWORDS = ["斗罗", "凡人", "庆余年", "仙逆"]


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


def classify_engine(api: Any) -> str:
    if isinstance(api, str) and api.startswith(("http://", "https://")) and "provide/vod" in api:
        return "maccms"
    if isinstance(api, str) and api.startswith(("http://", "https://")):
        return "remote_js"
    if isinstance(api, str) and api.startswith("./py/"):
        return "local_py"
    if isinstance(api, str) and api.startswith("./"):
        return "local_js"
    if isinstance(api, str) and api.startswith("csp_"):
        return "csp"
    return "other"


def load_sites() -> list[dict[str, Any]]:
    tvbox = json.loads(TVBOX_PATH.read_text(encoding="utf-8"))
    used: set[str] = set()
    out: list[dict[str, Any]] = []
    for idx, site in enumerate(tvbox.get("sites", []), 1):
        if not isinstance(site, dict):
            continue
        key = safe_key(str(site.get("key") or f"site_{idx}"), used, f"site_{idx}")
        api = site.get("api")
        out.append({"index": idx, "key": key, "name": site.get("name") or site.get("key") or key, "api": api, "engine": classify_engine(api)})
    return out


def urlopen_json(url: str, timeout: int = 15, limit: int = 4 * 1024 * 1024) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json,text/plain,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(limit)
    return json.loads(body.decode("utf-8-sig", "replace"))


def test_maccms(site: dict[str, Any]) -> dict[str, Any]:
    base = normalize_maccms_api(str(site["api"]))
    last_error = "no keyword tested"
    saw_json = False
    for kw in KEYWORDS:
        url = base + "?ac=videolist&wd=" + urllib.parse.quote(kw)
        try:
            data = urlopen_json(url)
            items = data.get("list") if isinstance(data, dict) else None
            if not isinstance(items, list):
                last_error = f"{kw}: JSON without list[]"
                continue
            saw_json = True
            playable = sum(1 for item in items if isinstance(item, dict) and ".m3u8" in str(item.get("vod_play_url", "")))
            if playable:
                return {"status": "playable", "api": base, "keyword": kw, "results": len(items), "playable": playable}
            last_error = f"{kw}: list={len(items)}, playable_m3u8=0"
        except Exception as exc:
            last_error = f"{kw}: {type(exc).__name__}: {str(exc)[:180]}"
    return {"status": "json_no_playable" if saw_json else "upstream_error", "api": base, "error": last_error}


def wait_health(port: int) -> dict[str, Any]:
    for _ in range(30):
        try:
            return urlopen_json(f"http://127.0.0.1:{port}/health", timeout=2)
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("bridge did not start")


def test_bridge_endpoint(site: dict[str, Any], port: int) -> dict[str, Any]:
    kw = urllib.parse.quote(KEYWORDS[0])
    key = urllib.parse.quote(site["key"])
    url = f"http://127.0.0.1:{port}/api/{key}/api.php/provide/vod?ac=videolist&wd={kw}"
    try:
        data = urlopen_json(url, timeout=30)
        items = data.get("list") if isinstance(data, dict) else []
        playable = sum(1 for item in items if isinstance(item, dict) and ".m3u8" in str(item.get("vod_play_url", "")))
        return {"http": 200, "code": data.get("code"), "results": len(items), "playable": playable, "msg": data.get("msg", "")}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8-sig", "replace")
        try:
            data = json.loads(body)
        except Exception:
            data = {"msg": body[:160]}
        return {"http": exc.code, "code": data.get("code"), "results": 0, "playable": 0, "msg": data.get("msg", "")}
    except Exception as exc:
        return {"http": 0, "code": 0, "results": 0, "playable": 0, "msg": f"{type(exc).__name__}: {str(exc)[:180]}"}


def main() -> int:
    sites = load_sites()
    maccms = [s for s in sites if s["engine"] == "maccms"]
    direct_results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(test_maccms, site): site for site in maccms}
        for future in as_completed(futures):
            site = futures[future]
            direct_results[site["key"]] = future.result()

    port = 8789
    proc = subprocess.Popen([sys.executable, str(BRIDGE), "--host", "127.0.0.1", "--port", str(port), "--tvbox", str(TVBOX_PATH)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    try:
        health = wait_health(port)
        bridge_results: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(test_bridge_endpoint, site, port): site for site in sites}
            for future in as_completed(futures):
                site = futures[future]
                bridge_results[site["key"]] = future.result()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    rows: list[dict[str, Any]] = []
    for site in sites:
        direct = direct_results.get(site["key"], {"status": "not_applicable"})
        bridge = bridge_results.get(site["key"], {})
        if site["engine"] == "maccms" and direct.get("status") == "playable" and bridge.get("playable", 0) > 0:
            final = "usable"
        elif site["engine"] == "maccms":
            final = direct.get("status", "failed")
        else:
            final = "needs_engine_adapter"
        rows.append({"index": site["index"], "key": site["key"], "name": site["name"], "engine": site["engine"], "final": final, "direct": direct, "bridge": bridge})

    summary: dict[str, Any] = {"total_sites": len(sites), "health": health, "by_engine": {}, "by_final": {}, "rows": rows}
    for row in rows:
        summary["by_engine"][row["engine"]] = summary["by_engine"].get(row["engine"], 0) + 1
        summary["by_final"][row["final"]] = summary["by_final"].get(row["final"], 0) + 1

    (ROOT / "full-test-report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = ["# Full TVBox → LunaTV test report", "", f"Total sites: {summary['total_sites']}", "", "## Summary", ""]
    for k, v in sorted(summary["by_final"].items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "## Usable sources", ""]
    for row in rows:
        if row["final"] == "usable":
            d = row["direct"]
            lines.append(f"- {row['key']} / {row['name']}：keyword={d.get('keyword')} results={d.get('results')} playable={d.get('playable')}")
    lines += ["", "## Not usable yet", ""]
    for row in rows:
        if row["final"] != "usable":
            msg = row["direct"].get("error") or row["bridge"].get("msg") or row["final"]
            lines.append(f"- {row['key']} / {row['name']}：{row['final']} / {msg}")
    (ROOT / "full-test-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"by_final": summary["by_final"], "by_engine": summary["by_engine"], "health": health}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
