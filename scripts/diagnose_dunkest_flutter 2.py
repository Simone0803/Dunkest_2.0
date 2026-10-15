from pathlib import Path
import json

from playwright.sync_api import sync_playwright

PROFILE = Path.home() / ".dunkest-optimizer" / "stats-browser-profile"
URL = "https://fantasy.dunkest.com/1/stats"


def main():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            print("\nURL:", page.url)
            print("Attivo:", page.evaluate("document.activeElement?.tagName"))

            result = page.evaluate("""() => {
              const out = [];
              const pending = [document];
              const seen = new Set();

              while (pending.length) {
                const root = pending.pop();

                for (const el of root.querySelectorAll('*')) {
                  if (el.shadowRoot) pending.push(el.shadowRoot);

                  const tag = el.tagName.toLowerCase();
                  if (!tag.startsWith('flt-')) continue;

                  const item = {
                    tag,
                    role: el.getAttribute('role'),
                    label: el.getAttribute('aria-label'),
                    text: (el.innerText || el.textContent || '').trim().slice(0, 200),
                    children: el.children.length
                  };

                  const key = JSON.stringify(item);
                  if (!seen.has(key)) {
                    seen.add(key);
                    out.push(item);
                  }
                }
              }

              return {
                bodyText: (document.body.innerText || '').slice(0, 3000),
                flutterNodes: out.slice(0, 150)
              };
            }""")

            print(json.dumps(result, ensure_ascii=False, indent=2))
            input("\nPremi INVIO per chiudere...")

        except EOFError:
            print("Input non disponibile.")
        finally:
            context.close()


if __name__ == "__main__":
    main()
