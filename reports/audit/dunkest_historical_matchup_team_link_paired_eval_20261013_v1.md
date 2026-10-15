# Historical matchup team-link correction — paired walk-forward evaluation v1

Generated UTC: 2026-10-13T11:44:58.226230+00:00

## Pairing and coverage

- V6 prediction rows: **274,979**; V7 rows: **283,736**.
- Exact common player-round predictions: **273,446**; V6-only: **1,533**; V7-only: **10,290**.
- Labels are checked equal on all paired rows. The paired comparison does not mix a changed target label with a changed prediction.

## Paired model results

| Feature family | Paired rows | V6 MAE | V7 MAE | Δ MAE (V7−V6) | 95% round-bootstrap CI | V6 RMSE | V7 RMSE | Δ RMSE |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| historical_form_plus_lagged_credit_and_expanded_matchup_v2 | 55,252 | 7.5178 | 7.5186 | +0.0008 | [-0.0050, +0.0066] | 9.8162 | 9.8175 | +0.0013 |
| historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 | 55,252 | 7.4931 | 7.4990 | +0.0060 | [-0.0000, +0.0120] | 9.7741 | 9.7783 | +0.0042 |

## By held-out season

| Feature family | Season ID | Paired rows | V6 MAE | V7 MAE | Δ MAE |
|---|---:|---:|---:|---:|---:|
| historical_form_plus_lagged_credit_and_expanded_matchup_v2 | 13 | 18,137 | 7.5408 | 7.5461 | +0.0054 |
| historical_form_plus_lagged_credit_and_expanded_matchup_v2 | 19 | 18,783 | 7.5194 | 7.5149 | -0.0046 |
| historical_form_plus_lagged_credit_and_expanded_matchup_v2 | 9 | 18,332 | 7.4934 | 7.4952 | +0.0018 |
| historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 | 13 | 18,137 | 7.5133 | 7.5204 | +0.0071 |
| historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 | 19 | 18,783 | 7.4984 | 7.5014 | +0.0030 |
| historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 | 9 | 18,332 | 7.4676 | 7.4755 | +0.0079 |

## Decision policy

A negative delta favors V7 on common held-out rows. Treat the result as supportive only if the round-clustered confidence interval excludes zero, the season-level results are not driven by one fold, and the expanded-coverage sample does not conceal a material data-quality issue. The corrected link is still a retrospective outcome linkage, not a historical pre-lock market snapshot. No production changes are made from this comparison alone.

## Artifacts
- Paired rows: reports/audit/dunkest_historical_matchup_team_link_paired_eval_20261013_v1_paired_rows.csv
- Summary: reports/audit/dunkest_historical_matchup_team_link_paired_eval_20261013_v1_summary.csv
- By season: reports/audit/dunkest_historical_matchup_team_link_paired_eval_20261013_v1_by_season.csv
- JSON: reports/audit/dunkest_historical_matchup_team_link_paired_eval_20261013_v1.json
