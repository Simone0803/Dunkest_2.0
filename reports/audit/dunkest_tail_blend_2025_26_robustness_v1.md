# Conditional-tail blend — 2025/26 retrospective robustness audit

Generated UTC: 2026-10-18T14:43:35.419353+00:00

## Protocol

Train the direct production ensemble and a two-part conditional-tail model on official PDK labels from 2020/21–2024/25. Choose the tail mixture weight only on the final 20% of dates in that training block, then freeze it and evaluate the 2025/26 matched official-PDK subset. This season was inspected in earlier experiments, so this is a retrospective robustness check, not a pristine final holdout. The 2026/27 prospective bundle is not loaded.

## Weight selection on earlier data

Selected tail weight: **75%**

 tail_weight     n    mae   rmse  bias_pred_minus_actual  n_actual_ge_25  mae_actual_ge_25  bias_actual_ge_25  n_actual_ge_30  mae_actual_ge_30  bias_actual_ge_30
      0.0000 19319 7.5224 9.7960                 -0.1113            4383           11.9360           -10.8658            2891           13.9954           -13.3775
      0.2500 19319 7.5156 9.7895                 -0.1171            4383           11.9281           -10.8610            2891           13.9938           -13.3740
      0.5000 19319 7.5121 9.7872                 -0.1229            4383           11.9247           -10.8561            2891           13.9971           -13.3705
      0.7500 19319 7.5116 9.7892                 -0.1287            4383           11.9251           -10.8513            2891           14.0037           -13.3670
      1.0000 19319 7.5140 9.7954                 -0.1344            4383           11.9289           -10.8464            2891           14.0131           -13.3635

## Outer 2025/26 results

          candidate     n    mae    rmse  bias_pred_minus_actual  n_actual_ge_25  mae_actual_ge_25  bias_actual_ge_25  n_actual_ge_30  mae_actual_ge_30  bias_actual_ge_30
         production 18412 7.5149  9.7659                 -0.0126            4168           11.7999           -10.8962            2712           13.7916           -13.3412
       tail_mixture 18412 7.5154  9.7735                 -0.0521            4168           11.8206           -10.9136            2712           13.8088           -13.3577
       nested_blend 18412 7.5106  9.7645                 -0.0422            4168           11.8100           -10.9092            2712           13.7983           -13.3536
previous10_baseline 18412 7.7886 10.1539                 -0.0479            4168           11.9017           -10.5639            2712           13.7713           -12.9438

## Paired game-date bootstrap

{
  "all": {
    "delta_mae_candidate_minus_baseline": -0.004331719803420232,
    "ci95_low": -0.01408905115438073,
    "ci95_high": 0.004907468212438293,
    "date_clusters": 160,
    "bootstrap_replicates": 5000
  },
  "actual_ge25": {
    "delta_mae_candidate_minus_baseline": 0.010117532860664006,
    "ci95_low": -0.018893119232044436,
    "ci95_high": 0.04109751453245479,
    "date_clusters": 160,
    "bootstrap_replicates": 5000
  },
  "actual_ge30": {
    "delta_mae_candidate_minus_baseline": 0.006713157709746862,
    "ci95_low": -0.0277255770483537,
    "ci95_high": 0.04131913089513224,
    "date_clusters": 159,
    "bootstrap_replicates": 5000
  }
}

Negative ΔMAE favors the nested blend. Actual-score cohorts are diagnostic only and cannot be used to choose a player before a game.

