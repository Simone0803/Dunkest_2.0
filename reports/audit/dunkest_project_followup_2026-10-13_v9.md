# Dunkest project follow-up (v9)

Generated: 2026-10-13

## Work completed in this continuation

### 1. Repository verification
- Full test suite: **276 passed, 0 failed** using `PYTHONPATH=src ./.venv/bin/python -m pytest -q`.
- Python compilation and `git diff --check` passed.
- Existing untracked files and local changes were preserved.
- No production weights/configuration, raw historical data, or frozen pre-match prediction artifacts were modified.

### 2. Role-conditioned matchup experiment (V5)
Added and ran `scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v5_role_interactions.py` on 93,785 historical player-round rows, using expanding-origin folds for 2022/23, 2023/24 and 2024/25.

The challenger interacts lagged player role (G/F/C) with prior opponent defensive points, rebounds, assists allowed and pace. It was compared against the expanded matchup baseline on the same 55,565 held-out player-round rows.

| Model | Pooled MAE | Pooled RMSE |
|---|---:|---:|
| Expanded matchup baseline | 7.502754 | 9.796561 |
| Role-interaction challenger | 7.502699 | 9.795763 |

Paired bootstrap over 467 season-week-round clusters (10,000 replicates):
- MAE delta, challenger minus baseline: **-0.000055 PDK**.
- 95% interval: **[-0.004265, +0.004187]**.
- Bootstrap fraction with a negative delta: 50.89%.

**Decision:** do not promote these role interactions. The MAE effect is effectively zero and the uncertainty interval includes improvements and regressions. This rejects this particular feature construction, not matchup modelling in general.

Artifacts:
- `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v5_role_interactions.md`
- Matching metrics CSV, prediction CSV and audit JSON.
- Paired inference: `reports/audit/dunkest_role_matchup_interactions_paired_bootstrap_20261013_v1.md`

## Updated research conclusions

1. Keep production model weights and target mode unchanged.
2. Keep the conservative 15% cap on the college-derived rookie-minute prior.
3. Do not use H2H for lineup selection in its current form: despite lower player-level MAE, the separate restricted lineup proxy showed worse realized lineups with H2H.
4. The new role-interaction feature family does not provide measurable incremental player-level MAE improvement.
5. The 2025/26 season remains previously examined evidence, not a globally untouched final holdout.
6. The frozen 2026/27 GW1 run `20261013T072534Z_76c01a55` still awaits verified actuals. The earliest safe result-collection cutoff is **2026-10-23 12:00 UTC**; keep its pre-match snapshots immutable and do not tune on this evaluation.

## Next actions

### P0 — Prospective GW1
After the safe cutoff, run `./scripts/run_prospective_gw1_backtest.sh`. Require complete fixture-linked player and coach outcome coverage before reporting full-lineup results.

### P1 — Historical source integrity
Continue source-scope/provenance investigation. Keep the two confirmed contaminated season-5 weekly files quarantined from certified derivatives. Do not overwrite raw archives or label the audit-only derivative clean.

### P2 — Better matchup research
If continuing feature work, prioritize better-grounded signals (minutes/role uncertainty, schedule/rest and opponent defensive trends) with strict chronological availability checks and paired cluster uncertainty. Avoid more feature complexity unless the ablation has a measurable effect.

### P3 — End-to-end decision validation
Any candidate must eventually be evaluated on identical pre-match candidate pools and frozen snapshots, including player score, coach score, credits, injuries, lineup constraints and transfer malus. Player-level MAE alone cannot certify a better Dunkest lineup.

## Release stance

**No production change is warranted by the new experiment.** The immediate priority remains the frozen prospective GW1 evaluation, while historical provenance work continues in parallel.
