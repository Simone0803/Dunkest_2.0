# Dunkest rookie projection balance audit — 2026-10-12

## Change

The college-to-NBA rookie model continues to use historical draft classes and chronological validation. The college-derived rate prior remains capped at 20% because its temporal MAE beat the historical rookie-rate baseline (0.1100 vs 0.1240). The college-derived minutes prior is now capped at **15%**, down from 35%, because its validation is conditional on observed NBA rookie minutes and can under-represent prospects who did not enter an NBA rotation. The lower weight leaves current Dunkest credit, current lineup designation, and current player/role evidence in control of the minutes estimate.

The cap is enforced both when the historical rookie model emits a prior and at inference, so an externally supplied row cannot bypass it. The weight still fades as NBA game history accumulates.

## Historical calibration

`data/rookie_college.csv` contains 595 rows from draft classes 2014–2026; 2014–2025 provide historical outcomes and 2026 provides 54 incoming prospects. Temporal validation currently reports:

- College-to-NBA PDK/minute rate: MAE 0.1100 vs 0.1240 historical rookie-rate baseline.
- Conditional NBA rookie minutes: MAE 5.84 vs 7.35 minutes for the historical position/overall median baseline.

The minutes result is useful but conditional: it should not be interpreted as evidence that every incoming rookie will receive those minutes. The new lower blend weight is a conservative correction for that selection limitation, not a claim that the model's absolute PDK accuracy has improved.

## Before/after production smoke comparison

Compared the last run before this change (`20261012T162434Z_7a50d394`) with the new run (`20261012T171217Z_2f98f42b`) over 552 matched market players:

- Rookie prospects with a college projection: 50 in the production market.
- Maximum college-minute blend weight: 35% → 15%.
- Mean projected minutes among these 50 prospects: 6.99 → 6.39 (−0.61 MPG).
- Mean expected PDK among these 50 prospects: 4.95 → 4.59 (−0.36 PDK).
- 23/50 rookie prospects received a lower minute projection; players unaffected by the prior remain unchanged.
- Non-rookie mean projection changes were close to zero (+0.028 MPG; +0.010 PDK), indicating the change is localized to rookie prior influence.

The per-player matched comparison is in `dunkest_rookie_balance_comparison_20261012T171217Z_2f98f42b_v1.csv`, with aggregate figures in the matching JSON file.

## Current lineup smoke test

The new production run completed successfully. Top roster projections are 210.2, 200.7, and 198.5 PDK. Rookie projections remain eligible when their current market price/role signals justify them; the adjustment reduces the college-minute prior rather than excluding rookies by age or name. This smoke test verifies integration and output consistency, **not** forecast accuracy.

## Validation and limitations

- Focused tests: 18 passed.
- Full suite: 222 passed; 6,800 warnings, primarily PuLP deprecations.
- The current historical rookie dataset does not reliably label every no-minute/no-game outcome as a confirmed zero, so this change does not fabricate zero-minute labels or train a participation classifier from ambiguous missing values.
- A full out-of-sample rookie-vs-veteran accuracy comparison still requires verified pre-game historical market/role snapshots linked to official PDK outcomes. No synthetic backtest was used.