## Cohorts

         cohort           candidate     n     mae    rmse  bias_pred_minus_actual  n_actual_ge_25  mae_actual_ge_25  bias_actual_ge_25  n_actual_ge_30  mae_actual_ge_30  bias_actual_ge_30
            all          production 18412  7.5149  9.7659                 -0.0126            4168           11.7999           -10.8962            2712           13.7916           -13.3412
            all        tail_mixture 18412  7.5154  9.7735                 -0.0521            4168           11.8206           -10.9136            2712           13.8088           -13.3577
            all        nested_blend 18412  7.5106  9.7645                 -0.0422            4168           11.8100           -10.9092            2712           13.7983           -13.3536
            all previous10_baseline 18412  7.7886 10.1539                 -0.0479            4168           11.9017           -10.5639            2712           13.7713           -12.9438
    actual_ge25          production  4168 11.7999 14.3488                -10.8962            4168           11.7999           -10.8962            2712           13.7916           -13.3412
    actual_ge25        tail_mixture  4168 11.8206 14.3805                -10.9136            4168           11.8206           -10.9136            2712           13.8088           -13.3577
    actual_ge25        nested_blend  4168 11.8100 14.3650                -10.9092            4168           11.8100           -10.9092            2712           13.7983           -13.3536
    actual_ge25 previous10_baseline  4168 11.9017 14.5813                -10.5639            4168           11.9017           -10.5639            2712           13.7713           -12.9438
    actual_ge30          production  2712 13.7916 16.3103                -13.3412            2712           13.7916           -13.3412            2712           13.7916           -13.3412
    actual_ge30        tail_mixture  2712 13.8088 16.3311                -13.3577            2712           13.8088           -13.3577            2712           13.8088           -13.3577
    actual_ge30        nested_blend  2712 13.7983 16.3182                -13.3536            2712           13.7983           -13.3536            2712           13.7983           -13.3536
    actual_ge30 previous10_baseline  2712 13.7713 16.4634                -12.9438            2712           13.7713           -12.9438            2712           13.7713           -12.9438
low_history_le5          production   524  5.2123  7.1371                  0.2675              24           17.0011           -16.7828              10           24.2213           -24.2213
low_history_le5        tail_mixture   524  5.0753  7.0830                 -0.1354              24           17.8887           -17.8332              10           25.0962           -25.0962
low_history_le5        nested_blend   524  5.1052  7.0860                 -0.0347              24           17.6668           -17.5706              10           24.8775           -24.8775
low_history_le5 previous10_baseline   524  6.1256  8.2934                  0.6151              24           17.0335           -15.9700              10           23.8686           -23.8686
    history_gt5          production 17888  7.5823  9.8323                 -0.0208            4144           11.7698           -10.8622            2702           13.7530           -13.3010
    history_gt5        tail_mixture 17888  7.5869  9.8412                 -0.0497            4144           11.7854           -10.8735            2702           13.7670           -13.3143
    history_gt5        nested_blend 17888  7.5810  9.8320                 -0.0425            4144           11.7761           -10.8707            2702           13.7573           -13.3109
    history_gt5 previous10_baseline 17888  7.8373 10.2033                 -0.0673            4144           11.8719           -10.5326            2702           13.7340           -12.9033
prediction_ge25          production  2977  9.9949 12.5985                  0.3546            1897            8.5571            -6.5717            1488            9.9296            -9.1088
prediction_ge25        tail_mixture  2977 10.0424 12.6680                  0.3134            1897            8.6299            -6.6380            1488           10.0108            -9.1887
prediction_ge25        nested_blend  2977 10.0234 12.6399                  0.3237            1897            8.6005            -6.6214            1488            9.9793            -9.1687
prediction_ge25 previous10_baseline  2977 10.2828 12.9627                  1.0101            1897            8.7185            -5.8099            1488            9.8307            -8.3224
prediction_ge30          production  1485 10.5286 13.3783                  0.5745            1076            8.4545            -5.2833             888            9.0109            -7.6354
prediction_ge30        tail_mixture  1485 10.6067 13.4875                  0.4475            1076            8.5804            -5.4405             888            9.1817            -7.8062
prediction_ge30        nested_blend  1485 10.5763 13.4451                  0.4792            1076            8.5338            -5.4012             888            9.1210            -7.7635
prediction_ge30 previous10_baseline  1485 10.8080 13.7470                  1.5821            1076            8.5880            -4.1447             888            8.9383            -6.4734

## Decision

Do not promote from this season alone. A positive result is evidence to retain the challenger for further prospective and temporal validation; a negative result is evidence against its robustness. Player-level metrics do not certify realized lineup superiority. No production model/configuration changed.

## Artifacts

- `reports/audit/dunkest_tail_blend_2025_26_robustness_v1.json`
- `reports/audit/dunkest_tail_blend_2025_26_robustness_v1.md`
- `reports/audit/dunkest_tail_blend_2025_26_robustness_v1_metrics.csv`
- `reports/audit/dunkest_tail_blend_2025_26_robustness_v1_predictions.csv`
- `reports/audit/dunkest_tail_blend_2025_26_robustness_v1_cohorts.csv`
