# Transfer-malus sensitivity — sequential lineup proxy

Generated UTC: 2026-10-13T10:26:53.857977+00:00

## Method

For each strategy and historical round, compare the fresh independently optimized proxy lineup with the prior round's proxy lineup carried forward. Score both rosters using current-round raw player PDK plus neutral-credit coach base score. Subtract a transfer penalty of 0, 1, 2, 3.5, or 5 points for each newly selected player and one more if the coach changes.

## Results

season_id          season         strategy  transitions  mean_transfer_count  median_transfer_count  mean_gross_gain_vs_carry  median_gross_gain_vs_carry  mean_gross_gain_per_transfer  switch_better_rate_penalty_0  mean_net_gain_penalty_0  switch_better_rate_penalty_1  mean_net_gain_penalty_1  switch_better_rate_penalty_2  mean_net_gain_penalty_2  switch_better_rate_penalty_3.5  mean_net_gain_penalty_3.5  switch_better_rate_penalty_5  mean_net_gain_penalty_5
       13         2023-24       matchup_v2           42             9.595238                   10.0                 81.507857                      85.840                      8.145339                      0.880952                81.507857                      0.857143                71.912619                      0.833333                62.317381                        0.785714                  47.924524                      0.690476                33.531667
       13         2023-24 rest_schedule_v6           42             9.738095                   10.0                 95.481905                      87.265                      9.639873                      0.952381                95.481905                      0.904762                85.743810                      0.904762                76.005714                        0.809524                  61.398571                      0.761905                46.791429
       19         2024-25       matchup_v2           35             9.314286                   10.0                 77.006857                      77.290                      7.766516                      0.828571                77.006857                      0.828571                67.692571                      0.800000                58.378286                        0.742857                  44.406857                      0.714286                30.435429
       19         2024-25 rest_schedule_v6           36             9.416667                   10.0                 73.691944                      64.690                      7.406019                      0.833333                73.691944                      0.722222                64.275278                      0.694444                54.858611                        0.638889                  40.733611                      0.611111                26.608611
        9         2022-23       matchup_v2           38            10.184211                   10.5                 93.432368                      97.450                      9.162622                      0.894737                93.432368                      0.894737                83.248158                      0.894737                73.063947                        0.842105                  57.787632                      0.763158                42.511316
        9         2022-23 rest_schedule_v6           36             9.944444                   10.0                 86.523889                      83.075                      8.659801                      0.888889                86.523889                      0.861111                76.579444                      0.833333                66.635000                        0.722222                  51.718333                      0.638889                36.801667
   POOLED 2022-23–2024-25       matchup_v2          115             9.704348                   10.0                 84.078261                      91.930                      8.366191                      0.869565                84.078261                      0.860870                74.373913                      0.843478                64.669565                        0.791304                  50.113043                      0.721739                35.556522
   POOLED 2022-23–2024-25 rest_schedule_v6          114             9.701754                   10.0                 85.772018                      83.965                      8.624949                      0.894737                85.772018                      0.833333                76.070263                      0.815789                66.368509                        0.728070                  51.815877                      0.675439                37.263246

## Interpretation

This isolates the economic threshold at which a recommended roster change is worth its transfer cost. It does not estimate the exact optimal transfer strategy: the roster is not re-optimized under each penalty, player slot multipliers are omitted, and coach price multipliers are unavailable. Use it to bound sensitivity, not to alter the production penalty without a full lineup-level test.

## Limitations

- Historical rosters/transfers are not archived; previous round's independent proxy lineup is used as carried roster.
- Current recommendation is not re-optimized under each penalty. This is an ex-post switch-value sensitivity, not a true strategy backtest.
- Player scores are unweighted raw PDK; lineup slot/captain multipliers cannot be reconstructed from saved lineup artifact.
- Coach score uses neutral-credit base score; historical coach CR and price multiplier are missing.
- Missing player target rows contribute zero within this restricted candidate proxy.

## Artifacts

reports/audit/dunkest_transfer_malus_sensitivity_sequential_lineup_proxy_20261013_v1_transitions.csv
reports/audit/dunkest_transfer_malus_sensitivity_sequential_lineup_proxy_20261013_v1_metrics.csv
reports/audit/dunkest_transfer_malus_sensitivity_sequential_lineup_proxy_20261013_v1.json
