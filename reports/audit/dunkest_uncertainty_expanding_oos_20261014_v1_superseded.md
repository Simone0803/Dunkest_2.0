# Superseded uncertainty audit — 2026-10-14

`dunkest_uncertainty_expanding_oos_20261014_v1.*` is superseded. Its first implementation inverted the sign of the residual quantiles when mapping prediction-error quantiles back to target-score intervals. Do not use its coverage values or recommendations.

The corrected implementation reverses the residual quantiles correctly and is the authoritative result:

- Report: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v2.md`
- Metrics: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v2_metrics.csv`
- Cohorts: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v2_cohorts.csv`
- Audit: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v2.json`
