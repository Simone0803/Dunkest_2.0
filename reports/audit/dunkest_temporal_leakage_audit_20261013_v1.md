# Dunkest temporal leakage and historical dataset audit — 2026-10-13

Generated: 2026-10-13T07:39:11.881321+00:00

**Scope:** read-only audit. Production data, model weights and the frozen prospective run were not changed.

## Executive summary

- The certified official PDK supervised dataset currently spans **2020/21–2025/26**, not 2018/19–2025/26.
- The official archive has 2018/19 and 2019/20 rows, but their archived game-valid flags are false; these rows are not certified PDK targets.
- The V3 training dataset has **112,178 rows** (2020/21–2025/26), including **93,766** rows through 2024/25.
- 2025/26 has already been inspected by project experiments and is not globally untouched.
- The main GW1 trainer is prior-season-only; the multi-season historical model is a separate path, not the main training matrix.
- When official labels are selected, the production rolling PDK features still originate from the PDK proxy column unless separately replaced.
- Lagged rolling features, strict-before-date history filters and fold-local imputation are present; integrity metrics are reported below.

## Findings

### [BLOCKER_FOR_REQUESTED_TRAINING_RANGE] No certified supervised PDK labels for 2018/19 and 2019/20

The dated official archive has rows for these seasons, but all recorded gameValidForDunkest flags are false. Do not use them as target labels without independent source certification; verified NBA boxscores can still be prior feature history.

| Season | Rows | Valid true | Valid false | Target non-null | Duplicate player-game |
|---|---:|---:|---:|---:|---:|
| 2018-19 | 26094 | 0 | 26094 | 26094 | 0 |
| 2019-20 | 22384 | 0 | 22384 | 22384 | 0 |

### [HIGH] 2025/26 is not a globally untouched holdout

The season has already been examined in prior model comparison, tuning, calibration and error-slice experiments. It can remain a walk-forward fold but must not be called a project-wide untouched final holdout.

### [HIGH] Auto target mode can fall back to proxy PDK

Production selects official labels only when at least 1,000 finite labels exist; otherwise it silently chooses target_pdk. Official-target experiments should assert label provenance and fail closed.

### [MEDIUM] Rolling features sort only by date

The production rolling builder sorts by GAME_DATE without a game/time tie-break. shift(1) is safe only when each player has unique dates; dataset duplicate counts are reported below.

### [HIGH] The main GW1 trainer is still prior-season-only

The production run_train opening-round branch loads player_game_logs_<feature_season>.parquet and builds its primary training matrix from that season. The multi-season V3 dataset is used by a separate historical model path, not as the main supervised training matrix. Therefore the requested 2018/19–2024/25 multi-season training policy is not yet the production trainer's policy.

### [MEDIUM] Official labels and rolling PDK features have different provenance

attach_official_pdk_labels adds PDK_OFFICIAL_VALID without replacing the original PDK column. build_feature_matrix derives target_pdk from PDK and rolling PDK features from that same column; when train_models selects target_pdk_official as y, the labels are official but PDK-history predictors may remain proxy-derived. This is not future leakage, but it is a feature/target provenance mismatch worth measuring before integration.

### [INFO] Historical certified target set spans 2020/21 onward

The existing V3 dataset has 112,178 rows from 2020/21–2025/26; 93,766 rows are from 2020/21–2024/25. Earlier two seasons can provide verified NBA history, not certified PDK supervised labels.

## Training dataset integrity

| Dataset | Rows | Duplicate player-game | Duplicate player/date | Lag1 value mismatches | Lag1 missingness mismatches | NBA history at/after target |
|---|---:|---:|---:|---:|---:|---:|
| training_v1 | 93766 | 0 | 0 | 0 | 0 | n/a |
| training_v2 | 93766 | 0 | 0 | 0 | 0 | 0 |
| training_v3 | 112178 | 0 | 0 | 0 | 0 | 0 |

## Static temporal-control checks

| Check | Status | File:line | Interpretation |
|---|---|---|---|
| rolling_shift | PASS | src/dunkest/features/builder.py:247 | Player rolling features shift by one game row. |
| season_mean_shift | PASS | src/dunkest/features/builder.py:261 | Season mean excludes the current game. |
| team_prior_rows | PASS | src/dunkest/features/builder.py:426 | Team context uses earlier rows only. |
| prematch_denylist | PASS | src/dunkest/data/temporal.py:22 | Post-match columns are explicitly forbidden as features. |
| historical_pdk_asof | PASS | src/dunkest/models/historical_pdk.py:121 | Historical PDK history is filtered strictly before target date. |
| historical_nba_asof | PASS | src/dunkest/models/historical_pdk.py:121, src/dunkest/models/historical_pdk.py:135 | NBA history is filtered strictly before target date. |
| nba_join_no_exact_match | PASS | scripts/build_dunkest_pdk_training_dataset_v3.py:120, scripts/build_dunkest_pdk_training_dataset_v3.py:346 | NBA as-of join excludes target-date records. |
| fold_local_imputation | PASS | src/dunkest/models/predictor.py:306 | OOF imputation is fit on each training fold, then applied to validation. |
| proxy_fallback | REVIEW | src/dunkest/models/predictor.py:204 | Auto target mode falls back to proxy PDK if official labels are insufficient. |
| date_only_sort | REVIEW | src/dunkest/features/builder.py:198, src/dunkest/features/builder.py:424 | Rolling order has no explicit game/time tie-break; require unique player/date rows. |
| opening_training_scope | REVIEW | src/dunkest/pipeline/train.py:24 | GW1 production trainer loads only the configured prior-season NBA logs; this is not multi-season supervised training. |
| proxy_feature_official_target | REVIEW | src/dunkest/data/dunkest/official_pdk.py:121 | Official PDK labels are attached in a separate column; the existing PDK proxy column is retained, so production rolling PDK features may be proxy-derived even when labels are official. |
| historical_model_inference_blend | INFO | src/dunkest/models/predictor.py:31, src/dunkest/models/predictor.py:936 | Historical multi-season model is an additional prediction path; inspect its blend weight and training artifact separately from the main season-only trainer. |
| holdout_caveat | PASS | scripts/optimize_dunkest_pdk_model_walk_forward_20261012_v1.py:130 | Experiment documents that 2025/26 was already examined project-wide. |

## Recommended next steps

1. For the requested 2018/19–2024/25 time span, use verified NBA boxscores from 2018/19–2019/20 as prior features, but train supervised PDK labels on certified 2020/21–2024/25 rows unless authoritative labels are recovered.
2. Use expanding-origin folds inside 2020/21–2024/25 for model, feature, rookie and calibration selection; treat 2025/26 as a historical final fold with explicit project-wide holdout caveat.
3. Make player/date uniqueness and lag-integrity checks hard assertions for each dataset build.
4. For official-target experiments, require a minimum certified label count and fail closed rather than silently switching to proxy labels.
5. Keep player PDK model validation separate from lineup/coach/transfer evaluation, which requires authentic pre-match snapshots and fixture-linked official results.

## Artifacts

- JSON: reports/audit/dunkest_temporal_leakage_audit_20261013_v1.json
- CSV: reports/audit/dunkest_temporal_leakage_season_coverage_20261013_v1.csv
