# Data sources

## Dunkest (HTTP JSON — preferred)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `https://www.dunkest.com/api/stats/table` | GET | Player stats, current CR, PDK and plusvalenza (params: `season_id`, `mode`, `stats_type`, `weeks[]`, `rounds[]`, `teams[]`, `positions[]`, `min_cr`, `max_cr`) |
| `https://www.dunkest.com/api/stats/dunkest/week/rounds` | GET | Official Turni (`rounds`) for a Dunkest Giornata (`season_id`, `week_number`) |

### Modes

- `mode=nba` + `date_from` / `date_to`: NBA box-derived stats for date range.
- `mode=dunkest` + `weeks[]` + the official `rounds[]`: Dunkest gameweek statistics. The historical client requests `stats_type=avg`, so returned PDK/minutes are aggregate statistics over the selected Dunkest scope; they are not a per-NBA-game score feed and must not be joined to an NBA `GAME_ID` or interpreted as Turno-level fantasy totals.
- If Dunkest returns no rounds for a historical Giornata, the client returns no sample. It does not substitute guessed round IDs; seasons, postseason calendars, and Giornate can have different Turno counts.

## Dunkest (HTML fallback)

| URL | Purpose |
|-----|---------|
| `https://www.dunkest.com/it/nba/infortuni` | Injury tables (`Giocatore`, status) via BeautifulSoup |

## NBA

| Source | Purpose |
|--------|---------|
| `nba_api` | Player game logs, team game logs, league game finder (schedule) |

## Coaches

Coach names and CR are scraped from the `HC` rows at the bottom of the two Lineups columns along with player quotations. `config/dunkest_coaches_2026-27.csv` remains a fallback snapshot; a complete live Lineups market takes precedence.

Public statistics endpoints are unauthenticated; the Lineups market scraper uses a separate authenticated app session.

### CR / quotazioni

For each run, a visible temporary Chromium session opens the authenticated Lineups app. After sign-in and confirmation, the scraper visits every visible matchup, scrolls through its lineup, coach, and optional unavailable section, and collects current player and head-coach quotations from Lineups responses. It replaces the CSV only when at least 250 players are priced and every team in the visible matchup schedule has player and coach prices. Teams with no matchup in that schedule window do not block the refresh. Credentials and browser storage are not persisted.

Historical PDK is fetched separately from `mode=nba` with `season_id=25` and the 2025/26 date range. The Dunkest API returned 527 historical NBA rows during verification, but an empty target-season pool (`season_id=26`) on 2026-09-30, so the browser scraper supplies current names, teams, roles and CR.

Historical API snapshots are used as official Dunkest PDK/PLUS observations at their returned aggregate grain. Player-game predictions are trained on NBA player-game box scores and reconstruct Dunkest PDK from the published weights; they are an approximation where NBA box scores do not carry fantasy-only context. In particular, NBA `PlayerGameLogs` does not contain Dunkest's starting-five flag, so the +1 starter bonus is applied only when a source row actually provides `START_POSITION`. The Dunkest API historical averages cannot safely fill this per-game field because their response is aggregated by Giornata/selected Turni.

The season opener now requires a verified score-bearing fixture for every team in the live player market before it generates optimized rosters. A missing team could be a valid Dunkest rest team, but the current browser snapshot does not yet capture that explicit “Squadre a riposo” classification, so unknown teams stop optimization instead of receiving a guessed matchup or zero projection.

In `mode=nba`, historical rows can return `cr=0` (no live fantasy price). The opener therefore uses the CSV for current player prices. The CSV needs `player_name`, `cr`, `team` and `role` columns so all roster constraints can be checked. The regular in-season pipeline also:

1. Uses current CR from `mode=nba` and recent `mode=dunkest` gameweeks where available.
2. Optionally imputes missing CR from PDK (`impute_missing_cr` in `config/default.yaml`) for non-opener runs.
