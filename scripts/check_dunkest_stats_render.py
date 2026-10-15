
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE = Path.home() / ".dunkest-optimizer" / "stats-browser-profile"
OUT = Path("data/raw/dunkest_stats_inspection")
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        headless=False,
    )

    try:
        page = context.new_page()
        page.goto(
            "https://fantasy.dunkest.com/1/stats",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_timeout(10000)

        screenshot = OUT / "stats_render.png"
        page.screenshot(path=str(screenshot), full_page=True)

        info = page.evaluate("""() => ({
            url: location.href,
            title: document.title,
            viewport: {
                width: innerWidth,
                height: innerHeight
            },
            flutterView: !!document.querySelector('flutter-view'),
            canvasCount: document.querySelectorAll('canvas').length,
            semanticsPlaceholder: !!document.querySelector(
                'flt-semantics-placeholder'
            ),
            bodyHTML: document.body.innerHTML.slice(0, 3000)
        })""")

        print(info)
        print(f"Screenshot salvato in: {screenshot}")
        input("Premi INVIO per chiudere il browser...")
    finally:
        context.close()

