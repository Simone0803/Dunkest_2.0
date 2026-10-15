# Missing player-round outcome recovery audit — V2

Generated UTC: 2026-10-14T13:38:03.698625+00:00

Selected player instances audited: 9,160

## Recovery status

| Status | Count |
|---|---:|
| weekly_round_score_observed | 5,872 |
| team_played_player_row_absent_zero_candidate | 1,930 |
| explicit_nonvalid_game_row_zero_candidate | 1,235 |
| team_did_not_play_identity_or_candidate_mismatch | 123 |

Lineup-strategy rows without unresolved outcomes: 808 / 916.

The audit now checks whether the player’s lagged team had a fixture on the target date. A missing player row on a confirmed team fixture is classified as a zero candidate (possible DNP/inactive), not an official zero. A selected player whose team has no fixture is flagged as a candidate-pool/team-link error.

## Limitations

- Zero candidates are not promoted to certified official scores; the team schedule is inferred from player-game logs.
- A prior team may be stale after trades, so a no-fixture result can expose team-link errors rather than a true invalid lineup.
- The official weekly archive remains authoritative for observed outcomes; missing rows remain unknown unless the scenario explicitly assumes zero.

Selected-player audit: `reports/audit/dunkest_missing_player_round_outcomes_20261014_v2_selected_players.csv`
Machine-readable summary: `reports/audit/dunkest_missing_player_round_outcomes_20261014_v2.json`
