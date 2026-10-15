# Injury source migration — 2026-10-15

## Decision

Use Dunkest's dedicated injury page as the single automatic source of player health/availability:
https://www.dunkest.com/it/nba/infortuni

Dunkest Lineups remains available for current player-market prices, candidate roster, and fixture-related captures, but its browser-scraped health labels are no longer merged into the injury feed.

## Implementation

- `get_injuries` fetches the dedicated injury page and caches it with season/gameweek scope. A cache from another gameweek is never reused.
- Official injury snapshots record source URL, gameweek, season, and observation timestamp. The per-gameweek archive uses `injuries_{season_id}_gw{gameweek}.parquet`.
- Explicit user-confirmed entries in `injury_overrides.csv` remain supported for the selected gameweek.
- If the page fails or returns an invalid/empty response, a same-gameweek official cache may be reused with a warning. Without one, prediction fails rather than treating all players as healthy or silently falling back to Lineups.
- Season-opener candidate filtering also uses this official feed and resolves abbreviated names conservatively by surname, initial, and team.
- Lineups' explicit roster-group exclusion `INDISPONIBILI` remains separate from injury-status labels; Lineups status text is not used as the health feed.

## Live source check

A read-only scrape of the dedicated page on 2026-10-15 returned 94 rows across 26 NBA teams:
- 14 `OUT` rows
- 79 `GAME TIME DECISION` rows
- 1 `UNKNOWN` row

Unknown descriptions are preserved as unknown and are not automatically treated as confirmed OUT. The page uses abbreviated player names, so matching remains team/initial-aware.

## Verification

- Focused injury, scraper, opening-market, and season-opener tests: 46 passed.
- Full suite after the source migration: 410 passed.
- `compileall` passed for modified modules/tests.
- `git diff --check` passed.
- No live GW1 prediction, historical injury reconstruction, commit, push, staging, or destructive cleanup was performed.

## Scope limit

The page is a current injury report, not a historical archive per gameweek. Each gameweek's snapshot is captured when that gameweek's prediction pipeline runs; today's page cannot be used to reconstruct past injury statuses.
