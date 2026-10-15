# Historical Dunkest coach base-score reconstruction — V1

Generated (UTC): 2026-10-13T08:17:47.246469+00:00

## What is reconstructed

For each NBA game and each team, the current Dunkest coach scoring rules are applied to final team points, margin, threshold bonuses/penalties and overtime. Coach credits are set equal on both sides, so the credit-difference multiplier is exactly 1.0. This isolates the base coach score that is recoverable from the NBA boxscore.

It is **not** an exact historical credit-adjusted coach score: historical coach CR prices are not archived in the local data.

- Games reconstructed: 9,519
- Team-game coach outcome rows: 19,038
- Overtime games: 502

## Chronological model evaluation

test_season                         method    n       mae      rmse  bias_pred_minus_actual
    2022-23        model_pregame_team_form 2460 16.127433 17.740191                0.028541
    2022-23  baseline_previous5_base_score 2460 16.873659 19.506902                0.007967
    2022-23 baseline_previous10_base_score 2460 16.636545 18.706157               -0.001829
    2022-23          baseline_train_median 2460 17.397967 18.320886                0.384146
    2023-24        model_pregame_team_form 2460 16.249609 18.004627               -0.027768
    2023-24  baseline_previous5_base_score 2460 17.007642 20.005123               -0.005366
    2023-24 baseline_previous10_base_score 2460 16.606951 19.124526                0.013537
    2023-24          baseline_train_median 2460 18.284553 19.409536                0.345528
    2024-25        model_pregame_team_form 2460 16.000109 17.980021                0.019002
    2024-25  baseline_previous5_base_score 2460 16.729512 19.850687                0.010650
    2024-25 baseline_previous10_base_score 2460 16.491138 19.125860               -0.000813
    2024-25          baseline_train_median 2460 18.448780 19.560060                0.376423
    2025-26        model_pregame_team_form 2460 15.915299 18.007851               -0.013995
    2025-26  baseline_previous5_base_score 2460 16.964797 20.183029               -0.012602
    2025-26 baseline_previous10_base_score 2460 16.649228 19.428757               -0.016789
    2025-26          baseline_train_median 2460 18.726423 19.883921                0.318293

The model predicts neutral-credit base coach PDK from prior team/offensive/defensive form. Test-season outcomes are never used to fit that season's model; rolling features within the test season use only earlier game dates.

## Limitations

1. Exact historical coach PDK still requires historical coach CR and opponent coach CR, or a validated reconstruction of those prices.
2. The base score uses the current repository scoring rules; historical rule changes have not been independently verified.
3. This evaluates coach score prediction, not a full budget-constrained player-plus-coach lineup optimizer.

## Artifacts

- Reconstructed outcomes: `reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_outcomes.csv`
- Walk-forward predictions: `reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_predictions.csv`
- Metrics: `reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_metrics.csv`
- Audit JSON: `reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1.json`
