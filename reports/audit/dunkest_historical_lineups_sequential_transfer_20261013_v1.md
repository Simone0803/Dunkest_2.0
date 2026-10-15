# Sequential Dunkest lineup backtest — transfer-penalty scenarios

Generated (UTC): 2026-10-13T10:45:46.787505+00:00

## Method

For each test season, each transfer-penalty scenario starts with no assumed roster. In every subsequent round, the optimizer selects a lineup using only lagged player features and pregame coach forecasts, while charging that scenario's own transfer penalty against its carried previous roster and coach. After selection, the lineup is scored using the archived target-round PDK labels; only then is it carried forward to the next round.

Penalty scenarios: [0.0, 2.5, 5.0]

## Results

season_id          season  transfer_penalty  rounds_evaluated  mean_net_team_score  median_net_team_score  mean_gross_team_score  mean_transfers  median_transfers  mean_transfer_malus  mean_candidate_coverage  mean_selected_roster_coverage  roster_valid_rate
       13         2023-24               0.0               132           163.115947               161.0550             163.115947       10.265152              11.0             0.000000                 0.601529                       0.950261                1.0
       13         2023-24               2.5               132           139.807197               141.6025             163.367803        9.424242              11.0            23.560606                 0.601529                       0.950261                1.0
       13         2023-24               5.0               132           116.623144               116.6100             161.547386        8.984848              10.0            44.924242                 0.601529                       0.950261                1.0
       19         2024-25               0.0               138           166.380000               171.1950             166.380000       10.210145              11.0             0.000000                 0.601715                       0.951834                1.0
       19         2024-25               2.5               138           140.814203               147.1450             164.274348        9.384058              11.0            23.460145                 0.601715                       0.951834                1.0
       19         2024-25               5.0               138           114.469130               122.3150             159.541594        9.014493              10.5            45.072464                 0.601715                       0.951834                1.0
        9         2022-23               0.0               139           150.276942               145.0550             150.276942       10.503597              11.0             0.000000                 0.612537                       0.945910                1.0
        9         2022-23               2.5               139           122.692950               113.8200             145.840432        9.258993              11.0            23.147482                 0.612537                       0.945910                1.0
        9         2022-23               5.0               139           100.908777                92.2850             145.045468        8.827338              11.0            44.136691                 0.612537                       0.945910                1.0
   POOLED 2022-23–2024-25               0.0               409           159.853888               158.5400             159.853888       10.327628              11.0             0.000000                 0.605333                       0.949313                1.0
   POOLED 2022-23–2024-25               2.5               409           134.330636               133.8750             157.716944        9.354523              11.0            23.386308                 0.605333                       0.949313                1.0
   POOLED 2022-23–2024-25               5.0               409           110.555782               110.5550             155.262384        8.941320              11.0            44.706601                 0.605333                       0.949313                1.0

## Coverage and failures

- Round status counts: {'evaluated': 1227, 'optimization_failed': 147, 'candidate_pool_too_small': 6}
- Sequential lineup records: 1,227

## Caveats

- The carried roster is the previous proxy recommendation, not the user's actual historical roster.
- Candidate pool only includes players observed earlier in the archived season; late additions and players absent from prior tables are omitted.
- Coach CR is fixed at 10 and coach points are neutral-credit base-score estimates; exact historical price-adjusted coach points are unavailable.
- Missing target player rows score zero within the restricted archive, which can misclassify archive gaps as no fantasy points.
- This experiment compares penalties in the same chronological walk-forward design, but is not an official complete-market backtest.

Do not pick a penalty solely from this proxy: the candidate universe is incomplete and the carried roster is simulated. Compare both net points and transfer frequency, and seek stable differences across seasons before any production change.

Production model/configuration remains unchanged.

## Artifacts

- Metrics: `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v1_metrics.csv`
- Per-round results: `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v1_rounds.csv`
- Sequential lineups: `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v1_lineups.csv`
- Audit JSON: `reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v1.json`
