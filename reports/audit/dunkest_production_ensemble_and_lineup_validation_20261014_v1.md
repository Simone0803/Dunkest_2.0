# Dunkest — production ensemble OOS validation and lineup-strategy readiness

Generated UTC: 2026-10-14T11:20:27.162605+00:00

## Executive decision

**No production change is promoted yet.** The core model-zoo ensemble improves player-game MAE over the previous-10 PDK baseline in every expanding-origin test season, and pooled residual intervals are close to nominal coverage. History-cohort intervals are a useful challenger for players with at most five prior Dunkest rows. However, this does not validate the final market-specific player forecast consumed by the optimizer, and complete historical pre-lock snapshots are absent. Keep production weights, uncertainty calibration, optimizer objective, and risk lambda unchanged until the complete inference path and full lineups can be evaluated without proxies.

## 1. Core production ensemble: expanding-origin OOS

- Certified official Dunkest PDK labels only; no proxy target fallback.
- Each test season is predicted by the production `train_models` model zoo fitted only on earlier certified seasons. Training cutoff assertions pass.
- The production inverse-MAE model weights and training-window projection weights are re-estimated inside each fold.
- The previous-10 baseline is reported on rows where that feature is available; row counts differ slightly from the model.

| test_season | n     | train_rows | mae    | rmse    | bias_pred_minus_actual | prev10_mae | mae_gain_vs_prev10 | prev10_rmse | rmse_gain_vs_prev10 |
| ----------- | ----- | ---------- | ------ | ------- | ---------------------- | ---------- | ------------------ | ----------- | ------------------- |
| 2021-22     | 18422 | 17662      | 7.8803 | 10.1983 | -0.2998                | 8.0942     | 0.2139             | 10.4792     | 0.2809              |
| 2022-23     | 19165 | 36084      | 7.5634 | 9.8726  | -0.5473                | 7.7635     | 0.2002             | 10.1137     | 0.241               |
| 2023-24     | 18927 | 55249      | 7.5574 | 9.8399  | -0.3766                | 7.7546     | 0.1973             | 10.0965     | 0.2566              |
| 2024-25     | 19590 | 74176      | 7.6067 | 9.9199  | -0.344                 | 7.7832     | 0.1764             | 10.1775     | 0.2576              |
| 2025-26     | 18412 | 93766      | 7.587  | 9.8742  | -0.3154                | 7.7817     | 0.1947             | 10.1544     | 0.2802              |

### Interpretation

- Core ensemble MAE is lower than the previous-10 baseline in every fold, with gains of approximately 0.18–0.21 PDK per player-game.
- RMSE also improves against the previous-10 baseline in these folds.
- Mean bias is negative from 2022/23 onward (about −0.32 to −0.55 PDK): the model slightly underpredicts on average. Do not apply a global median correction just because it improves MAE by a few hundredths; it makes mean bias more negative.
- Fold model weights are consistently close to one-third each for Ridge, Random Forest and Gradient Boosting. The separate RF/Ridge/previous-10 tuned blend remains a challenger, not a reason to overwrite the production ensemble.

## 2. Uncertainty calibration using only prior OOS residuals

For each test season, interval quantiles are fit only on residuals from earlier out-of-sample seasons. Residual = prediction − actual; score bounds are lower = prediction − q90(residual), upper = prediction − q10(residual). Nominal central coverage is 80%; each one-sided marginal coverage is 90%.

| test_season | calibration_seasons             | n     | lower_tail_coverage | upper_tail_coverage | central_80_coverage | mean_interval_width | raw_mae | median_corrected_mae | median_corrected_bias |
| ----------- | ------------------------------- | ----- | ------------------- | ------------------- | ------------------- | ------------------- | ------- | -------------------- | --------------------- |
| 2022-23     | 2021-22                         | 19165 | 0.9241              | 0.8989              | 0.823               | 25.5058             | 7.5634  | 7.5338               | -1.2264               |
| 2023-24     | 2021-22;2022-23                 | 18927 | 0.91                | 0.9015              | 0.8115              | 24.9367             | 7.5574  | 7.5128               | -1.1343               |
| 2024-25     | 2021-22;2022-23;2023-24         | 19590 | 0.9012              | 0.906               | 0.8072              | 24.7258             | 7.6067  | 7.5658               | -1.2146               |
| 2025-26     | 2021-22;2022-23;2023-24;2024-25 | 18412 | 0.9006              | 0.9064              | 0.807               | 24.5653             | 7.587   | 7.5501               | -1.2085               |

