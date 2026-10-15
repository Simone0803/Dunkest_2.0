
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = (
    "https://www.dunkest.com/it/nba/statistiche/"
    "giocatori/tabellone?iframe=yes"
)

OUT = Path("data/raw/dunkest_stats_inspection")
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})

    responses = []

    def record_response(response):
        if "dunkest.com" in response.url:
            try:
                content_type = response.headers.get("content-type", "")
            except Exception:
                content_type = ""

            responses.append({
                "status": response.status,
                "url": response.url,
                "content_type": content_type,
            })

    page.on("response", record_response)

    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)

        page.screenshot(
            path=str(OUT / "stats_iframe.png"),
            full_page=True,
        )

        print("URL finale:", page.url)
        print("Titolo:", page.title())
        print("Testo visibile:")
        print(page.locator("body").inner_text()[:12000])

        print("\nTABELLE HTML:", page.locator("table").count())
        print("RIGHE HTML:", page.locator("tr").count())

        print("\nRICHIESTE DI RETE:")
        for response in responses:
            print(response)

        (OUT / "iframe_responses.json").write_text(
            __import__("json").dumps(
                responses, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )

        input("\nPremi INVIO per chiudere il browser...")
    finally:
        browser.close()
