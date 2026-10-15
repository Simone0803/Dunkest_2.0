# Plusvalenza: ricostruzione del prezzo pre-giornata — V1

Generated UTC: 2026-10-15

## Objective

Train the Dunkest price-change model using the price available before the target gameweek, rather than the price reported after the gameweek. The official historical rows contain the gameweek PDK score, the resulting plusvalenza (ΔCR), and the updated CR.

## Transformation

For every historical player-gameweek row:

`CR_start = CR_end - plusvalenza`

The model is then fitted on `(PDK, CR_start, PDK / CR_start) -> plusvalenza`. At prediction time, the input `cr` is already the current market price before the upcoming gameweek, so the feature basis now matches between training and inference. The credit bands, residual pools, and supported price range also use reconstructed starting CR.

## Data

- Official Dunkest history: 93,744 rows.
- Seasons: 2020/21–2024/25 (IDs 5, 7, 9, 13, 19).
- NBA team coverage: 30 teams in each season.
- Observed gameweeks: 59, 64, 64, 62, 64.
- Valid training rows: 87,626.
- Expanding-origin walk-forward validation rows: 17,256.
- The 2026/27 GW1 prospective bundle was not loaded or tuned.

## Same-data walk-forward comparison

Both versions use the same official rows, temporal splits, estimator family, calibration, and target. The only difference is the historical CR feature basis.

| Metric | Old: end CR feature | New: reconstructed start CR |
|---|---:|---:|
| ΔCR MAE | 0.069512 | **0.061434** |
| Mean-window baseline MAE | 0.182975 | 0.182975 |
| Validation rows | 17,256 | 17,256 |
| Multiclass Brier, raw gain/flat/loss | 0.318655 | **0.269101** |
| Multiclass Brier, calibrated | 0.314660 | **0.261478** |
| Multiclass log loss, raw | 0.644684 | **0.584323** |
| Multiclass log loss, calibrated | 0.562063 | **0.505167** |
| Calibrated gain-probability bias | +0.205 pp | +0.187 pp |

The corrected CR basis reduces walk-forward ΔCR MAE by 11.6% versus the old feature basis on identical rows and splits. Calibrated multiclass Brier improves by about 16.9%. This is evidence that removing the end-price leakage improves prediction, not proof that all Dunkest pricing rules have been reverse-engineered exactly.

## Implementation

- `src/dunkest/models/capital_gain.py`: added `_starting_credit_from_end_price`; training reconstructs starting CR before fitting, cross-validation, credit-band calibration, and residual pooling.
- Forecasting continues to use the live pre-gameweek market CR.
- Forecast output now exposes `capital_gain_price_basis` and states the transformation in `capital_gain_metric_validation`.
- `tests/test_role_minutes_projection.py`: test for exact reconstruction and synthetic historical data now models end CR = start CR + plusvalenza.

## Interpretation and limits

The model estimates the empirical score-to-ΔCR relationship conditional on starting CR, using walk-forward residuals and past-only probability calibration. It does not reconstruct missing historical rows or invent prices. Historical PDK is the official stats-table value for the relevant Dunkest gameweek scope; any future audit of whether multi-round weeks should be aggregated differently must preserve the source's round mapping rather than silently sum or average rows.

No commit, push, staging, or destructive cleanup was performed.
