# Paired evaluation: production hybrid vs HGB shadow minutes (archived GW1)

**Generated:** 2026-10-24 UTC
**Scope:** evaluation only; no model or production changes.
**Status:** partial single-round diagnostic, not a certified pre-lock walk-forward result.

## Summary

The repository does not contain historical forecasts of the actual production minutes hybrid for the three multi-season folds in the existing HGB walk-forward audit. The existing historical files compare HGB with previous-game baselines or a research gate based on previous-five minutes; neither is the current production formula. One saved 2026-27 GW1 prediction archive does contain both `expected_min` and `expected_min_model_shadow`, so it permits a real but incomplete paired comparison on player-game rows with an observed NBA log entry. Its archive manifest explicitly marks `pre_lock_eligible=false`. It is therefore useful as a diagnostic only, not as certification or a replacement for multi-season walk-forward.

On the 289 jointly scored rows, the HGB shadow has lower MAE and RMSE than the production hybrid. The result is strongly limited by selection: only candidates with an NBA log row (all positive-minute appearances in this source) can be labelled, leaving 233 of 528 candidates without an outcome. It excludes zero-minute/DNP cases, which are a known weak cohort for HGB. No production decision should be based on these numbers.

## Production minutes and HGB path

In [`predictor.py`](../../src/dunkest/models/predictor.py), `_base_minutes` uses `0.65 × e_min_5 + 0.35 × e_min_season` when both are present, otherwise the available history; without history it uses a current lineup prior, then a credit prior, then a 1-minute fallback. With history, a confidence `n_games / (n_games + 12)` controls blending toward the role prior (`0.35 × confidence` historical weight) or credit prior (full confidence blend). The result is clipped and capped to the current role. The prediction is then adjusted by current-roster role competition and positional minute allocation; `expected_min` is the resulting operational value.

The shadow model is trained in `train_models` on target NBA minutes using the model feature columns. At inference, it predicts from the latest player feature row after numeric conversion, infinity replacement, stored median imputation and zero fill, then clips to 0–48. It is emitted as `expected_min_model_shadow`; it does not replace `expected_min`, does not pass through the production hybrid blend and does not determine `expected_pdk`.

The shadow's `FEATURE_COLS` cover lagged and rolling Dunkest PDK/minutes, points/rebounds/assists and per-36 rates, recent-minute trend/variance/zero-rate, home/rest/back-to-back, opponent pace/defense, player-opponent history, and team-change/history indicators. Current Dunkest role, current lineup group, credits, injury/status and teammate rotation competition are not direct HGB inputs in this list. Role/lineup/credit and availability signals instead enter the operational rule path and subsequent minute allocation.

The archived per-player outcome label is NBA player game-log `MIN` for the same NBA `GAME_ID`, after joining a normalized player name and team abbreviation to the forecast's `nba_game_id`. This log source contains only 324 player-game rows for the 16 relevant games, versus 528 forecast candidates. In this joined subset every row has positive minutes. Missing log rows are not assigned zero.

## Source records and pairing protocol

- Forecast archive: `data/archives/pre_lock/season_id=26/gw=1/20261018T120440Z_88d2ef45/predictions.parquet` (528 candidates; 528 `expected_min`; 443 non-null shadow predictions).
- Forecast timestamp: `2026-10-18T12:04:40.936984Z`; first target games in outcome logs: 2026-10-20 through 2026-10-22.
- Latest `fetched_at` among input records that carry such metadata: `2026-10-18T12:04:37.304519Z`. Only 17 of 30 manifest input entries carry acquisition timestamps; all recorded ones precede the forecast. Remaining input hashes and paths are in the saved manifest, but their acquisition timestamps are absent.
- Official lock timestamp: unavailable. This audit does not infer or certify it.
- The archive manifest has `pre_lock_eligible=false`: fixture mapping freshness check failed (mapping snapshot fetched 2026-10-12) and the Lineups availability snapshot failed content validation. Predictions themselves predate target games, but the archive fails the project's pre-lock evidence gate.
- Identity mapping is unique at `(normalized player name, team abbreviation, nba_game_id)` in both forecast and logs; no duplicate identity keys were found. The prediction file does not retain a canonical Dunkest player ID, so name-based identity remains a limitation.
- Matching was one-to-one and required the same player key, team and `nba_game_id`. Rows without a matching log record remain unlabelled. No future injury, role, or availability information was joined into the forecast.

### Coverage

| Stage | Records | Interpretation |
|---|---:|---|
| Forecast candidates | 528 | Full saved candidate pool |
| Production hybrid available | 528 | All candidates |
| HGB shadow available | 443 | 85 shadow predictions missing |
| Candidate with matching NBA log row | 295 | All 295 have positive `MIN` |
| Matching log rows with HGB prediction | 289 | Paired scored sample |
| Paired games | 16 | Dates span Oct 20–22, 2026 |
| No matching log row | 233 | Outcome unknown; not treated as zero or DNP |
| HGB missing among log-matched records | 6 | Excluded from paired comparison |
| Verified zero-minute labels | 0 | This log extract supplies no such matched rows |

This leaves paired coverage at 54.7% of the candidate pool, 65.2% of candidates with an HGB prediction, and 98.0% of candidates with a matched log row. The last percentage must not be mistaken for roster outcome coverage.

## Paired metrics

