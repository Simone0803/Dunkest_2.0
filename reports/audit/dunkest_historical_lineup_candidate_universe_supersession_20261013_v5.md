# Historical lineup candidate-universe audit — supersession note v5 (2026-10-13)

## Data-link correction retained; predictive promotion deferred

The final v2 derived dataset links 93,317 of 93,779 weekly outcome rows with gp=1 uniquely. Of the 7,873 candidates found after excluding the source team key, 7,828 have an identified NBA game team that differs from the source team, 12 have a unique date/outcome link but no NBA team ID, 33 remain ambiguous, and 19 have no exact 17-stat signature. Another 410 rows have ambiguous strict team-inclusive signatures. Original team fields and labels are preserved.

The corrected link increases official-valid unique player/date candidates from 64,996 to 93,316. Under the existing date-confidence threshold, 778 of 779 rounds become usable (up from 768); the 768 shared accepted dates all agree. Schedule-derived opponent coverage increases from 90,219 to 93,284 rows, with 3,516 rows gaining coverage and 451 losing a legacy association that may have been a wrong-team join.

## Predictive evaluation

An expanding-origin V7 experiment used the corrected historical NBA game team for opponent and past-only rest features. On 55,252 common held-out player-rounds per model family, it did not improve MAE relative to V6. Expanded-matchup MAE delta was +0.0008 (95% round-cluster bootstrap CI [-0.0050, +0.0066]); rest/schedule MAE delta was +0.0060 (95% CI approximately [0.0000, +0.0120]). On 2,710 common rows with source-team mismatch, deltas were +0.0035 and +0.0013 respectively. These are neutral/slightly worse results, not evidence for promotion.

## Decision

- Keep the derived game-link dataset for data provenance and controlled research.
- Do not rewrite source team_code/team_name globally.
- Do not promote V7 to production based on current predictive evidence.
- Do not infer team IDs for the 12 no-team rows or game identity for ambiguous/unresolved rows.
- The data remains outcome linkage, not a complete pre-lock market snapshot; historical CR, injuries/availability and full candidate universe are still missing.
- The 2026/27 GW1 holdout remains frozen until 2026-10-23 12:00 UTC.

## Artifacts

- scripts/build_dunkest_historical_game_linked_rows_v2.py
- data/processed/dunkest_historical_game_linked_rows_20261013_v2.parquet
- reports/audit/dunkest_historical_game_linked_rows_20261013_v2.md
- scripts/audit_dunkest_historical_matchup_team_link_coverage_v1.py
- reports/audit/dunkest_historical_matchup_team_link_coverage_20261013_v1.md
- scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v7_corrected_team_link.py
- reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v7_corrected_team_link.md
- scripts/audit_dunkest_historical_matchup_team_link_paired_evaluation_v1.py
- reports/audit/dunkest_historical_matchup_team_link_paired_eval_20261013_v1.md
- reports/audit/dunkest_project_followup_2026-10-13_v19.md

No production code/config, source datasets, official targets, temporal splits, or frozen holdout were changed. No commit/push was performed.
