from pathlib import Path
import json
import re

from playwright.sync_api import sync_playwright

from dunkest.data.dunkest.lineups_browser import (
    _enable_flutter_accessibility,
)

URL = "https://fantasy.dunkest.com/1/stats"
PROFILE = Path.home() / ".dunkest-optimizer" / "stats-browser-profile"
OUTPUT = Path("data/raw/dunkest_stats_inspection/ui_snapshot.json")


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
            page.wait_for_timeout(2500)

            print("\nBrowser aperto.")
            print("Se richiesto, accedi a Dunkest.")
            print("Apri la pagina Statistiche e la scheda Stats.")
            print("Verifica che sia visibile la tabella dei giocatori.")
            print("Poi torna qui e premi INVIO.")
            input()

            _enable_flutter_accessibility(page)
            page.wait_for_timeout(1500)

            snapshot = page.evaluate("""() => {
              const roots = [document];
              const nodes = [];
              const seen = new Set();

              while (roots.length) {
                const root = roots.pop();

                for (const el of root.querySelectorAll('*')) {
                  if (el.shadowRoot) roots.push(el.shadowRoot);

                  const label = (
                    el.getAttribute('aria-label') ||
                    el.getAttribute('title') ||
                    el.innerText ||
                    el.textContent ||
                    ''
                  ).trim().replace(/\\s+/g, ' ');

                  if (!label || label.length > 180) continue;

                  const role = el.getAttribute('role') || '';
                  const tag = el.tagName.toLowerCase();

                  const rect = el.getBoundingClientRect();
                  if (rect.width === 0 || rect.height === 0) continue;

                  const relevant =
                    /stagione|modalità|statistiche|giornate|turni|cerca giocatore|filtri avanzati|regular season|dunkest|enable accessibility/i.test(label) ||
                    ['button', 'combobox', 'option', 'listbox', 'select'].includes(role) ||
                    ['button', 'select', 'input', 'flt-semantics'].includes(tag);

                  if (!relevant) continue;

                  const key = tag + '|' + role + '|' + label;
                  if (seen.has(key)) continue;
                  seen.add(key);

                  nodes.push({
                    tag,
                    role,
                    label,
                    ariaLabel: el.getAttribute('aria-label'),
                    rect: {
                      x: Math.round(rect.x),
                      y: Math.round(rect.y),
                      width: Math.round(rect.width),
                      height: Math.round(rect.height)
                    }
                  });
                }
              }

              return {
                url: location.href,
                title: document.title,
                bodyText: (document.body.innerText || '').slice(0, 12000),
                nodes
              };
            }""")

            OUTPUT.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            print("\nURL:", snapshot["url"])
            print("Titolo:", snapshot["title"])
            print("\nTesto visibile:")
            print(snapshot["bodyText"][:5000])
            print("\nControlli individuati:")
            for node in snapshot["nodes"]:
                print(
                    f"- [{node['tag']}/{node['role']}] "
                    f"{node['label'][:140]}"
                )

            print("\nSnapshot salvato in:", OUTPUT.resolve())
            input("\nPremi INVIO per chiudere il browser...")

        except EOFError:
            print("\nInput non disponibile; chiudo il browser.")
        except Exception as exc:
            print(f"\nErrore: {type(exc).__name__}: {exc}")
        finally:
            context.close()


if __name__ == "__main__":
    main()
