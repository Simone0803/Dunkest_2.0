# Nested production / conditional-tail blend — V1

Generated UTC: 2026-10-14T20:15:29.363557+00:00

## Method

For each held-out season, the direct production ensemble and a conditional PDK≥25 mixture are fit only on earlier seasons. The blend weight is selected from {0, .25, .5, .75, 1} using a later-in-time 20% validation slice inside the training block; the outer test season is not used for blend selection. The 2025/26 holdout and frozen 2026/27 prospective bundle are excluded.

## Pooled outer-fold metrics

          candidate     n    mae    rmse  bias_pred_minus_actual  mae_actual_ge25  mae_actual_ge30  mae_history_lt5
production_ensemble 57682 7.5573  9.8230                 -0.1067          12.1888          14.1802           5.2229
     tail_mixture25 57682 7.5580  9.8271                 -0.0536          12.0874          14.0516           5.1914
       nested_blend 57682 7.5477  9.8119                 -0.1014          12.1548          14.1409           5.1993
    baseline_prev10 57682 7.7756 10.1316                 -0.0307          12.0176          13.7098           6.3476

## Outer-fold metrics

fold_season_id fold_season           candidate  selected_tail_weight     n    mae    rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5
             9     2022-23 production_ensemble                   NaN 19165 7.5582  9.8153                 -0.1083          12.3034           4310          14.2199           2903           5.4348            384
             9     2022-23      tail_mixture25                   NaN 19165 7.5671  9.8298                 -0.0241          12.1892           4310          14.0474           2903           5.4996            384
             9     2022-23        nested_blend                0.2500 19165 7.5520  9.8065                 -0.0873          12.2610           4310          14.1630           2903           5.4398            384
             9     2022-23     baseline_prev10                   NaN 19165 7.7689 10.1134                 -0.0687          12.0819           4310          13.7223           2903           6.5236            384
            13     2023-24 production_ensemble                   NaN 18927 7.5464  9.7977                 -0.1471          12.2774           4369          14.2122           2972           5.4331            434
            13     2023-24      tail_mixture25                   NaN 18927 7.5588  9.8061                  0.0258          12.0626           4369          13.9520           2972           5.3620            434
            13     2023-24        nested_blend                0.2500 18927 7.5409  9.7882                 -0.1039          12.2146           4369          14.1386           2972           5.4071            434
            13     2023-24     baseline_prev10                   NaN 18927 7.7652 10.1003                  0.0479          11.9552           4369          13.5282           2972           6.4113            434
            19     2024-25 production_ensemble                   NaN 19590 7.5668  9.8548                 -0.0661          11.9912           4425          14.1106           2919           4.8126            404
            19     2024-25      tail_mixture25                   NaN 19590 7.5483  9.8446                 -0.1592          12.0119           4425          14.1520           2919           4.7251            404
            19     2024-25        nested_blend                0.5000 19590 7.5500  9.8399                 -0.1127          11.9930           4425          14.1215           2919           4.7634            404
            19     2024-25     baseline_prev10                   NaN 19590 7.7920 10.1795                 -0.0694          12.0151           4425          13.8729           2919           6.1140            404

## Inner selection audit

