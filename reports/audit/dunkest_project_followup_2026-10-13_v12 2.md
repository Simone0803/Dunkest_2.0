# Dunkest project follow-up — 2026-10-13 V12

## Scope of this iteration

Continued offline improvement work without changing production weights, configuration, or raw data. The new tests cover (1) rest/schedule features at player-score and lineup level, (2) production PDK-history provenance across multiple seasons, and (3) whether current archives can support a participation/DNP probability model.

## 1. Rest/schedule features: player-level gain does not translate into a reliable lineup gain

### Player score OOF
- Baseline expanded matchup V2: MAE 7.50275, RMSE 9.79656.
- V6 plus seven past-only rest/schedule features: MAE 7.47766, RMSE 9.75439.
- Macro-season paired date/round-cluster bootstrap 95% CI for delta MAE (V6 − V2): [-0.03388, -0.01679]. This is a small, consistent player-level gain.

### Lineup proxy
- Same candidate pool and rounds, V2 versus V6, expanding-origin model training.
- 409 paired rounds evaluated; 49 optimization failures and 6 rounds with too few candidates were excluded.
- Macro-season mean realized team-score delta (V6 − V2): +1.564 points per round.
- Paired whole-round bootstrap 95% CI: [-1.950, +5.080]; only 81.0% of bootstrap estimates were positive.
- Pooled V6 round win rate: 49.1%; median round delta: 0.

**Decision:** no production promotion. The lineup-level interval crosses zero and the proxy has important market, coach and transfer assumptions.

Artifacts:
- scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v6_rest_schedule.py
- scripts/backtest_dunkest_historical_lineups_rest_schedule_v1.py
- scripts/audit_dunkest_historical_lineups_rest_schedule_paired_bootstrap_v1.py
- reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v6_rest_schedule.md
- reports/audit/dunkest_historical_lineups_rest_schedule_20261013_v1.md
- reports/audit/dunkest_historical_lineups_rest_schedule_paired_bootstrap_20261013_v1.md

## 2. Production PDK-history provenance: official-history features are directionally promising but not significant

Compared current proxy PDK rolling history with a challenger that uses verified official PDK history wherever a match exists, falling back to the NBA-boxscore proxy for unmatched games. Both arms use identical official supervised targets and the same production feature builder/trainer.

Validation seasons 2021/22–2024/25:
- 30,971 paired out-of-fold predictions.
- Macro-season delta MAE (official-history minus proxy-history): -0.00315.
- 95% date-cluster bootstrap interval: [-0.00786, +0.00142].
- Bootstrap fraction favoring official history: 91.1%.
- Season deltas: 2021/22 -0.00429; 2022/23 +0.00049; 2023/24 -0.00457; 2024/25 -0.00423.
- Secondary 2025/26 delta: -0.00535, not used for selection because that season has already been examined in earlier experiments.

**Decision:** keep the official-history variant experimental. The mean gain is tiny and the validation interval includes zero. Do not change production based on it alone.

Artifacts:
- scripts/audit_dunkest_production_pdk_history_source_ablation_v1.py
- scripts/audit_dunkest_production_pdk_history_source_ablation_v2_multiseason.py
- reports/audit/dunkest_production_pdk_history_source_ablation_20261013_v2_multiseason.md
- reports/audit/dunkest_production_pdk_history_source_ablation_20261013_v2_multiseason_metrics.csv
- reports/audit/dunkest_production_pdk_history_source_ablation_20261013_v2_multiseason_predictions.csv
- reports/audit/dunkest_production_pdk_history_source_ablation_20261013_v2_multiseason.json

## 3. Participation/DNP modelling is blocked by the training labels

The readiness audit found no full pre-lock candidate universe in the available NBA player-game logs. Zero-minute rows are rare (roughly 0.29–0.45% in 2018/19–2024/25; 1 row in the 2025/26 processed archive), and players who do not appear in the NBA game log are not represented as explicit DNP/OUT outcomes. The official PDK archive contains outcomes, not complete timestamped roster and availability snapshots.

**Decision:** do not train or calibrate a p_play model from these logs alone. Keep current deterministic availability/injury rules until complete pre-lock snapshots can be paired with played/DNP outcomes.

Artifacts:
- scripts/audit_dunkest_participation_label_readiness_v1.py
- reports/audit/dunkest_participation_label_readiness_20261013_v1.md
- reports/audit/dunkest_participation_label_readiness_20261013_v1.csv
- reports/audit/dunkest_participation_label_readiness_20261013_v1.json

## 4. Existing validated decisions retained

- Role-conditioned matchup interactions were not promoted because their player-level MAE gain was effectively zero.
- H2H history remains unpromoted because the player-level improvement did not translate to the restricted lineup proxy.
- Platt calibration for coach win probability remains diagnostic-only; it worsened Brier score and log loss on the 2024/25 validation season.
- The historical PDK blend remains at its existing conservative setting; exact blend-weight tuning is not justified without archived market-implied expected minutes to reproduce the production scaling.
- Rookie priors remain capped and are not changed in this iteration.

## 5. Hard blockers and next steps

The following cannot be certified from the currently available historical archives:
1. A complete pre-lock lineup optimum: requires full timestamped roster/CR/availability snapshots.
2. Exact historical coach PDK: requires coach CRs at lock, in addition to the reconstructed base coach score.
3. Transfer strategy and transfer malus: requires carried rosters and historical transfer state.
4. Participation probability: requires explicit DNP/OUT labels for every pre-lock candidate.
5. Final prospective GW1 evaluation: the frozen 2026/27 run must remain untouched until the existing cutoff, **2026-10-23 12:00 UTC**. Do not tune on it.

The next production change should only be made when a candidate has a consistent out-of-sample gain and the required inputs are verifiable. No production configuration or weights were changed in this iteration; no commit or push was performed.

## Final verification

- Test suite: 276 passed, 6,800 warnings (mainly PuLP deprecations and one fixture freshness-metadata warning).
- Python compilation passed for all new experiment/audit scripts.
- git diff --check passed.
- Existing tracked working-tree modifications were preserved; new scripts and reports remain uncommitted.
