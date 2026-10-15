#!/usr/bin/env python3
"""Bounded, read-only inspection of the Dunkest profile's per-game tab API."""
from __future__ import annotations
import asyncio, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/dunkest_profile_games_api_inspection_v2.json"
URL = "https://www.dunkest.com/it/giocatore/127/luka-doncic"
SEASONS = ["1", "3", "19", "25"]

async def main():
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {OUT}")
    responses, tasks, ui = [], [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="it-IT")
        page = await context.new_page()
        page.set_default_timeout(7000)
        async def capture(resp):
            parsed = urlparse(resp.url)
            if "/api/" not in parsed.path and "graphql" not in parsed.path.lower():
                return
            item = {"url": resp.url, "status": resp.status, "method": resp.request.method,
                    "content_type": resp.headers.get("content-type", "")}
            try:
                body = await resp.body()
                item["bytes"] = len(body)
                item["sha256"] = hashlib.sha256(body).hexdigest()
                try:
                    data = json.loads(body)
                    item["json_type"] = type(data).__name__
                    if isinstance(data, list):
                        item["rows"] = len(data)
                        if data and isinstance(data[0], dict):
                            item["row_keys"] = list(data[0].keys())[:80]
                            item["samples"] = data[:3]
                    elif isinstance(data, dict):
                        item["keys"] = list(data.keys())[:80]
                        item["preview"] = {k: (v if isinstance(v,(str,int,float,bool,type(None))) else f"<{type(v).__name__}:{len(v) if hasattr(v,'__len__') else '?'}>") for k,v in list(data.items())[:25]}
                    else: item["preview"] = repr(data)[:300]
                except Exception: item["text_preview"] = body[:300].decode("utf-8", "replace")
            except Exception as e: item["body_error"] = repr(e)[:200]
            responses.append(item)
            print("API", resp.status, resp.request.method, resp.url[:240], flush=True)
        page.on("response", lambda resp: tasks.append(asyncio.create_task(capture(resp))))
        nav_error = None
        try:
            await page.goto(URL, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2500)
            ui.append({"step":"initial", "url":page.url, "title":await page.title()})
            # Trigger the actual Partite tab via DOM, bypassing cookie overlays.
            await page.evaluate("""() => { const e=[...document.querySelectorAll('[data-tab-id=\"games\"]')].find(x=>x.tagName.toLowerCase()==='span'); if(e)e.click(); }""")
            await page.wait_for_timeout(2200)
            try:
                ui.append({"step":"games_tab", "text":(await page.locator('[data-tab-id="games"]').last.inner_text())[:1800]})
            except Exception as e: ui.append({"step":"games_tab", "error":repr(e)[:200]})
            for season in SEASONS:
                try:
                    changed = await page.evaluate("""(season) => { const s=document.querySelector('#seasonSelect'); if(!s)return {error:'no season select'}; s.value=season; s.dispatchEvent(new Event('input',{bubbles:true})); s.dispatchEvent(new Event('change',{bubbles:true})); return {value:s.value, options:[...s.options].map(o=>({value:o.value,text:o.textContent.trim()}))}; }""", season)
                    await page.wait_for_timeout(1800)
                    try: text = (await page.locator('[data-tab-id="games"]').last.inner_text())[:1800]
                    except Exception as e: text = 'read error '+repr(e)[:200]
                    ui.append({"step":"season", "season_id":season, "select":changed, "games_text":text})
                except Exception as e: ui.append({"step":"season", "season_id":season, "error":repr(e)[:300]})
        except Exception as e: nav_error = repr(e)
        await page.wait_for_timeout(1000)
        for t in tasks:
            try: await asyncio.wait_for(t, timeout=3)
            except Exception: pass
        result = {"captured_at_utc":datetime.now(timezone.utc).isoformat(), "url":URL,
                  "navigation_error":nav_error, "ui_checks":ui, "api_responses":responses}
        await browser.close()
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({"output":str(OUT.relative_to(ROOT)),"response_count":len(responses),
                      "api_urls":[x['url'] for x in responses],"ui_steps":len(ui),"navigation_error":nav_error},ensure_ascii=False,indent=2))

if __name__ == '__main__': asyncio.run(main())
