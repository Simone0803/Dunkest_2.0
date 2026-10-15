# Sequential transfer-penalty scenarios — paired bootstrap audit

Generated UTC: 2026-10-13T10:51:37.280567+00:00

## Method

Uses 409 matched rounds where all three optimizer coefficients (0, 2.5, 5) returned a valid lineup. The score of every lineup uses the same fixed 5-point transfer malus; only the optimizer's transfer-cost coefficient changes. The 95% intervals come from 10,000 paired round-bootstrap replicates stratified by season.

## Pooled paired comparisons

                   comparison  penalty_a  penalty_b  matched_rounds  mean_official_net_delta  median_official_net_delta  fraction_rounds_a_better  ci95_low  ci95_high  bootstrap_replicates     seed
optimizer_penalty_2.5_minus_5        2.5        5.0             409                 0.323130                        0.0                  0.322738 -2.424604   3.009457                 10000 20261013
optimizer_penalty_2.5_minus_0        2.5        0.0             409                 2.661259                        0.0                  0.400978  0.036044   5.313366                 10000 20261013
  optimizer_penalty_0_minus_5        0.0        5.0             409                -2.338130                        0.0                  0.303178 -5.572543   0.797569                 10000 20261013

## Season-level comparisons

                   comparison  penalty_a  penalty_b  matched_rounds  mean_official_net_delta  median_official_net_delta  fraction_rounds_a_better  ci95_low  ci95_high  bootstrap_replicates     seed
season_13_penalty_2.5_minus_5        2.5        5.0             132                -0.579242                        0.0                  0.333333       NaN        NaN                     0 20261013
season_19_penalty_2.5_minus_5        2.5        5.0             138                 2.884928                        0.0                  0.304348       NaN        NaN                     0 20261013
 season_9_penalty_2.5_minus_5        2.5        5.0             139                -1.363309                        0.0                  0.330935       NaN        NaN                     0 20261013
season_13_penalty_2.5_minus_0        2.5        0.0             132                 4.253712                        0.0                  0.378788       NaN        NaN                     0 20261013
season_19_penalty_2.5_minus_0        2.5        0.0             138                 2.019130                        0.0                  0.391304       NaN        NaN                     0 20261013
 season_9_penalty_2.5_minus_0        2.5        0.0             139                 1.786511                        0.0                  0.431655       NaN        NaN                     0 20261013
  season_13_penalty_0_minus_5        0.0        5.0             132                -4.832955                        0.0                  0.250000       NaN        NaN                     0 20261013
  season_19_penalty_0_minus_5        0.0        5.0             138                 0.865797                        0.0                  0.369565       NaN        NaN                     0 20261013
   season_9_penalty_0_minus_5        0.0        5.0             139                -3.149820                        0.0                  0.287770       NaN        NaN                     0 20261013

## Interpretation

A positive delta favours the first optimizer coefficient on official-net proxy score. If the interval includes zero, the observed difference is not robust enough to select a coefficient. These are restricted-universe simulations, not a recommendation to change the official scoring rule or production setting.

## Coverage

- Matched rounds: 409
- Status counts over all scenario-round attempts: {'evaluated': 1227, 'optimization_failed': 147, 'candidate_pool_too_small': 6}
- Failed/undersized rounds are excluded from paired comparisons; failures are disclosed in the sequential backtest report.

## Artifacts

reports/audit/dunkest_historical_lineups_sequential_transfer_paired_bootstrap_20261013_v1.csv
reports/audit/dunkest_historical_lineups_sequential_transfer_paired_bootstrap_20261013_v1.json
