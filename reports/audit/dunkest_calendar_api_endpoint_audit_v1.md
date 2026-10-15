# Dunkest calendar API endpoint audit v1

## Scope
Read-only exploration of public Dunkest/Fantaking API endpoints to determine whether they expose a historical mapping between Dunkest matchdays/turns and individual NBA games. No account credentials or private account data were collected.

## Findings

- `GET https://fantaking-api.dunkest.com/api/v1/games/1/config` returns public game configuration; the league metadata labels league 1 as NBA 2026/27.
- `GET https://fantaking-api.dunkest.com/api/v1/leagues/1/config` returns `current_schedule_id=57`, `current_competition_id=57`, `current_matchday={id:1858, number:1, num_rounds:3}`, `current_round={id:2890, number:1, started_at:2026-10-20T18:59:00Z}`, and 63 matchday entries. These entries contain IDs/numbers but no date/game IDs in the sampled objects.
- Adding `season_id=19`, `schedule_id=19`, or `competition_id=19` to the league-1 config request does not select a historical season; it still returns schedule/competition 57 and 63 matchdays.
- `/api/v1/matches/1858/lineups` returned HTTP 403 (`Did not find a league configs for this competition`). Other guessed routes such as `/schedules/57/matchdays` and `/competitions/57/matchdays` did not provide a usable historical mapping. These failures are not proof that no other endpoint exists.
- The public stats API's weekly/round tables and the local weekly archives remain aggregates keyed by season/week/round; they do not supply an authoritative dated mapping from a round to individual NBA games.
- Dunkest's official help pages state that the complete calendar is available in the app and explain valid/invalid team games, but do not publish a downloadable historical calendar.

## Conclusion

The public configuration endpoint confirms that Dunkest maintains explicit matchday and turn identifiers, but the unauthenticated configuration response inspected here is for the current season and is insufficient to validate historical `gameValidForDunkest` values row by row. No authoritative historical round-to-NBA-game mapping was recovered in this pass.

## Decision / safeguards

- Preserve `gameValidForDunkest` and official PDK values unchanged.
- Do not synthesize matchday boundaries or replace official labels with calendar-based proxies.
- Do not alter model, training target, temporal splits, or walk-forward/backtest settings.
- Next evidence source, if available, is a historical calendar export/screenshot from the Dunkest app or a supported API endpoint exposed when navigating historical seasons in the app.
