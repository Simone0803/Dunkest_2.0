from pathlib import Path
import json

from playwright.sync_api import sync_playwright

PROFILE = Path.home() / ".dunkest-optimizer" / "stats-browser-profile"
URL = "https://fantasy.dunkest.com/1/stats"
OUTPUT = Path("data/raw/dunkest_stats_inspection/accessibility_test.json")


def main():
    PROFILE.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            print("URL iniziale:", page.url)

            # Tentativo 1: clic JavaScript sul placeholder Flutter.
            clicked = page.evaluate("""() => {
              const pending = [document];

              while (pending.length) {
                const root = pending.pop();

                for (const el of root.querySelectorAll('*')) {
                  if (el.shadowRoot) pending.push(el.shadowRoot);

                  if (
                    el.tagName.toLowerCase() ===
                    'flt-semantics-placeholder'
                  ) {
                    el.click();
                    return true;
                  }
                }
              }

              return false;
            }""")

            print("Placeholder attivato:", clicked)
            page.wait_for_timeout(2000)

            # Tentativo 2: clic al centro del controllo, se necessario.
            remaining = page.locator("flt-semantics-placeholder").count()

            if remaining:
                rect = page.locator(
                    "flt-semantics-placeholder"
                ).evaluate("""el => {
                  const r = el.getBoundingClientRect();
                  return {
                    x: r.x,
                    y: r.y,
                    width: r.width,
                    height: r.height
                  };
                }""")

                print("Posizione placeholder:", rect)

                if rect["width"] > 0 and rect["height"] > 0:
                    page.mouse.click(
                        max(1, rect["x"] + rect["width"] / 2),
                        max(1, rect["y"] + rect["height"] / 2),
                    )
                    page.wait_for_timeout(2000)

            snapshot = page.evaluate("""() => {
              const pending = [document];
              const nodes = [];
              const seen = new Set();

              while (pending.length) {
                const root = pending.pop();

                for (const el of root.querySelectorAll('*')) {
                  if (el.shadowRoot) pending.push(el.shadowRoot);

                  const tag = el.tagName.toLowerCase();
                  const label = (
                    el.getAttribute('aria-label') ||
                    el.getAttribute('title') ||
                    el.innerText ||
                    el.textContent ||
                    ''
                  ).trim().replace(/\\s+/g, ' ');

                  if (!label || label.length > 200) continue;

                  const role = el.getAttribute('role') || '';
                  const relevant =
                    tag.startsWith('flt-semantics') ||
                    ['button', 'combobox', 'option', 'listbox'].includes(role);

                  if (!relevant) continue;

                  const key = tag + '|' + role + '|' + label;
                  if (seen.has(key)) continue;
                  seen.add(key);

                  nodes.push({tag, role, label});
                }
              }

              return {
                url: location.href,
                title: document.title,
                bodyText: (document.body.innerText || '').slice(0, 5000),
                nodes
              };
            }""")

            OUTPUT.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            print("\nURL finale:", snapshot["url"])
            print("Testo visibile:", snapshot["bodyText"])

            print("\nNodi accessibili:")
            for node in snapshot["nodes"][:100]:
                print(
                    f"- [{node['tag']}/{node['role']}] "
                    f"{node['label'][:140]}"
                )

            print("\nSnapshot:", OUTPUT.resolve())
            input("\nPremi INVIO per chiudere il browser...")

        except EOFError:
            print("Input non disponibile.")
        except Exception as exc:
            print(f"Errore: {type(exc).__name__}: {exc}")
        finally:
            context.close()


if __name__ == "__main__":
    main()
