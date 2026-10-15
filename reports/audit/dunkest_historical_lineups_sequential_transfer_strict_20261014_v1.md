# Sequential Dunkest lineup backtest — strict observed-only transfer-penalty scenarios

Generated (UTC): 2026-10-14T19:16:29.239563+00:00

## Method

Each transfer-penalty scenario carries its own previous proxy roster forward. All scenarios are scored with the same 5-point-per-transfer malus. Missing selected-player scores remain unknown; no missing outcome is replaced by zero. Pooled comparisons use identical rounds where all three scenarios have complete observed player and coach outcomes.

## Coverage

- Optimized rounds per scenario: 409 (across three held-out seasons)
- Fully observed paired rounds across all scenarios: 11 / 409
- Excluded from paired score comparison because of missing selected-player/coach actuals: 398

## Results

    season_id          season  transfer_penalty  rounds_evaluated  rounds_optimized  rounds_with_complete_observed_actuals  mean_net_team_score  median_net_team_score  mean_gross_team_score  mean_transfers  median_transfers  mean_official_transfer_malus  mean_objective_proxy_score  mean_candidate_coverage  mean_target_players_in_candidate_pool_fraction  roster_valid_rate
            9         2022-23               0.0                 5               139                                      5           149.704000               138.3100             193.704000        8.800000              11.0                     44.000000                  193.704000                 0.703259                                        0.915617                1.0
            9         2022-23               2.5                 5               139                                      5           152.519000               141.0600             196.519000        8.800000              11.0                     44.000000                  174.519000                 0.703259                                        0.915617                1.0
            9         2022-23               5.0                 5               139                                      5           150.742000               138.3100             194.742000        8.800000              11.0                     44.000000                  150.742000                 0.703259                                        0.915617                1.0
           13         2023-24               0.0                 4               132                                      4           174.066250               179.9625             212.816250        7.750000              10.0                     38.750000                  212.816250                 0.728883                                        0.905260                1.0
           13         2023-24               2.5                 4               132                                      4           200.733750               185.8600             233.233750        6.500000               8.0                     32.500000                  216.983750                 0.728883                                        0.905260                1.0
           13         2023-24               5.0                 4               132                                      4           200.930000               186.2525             233.430000        6.500000               8.0                     32.500000                  200.930000                 0.728883                                        0.905260                1.0
           19         2024-25               0.0                 2               138                                      2           129.152500               129.1525             184.152500       11.000000              11.0                     55.000000                  184.152500                 0.753108                                        0.917508                1.0
           19         2024-25               2.5                 2               138                                      2           129.152500               129.1525             184.152500       11.000000              11.0                     55.000000                  156.652500                 0.753108                                        0.917508                1.0
           19         2024-25               5.0                 2               138                                      2           129.152500               129.1525             184.152500       11.000000              11.0                     55.000000                  129.152500                 0.753108                                        0.917508                1.0
POOLED_STRICT 2022-23–2024-25               0.0                11               409                                     11           154.826364               146.5000             198.917273        8.818182              11.0                     44.090909                  198.917273                 0.721641                                        0.912195                1.0
POOLED_STRICT 2022-23–2024-25               2.5                11               409                                     11           165.803182               152.3050             207.621364        8.363636              11.0                     41.818182                  186.712273                 0.721641                                        0.912195                1.0
POOLED_STRICT 2022-23–2024-25               5.0                11               409                                     11           165.066818               151.1800             206.885000        8.363636              11.0                     41.818182                  165.066818                 0.721641                                        0.912195                1.0

## Limitations

- Candidate market is reconstructed from players observed earlier in the season; it is not a complete timestamped pre-lock Dunkest market.
- Coach CR is fixed to 10 and coach results are reconstructed neutral-credit base scores, not exact price-adjusted official outcomes.
- The carried roster is simulated from the previous recommendation, not the user's actual historical roster.
- Eleven complete paired rounds are insufficient to certify a transfer-penalty winner; do not tune production from these estimates.

Production parameters unchanged.