### Low-history cohort (0–5 prior Dunkest rows): pooled versus cohort-specific

| test_season | comparison              | n   | lower_tail_coverage | upper_tail_coverage | central_80_coverage | mean_interval_width | median_corrected_mae | median_corrected_bias |
| ----------- | ----------------------- | --- | ------------------- | ------------------- | ------------------- | ------------------- | -------------------- | --------------------- |
| 2022-23     | cohort-specific, shrunk | 456 | 0.9452              | 0.875               | 0.8202              | 17.4044             | 5.5582               | -1.0699               |
| 2022-23     | pooled                  | 456 | 0.9693              | 0.9539              | 0.9232              | 25.5058             | 5.6613               | -0.0593               |
| 2023-24     | cohort-specific, shrunk | 518 | 0.9073              | 0.9073              | 0.8147              | 17.3965             | 5.4629               | -0.9752               |
| 2023-24     | pooled                  | 518 | 0.9575              | 0.9537              | 0.9112              | 24.9367             | 5.5649               | 0.1232                |
| 2024-25     | cohort-specific, shrunk | 480 | 0.9083              | 0.8958              | 0.8042              | 17.1749             | 5.0186               | -0.863                |
| 2024-25     | pooled                  | 480 | 0.9521              | 0.9708              | 0.9229              | 24.7258             | 5.1806               | 0.1658                |
| 2025-26     | cohort-specific, shrunk | 524 | 0.9141              | 0.8969              | 0.8111              | 17.2166             | 5.1147               | -1.2307               |
| 2025-26     | pooled                  | 524 | 0.9599              | 0.9618              | 0.9218              | 24.5653             | 5.2473               | -0.0331               |

### History cohort (6–10 prior rows): pooled versus cohort-specific

| test_season | comparison              | n   | lower_tail_coverage | upper_tail_coverage | central_80_coverage | mean_interval_width |
| ----------- | ----------------------- | --- | ------------------- | ------------------- | ------------------- | ------------------- |
| 2022-23     | pooled                  | 341 | 0.9736              | 0.9443              | 0.9179              | 25.5058             |
| 2023-24     | cohort-specific, shrunk | 394 | 0.9416              | 0.9086              | 0.8503              | 19.2842             |
| 2023-24     | pooled                  | 394 | 0.9695              | 0.9569              | 0.9264              | 24.9367             |
| 2024-25     | cohort-specific, shrunk | 384 | 0.9193              | 0.9167              | 0.8359              | 18.4808             |
| 2024-25     | pooled                  | 384 | 0.9792              | 0.9479              | 0.9271              | 24.7258             |
| 2025-26     | cohort-specific, shrunk | 387 | 0.8837              | 0.8915              | 0.7752              | 18.1624             |
| 2025-26     | pooled                  | 387 | 0.9406              | 0.9251              | 0.8656              | 24.5653             |

**Decision:** cohort-specific quantiles for 0–5 prior rows narrow intervals from roughly 24.6–25.5 PDK to 17.2–17.4 PDK while retaining central coverage around 80.4–82.0% across these folds. This is a strong challenger for low-history players. The 6–10 cohort is less stable; in 2025/26 its central coverage is below nominal, so do not deploy a blanket cohort calibrator. The 2025/26 fold has already been inspected in earlier project work and is not a globally untouched final holdout.

## 3. What this calibration does not yet certify

This audit validates the core model-zoo ensemble and the projection layer that can be reconstructed from certified historical player-game rows. It does **not** validate the final market-specific forecast after current-role/minutes allocation, the separately blended historical PDK model, rookie priors, and availability weighting. Those transformations depend on pre-lock market, role, injury and availability information not consistently archived historically. Applying the new cohort quantiles to the final production forecast now would therefore be an unvalidated production change.

## 4. Full-lineup strategy comparison: data readiness

