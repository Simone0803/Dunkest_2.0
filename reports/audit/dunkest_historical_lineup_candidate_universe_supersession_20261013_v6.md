# Historical lineup candidate-universe audit — supersession note v6 (2026-10-13)

## Legacy-only opponent rows and date-assisted resolution

The 451 rows that had a legacy opponent but no corrected-link opponent split into five groups:

- 6 multi-game aggregate rows (`gp>1`), not eligible for one-game linkage;
- 405 single-game rows with exact same-date PDK + 17-stat signature and matching source NBA team/opponent;
- 23 single-game rows with exact same-date PDK + 17-stat signature but a different official NBA team, so the source-team opponent was wrong for that game;
- 2 single-game rows whose same-team/date candidate fails the full 17-stat signature;
- 15 single-game rows with no official player-game record on the inferred date.

An experimental V8 fallback uses the independently inferred round date only to disambiguate a unique official-valid same-date candidate matching rounded PDK and all 17 box-score fields. It is limited to `gp=1`, never uses source `team_code` to infer the NBA game team, and does not fill ambiguous/unmatched rows. It considered 475 unresolved single-game rows and uniquely resolved 441, including 36 with an NBA team different from the source Dunkest team. Target-opponent coverage rose to 93,725 rows.

## Paired predictive evaluation

On 57,342 common held-out player-rounds per main model family, V8 versus V7 yielded:

- Expanded matchup: MAE 7.4897 → 7.4904, Δ +0.00065, 95% round-cluster bootstrap CI [−0.00349, +0.00492].
- Expanded matchup + rest/schedule: MAE 7.4716 → 7.4685, Δ −0.00313, 95% CI [−0.00725, +0.00096].

Both intervals include zero; the rest/schedule point estimate is favorable but inconclusive and season-level results vary. Keep date-assisted linkage as an audit-only data-quality experiment; do not promote V8 or alter production. Historical outcome linkage still does not supply a full pre-lock candidate universe or availability snapshot.

## Guardrails

- Preserve source `team_code` and `team_name`; keep linked NBA game team in a separate field.
- Do not assign a single opponent to `gp>1` aggregates.
- Do not infer DNP/OUT from a missing official player-game record.
- Leave ambiguous/unmatched candidates unresolved unless exact-signature and independent-date evidence uniquely identify a game.
- The frozen 2026/27 GW1 holdout remains untouched until 2026-10-23 12:00 UTC.
- No production code/config, official labels, temporal splits, or holdout was changed. No commit/push was performed.

## Artifacts

- `scripts/audit_dunkest_legacy_only_opponent_rows_v1.py`
- `reports/audit/dunkest_legacy_only_opponent_rows_20261013_v1.md`
- `scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v8_date_assisted_link.py`
- `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v8_date_assisted_link.md`
- `scripts/audit_dunkest_date_assisted_link_paired_evaluation_v1.py`
- `reports/audit/dunkest_date_assisted_link_paired_eval_20261013_v1.md`
- `reports/audit/dunkest_project_followup_2026-10-13_v20.md`
