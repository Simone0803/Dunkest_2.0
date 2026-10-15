# Paired strategy comparison: V6 vs V7

Generated UTC: 2026-10-14T13:16:43.732474+00:00

Paired rounds: 458

## Comparisons

### model_v7_calibrated_zero_inclusive_minus_model_v6_raw

- Mean paired delta: **26.244 PDK**
- Median paired delta: 21.125 PDK
- New strategy wins: **68.8%**
- Season-stratified bootstrap 95% CI: **[21.241, 31.279]**

| Season ID | Rounds | Mean delta | Win rate |
|---:|---:|---:|---:|
| 9 | 159 | 24.389 | 67.9% |
| 13 | 147 | 31.385 | 73.5% |
| 19 | 152 | 23.213 | 65.1% |

### baseline_v7_calibrated_minus_baseline_v6_raw

- Mean paired delta: **-2.124 PDK**
- Median paired delta: 0.000 PDK
- New strategy wins: **24.7%**
- Season-stratified bootstrap 95% CI: **[-3.756, -0.497]**

| Season ID | Rounds | Mean delta | Win rate |
|---:|---:|---:|---:|
| 9 | 159 | -2.384 | 23.3% |
| 13 | 147 | -1.089 | 30.6% |
| 19 | 152 | -2.852 | 20.4% |

## Limitations

- Zero-inclusive labels assume a missing player-week-round row means 0 points; this is a proxy, not official observation.
- Candidate pool, CR/role and availability are reconstructed rather than certified pre-lock state.
- Coach price and transfer malus remain proxies.

Paired per-round data: `reports/audit/dunkest_v6_v7_lineup_strategy_paired_bootstrap_20261014_v1.csv`
Machine-readable report: `reports/audit/dunkest_v6_v7_lineup_strategy_paired_bootstrap_20261014_v1.json`
