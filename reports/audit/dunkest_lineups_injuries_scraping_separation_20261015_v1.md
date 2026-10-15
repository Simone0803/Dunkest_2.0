# Dunkest Lineups / Injuries scraping separation — 2026-10-15

## Changes

- `scrape_lineups_market` now captures only the full-gameweek player/coach market, fixture mapping, and roster annotations (starting five, bench, coach). It does not apply injury-panel labels, print ambiguous surname warnings, or create/update `lineups_availability.csv`.
- The Lineups CSV's `status` field is cleared explicitly. The multi-turn market merge also discards legacy `INDISPONIBILI` labels and old status values, so old captures cannot reintroduce injury exclusions.
- Lineups metadata marks `injury_statuses_included: false` and points to the separate official injuries source.
- The official injuries pass opens `https://fantasy.dunkest.com/1/injuries`, scrolls the rendered page through its scrollable content to the bottom, and captures `/api/v1/leagues/1/injuries` from the page session. It fails closed if the official payload is invalid.
- Injury rows retain Dunkest's original description and reason and now include `injury_type`, `injury_severity`, `expected_return_days`, and `season_ending`. Categories distinguish season-ending, finite temporary absence, rest, day-to-day uncertainty, and unspecified/unknown cases. Past return dates are flagged rather than silently treated as proof of availability.
- User-confirmed overrides now update a matching official row in place instead of replacing it during deduplication and losing its injury classification.

## Live validation

- Lineups smoke test written to a temporary path (the current GW1 market artifact was not overwritten): **593 rows = 563 players + 30 coaches**.
- Fixture coverage: **16/16**; unverified lineup fixtures: **0**.
- Non-empty Lineups status fields: **0**; `INDISPONIBILI` market rows: **0**.
- Official injuries scrape completed after opening and scrolling the page: **124 records**, with **104 `GAME TIME DECISION`** and **20 `OUT`**.
- The refreshed official injury cache includes two records explicitly labelled unavailable for the whole season; finite return dates remain temporary absences rather than being mislabelled season-ending. `Riposo` is separately classified from injury-related day-to-day decisions.
- Injury cache and override merge checked: **124 rows**, no missing `injury_type` or `injury_severity` values.

## Verification and guardrails

- Full test suite: **425 passed**.
- `compileall` and `git diff --check`: passed.
- No season-opener prediction/optimization was run as part of this change. No commit, push, or staging was performed.
