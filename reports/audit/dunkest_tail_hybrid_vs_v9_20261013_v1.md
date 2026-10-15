# Tail-specialist hybrid vs V9 — V1

Generated UTC: 2026-10-13T14:21:37.838674+00:00

## Question

Does a small blend of the conditional-tail specialist add value to the strongest existing walk-forward predictor, V9 (historical form + lagged credit + matchup/rest/schedule), rather than only beating the weaker direct HGB baseline?

## Protocol

Join the two prediction sets on season, target date, and player name. Exact pairing is required: 57,662 rows and zero label mismatches. Choose the hybrid weight on 2022/23 only among 5%, 10%, 15%, 25%, and 50%, then freeze it and evaluate 2023/24 and 2024/25. The later folds have been examined previously, and the tail specialist itself was discovered in exploratory work, so this is not a pristine final test.

Selected tail-specialist weight: **25%**. Selection-fold MAEs: `{'0.05': 7.417781812407349, '0.1': 7.40497432803741, '0.15': 7.394881435869592, '0.25': 7.382213693701646, '0.5': 7.3889043294661265}`.

## Results

                 scope  candidate     n     mae    rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30
2022-23_selection_fold         v9 19155 7.43303 9.66172                -0.11239         11.74061           4307         13.48120           2901
2022-23_selection_fold     hybrid 19155 7.38221 9.58365                -0.07090         11.74304           4307         13.51787           2901
2022-23_selection_fold tail_model 19155 7.56544 9.80758                 0.05356         12.06372           4307         13.85141           2901
               2023-24         v9 18918 7.46376 9.74769                -0.89393         12.87929           4366         14.92784           2970
               2023-24     hybrid 18918 7.40971 9.65500                -0.66553         12.60754           4366         14.63116           2970
               2023-24 tail_model 18918 7.55615 9.79039                 0.01967         12.06301           4366         13.89918           2970
               2024-25         v9 19589 7.46322 9.76162                -0.68642         12.55302           4425         14.72074           2919
               2024-25     hybrid 19589 7.40888 9.67598                -0.53039         12.33086           4425         14.50192           2919
               2024-25 tail_model 19589 7.56393 9.85794                -0.06230         11.93552           4425         13.99922           2919
    pooled_later_folds         v9 38507 7.46348 9.75478                -0.78836         12.71506           8791         14.82519           5889
    pooled_later_folds     hybrid 38507 7.40929 9.66568                -0.59678         12.46827           8791         14.56710           5889
    pooled_later_folds tail_model 38507 7.56011 9.82481                -0.02203         11.99884           8791         13.94877           5889
 all_folds_descriptive         v9 57662 7.45337 9.72397                -0.56381         12.39463          13098         14.38163           8790
 all_folds_descriptive     hybrid 57662 7.40030 9.63851                -0.42209         12.22980          13098         14.22082           8790
 all_folds_descriptive tail_model 57662 7.56188 9.81909                 0.00308         12.02017          13098         13.91663           8790

## Paired date-cluster bootstrap on later folds

Delta MAE = hybrid minus V9; negative favors the hybrid. Resampling is stratified by season and clusters all player rows on a target date.

{
  "overall_later_folds": {
    "n": 38507,
    "date_clusters": 311,
    "delta_mae_candidate_minus_v9": -0.05419246732385148,
    "ci95": [
      -0.07551916839050787,
      -0.036423859834047015
    ],
    "bootstrap_reps": 5000
  },
  "actual_ge25_later_folds": {
    "n": 8791,
    "date_clusters": 311,
    "delta_mae_candidate_minus_v9": -0.2467852560490535,
    "ci95": [
      -0.28422163240764986,
      -0.21458853245027693
    ],
    "bootstrap_reps": 5000
  },
  "actual_ge30_later_folds": {
    "n": 5889,
    "date_clusters": 311,
    "delta_mae_candidate_minus_v9": -0.258085488354917,
    "ci95": [
      -0.3009746956624972,
      -0.21963177919059146
    ],
    "bootstrap_reps": 5000
  }
}

## Decision

This validates only player-round prediction accuracy. The tail-specialist adds no lagged-credit feature and does not reproduce the V9 feature family; a positive hybrid result is a reason to continue with a dedicated walk-forward lineup replay, not permission to deploy it. No production model, config, weights, optimizer, or prospective snapshot was changed.

## Artifacts

- Metrics: `reports/audit/dunkest_tail_hybrid_vs_v9_20261013_v1_metrics.csv`
- Audit: `reports/audit/dunkest_tail_hybrid_vs_v9_20261013_v1.json`

No commit or push.
