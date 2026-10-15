# Dunkest project follow-up - 2026-10-13 (v23)

This version extends the v22 report with a lineup-level robustness analysis of the previously evaluated rest/schedule model. See `reports/audit/dunkest_project_followup_2026-10-13_v22.md` for the full preceding research log and artifacts.

## 15. Robustness of rest/schedule features at lineup level

I re-examined the paired V2-versus-V6 historical lineup proxy by candidate-pool coverage, target-player coverage, and whether the optimizer changed its roster or coach. This is a diagnostic breakdown of the same 409 paired rounds, not a new model fit.

The overall mean V6-V2 realized score difference remains +1.557 points per round, but the existing season-stratified round-cluster 95% bootstrap interval is [-1.950, +5.080], which includes zero. V6 wins 49.1% of paired rounds; the median score difference is zero.

The effect is not monotonic with candidate coverage. In rounds where at least 98% of target-round players were present in the restricted candidate pool (158 rounds), the mean V6-V2 difference is -1.671 points and V6 wins 44.9% of rounds. The largest positive means occur in coverage bands with fewer rounds and/or lower candidate completeness. These subgroup results are descriptive and unadjusted for multiple comparisons, but they warn that the positive pooled mean is not robust to the candidate-pool slice.

The models selected the same player roster in only 22 rounds; 387 rounds had a different player roster. The average difference was +1.664 when the roster differed and -0.316 when it matched. Coach selections differed in only 12 rounds. This suggests the observed differences primarily arise through player selection, but the analysis is not causal and the incomplete historical market makes interpretation uncertain.

**Decision:** do not promote V6 based on lineup-level evidence. Player-level walk-forward metrics favor the rest/schedule features by a small amount, but the lineup proxy remains inconclusive and sensitive to candidate coverage. A stronger decision requires a complete pre-lock candidate universe and validated historical coach-credit and transfer state. Production remains unchanged.

Artifact: `reports/audit/dunkest_lineup_rest_schedule_robustness_20261013_v1.md` and `reports/audit/dunkest_lineup_rest_schedule_robustness_20261013_v1.csv`.

## Verification

The analysis used saved historical proxy outputs only. It did not read the 2025/26 final holdout or the frozen 2026/27 GW1 prospective run, and it did not change production source/configuration. No commit or push was performed.
