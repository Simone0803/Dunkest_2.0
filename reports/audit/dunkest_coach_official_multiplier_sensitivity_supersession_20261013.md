# Coach multiplier sensitivity audit — supersession note

The V1 and V2 sensitivity artifacts are superseded by V3 and must not be used for conclusions. Their transformation helper applied an inverse coefficient twice to negative base scores. V3 fixes the transformation by multiplying the base score by the value returned by `coach_coefficient`, which already returns the reciprocal coefficient for negative scores. The rule unit tests explicitly cover positive and negative scores for both price tiers.

Use `dunkest_coach_official_multiplier_sensitivity_2018-26_v3.md`, `.json`, and `_metrics.csv` as the current reference. Historical coach CR pairs remain unavailable for the tested seasons, so CR-spread scenarios are sensitivity analyses, not exact historical PDK backtests.
