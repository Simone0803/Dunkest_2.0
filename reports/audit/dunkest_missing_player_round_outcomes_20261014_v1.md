# Missing player-round outcome recovery audit

Generated UTC: 2026-10-14T13:22:20.262234+00:00

Selected player instances audited: 9,160

## Recovery status

| Status | Count |
|---|---:|
| weekly_round_score_observed | 5,872 |
| no_weekly_or_gamelevel_record | 2,053 |
| explicit_nonvalid_game_row_zero_candidate | 1,235 |

Lineup-strategy rows with all ten scores observed/recovered or explicit non-valid rows: 173 / 916.

Explicit `gameValidForDunkest=False` records are kept separate from certified actual scores: they may indicate a genuine zero, but may also reveal a stale or incorrect historical candidate identity. A player with no weekly or game-level record is left unknown, never automatically treated as zero in strict metrics.

## Limitations

- Game-level records are matched by season, target date, and Dunkest player ID; this is not a complete historical pre-lock market snapshot.
- An explicit gameValidForDunkest=False row is a candidate for zero actual score but may indicate market/identity mismatch; it is reported separately and not silently promoted into certified scoring.
- No row in either source remains unknown, not zero.

Selected-player audit: `reports/audit/dunkest_missing_player_round_outcomes_20261014_v1_selected_players.csv`
Machine-readable summary: `reports/audit/dunkest_missing_player_round_outcomes_20261014_v1.json`
