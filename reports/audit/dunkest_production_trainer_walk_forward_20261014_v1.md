# Exact production trainer — player-level walk-forward V1

Generated UTC: 2026-10-14T20:05:27.426213+00:00

## Method

The exact `train_multiseason_models` adapter and production `train_models` trainer are refit separately before each held-out season (2022/23, 2023/24, 2024/25). Only earlier certified Dunkest official-PDK rows enter training; the model learns its ensemble weights and calibration using the training block’s own past-only folds. Evaluation uses the held-out season. The 2025/26 holdout and frozen 2026/27 bundle are not loaded.

## Pooled results

          candidate     n    mae    rmse  bias_pred_minus_actual  mae_actual_ge25  mae_actual_ge30  mae_history_lt5
production_ensemble 57682 7.5573  9.8230                 -0.1067          12.1888          14.1802           5.2229
    baseline_prev10 57682 7.7756 10.1316                 -0.0307          12.0176          13.7098           6.3476

## Fold results

fold_season_id fold_season           candidate     n    mae    rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5
             9     2022-23 production_ensemble 19165 7.5582  9.8153                 -0.1083          12.3034           4310          14.2199           2903           5.4348            384
             9     2022-23     baseline_prev10 19165 7.7689 10.1134                 -0.0687          12.0819           4310          13.7223           2903           6.5236            384
            13     2023-24 production_ensemble 18927 7.5464  9.7977                 -0.1471          12.2774           4369          14.2122           2972           5.4331            434
            13     2023-24     baseline_prev10 18927 7.7652 10.1003                  0.0479          11.9552           4369          13.5282           2972           6.4113            434
            19     2024-25 production_ensemble 19590 7.5668  9.8548                 -0.0661          11.9912           4425          14.1106           2919           4.8126            404
            19     2024-25     baseline_prev10 19590 7.7920 10.1795                 -0.0694          12.0151           4425          13.8729           2919           6.1140            404

## Fold-specific model metadata

