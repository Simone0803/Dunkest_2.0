# Rookie and plusvalenza calibration audit — 2026-10-13

## Changes applied

### 1. Rookie PDK/minute target

- Added `scripts/build_official_rookie_pdk_labels_v1.py` and generated `data/rookie_official_pdk.csv`.
- The file contains 264 official rookie-season labels across draft classes 2020–2025. Each label is the player's official Dunkest PDK total divided by official minutes in their first verified Dunkest season on or after the draft year.
- The builder checks one-to-one join keys and requires the joined official PDK values to match the training target exactly. Rebuilding to a temporary path produced a byte-identical CSV.
- `load_college_rookie_priors` now uses the official Dunkest target when at least 40 labels across at least four draft classes are available. It does not mix official targets with the older NBA box-score proxy in one rate model; the proxy remains a fallback if the official label dataset is unavailable or too small.
- The minutes prior remains trained on the broader historical rookie sample, since minutes are a separate target and more draft classes are available.
- Walk-forward rate MAE: **0.10741 PDK/min**, versus **0.12662 PDK/min** for the training-window median baseline (about 15.2% lower MAE). The test covers later draft classes 2022–2025; this is a small cohort-level sample, so the prior remains capped at 20%.
- Minutes-prior MAE remains **5.84 minutes**, versus **7.35 minutes** for its baseline.

### 2. Plusvalenza model and uncertainty

- Replaced the all-price Ridge-only fit with a CR-adaptive estimator: ExtraTrees for CR below 5, a 50/50 Ridge–ExtraTrees blend for CR from 5 to below 9, and Ridge for CR 9 and above. Walk-forward evidence showed the nonlinear estimator was helpful at low CR but extrapolated less reliably at high CR.
- Added past-only bias calibration by credit band. For every validation fold, the correction is estimated exclusively from earlier out-of-fold residuals.
- Fixed a units error: the plusvalenza residual is in **credits**, so it is now added after converting the score forecast to ΔCR, not to the PDK score itself.
- Residual distributions are sampled within CR bands when enough out-of-fold observations are available; otherwise the global residual pool is used.
- Walk-forward MAE after calibration: **0.06843 CR**, versus **0.17919 CR** for the training-window mean baseline, on **7,436 out-of-fold validation rows** from 39,238 historical rows.
- The score-to-CR probability audit still shows some optimism in gain probabilities: in a conversion-only test with the actual PDK score known, mean predicted gain probability exceeded the observed gain rate by about 3.3 percentage points. This audit omits score-forecast error, so probability calibration remains a limitation; expected ΔCR and interval construction are now unit-consistent.

## Roster objective

The season-opener configuration now uses `risk_adjusted` with `risk_lambda: 0.10`, to avoid letting uncertain rookie projections dominate the roster.

| Top-lineup objective | Expected PDK | P10–P90 spread | 2026-class rookies |
|---|---:|---:|---:|
| Expected value | 201.75 | 154.29 | 5 |
| Risk-adjusted, λ = 0.10 | 199.71 | 134.31 | 1 |

This is a model-based tradeoff, not proof of better realized scores: the risk-adjusted top lineup gives up about 1% projected mean while reducing the P10–P90 spread by about 13%. The three risk-adjusted recommendations contain 1, 3, and 3 rookies from the 2026 draft class, respectively.

## Current run

- Prediction run: `data/predictions/20261013T184846Z_21d331f5`
- Gameweek: 1, season 2026–27
- Budget: 95 CR for each lineup
- Objective: risk-adjusted, λ = 0.10

## Validation status

- Full test suite: **281 passed**.
- Existing warnings remain: the official PDK overlay leaves 48 of 24,146 2025–26 player-game rows unmatched; malformed lineup tags for Cleveland and Denver are ignored; and the opener uses the legacy prior-season GW35 market snapshot because a versioned snapshot is missing.
- No claim is made that the projected lineup scores are realized outcomes. The next major validation step is a walk-forward roster backtest with verified pre-lock market, injury, coach, and player-score snapshots.