[
  {
    "season": "2022-23",
    "outer_train_rows": 36084,
    "outer_test_rows": 19165,
    "inner_train_rows": 29188,
    "inner_valid_rows": 6896,
    "inner_cutoff_utc": "2022-02-02T00:00:00",
    "inner_blend_scores": [
      {
        "tail_weight": 0.0,
        "mae": 7.92900523072502,
        "rmse": 10.292191114332473
      },
      {
        "tail_weight": 0.25,
        "mae": 7.92130826226971,
        "rmse": 10.27792428990539
      },
      {
        "tail_weight": 0.5,
        "mae": 7.922056681306375,
        "rmse": 10.27274738129619
      },
      {
        "tail_weight": 0.75,
        "mae": 7.928947881074525,
        "rmse": 10.2766741257396
      },
      {
        "tail_weight": 1.0,
        "mae": 7.941542172065051,
        "rmse": 10.289694100855543
      }
    ],
    "selected_tail_weight": 0.25,
    "direct_model_weights": {
      "ridge": 0.33438470930071806,
      "rf": 0.33180521420229286,
      "gbr": 0.3338100764969891
    },
    "production_feature_count": 50,
    "inner_tail": {
      "tail_train_rows": 29188,
      "tail_high_rows": 5537,
      "tail_low_rows": 23651,
      "tail_feature_count": 50
    },
    "outer_tail": {
      "tail_train_rows": 36084,
      "tail_high_rows": 7034,
      "tail_low_rows": 29050,
      "tail_feature_count": 50
    }
  },
  {
    "season": "2023-24",
    "outer_train_rows": 55249,
    "outer_test_rows": 18927,
    "inner_train_rows": 44546,
    "inner_valid_rows": 10703,
    "inner_cutoff_utc": "2022-12-30T00:00:00",
    "inner_blend_scores": [
      {
        "tail_weight": 0.0,
        "mae": 7.5913602606693455,
        "rmse": 9.952092275635358
      },
      {
        "tail_weight": 0.25,
        "mae": 7.5867047602092015,
        "rmse": 9.945649981139898
      },
      {
        "tail_weight": 0.5,
        "mae": 7.58740023944509,
        "rmse": 9.945550779876879
      },
      {
        "tail_weight": 0.75,
        "mae": 7.5924780146857405,
        "rmse": 9.951794861533555
      },
      {
        "tail_weight": 1.0,
        "mae": 7.601520632756783,
        "rmse": 9.964370301236114
      }
    ],
    "selected_tail_weight": 0.25,
    "direct_model_weights": {
      "ridge": 0.3332244783204819,
      "rf": 0.3324871383157729,
      "gbr": 0.3342883833637452
    },
    "production_feature_count": 50,
    "inner_tail": {
      "tail_train_rows": 44546,
      "tail_high_rows": 8856,
      "tail_low_rows": 35690,
      "tail_feature_count": 50
    },
    "outer_tail": {
      "tail_train_rows": 55249,
      "tail_high_rows": 11344,
      "tail_low_rows": 43905,
      "tail_feature_count": 50
    }
  },
  {
    "season": "2024-25",
    "outer_train_rows": 74176,
    "outer_test_rows": 19590,
    "inner_train_rows": 58600,
    "inner_valid_rows": 15576,
    "inner_cutoff_utc": "2023-11-24T00:00:00",
    "inner_blend_scores": [
      {
        "tail_weight": 0.0,
        "mae": 7.561021926937658,
        "rmse": 9.830381096977941
      },
      {
        "tail_weight": 0.25,
        "mae": 7.55033102724041,
        "rmse": 9.825491077070197
      },
      {
        "tail_weight": 0.5,
        "mae": 7.54556418040549,
        "rmse": 9.829331471119591
      },
      {
        "tail_weight": 0.75,
        "mae": 7.547316382178477,
        "rmse": 9.841892059075288
      },
      {
        "tail_weight": 1.0,
        "mae": 7.555069643891681,
        "rmse": 9.863139525811626
      }
    ],
    "selected_tail_weight": 0.5,
    "direct_model_weights": {
      "ridge": 0.33347698522147456,
      "rf": 0.3329838533863463,
      "gbr": 0.33353916139217915
    },
    "production_feature_count": 50,
    "inner_tail": {
      "tail_train_rows": 58600,
      "tail_high_rows": 12065,
      "tail_low_rows": 46535,
      "tail_feature_count": 50
    },
    "outer_tail": {
      "tail_train_rows": 74176,
      "tail_high_rows": 15713,
      "tail_low_rows": 58463,
      "tail_feature_count": 50
    }
  }
]

## Paired uncertainty and subgroup audit

A paired bootstrap resampling 10,000 times over 475 target-date clusters compares the nested blend against the direct production ensemble. Mean absolute error difference (blend minus production) is **−0.00958 PDK**, 95% CI **[−0.01243, −0.00667]**. The absolute gain is small, even though the interval is consistently below zero under this date-cluster bootstrap.

| Subgroup | N | Production MAE | Tail MAE | Nested blend MAE |
|---|---:|---:|---:|---:|
| No prior Dunkest PDK games | 249 | 5.4703 | 5.4626 | 5.4621 |
| Fewer than 3 prior Dunkest games | 743 | 5.0623 | 5.0160 | 5.0325 |
| Fewer than 5 prior Dunkest games | 1,222 | 5.2285 | 5.1947 | 5.2045 |
| At least 5 prior Dunkest games | 56,460 | 7.6077 | 7.6091 | 7.5984 |
| Actual PDK ≥25 | 13,104 | 12.1893 | 12.0871 | 12.1550 |
| Actual PDK ≥30 | 8,794 | 14.1810 | 14.0499 | 14.1410 |

The blend improves overall MAE/RMSE in each outer season and improves pooled high-score MAE relative to the direct model. However, the tail-only model is better on the actual ≥25/≥30 subgroups; blending dilutes some of that gain, and the ≥30 MAE in 2024/25 is slightly worse than the direct model. The no-prior-history subgroup is only 249 rows, too small to claim robust rookie generalization; it is not a validated rookie label, merely no observed Dunkest PDK history.

## Decision

**Keep the nested blend in research, do not promote it to production yet.** It yields a statistically stable but very small overall gain, while the benefit for high-score players is not uniformly strongest under the blend and the true rookie sample is small. The production feature enrichment remains active; no fixed tail weight is installed. Next, investigate role-aware minutes and the conditional tail separately, and require a wider past-only cohort validation before changing the production score calculation. These are player-game forecasting results only, not realized lineup validation.

No commit or push.