| Model | n records | Players | Games | MAE (min) | RMSE (min) | Bias, predicted − observed (min) |
|---|---:|---:|---:|---:|---:|---:|
| Production hybrid `expected_min` | 289 | 289 | 16 | 7.2182 | 9.3209 | −5.3926 |
| HGB shadow | 289 | 289 | 16 | 5.2252 | 6.5678 | −0.7050 |
| HGB − hybrid | same rows | same rows | same games | −1.9930 | −2.7531 | +4.6876 |

Paired bootstrap resampling by `nba_game_id` (10,000 replicates, seed 20261024) gives 95% percentile intervals for HGB minus hybrid of:

| Difference | 95% CI |
|---|---:|
| MAE | [−2.4938, −1.5302] min |
| RMSE | [−3.4531, −2.0590] min |
| Bias | [+4.1268, +5.2604] min |

The per-date descriptive slices (Oct 20: 62 records/3 games; Oct 21: 210/11; Oct 22: 17/2) are not independent forecast folds: the entire GW was forecast once on Oct 18. There is only one saved forecast origin, one season, and one target GW. The confidence intervals describe game-cluster sampling variability within this selected observed-player sample; they do not account for missing DNP/nonappearance outcomes, forecast-origin variability, or the archive's failed certification.

### Subgroups and availability

- Zero observed minutes: not evaluable. No matched log row has zero minutes, and absent log rows are not zero-minute evidence.
- Fewer than five prior Dunkest games: only 1 paired record; not interpretable. The 288 other paired rows have at least five prior games.
- Role available in forecast: guards 125, forwards 113, centers 51. The current role can be sliced in the generated metrics JSON, but no historical role-at-prior-cutoff sequence is archived, so role changes are not measurable.
- Role slices: HGB vs hybrid MAE is 5.286 vs 7.710 for guards (n=125), 4.884 vs 7.342 for forwards (n=113), and 5.833 vs 5.741 for centers (n=51). This single selected round is insufficient for a subgroup conclusion; the center slice does not favor HGB.
- Current lineup group available for 273 paired rows (127 `QUINTETTO`, 146 `PANCHINA`); 16 rows have no group. These slices are descriptive and inherit the archive's non-certified status.
- Lineup slices: HGB vs hybrid MAE is 4.973 vs 5.141 for `QUINTETTO` (n=127) and 5.645 vs 8.026 for `PANCHINA` (n=146). The 16 rows without a group have too little, selectively missing coverage for interpretation.
- Team changes cannot be identified reliably from this single forecast snapshot and the matching outcome logs. The `cr_change_last_gameweek` field is credit movement, not a team-change label.
- Availability subgroups are not certified: the Lineups availability snapshot was invalid and stale in the archive validation. The per-output `status` field is not sufficient to establish a reliable pre-cutoff injury/availability cohort.
- Stable-history subgroup distinctions beyond the stored `n_games` count are not reconstructible from one run.

## Existing temporal audits and protocol differences

[`dunkest_minutes_forecast_walk_forward_20261014_v1.md`](dunkest_minutes_forecast_walk_forward_20261014_v1.md) reports expanding-origin held-out seasons 2022/23–2024/25. It scores HGB against previous 1/3/5-game baselines, with 57,682 HGB rows and 57,500 previous-five rows. HGB MAE is 4.9831 vs previous-five 5.1269 pooled, but HGB has worse zero-minute MAE (10.6455 vs 9.4419; n=178 vs 177). Those are not production hybrid predictions.

[`dunkest_minutes_hybrid_nested_20261014_v1.md`](dunkest_minutes_hybrid_nested_20261014_v1.md) calls one candidate `nested_gated`, but that candidate is a train-fit HGB gated/blended with previous-five minutes by history cohort. It does not recreate production current-lineup and credit priors, current-role caps, same-team role competition or positional minute allocation. Its reported HGB/prev5/gated figures therefore cannot be substituted for a paired production-hybrid result.

The rate-decomposition audit uses the same historical HGB predictions with a separate PDK-per-minute experiment; its target, row selection and counterfactual differ. The production PDK 2025/26 holdout is a separate season and protocol. None of those metric sets can be combined with this GW1 archive comparison as if they were one walk-forward sample.

## PDK impact

No PDK counterfactual is reported. The saved output contains production PDK components based on the operational, role-adjusted/allocated hybrid minutes. The shadow value is a raw HGB minutes prediction, not a version of `expected_min` that has been passed through the same production role caps, competition, positional allocation, and subsequent PDK blend. It is missing for 85 candidates, so using only the paired subset would also change the team/role competition context. Substituting it by `minutes × rate` would not preserve production logic. A faithful rerun with a controlled minutes override is not verified from the saved archive, so the PDK effect remains unmeasured.

## Reproducibility and decision

Run from the repository root:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_minutes_hybrid_shadow_archive_v1.py
```

This writes the row-level paired dataset and machine-readable metrics JSON next to this report. Matching, date ordering, feature/forecast chronology checks, metric definitions and paired game-cluster bootstrap behavior have targeted unit tests in `tests/test_minutes_comparison.py`.

**Operational decision:** keep the production hybrid unchanged and continue HGB in shadow. The partial GW1 diagnostic favors HGB on observed participants, but excludes all unmatched candidates and zero-minute cases, has a pre-lock-ineligible archive, and represents one forecast origin only. It is not a valid basis to promote HGB. The strongest prior evidence also warns that HGB is weaker on zero-minute and low-history cohorts.

**Next experiment:** capture several future, manifest-certified forecast origins with complete canonical player/game outcome reconciliation (including verified zero-minute/DNP labels), then run the same paired comparison by chronological forecast fold before considering any production change.
