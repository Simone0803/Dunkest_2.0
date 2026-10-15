# Conditional tail blend — V1

Generated UTC: 2026-10-13T14:09:41.492905+00:00

The blend is `(1-w) × direct HistGradientBoosting + w × threshold-25 mixture`. All predictions share identical labels and expanding-origin folds. This is a validation-only ensemble experiment, not production tuning on the 2025/26 holdout.

## Pooled metrics

            candidate  mixture_weight     n     mae    rmse  bias_pred_minus_actual  mae_actual_ge25  n_ge25  mae_actual_ge30  n_ge30
blend_mix_weight_0.50         0.50000 57682 7.55734 9.81521                -0.01415         12.01897   13104         13.92717    8794
blend_mix_weight_0.75         0.75000 57682 7.55747 9.81913                -0.03229         12.02671   13104         13.94838    8794
blend_mix_weight_0.25         0.25000 57682 7.56220 9.81904                 0.00399         12.01888   13104         13.91398    8794
            mixture25         1.00000 57682 7.56329 9.83079                -0.05043         12.04410   13104         13.97933    8794
           direct_hgb         0.00000 57682 7.57227 9.83061                 0.02212         12.02739   13104         13.90933    8794

## Paired date-cluster bootstrap vs direct HGB

Delta MAE is blend minus direct HGB; negative favors the blend.

{
  "blend_mix_weight_0.25": {
    "vs_direct_hgb_overall": {
      "n": 57682,
      "delta_mae_candidate_minus_baseline": -0.010065303061059336,
      "ci95": [
        -0.012347537513230308,
        -0.007844517116223412
      ],
      "clusters": 475,
      "reps": 3000
    },
    "vs_direct_hgb_actual_ge25": {
      "n": 13104,
      "delta_mae_candidate_minus_baseline": -0.008513924088989202,
      "ci95": [
        -0.014762673402052666,
        -0.0025147445986345536
      ],
      "clusters": 475,
      "reps": 3000
    },
    "vs_direct_hgb_actual_ge30": {
      "n": 8794,
      "delta_mae_candidate_minus_baseline": 0.0046473417399170245,
      "ci95": [
        -0.003444410659748619,
        0.013225735239441922
      ],
      "clusters": 474,
      "reps": 3000
    }
  },
  "blend_mix_weight_0.50": {
    "vs_direct_hgb_overall": {
      "n": 57682,
      "delta_mae_candidate_minus_baseline": -0.014931888129842613,
      "ci95": [
        -0.01954147651197454,
        -0.010411285196264955
      ],
      "clusters": 475,
      "reps": 3000
    },
    "vs_direct_hgb_actual_ge25": {
      "n": 13104,
      "delta_mae_candidate_minus_baseline": -0.008426285455069576,
      "ci95": [
        -0.020997514719733722,
        0.004398953025528353
      ],
      "clusters": 475,
      "reps": 3000
    },
    "vs_direct_hgb_actual_ge30": {
      "n": 8794,
      "delta_mae_candidate_minus_baseline": 0.017830915725914435,
      "ci95": [
        0.0019553196685317066,
        0.03446366292306292
      ],
      "clusters": 474,
      "reps": 3000
    }
  },
  "blend_mix_weight_0.75": {
    "vs_direct_hgb_overall": {
      "n": 57682,
      "delta_mae_candidate_minus_baseline": -0.014798138474189473,
      "ci95": [
        -0.021827794753664136,
        -0.007817783396339588
      ],
      "clusters": 475,
      "reps": 3000
    },
    "vs_direct_hgb_actual_ge25": {
      "n": 13104,
      "delta_mae_candidate_minus_baseline": -0.000686612175853876,
      "ci95": [
        -0.019945720483912317,
        0.017824874438002083
      ],
      "clusters": 475,
      "reps": 3000
    },
    "vs_direct_hgb_actual_ge30": {
      "n": 8794,
      "delta_mae_candidate_minus_baseline": 0.039046700438950754,
      "ci95": [
        0.013409555289404969,
        0.06384906850514614
      ],
      "clusters": 474,
      "reps": 3000
    }
  }
}

## Per-fold metrics

| Season | Candidate | MAE | RMSE | MAE actual PDK ≥25 | MAE actual PDK ≥30 |
|---|---|---:|---:|---:|---:|
| 2022/23 | Direct HGB | 7.58273 | 9.82520 | 12.07991 | 13.86554 |
| 2022/23 | 25% mixture blend | 7.56610 | 9.80797 | 12.06158 | 13.84689 |
| 2023/24 | Direct HGB | 7.56311 | 9.79798 | 12.06123 | 13.87107 |
| 2023/24 | 25% mixture blend | 7.55650 | 9.78997 | 12.06118 | 13.89580 |
| 2024/25 | Direct HGB | 7.57088 | 9.86730 | 11.94283 | 13.99184 |
| 2024/25 | 25% mixture blend | 7.56390 | 9.85782 | 11.93552 | 13.99922 |

The 25% mixture blend improves MAE and RMSE in all three validation folds. The ≥25 segment also improves slightly in every fold; the ≥30 segment improves in 2022/23 and is marginally worse in the next two seasons.

## Decision

A blend is not promoted solely on a small aggregate MAE change. It must preserve or improve high-score tails, improve RMSE/calibration, and then pass a complete lineup-level historical replay. No production source/config/weights/snapshot was changed; no commit or push.

## Artifacts

- Metrics: `reports/audit/dunkest_20261013_conditional_tail_blend_v1_metrics.csv`
- Predictions: `reports/audit/dunkest_20261013_conditional_tail_blend_v1_predictions.csv`
- Audit: `reports/audit/dunkest_20261013_conditional_tail_blend_v1.json`
