# Dunkest project follow-up (v8)

Generated: 2026-10-13

## Verification performed in this continuation

- Full test suite executed with the repository's required source path:
  `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Result: **276 passed, 0 failed** in 6.30 seconds.
- Warnings: 6,800, mostly PuLP deprecations, plus one warning about freshness metadata in a test fixture.
- A first run without `PYTHONPATH=src` failed during collection because the local package was not on the import path; this was an invocation/environment issue, not a test failure. The documented invocation passed.
- No production configuration, model weights, source datasets, or frozen predictions were changed in this continuation.

## Current evidence and decisions

1. **Player PDK prediction:** the combined PDK + NBA-history feature family remains the leading research candidate. Existing 2025/26 historical metrics are not an untouched final holdout.
2. **Ensemble:** the 60/35/5 RF/Ridge/previous-10 blend has only a 0.0207 PDK MAE improvement over RF on the existing 2025/26 comparison. Keep production weights unchanged.
3. **Opponent/H2H features:** the richer H2H model improves game-level player MAE in its walk-forward experiment, but the H2H lineup challenger underperforms the no-H2H lineup model by 5.66 realized points per round in the restricted 409-round proxy. Reject H2H for lineup selection in its current form.
4. **Rookies:** retain the conservative 15% cap on college-derived rookie-minute prior.
5. **Coach prediction:** keep the points-only NBA win-probability baseline. Coach fantasy-score audits remain conditional on assumed historical coach CR pairs; they are not exact historical credit-adjusted PDK validation.
6. **Historical lineup backtest:** available results remain proxy results, not a certified market backtest. Historical coach CR, transfer carry-over/malus, full pre-lock player universe, and authenticated pre-match snapshots are not consistently archived.
7. **Prospective 2026/27 GW1:** frozen run `20261013T072534Z_76c01a55` has 552 prediction rows and 11 hashed pre-match snapshot files. It is frozen before fixtures and awaits actuals. The guarded result collection time is **2026-10-23 12:00 UTC**; do not evaluate before that cutoff or accept partial player/coach actual coverage.

## Ordered next actions

### P0 — Preserve and evaluate the prospective GW1 test
- Leave the frozen run and its snapshots immutable.
- After the safe cutoff, execute `./scripts/run_prospective_gw1_backtest.sh`.
- Require fixture-linked realized player and coach results, complete coverage checks, and a successful evaluator status before reporting lineup metrics.
- Report player/coach contributions separately, full-lineup realized score, paired comparisons, and uncertainty. Do not tune on this one holdout.

### P1 — Improve historical market provenance without fabricating inputs
- Continue endpoint/source-scope investigation for the two confirmed contaminated season-5 weekly files; keep both quarantined from certified training derivatives.
- Preserve isolated review-only contamination candidates and never overwrite raw archives.
- Do not label the existing audit-only derivative as clean or training-eligible.
- Seek reliable historical coach CR and pre-lock roster/transfer snapshots; where unavailable, label assumptions and report sensitivity analysis only.

### P2 — Refine player matchup features as a separate ablation
- Test position-specific opponent defensive allowances, pace/possession, and player role/minutes interactions in chronological folds.
- Compare each addition against the same baseline and identical rows/folds; use paired season-week-round uncertainty.
- Do not promote H2H features based solely on player-game MAE: the lineup-level result currently contradicts that choice.

### P3 — Revisit model selection only with a valid untouched evaluation
- Keep 2025/26 as previously reported evidence, not a globally untouched final holdout.
- Do not tune ensemble weights, calibration, rookie priors, or coach parameters against 2025/26 again.
- Make production changes only after paired end-to-end lineup validation on a genuinely future holdout.

## Current release stance

**No production model or configuration change is justified by the current experiments.** The next decisive evidence should come from the frozen prospective GW1 evaluation, then from improved source provenance and chronological matchup ablations.
