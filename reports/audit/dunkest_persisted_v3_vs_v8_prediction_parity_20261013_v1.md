# Persisted v3 dataset and V8/V9 prediction parity — v1

Generated UTC: 2026-10-13T12:14:25.154497+00:00

## Dataset integrity

- v3 rows: **93,785**; date-assisted rows: **441**.
- Date-assisted rows matched to an official-valid candidate on the stored game/date/team: **441/441**.
- Exact PDK matches: **441/441**; all 17 statistic signatures match: **441/441**.
- Source-stat mismatches against the raw source, by field: `{"pts": 0, "reb": 0, "ast": 0, "stl": 0, "blk": 0, "blka": 0, "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0, "oreb": 0, "dreb": 0, "tov": 0, "pf": 0, "plus_minus": 0, "target_pdk_round_total": 0}`.

## Prediction parity

- V8 rows: **285,304**; V9 rows: **285,304**; common: **285,304**; V8-only/V9-only: **0/0**.
- Target labels identical: **True**.
- Maximum absolute prediction difference: **2.842e-14**.
- All predictions equal within 1e-12: **True**.

| Feature family | Common rows | Max absolute difference | Equal within 1e-12 |
|---|---:|---:|---|
| baseline_last_round | 56,159 | 0.000e+00 | True |
| baseline_previous5_mean | 56,159 | 0.000e+00 | True |
| baseline_train_median | 57,662 | 0.000e+00 | True |
| historical_form_plus_lagged_credit_and_expanded_matchup_v2 | 57,662 | 2.132e-14 | True |
| historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 | 57,662 | 2.842e-14 | True |

## Interpretation

V9 consumes the persisted v3 mapping while reconstructing round dates only from original v2 links. Exact prediction parity with V8 demonstrates that the persisted experimental dataset reproduces the previous in-script fallback without changing the walk-forward predictions. This is a reproducibility check, not evidence that the feature improves prediction or that historical pre-lock market snapshots are complete.

## Guardrails

- V3 and V9 are experimental only; no production code/config changed.
- V9 round-date consensus is computed from original v2 links only, excluding date-assisted rows from date inference.
- No holdout data was inspected or used.
