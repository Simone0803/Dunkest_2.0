# Sequential Dunkest lineup backtest — transfer-penalty scenarios

Generated (UTC): 2026-10-13T10:51:02.015068+00:00

## Method

For each test season, each transfer-penalty scenario starts with no assumed roster. In every subsequent round, the optimizer selects a lineup using only lagged player features and pregame coach forecasts, while using that scenario's transfer penalty coefficient in the selection objective. All scenarios are scored under the same fixed 5-point transfer malus; only after scoring is the lineup carried forward to the next round.

Optimizer penalty coefficients tested: [0.0, 2.5, 5.0]. Every scenario is scored with the same official proxy transfer penalty of 5.0 points per transfer.

## Results

season_id          season  transfer_penalty  rounds_evaluated  mean_net_team_score  median_net_team_score  mean_gross_team_score  mean_transfers  median_transfers  mean_official_transfer_malus  mean_objective_proxy_score  mean_candidate_coverage  mean_target_players_in_candidate_pool_fraction  roster_valid_rate
       13         2023-24               0.0               132           111.790189               110.6425             163.115947       10.265152              11.0                     51.325758                  163.115947                 0.601529                       0.950261                1.0
       13         2023-24               2.5               132           116.043902               117.2025             163.165114        9.424242              11.0                     47.121212                  139.604508                 0.601529                       0.950261                1.0
       13         2023-24               5.0               132           116.623144               116.6100             161.547386        8.984848              10.0                     44.924242                  116.623144                 0.601529                       0.950261                1.0
       19         2024-25               0.0               138           115.334928               118.8775             166.385652       10.210145              11.0                     51.050725                  166.385652                 0.601715                       0.951834                1.0
       19         2024-25               2.5               138           117.354058               122.6350             164.274348        9.384058              11.0                     46.920290                  140.814203                 0.601715                       0.951834                1.0
       19         2024-25               5.0               138           114.469130               122.3150             159.541594        9.014493              10.5                     45.072464                  114.469130                 0.601715                       0.951834                1.0
        9         2022-23               0.0               139            97.758957                93.2650             150.276942       10.503597              11.0                     52.517986                  150.276942                 0.612537                       0.945910                1.0
        9         2022-23               2.5               139            99.545468                90.1900             145.840432        9.258993              11.0                     46.294964                  122.692950                 0.612537                       0.945910                1.0
        9         2022-23               5.0               139           100.908777                92.2850             145.045468        8.827338              11.0                     44.136691                  100.908777                 0.612537                       0.945910                1.0
   POOLED 2022-23–2024-25               0.0               409           108.217653               107.4750             159.855795       10.327628              11.0                     51.638142                  159.855795                 0.605333                       0.949313                1.0
   POOLED 2022-23–2024-25               2.5               409           110.878912               111.8050             157.651528        9.354523              11.0                     46.772616                  134.265220                 0.605333                       0.949313                1.0
   POOLED 2022-23–2024-25               5.0               409           110.555782               110.5550             155.262384        8.941320              11.0                     44.706601                  110.555782                 0.605333                       0.949313                1.0

## Coverage and failures

- Round status counts: {'evaluated': 1227, 'optimization_failed': 147, 'candidate_pool_too_small': 6}
- Sequential lineup records: 1,227
- Failed optimizations: 147 (all reported as infeasible); candidate pools too small: 6. The same 49 rounds failed in each penalty scenario and were excluded from paired comparisons.

## Caveats

- The carried roster is the previous proxy recommendation, not the user's actual historical roster.
- Candidate pool only includes players observed earlier in the archived season; late additions and players absent from prior tables are omitted.
- Coach CR is fixed at 10 and coach points are neutral-credit base-score estimates; exact historical price-adjusted coach points are unavailable.
- Missing target player rows score zero within the restricted archive, which can misclassify archive gaps as no fantasy points.
- This experiment compares penalties in the same chronological walk-forward design, but is not an official complete-market backtest.

The coefficient in the optimizer is a decision parameter, while the official 5-point malus is fixed for scoring all scenarios. Compare official-net score, gross score and transfer frequency; do not change production without stable differences across seasons and broader market coverage.

Production model/configuration remains unchanged.

## Artifacts

- Metrics: `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v2_metrics.csv`
- Per-round results: `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v2_rounds.csv`
- Sequential lineups: `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v2_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v2.json`
