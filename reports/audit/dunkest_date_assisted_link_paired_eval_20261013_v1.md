# Date-assisted exact-signature linkage — paired walk-forward evaluation v1

Generated UTC: 2026-10-13T12:03:42.047212+00:00

## Pairing and coverage

- V7 prediction rows: **283,736**; V8 prediction rows: **285,304**.
- Common held-out predictions: **283,736**; V7-only: **0**; V8-only: **1,568**.

## Paired model results

| Feature family | Paired rows | V7 MAE | V8 MAE | Δ MAE (V8−V7) | 95% round-bootstrap CI | V7 RMSE | V8 RMSE | Δ RMSE |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| historical_form_plus_lagged_credit_and_expanded_matchup_v2 | 57,342 | 7.4897 | 7.4904 | +0.0006 | [-0.0035, +0.0049] | 9.7810 | 9.7815 | +0.0005 |
| historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 | 57,342 | 7.4716 | 7.4685 | -0.0031 | [-0.0072, +0.0010] | 9.7431 | 9.7432 | +0.0001 |

## By held-out season

| Feature family | Season ID | Paired rows | V7 MAE | V8 MAE | Δ MAE |
|---|---:|---:|---:|---:|---:|
| historical_form_plus_lagged_credit_and_expanded_matchup_v2 | 13 | 18,774 | 7.5164 | 7.5128 | -0.0036 |
| historical_form_plus_lagged_credit_and_expanded_matchup_v2 | 19 | 19,486 | 7.4906 | 7.4925 | +0.0019 |
| historical_form_plus_lagged_credit_and_expanded_matchup_v2 | 9 | 19,082 | 7.4626 | 7.4661 | +0.0035 |
| historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 | 13 | 18,774 | 7.4907 | 7.4823 | -0.0084 |
| historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 | 19 | 19,486 | 7.4815 | 7.4794 | -0.0021 |
| historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 | 9 | 19,082 | 7.4427 | 7.4437 | +0.0010 |

## Decision policy

A negative delta favors V8 on common held-out rows. Promotion requires a stable improvement with round-clustered intervals, consistent season-level behavior, and a documented linkage audit. Regardless of metrics, this is retrospective outcome linkage—not a complete pre-lock market snapshot. No production change follows from this experiment alone.

## Artifacts
- Paired rows: `reports/audit/dunkest_date_assisted_link_paired_eval_20261013_v1_paired_rows.csv`
- Summary: `reports/audit/dunkest_date_assisted_link_paired_eval_20261013_v1_summary.csv`
- By season: `reports/audit/dunkest_date_assisted_link_paired_eval_20261013_v1_by_season.csv`
- JSON: `reports/audit/dunkest_date_assisted_link_paired_eval_20261013_v1.json`
