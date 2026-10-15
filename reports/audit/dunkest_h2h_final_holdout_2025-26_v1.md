# Player-vs-opponent history — final 2025/26 holdout

Generated UTC: 2026-10-13T09:29:44.821218+00:00

## Protocol

- Train on official-valid game-level Dunkest PDK targets from 2020/21–2024/25 (93,766 player-games).
- Evaluate once on the untouched 2025/26 season (18,412 player-games).
- Compare the same Random Forest architecture and training rows, with the baseline feature set versus three H2H features.
- H2H history is grouped by normalized player name and opponent. `searchsorted(side='left')` excludes every same-day game; only earlier official-valid target rows contribute.
- The 2025/26 setting is online one-step-ahead: later test rows may use prior dated 2025/26 outcomes, but not current/future labels.

## Results

| Model | MAE | RMSE | Bias | R² |
|---|---:|---:|---:|---:|
| Random Forest baseline | 7.5775 | 9.8563 | -0.1725 | 0.4214 |
| Random Forest + shrunk H2H | 7.5541 | 9.8267 | -0.1776 | 0.4249 |
| Previous-10 PDK mean | 7.7886 | 10.1539 | -0.0479 | 0.3859 |

Paired bootstrap by target calendar date, 10,000 replicates: RF+H2H minus baseline RF delta MAE **-0.0234**, 95% CI **[-0.0351, -0.0119]**. Fraction of bootstrap estimates below zero: 1.0000.

## H2H coverage

- Rows with prior player-vs-opponent games: 89,463 / 112,178 (79.8%).
- Distinct player-opponent groups: 22,715.
- Shrinkage uses three pseudo-observations from the player's general previous-five-game PDK mean.

## Interpretation and production decision

This is the key independent-season check for the H2H idea. If the confidence interval excludes zero, it supports a robust incremental gain on the 2025/26 game-level target. It still does not automatically justify production integration: the production predictor must reproduce the same pre-lock feature logic, and this game-level PDK target differs from the weekly-round total used in the earlier experiment. Production model/configuration remains unchanged.

## Artifacts

- Predictions: `reports/audit/dunkest_h2h_final_holdout_2025-26_v1_predictions.csv`
- Metrics: `reports/audit/dunkest_h2h_final_holdout_2025-26_v1_metrics.csv`
- Audit: `reports/audit/dunkest_h2h_final_holdout_2025-26_v1.json`
