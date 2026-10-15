# Historical lineup rest/schedule robustness audit

## Scope

Descriptive robustness analysis of the existing paired V2-versus-V6 historical lineup proxy. It uses the same 409 evaluated rounds and realized scores as the earlier paired bootstrap. No new model was trained and no prospective holdout data was used.

## Main result

Across 409 paired rounds, V6 averaged +1.557 realized team points versus V2, with median difference 0 and V6 winning 49.1% of rounds. The existing season-stratified round-cluster bootstrap remains the relevant inferential result: 95% CI [-1.950, +5.080]. It includes zero, so lineup-level evidence is inconclusive.

## Coverage sensitivity (descriptive only)

| Segment | Rounds | Mean V6-V2 | Median | V6 win rate |
|---|---:|---:|---:|---:|
| Candidate coverage <50% | 43 | +3.156 | +1.875 | 55.8% |
| Candidate coverage 50-60% | 107 | +6.707 | +3.690 | 55.1% |
| Candidate coverage 60-70% | 234 | -1.905 | -0.958 | 42.7% |
| Candidate coverage >70% | 25 | +9.168 | +11.515 | 72.0% |
| Target-player coverage <90% | 58 | +9.629 | +4.580 | 53.4% |
| Target-player coverage 90-95% | 135 | +2.478 | +0.270 | 50.4% |
| Target-player coverage 95-98% | 58 | +0.136 | +0.810 | 53.4% |
| Target-player coverage >=98% | 158 | -1.671 | 0.000 | 44.9% |

The effect is not monotonic with candidate-pool coverage. The >=98% target-player-coverage subset does not favor V6. This weakens the case that the positive pooled mean reflects a robust lineup advantage; selection effects and incomplete candidate universes remain plausible explanations. These subgroup summaries are exploratory and not multiplicity-adjusted.

## Selection-change diagnostics

The two models selected identical player rosters in only 22 of 409 rounds; 387 rounds changed the roster. Mean V6-V2 realized-score difference was +1.664 when the roster differed and -0.316 when it matched. Coach selections differed in 12 rounds, so most of the aggregate difference arises in player-roster changes, not coach choice. These comparisons are descriptive, not causal.

## Decision

Do not promote the rest/schedule model to production based on lineup outcomes. Player-level walk-forward evidence is favorable but the restricted lineup proxy is inconclusive and sensitive to candidate coverage. A stronger decision requires a more complete pre-lock candidate universe and validated coach-credit/transfer state. Keep production unchanged.

## Artifacts

- `reports/audit/dunkest_lineup_rest_schedule_robustness_20261013_v1.csv`
- `reports/audit/dunkest_lineup_rest_schedule_robustness_20261013_v1.md`
