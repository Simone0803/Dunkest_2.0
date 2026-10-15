#!/usr/bin/env python3
"""Inspect public network responses on a Dunkest player profile (no production writes)."""
from __future__ import annotations
import asyncio, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/dunkest_profile_api_inspection_luka_v1.json"
PLAYER_URL = "https://www.dunkest.com/it/giocatore/127/luka-doncic"

async def main() -> None:
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {OUT}")
    captured = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="it-IT")
        page = await context.new_page()
        async def on_response(response):
            url = response.url
            parsed = urlparse(url)
            if "/api/" not in parsed.path and "graphql" not in parsed.path.lower():
                return
            item = {"url": url, "status": response.status,
                    "content_type": response.headers.get("content-type", ""),
                    "method": response.request.method}
            try:
                body = await response.body()
                item["body_bytes"] = len(body)
                item["body_sha256"] = hashlib.sha256(body).hexdigest()
                if "json" in item["content_type"].lower() or body[:1] in (b"{", b"["):
                    try:
                        data = json.loads(body)
                        item["json_type"] = type(data).__name__
                        item["json_keys"] = list(data.keys())[:80] if isinstance(data, dict) else []
                        item["json_rows"] = len(data) if isinstance(data, list) else None
                        if isinstance(data, list) and data and isinstance(data[0], dict):
                            item["first_row_keys"] = list(data[0].keys())[:80]
                            item["first_row_sample"] = {k: data[0].get(k) for k in list(data[0])[:12]}
                        elif isinstance(data, dict):
                            item["json_preview"] = {k: (v if isinstance(v, (str, int, float, bool, type(None))) else f"<{type(v).__name__}:{len(v) if hasattr(v, '__len__') else '?'}>") for k,v in list(data.items())[:30]}
                    except Exception as exc:
                        item["json_parse_error"] = str(exc)[:200]
            except Exception as exc:
                item["body_error"] = str(exc)[:200]
            captured.append(item)
            print(f"HTTP {item['status']} {item['method']} {url[:230]}")
        page.on("response", lambda response: asyncio.create_task(on_response(response)))
        nav_error = None
        try:
            await page.goto(PLAYER_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(9000)
            for frame in page.frames:
                try: await frame.wait_for_timeout(1000)
                except Exception: pass
        except Exception as exc:
            nav_error = repr(exc)
        result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
                  "page_url": PLAYER_URL, "final_url": page.url, "navigation_error": nav_error,
                  "title": await page.title(),
                  "frames": [{"url": f.url, "name": f.name} for f in page.frames],
                  "api_responses": captured}
        await browser.close()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "api_response_count": len(captured),
                      "api_urls": [x["url"] for x in captured]}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
