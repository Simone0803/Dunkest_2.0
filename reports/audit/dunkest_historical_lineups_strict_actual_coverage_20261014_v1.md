# Historical Dunkest lineup proxy — strict realized-player coverage

Generated UTC: 2026-10-14T11:34:12.058801+00:00

## Method

The broad proxy run could assign zero realized points when a selected player lacked a target-round row. This audit removes that assumption: each lineup is eligible only when all ten selected players have a finite target-round outcome row. Model and previous-five baseline are compared on the same rounds where both qualify.

## Coverage

- Unique round keys: 409
- Paired rounds with all 10 outcomes observed for both strategies: 3

| Strategy | Complete 10-player lineups | Total lineup rows |
|---|---:|---:|
| model | 17 | 409 |
| previous5_baseline | 9 | 409 |

## Strict paired comparison

- Mean realized player-lineup score, model: **197.015**
- Mean realized player-lineup score, baseline: **203.240**
- Mean paired difference: **-6.225**
- Median paired difference: **10.185**
- Model win rate: **66.7%**
- Round-bootstrap 95% CI: **[-56.515, 27.655]**

| Season ID | Paired rounds | Mean model | Mean baseline | Mean delta | Model win rate | 95% CI delta |
|---:|---:|---:|---:|---:|---:|---:|
| 13 | 1 | 174.865 | 231.380 | -56.515 | 0.0% | [-56.515, -56.515] |
| 9 | 2 | 208.090 | 189.170 | 18.920 | 100.0% | [10.185, 27.655] |

## Interpretation and limitations

This is a stricter historical proxy, not a certified complete Dunkest backtest. It avoids imputing absent outcomes as zero but still uses a reconstructed candidate universe and lagged prices/roles. Historical coach prices and transfer malus remain unavailable. Use this as partial evidence alongside prospective pre-lock capture.

## Reproducibility

Script: scripts/audit_dunkest_historical_lineups_strict_actual_coverage_v1.py
Paired rounds: reports/audit/dunkest_historical_lineups_strict_actual_coverage_20261014_v1_paired_rounds.csv
Row-level coverage: reports/audit/dunkest_historical_lineups_strict_actual_coverage_20261014_v1_rounds.csv
Machine-readable audit: reports/audit/dunkest_historical_lineups_strict_actual_coverage_20261014_v1.json
