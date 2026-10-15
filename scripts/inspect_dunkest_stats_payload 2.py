
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

OUT_DIR = Path("data/raw/dunkest_stats_inspection")
STATS_URL = (
    "https://www.dunkest.com/it/nba/statistiche/"
    "giocatori/tabellone?iframe=yes"
)


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="it-IT")
        page = await context.new_page()

        async def on_response(response):
            url = response.url
            if "/api/stats/" not in url:
                return

            item = {
                "status": response.status,
                "url": url,
                "content_type": response.headers.get("content-type", ""),
            }

            try:
                item["body"] = await response.json()
            except Exception:
                try:
                    item["body_text"] = (await response.text())[:5000]
                except Exception as exc:
                    item["body_error"] = str(exc)

            captured.append(item)
            print(
                f"API intercettata: HTTP {response.status} "
                f"{url[:180]}"
            )

        page.on("response", lambda response: asyncio.create_task(
            on_response(response)
        ))

        print("Apro le statistiche...")
        await page.goto(
            STATS_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await page.wait_for_timeout(7000)

        # La pagina può contenere un iframe: attendiamo anche le sue API.
        for frame in page.frames:
            try:
                await frame.wait_for_timeout(1000)
            except Exception:
                pass

        payload = {
            "page_url": page.url,
            "frames": [
                {"url": frame.url, "name": frame.name}
                for frame in page.frames
            ],
            "api_responses": captured,
        }

        output = OUT_DIR / "browser_api_responses.json"
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("\nURL pagina:", page.url)
        print("Frame individuati:", len(page.frames))
        print("Risposte API catturate:", len(captured))
        print("File salvato:", output)

        for index, item in enumerate(captured):
            print(f"\n--- RISPOSTA API {index + 1} ---")
            print("HTTP:", item["status"])
            print("URL:", item["url"][:500])

            body = item.get("body")
            if isinstance(body, dict):
                print("Chiavi JSON:", list(body.keys()))
            elif isinstance(body, list):
                print("Elementi JSON:", len(body))
                if body:
                    print("Primo elemento:", repr(body[0])[:1000])
            else:
                print("Corpo:", repr(item.get("body_text", ""))[:1000])

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
