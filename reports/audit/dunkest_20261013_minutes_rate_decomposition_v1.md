# Minutes × rate decomposition — V1

Generated UTC: 2026-10-13T13:59:17.758983+00:00

## Design

Compare direct player-game Dunkest PDK forecasts with a two-stage forecast: expected minutes × expected PDK per minute. Target-game NBA minutes/statistics are labels only and never predictors. Candidate models are fitted in expanding-origin folds (2022/23, 2023/24, 2024/25), with all earlier eligible seasons used for training. The 2025/26 holdout and frozen 2026/27 GW1 prediction bundle are not loaded.

## Data integrity

- Rows after target-minute linkage: 93,753
- Target minutes non-null: 100.000%
- Lag-1 PDK mismatches: 0
- Duplicate crosswalk keys: 0; conflicting duplicate labels: 0
- Only the 2020/21–2024/25 training parquet and 2018–2025 enriched historical crosswalk were read.

## Pooled candidate results

               candidate     n     mae     rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_low_history_lt5  n_low_history_lt5
 minutes_hgb_x_rate_et12 57682 7.55559  9.86579                -0.55193         12.52221          13104         14.53196           8794              5.26104               1222
minutes_et12_x_rate_et12 57682 7.56197  9.88248                -0.61095         12.57858          13104         14.58704           8794              5.30122               1222
             direct_et12 57682 7.56576  9.83902                -0.19890         12.29172          13104         14.31164           8794              5.18328               1222
  minutes_hgb_x_rate_hgb 57682 7.56733  9.87641                -0.50378         12.48074          13104         14.45368           8794              5.26005               1222
 minutes_et12_x_rate_hgb 57682 7.57209  9.89085                -0.56508         12.53592          13104         14.50809           8794              5.29929               1222
              direct_hgb 57682 7.57227  9.83061                 0.02212         12.02739          13104         13.90933           8794              5.25504               1222
          baseline_prev5 57682 7.98231 10.43836                -0.00571         12.17217          13104         13.82308           8794              6.34831               1222

## Fold metrics

fold_season_id fold_season                candidate     n     mae     rmse  bias_pred_minus_actual
            13     2023-24           baseline_prev5 18927 7.96870 10.41537                 0.06383
            19     2024-25           baseline_prev5 19590 8.00285 10.45844                -0.02286
             9     2022-23           baseline_prev5 19165 7.97474 10.44049                -0.05684
            13     2023-24              direct_et12 18927 7.56279  9.81471                -0.15419
            19     2024-25              direct_et12 19590 7.57911  9.87304                -0.13839
             9     2022-23              direct_et12 19165 7.55505  9.82815                -0.30491
            13     2023-24               direct_hgb 18927 7.56311  9.79798                 0.03394
            19     2024-25               direct_hgb 19590 7.57088  9.86730                -0.04583
             9     2022-23               direct_hgb 19165 7.58273  9.82520                 0.07992
            13     2023-24 minutes_et12_x_rate_et12 18927 7.54907  9.84618                -0.57865
            19     2024-25 minutes_et12_x_rate_et12 19590 7.55043  9.90042                -0.61006
             9     2022-23 minutes_et12_x_rate_et12 19165 7.58650  9.89990                -0.64375
            13     2023-24  minutes_et12_x_rate_hgb 18927 7.55496  9.85241                -0.53876
            19     2024-25  minutes_et12_x_rate_hgb 19590 7.57365  9.92699                -0.59129
             9     2022-23  minutes_et12_x_rate_hgb 19165 7.58740  9.89173                -0.56429
            13     2023-24  minutes_hgb_x_rate_et12 18927 7.54543  9.82783                -0.46705
            19     2024-25  minutes_hgb_x_rate_et12 19590 7.53219  9.88300                -0.62513
             9     2022-23  minutes_hgb_x_rate_et12 19165 7.58953  9.88558                -0.56094
            13     2023-24   minutes_hgb_x_rate_hgb 18927 7.55485  9.83840                -0.42427
            19     2024-25   minutes_hgb_x_rate_hgb 19590 7.55723  9.91066                -0.60578
             9     2022-23   minutes_hgb_x_rate_hgb 19165 7.58997  9.87880                -0.47804

## Paired date-cluster bootstrap

Delta is decomposition MAE minus direct-model MAE; negative favors decomposition.

{
  "2022-23": {
    "clusters": 163,
    "delta_mae_b_minus_a": 0.034476479963195625,
    "ci95": [
      0.011719054592768731,
      0.05837726929402562
    ]
  },
  "2023-24": {
    "clusters": 154,
    "delta_mae_b_minus_a": -0.017360050606212363,
    "ci95": [
      -0.040647963519990477,
      0.003417031493956294
    ]
  },
  "2024-25": {
    "clusters": 158,
    "delta_mae_b_minus_a": -0.04692433451391677,
    "ci95": [
      -0.06670236749336597,
      -0.02808095800235133
    ]
  }
}

## Minute component accuracy and rate-reference limitation

The minute MAE/RMSE rows are held-out fold metrics. The `rate_pdk_per_min / historical_train_rate_mean` row is only a descriptive in-sample training-mean reference, not a held-out rate-model metric; do not use that row as evidence of rate-prediction accuracy.

fold_season_id fold_season           target                  candidate     n     mae    rmse  bias_pred_minus_actual
             9     2022-23          minutes                       et12 19165 5.11262 6.65243                 0.16006
             9     2022-23          minutes                        hgb 19165 5.09148 6.60276                 0.30383
             9     2022-23 rate_pdk_per_min historical_train_rate_mean 35950 0.41961 0.64535                 0.00000
            13     2023-24          minutes                       et12 18927 5.02682 6.45759                 0.20061
            13     2023-24          minutes                        hgb 18927 5.00869 6.42076                 0.40045
            13     2023-24 rate_pdk_per_min historical_train_rate_mean 55067 0.39001 0.58391                 0.00000
            19     2024-25          minutes                       et12 19590 4.89934 6.38950                 0.18801
            19     2024-25          minutes                        hgb 19590 4.85223 6.32947                 0.16330
            19     2024-25 rate_pdk_per_min historical_train_rate_mean 73923 0.37958 0.55593                 0.00000

## Decision rule

This is a research experiment, not a production change. A candidate should not be promoted if it only improves pooled player-game MAE while harming high-score or low-history segments, or if date-cluster intervals are inconclusive. Lineup-level gains still require a valid historical player pool and matched coach/credit/transfer rules; this experiment does not claim lineup improvement.

## Artifacts

- Metrics: `reports/audit/dunkest_20261013_minutes_rate_decomposition_v1_metrics.csv`
- Predictions: `reports/audit/dunkest_20261013_minutes_rate_decomposition_v1_predictions.csv`
- Audit JSON: `reports/audit/dunkest_20261013_minutes_rate_decomposition_v1.json`

No production source/config/model/weights or prospective snapshot was changed. No commit or push was performed.