Historical player-game and round-level score data exist, but a valid lineup backtest also requires the exact pre-lock candidate universe and rules state for each round. The snapshot inventory found:
- Saved prediction snapshots contain repeated copies of `player_credits_26_gw1.parquet`, `coach_market_26_gw1.parquet`, and `injuries_26_gw1.parquet` for 2026/27 Gameweek 1; they are not historical season/round archives.
- There are no corresponding historical `player_credits_*`, coach-market, or injury snapshots in `data/processed` for archived seasons.
- The historical 2020–25 round dataset has 93,785 rows and contains CR values, but these records are not certified as pre-lock prices. Using them as the pregame market would risk leakage.
- Previously frozen 2026/27 GW1 strategy runs were captured roughly 149–151 hours before earliest kickoff; the pipeline freshness gate is 36 hours. Those runs are useful for pipeline checks only.
- Player actuals can now be reconstructed from official per-game Dunkest PDK and validated against the historical weekly archive. Historical coach-market prices, exact coach credit multipliers, and transfer counts/malus remain unavailable, so the full official team score is still not certified.

**Decision:** a historical player-lineup proxy comparison is now available, but no complete historical strategy is promoted and no optimizer objective/risk lambda is changed. A complete strategy comparison still requires new snapshots captured within the strict 36-hour pre-lock window, archived with timestamps and fixture mapping, then official player/coach outcomes after the safe post-game cutoff. Compare strategies on identical eligible rounds with paired round-cluster bootstrap intervals. Preserve 2026/27 as the prospective evaluation period rather than tuning on its eventual holdout outcomes.

## 5. Reproducibility artifacts

- OOS audit script: `scripts/audit_dunkest_production_ensemble_expanding_oos_v1.py`
- Detailed audit: `reports/audit/dunkest_production_ensemble_expanding_oos_20261014_v1.md`
- Point metrics: `reports/audit/dunkest_production_ensemble_expanding_oos_20261014_v1_metrics.csv`
- Row-level predictions: `reports/audit/dunkest_production_ensemble_expanding_oos_20261014_v1_predictions.csv`
- Interval diagnostics: `reports/audit/dunkest_production_ensemble_expanding_oos_20261014_v1_intervals.csv`
- Machine-readable audit: `reports/audit/dunkest_production_ensemble_expanding_oos_20261014_v1.json`

No production weights, calibrator, model artifacts, scoring rules, lineup objective, or risk lambda were changed. No commit or push was performed.

## 6. Verification

- Full test suite: **312 passed, 6,800 warnings**.
- `git diff --check`: passed.
- Audit script compiles with `py_compile`.
- Production settings and model artifacts were not changed; no commit or push was performed.

## 7. Historical player-actual recovery and lineup proxy — 2026-10-14

The first game-level lineup experiment (V1) has been **superseded**. It unioned linked game IDs by round, which let a few repeated box-score signatures pull in games from another date. Do not use V1's lineup scores or bootstrap estimate; see `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v1_superseded.md`.

The corrected V2 method first establishes a round date from linked player-game dates, requiring at least 75% date agreement and at least 10 unique player links, then sums official Dunkest-valid player-game PDK for that season/date. The strict V2 run compared **93,734 player-round rows**: **93,728 (99.994%)** matched the historical weekly PDK within 0.02 points, with mean absolute difference **0.00149 PDK**.

The leakage-safe V3 lineup comparison evaluated **409 paired rounds** from 2022/23–2024/25. Mean model lineup plus neutral-credit coach base score was **160.83**, versus **140.34** for the raw previous-five-observation baseline; mean paired gain **+20.49 PDK**, model wins **64.1%** of rounds, and season-stratified paired-round bootstrap 95% CI **[+15.19, +25.78]**. Official player actuals were reconstructed from per-game Dunkest PDK with 99.994% of 93,734 comparable player-round rows matching the weekly archive within 0.02 PDK.

This is still **conditional evidence**, not proof of strategy superiority: the raw baseline's selected lineups are severely overoptimistic after optimization (expected **271.72** versus realized **140.34**; model expected **207.82** versus realized **160.83**). A calibrated baseline and selection-conditioned score calibration are still needed. The candidate universe/CR/role/team are lagged proxies, coach CR is fixed at 10, coach scores use neutral-credit base points, and transfer malus is zero because historical carried rosters and transfer counts are missing. No production change has been made. See `reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v3.md` and its bootstrap report.

## 8. Prospective pre-lock archive gate

Added `scripts/archive_dunkest_prelock_run_v1.py`. It copies a run only once, records SHA-256 hashes, and refuses to certify runs without fixture-linked timestamps, required market/injury/coach snapshots, frozen predictions and lineups, or freshness within 36 hours of the earliest kickoff. Tested against run `20261014T104418Z_49f79e8c`: correctly rejected it as **not certified** because the run was 133.3 hours before kickoff. No archive was created for that stale run; it remains useful for pipeline diagnostics only.

No commit or push was performed.
