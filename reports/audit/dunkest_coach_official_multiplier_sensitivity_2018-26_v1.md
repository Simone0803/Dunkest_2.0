# Dunkest coach official multiplier sensitivity — V1

Generated UTC: 2026-10-13T08:50:24.265263+00:00

## Objective

The base-score model is trained and evaluated without coach credits. This audit then applies the official deterministic multiplier to both each walk-forward prediction and its realized base score under explicit price-difference scenarios.

## Official rule verification

The coefficient table is checked against the official Dunkest rule page. Positive base scores are multiplied by the coefficient; negative base scores are divided by it. All threshold checks passed.

| CR difference scenario | MAE if coach has higher price | MAE if coach has lower price |
|---:|---:|---:|
| 0 | 16.073 | 16.073 |
| 1.5 | 15.269 | 16.877 |
| 3 | 14.627 | 18.323 |
| 5 | 13.984 | 19.770 |
| 7 | 13.341 | 21.217 |
| 10 | 12.698 | 22.663 |
| 14 | 12.055 | 24.110 |
| 16 | 11.251 | 25.717 |

## Interpretation

- Walk-forward base-score predictions analyzed: 9,840.
- These CR differences are controlled scenarios, not archived historical prices. Therefore the transformed MAE/RMSE show sensitivity to the official multiplier, not exact historical PDK accuracy.
- To calculate exact historical PDK for a given game, the model also needs both coaches’ pregame CRs for that game. The rule table alone determines the coefficient only after that CR difference is known.
- The base-score model metrics remain those in `dunkest_coach_base_points_walk_forward_2018-26_v1_metrics.csv`.

## Artifacts

- Pooled scenario metrics: `reports/audit/dunkest_coach_official_multiplier_sensitivity_2018-26_v1_metrics.csv`
- Per-season scenario metrics: `reports/audit/dunkest_coach_official_multiplier_sensitivity_2018-26_v1_scenarios.csv`
- Audit JSON: `reports/audit/dunkest_coach_official_multiplier_sensitivity_2018-26_v1.json`

Production model/configuration were not changed.
