# Paired lineup bootstrap — expanded matchup V2 vs rest/schedule V6

Generated UTC: 2026-10-13T10:03:49.864584+00:00

Evaluated paired rounds: 409; held-out seasons: 13, 19, 9.

## Results

       scope  n_rounds  mean_v2_realized_team_score  mean_v6_realized_team_score  delta_v6_minus_v2  median_delta_v6_minus_v2  v6_win_rate  ci95_low  ci95_high  bootstrap_fraction_delta_positive
          13       132                   163.115947                   164.843182           1.727235                      0.00     0.492424 -4.307170   7.833641                             0.7129
          19       138                   166.380000                   169.748261           3.368261                      0.32     0.514493 -1.679275   8.403662                             0.9045
           9       139                   150.330755                   149.928237          -0.402518                      0.00     0.467626 -7.147413   6.151424                             0.4575
macro_season       409                   159.942234                   161.506560           1.564326                      0.00     0.491514 -1.949538   5.079916                             0.8102

## Interpretation

Macro-season delta (V6 − V2): 1.564 realized team points per round; 95% cluster-bootstrap interval [-1.950, 5.080].
Fraction of bootstrap replicates above zero: 0.8102.

This comparison is paired on the same rounds and candidate pool. It is still a restricted historical proxy: coach prices and transfer malus are not historically validated, and the archived player universe is incomplete. Do not promote V6 to production solely from this result.