[
  {
    "season": "2022-23",
    "train_rows": 36084,
    "test_rows": 19165,
    "feature_count": 50,
    "features": [
      "pdk_mean_3",
      "pdk_mean_5",
      "pdk_mean_10",
      "pdk_std_5",
      "pdk_median_5",
      "pdk_season_mean",
      "min_mean_5",
      "pdk_per_min_season",
      "expected_pdk_minutes_model",
      "pts_mean_5",
      "reb_mean_5",
      "ast_mean_5",
      "stl_per36_5",
      "blk_per36_5",
      "tov_per36_5",
      "oreb_per36_5",
      "dreb_per36_5",
      "fg3m_per36_5",
      "fga_per36_5",
      "rest_days",
      "is_b2b",
      "is_home",
      "player_opp_pdk_per_min",
      "player_opp_games",
      "lag1_pdk",
      "lag2_pdk",
      "lag3_pdk",
      "lag4_pdk",
      "lag5_pdk",
      "pdk_trend_3v10",
      "min_trend_3v5",
      "min_last_vs_prev5",
      "lag1_nba_min",
      "lag2_nba_min",
      "lag3_nba_min",
      "prev3_nba_min_mean",
      "lag1_nba_pts",
      "lag2_nba_pts",
      "lag3_nba_pts",
      "prev3_nba_pts_mean",
      "lag1_nba_reb",
      "lag2_nba_reb",
      "lag3_nba_reb",
      "prev3_nba_reb_mean",
      "lag1_nba_ast",
      "lag2_nba_ast",
      "lag3_nba_ast",
      "prev3_nba_ast_mean",
      "history_games_before_target",
      "nba_history_games_before_target"
    ],
    "weights": {
      "ridge": 0.33438470930071806,
      "rf": 0.3318052142022928,
      "gbr": 0.3338100764969891
    },
    "ridge_alpha": 0.3,
    "residual_std": 10.233586658942349
  },
  {
    "season": "2023-24",
    "train_rows": 55249,
    "test_rows": 18927,
    "feature_count": 50,
    "features": [
      "pdk_mean_3",
      "pdk_mean_5",
      "pdk_mean_10",
      "pdk_std_5",
      "pdk_median_5",
      "pdk_season_mean",
      "min_mean_5",
      "pdk_per_min_season",
      "expected_pdk_minutes_model",
      "pts_mean_5",
      "reb_mean_5",
      "ast_mean_5",
      "stl_per36_5",
      "blk_per36_5",
      "tov_per36_5",
      "oreb_per36_5",
      "dreb_per36_5",
      "fg3m_per36_5",
      "fga_per36_5",
      "rest_days",
      "is_b2b",
      "is_home",
      "player_opp_pdk_per_min",
      "player_opp_games",
      "lag1_pdk",
      "lag2_pdk",
      "lag3_pdk",
      "lag4_pdk",
      "lag5_pdk",
      "pdk_trend_3v10",
      "min_trend_3v5",
      "min_last_vs_prev5",
      "lag1_nba_min",
      "lag2_nba_min",
      "lag3_nba_min",
      "prev3_nba_min_mean",
      "lag1_nba_pts",
      "lag2_nba_pts",
      "lag3_nba_pts",
      "prev3_nba_pts_mean",
      "lag1_nba_reb",
      "lag2_nba_reb",
      "lag3_nba_reb",
      "prev3_nba_reb_mean",
      "lag1_nba_ast",
      "lag2_nba_ast",
      "lag3_nba_ast",
      "prev3_nba_ast_mean",
      "history_games_before_target",
      "nba_history_games_before_target"
    ],
    "weights": {
      "ridge": 0.3332244783204819,
      "rf": 0.3324871383157729,
      "gbr": 0.3342883833637452
    },
    "ridge_alpha": 0.3,
    "residual_std": 9.874649559152502
  },
  {
    "season": "2024-25",
    "train_rows": 74176,
    "test_rows": 19590,
    "feature_count": 50,
    "features": [
      "pdk_mean_3",
      "pdk_mean_5",
      "pdk_mean_10",
      "pdk_std_5",
      "pdk_median_5",
      "pdk_season_mean",
      "min_mean_5",
      "pdk_per_min_season",
      "expected_pdk_minutes_model",
      "pts_mean_5",
      "reb_mean_5",
      "ast_mean_5",
      "stl_per36_5",
      "blk_per36_5",
      "tov_per36_5",
      "oreb_per36_5",
      "dreb_per36_5",
      "fg3m_per36_5",
      "fga_per36_5",
      "rest_days",
      "is_b2b",
      "is_home",
      "player_opp_pdk_per_min",
      "player_opp_games",
      "lag1_pdk",
      "lag2_pdk",
      "lag3_pdk",
      "lag4_pdk",
      "lag5_pdk",
      "pdk_trend_3v10",
      "min_trend_3v5",
      "min_last_vs_prev5",
      "lag1_nba_min",
      "lag2_nba_min",
      "lag3_nba_min",
      "prev3_nba_min_mean",
      "lag1_nba_pts",
      "lag2_nba_pts",
      "lag3_nba_pts",
      "prev3_nba_pts_mean",
      "lag1_nba_reb",
      "lag2_nba_reb",
      "lag3_nba_reb",
      "prev3_nba_reb_mean",
      "lag1_nba_ast",
      "lag2_nba_ast",
      "lag3_nba_ast",
      "prev3_nba_ast_mean",
      "history_games_before_target",
      "nba_history_games_before_target"
    ],
    "weights": {
      "ridge": 0.33347698522147456,
      "rf": 0.3329838533863463,
      "gbr": 0.33353916139217915
    },
    "ridge_alpha": 0.3,
    "residual_std": 9.842142062722152
  }
]

## Interpretation

This audit measures the exact production trainer with the expanded feature schema. The previous lag ablation used fixed ExtraTrees/HistGradientBoosting candidates; those results were research evidence for feature enrichment, not a substitute for this production-trainer test. Do not use these player-level results as evidence of realized lineup superiority.

No commit or push.
