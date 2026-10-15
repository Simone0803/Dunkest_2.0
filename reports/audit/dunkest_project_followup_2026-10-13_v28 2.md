# Dunkest project follow-up — 2026-10-13 V28

This follow-up validates the conditional-tail candidate against the strongest existing walk-forward predictor, V9, and determines whether production implementation is justified. It supersedes neither V27's model audit nor the frozen prospective holdout.

## 1. Why the first positive result was insufficient

The 25% conditional-tail / 75% direct-HGB blend improved MAE versus its own direct-HGB baseline by about 0.010 PDK on pooled folds. However, the weight was selected after examining all three folds, so that result is vulnerable to model-selection optimism. More importantly, the direct-HGB model is not the strongest existing V9 predictor: V9 includes lagged credits, opponent defense, pace, and rest/schedule features. The first blend experiment alone therefore does not establish superiority over the model used in the wider Dunkest pipeline.

## 2. Exact paired comparison against V9

Added `scripts/audit_dunkest_tail_hybrid_vs_v9_v1.py` and report `reports/audit/dunkest_tail_hybrid_vs_v9_20261013_v1.md`.

- Joined the saved tail-blend predictions with V9's `historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6` predictions on season, date, and player name.
- **57,662 paired rows; zero target-label mismatches.** 20 rows in the tail-blend artifact have no V9 counterpart and are excluded from this paired comparison.
- The tail specialist is the 25% conditional-tail mixture + 75% direct HGB, which remains an exploratory model, not a production predictor.
- For the hybrid weight, select among 5%, 10%, 15%, 25%, and 50% tail-specialist weight on 2022/23 MAE only, then freeze the chosen weight for the later folds. The selected weight is 25%.
- This is not a pristine final test: the candidate tail specialist and these historical folds have been inspected in previous exploratory work. The 2025/26 holdout and 2026/27 GW1 prospective snapshot were not loaded.

### Frozen 25% tail-specialist hybrid on later folds (2023/24–2024/25)

| Metric | V9 | Hybrid | Change |
|---|---:|---:|---:|
| MAE | 7.46349 | **7.40929** | −0.05419 |
| RMSE | 9.75478 | **9.66568** | −0.08910 |
| MAE, actual PDK ≥25 | 12.71506 | **12.46828** | −0.24679 |
| MAE, actual PDK ≥30 | 14.82519 | **14.56710** | −0.25809 |

Paired date-cluster bootstrap (5,000 repetitions, stratified by season):
- Overall ΔMAE hybrid − V9: −0.05419; 95% CI **[−0.07552, −0.03642]**.
- Actual PDK ≥25: −0.24679; 95% CI **[−0.28422, −0.21459]**.
- Actual PDK ≥30: −0.25809; 95% CI **[−0.30097, −0.21963]**.

The result is materially more promising than the standalone blend comparison: on the two later folds the hybrid improves aggregate MAE/RMSE and both high-score segments. The same sign holds in each later season. However, the baseline is biased low, and part of the hybrid gain may be correction of that bias; the candidate model family has already been explored on these folds. This is evidence to advance the hybrid to the next research gate, not evidence to deploy it.

## 3. Why production implementation is still blocked

The hybrid has only been evaluated on individual player-round prediction rows. It has **not** been evaluated by re-optimizing the lineup under the same pre-lock candidate universe. The available V5 lineup replay is a restricted proxy:
- 409 rounds evaluated, 49 optimization failures and 6 rounds with too-small candidate pools;
- about 210 candidates per round and about 60.5% candidate target-row coverage;
- all coaches priced at 10 CR, neutral-credit coach score, and transfer malus set to zero;
- the archived player table is not a complete timestamped pre-lock market; players absent from the previous observed archive can be omitted.

It would be invalid to re-use saved target-round predictions as if they existed for every candidate, or to treat missing target rows as pre-lock knowledge. A valid comparison must reconstruct the candidate forecast at lock time for the same candidate universe, use only then-known team fixtures/eligibility, preserve credits/roles and coach rules, and apply the same transfer strategy and malus to both strategies. Until those are recovered, lineup-level utility is not established.

## 4. Recommendation

**Do not implement the new blend in production yet.** Promote it only to a shadow/research candidate for a proper walk-forward lineup replay. If that replay is positive, refit the candidate using training data available before each historical round and then run a pre-registered evaluation on a genuinely untouched period. Do not use 2025/26 for further tuning, and do not touch the frozen GW1 2026/27 run before its 2026-10-23 12:00 UTC cutoff.

## 5. Integrity

- New script: `scripts/audit_dunkest_tail_hybrid_vs_v9_v1.py`.
- New outputs: `reports/audit/dunkest_tail_hybrid_vs_v9_20261013_v1.{md,json,csv}`.
- Exact pairing verified; 57,662 rows; zero label mismatches.
- Script compilation and `git diff --check` pass.
- No production source, config, model weights, optimizer, or prospective snapshot modified.
- No commit or push.
