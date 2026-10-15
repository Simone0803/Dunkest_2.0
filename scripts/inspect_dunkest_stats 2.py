from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from dunkest.data.dunkest.lineups_browser import (
    _enable_flutter_accessibility,
)

URL = "https://fantasy.dunkest.com/1/stats"
API_HOST = "fantaking-api.dunkest.com"

PROFILE = Path.home() / ".dunkest-optimizer" / "stats-browser-profile"
OUTPUT_DIR = Path("data/raw/dunkest_stats_inspection")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_PATH = OUTPUT_DIR / "api_responses.jsonl"
UI_PATH = OUTPUT_DIR / "visible_controls.json"


def write_jsonl(path: Path, item: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()

        def on_response(response) -> None:
            if API_HOST not in response.url:
                return

            # Non registrare risposte che possono contenere credenziali
            # o informazioni personali dell'account.
            path = response.url.split("?", 1)[0].lower()
            if re.search(r"/(login|logout|user)(/|$)", path):
                return

            item = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": response.status,
                "url": response.url,
            }

            try:
                body = response.json()
                item["json_type"] = type(body).__name__

                if isinstance(body, dict):
                    item["keys"] = list(body.keys())[:60]
                    data = body.get("data")

                    if isinstance(data, dict):
                        item["data_keys"] = list(data.keys())[:80]
                    elif isinstance(data, list):
                        item["data_count"] = len(data)
                        if data and isinstance(data[0], dict):
                            item["first_item_keys"] = list(data[0].keys())[:80]

                elif isinstance(body, list):
                    item["data_count"] = len(body)
                    if body and isinstance(body[0], dict):
                        item["first_item_keys"] = list(body[0].keys())[:80]

            except Exception as exc:
                item["parse_error"] = type(exc).__name__

            write_jsonl(LOG_PATH, item)
            print("\nAPI:", json.dumps(item, ensure_ascii=False), flush=True)

        page.on("response", on_response)

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            _enable_flutter_accessibility(page)

            print("\nPagina aperta:", page.url, flush=True)
            print("Titolo:", page.title(), flush=True)
            print("\nAccedi se necessario e apri la sezione Stats.", flush=True)
            print(
                "Seleziona una stagione o cambia Giornate/Turni. "
                "Dopo ogni modifica attendi qualche secondo.",
                flush=True,
            )

            while not page.is_closed():
                page.wait_for_timeout(1000)

                # Legge controlli accessibili, inclusi quelli Flutter.
                try:
                    controls = page.evaluate("""() => {
                      const roots = [document];
                      const found = [];
                      const seen = new Set();

                      while (roots.length) {
                        const root = roots.pop();

                        for (const el of root.querySelectorAll('*')) {
                          if (el.shadowRoot) roots.push(el.shadowRoot);

                          const label = (
                            el.getAttribute('aria-label') ||
                            el.getAttribute('title') ||
                            el.innerText ||
                            ''
                          ).trim().replace(/\\s+/g, ' ');

                          if (!label || label.length > 160) continue;

                          const role = el.getAttribute('role') || '';
                          const tag = el.tagName.toLowerCase();

                          if (
                            role === 'button' ||
                            role === 'combobox' ||
                            role === 'option' ||
                            role === 'listbox' ||
                            tag === 'button' ||
                            tag === 'select' ||
                            tag === 'input' ||
                            tag === 'flt-semantics'
                          ) {
                            const key = role + '|' + tag + '|' + label;

                            if (!seen.has(key)) {
                              seen.add(key);
                              found.push({role, tag, label});
                            }
                          }
                        }
                      }

                      return found;
                    }""")

                    UI_PATH.write_text(
                        json.dumps(controls, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    pass

        except KeyboardInterrupt:
            print("\nInterruzione richiesta.", flush=True)
        except Exception as exc:
            print(
                f"\nBrowser terminato: {type(exc).__name__}: {exc}",
                flush=True,
            )
        finally:
            context.close()

    print("\nFile prodotti:")
    print(LOG_PATH.resolve())
    print(UI_PATH.resolve())


if __name__ == "__main__":
    main()
