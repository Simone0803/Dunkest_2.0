# Same-constraint lineup baselines and multi-gameweek policy — paired bootstrap

Generated (UTC): 2026-10-14T19:17:07.790440+00:00

## Coverage

{
  "same_constraint_baselines": {
    "rounds_optimized": 409,
    "rounds_strict_complete_all_strategies": 2,
    "rounds_excluded_for_incomplete_actuals": 407
  },
  "sequential_transfer_policy": {
    "rounds_optimized_any_scenario": 409,
    "rounds_complete_across_all_penalties": 11,
    "rounds_excluded_for_incomplete_actuals": 398,
    "scenarios": [
      0.0,
      2.5,
      5.0
    ],
    "scoring_malus_per_transfer": 5.0
  }
}

## Comparisons

                     left                          right  n_paired_rounds  mean_difference  median_difference  win_rate  ci95_low  ci95_high  bootstrap_replicates     seed                 experiment                  comparison
model_realized_team_score   baseline_realized_team_score                2         7.285000             7.2850  0.500000 -0.480000  15.050000                 10000 20261014  same_constraint_baselines  model_milp_minus_previous5
model_realized_team_score pdk_per_cr_realized_team_score                2        73.652500            73.6525  1.000000 59.925000  87.380000                 10000 20261015  same_constraint_baselines model_milp_minus_pdk_per_cr
model_realized_team_score  role_rank_realized_team_score                2         8.320000             8.3200  0.500000 -6.130000  22.770000                 10000 20261016  same_constraint_baselines  model_milp_minus_role_rank
                      2.5                            0.0               11        10.976818             2.7500  0.545455  2.001364  22.877284                 10000 20261114 sequential_transfer_policy penalty_2_5_minus_penalty_0
                      2.5                            5.0               11         0.736364             0.0000  0.181818 -0.142727   1.959773                 10000 20261115 sequential_transfer_policy penalty_2_5_minus_penalty_5
                      5.0                            0.0               11        10.240455             0.0000  0.363636  0.943636  22.167727                 10000 20261116 sequential_transfer_policy   penalty_5_minus_penalty_0

## Interpretation limits

- Historical player market and availability snapshots are incomplete; these results apply only to the reconstructed lagged candidate universe.
- Coach CR is fixed to 10 and coach actuals are reconstructed neutral-credit base scores, not exact price-adjusted official coach outcomes.
- Sequential transfer rosters are simulated recommendations, not the user's actual historical carried roster.
- Bootstrap intervals quantify sampling uncertainty conditional on the observed strict paired rounds; they do not remove market reconstruction bias.

No production parameters were changed.
