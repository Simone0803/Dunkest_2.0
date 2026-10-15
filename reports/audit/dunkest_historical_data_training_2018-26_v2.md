# Dunkest historical data and PDK model — V3 through 2025/26

Date: 2026-10-11
Status: historical data extended, V3 trained and evaluated, **not integrated into production**.

## Summary

The experimental training set has been extended with verified official PDK labels from the completed 2025/26 Regular Season. The Random Forest V3 was trained on 112,178 player-game rows from 2020/21–2025/26. Four expanding-season walk-forward folds were evaluated; the latest 2025/26 season was held out and predicted using only 2020/21–2024/25 training rows.

The model continues to beat the previous-10-PDK mean baseline on overall MAE and RMSE in all four tested seasons. The absolute gain remains modest, and the model is worse than the baseline in the lowest and highest target-score bands. It is retained as an experimental candidate only.

## 1. Dataset extension and labels

V3 starts from the verified V2 training set and adds 18,412 records from the 2025/26 Dunkest official game-history feed. Added records must satisfy both:
1. `gameValidForDunkest=True`
2. unique verified NBA player/date/opponent match to the regular-season NBA player game log.

The wider official Dunkest season archive has 21,889 valid-flag rows. Only 18,412 entered V3; the remaining 3,477 were not added because they were not in the verified matched sample. This is a deliberate conservative choice: no approximate-date or PDK-score-only join was used.

| Season | Training rows |
|---|---:|
| 2020/21 | 17,662 |
| 2021/22 | 18,422 |
| 2022/23 | 19,165 |
| 2023/24 | 18,927 |
| 2024/25 | 19,590 |
| 2025/26 | 18,412 |
| **Total V3** | **112,178** |

The V2 source rows and their existing lag/rolling features were checked against the V3 rebuild: **zero feature-value or missingness mismatches** across the compared PDK and NBA-history features. V3 contains 95 columns, with an explicit whitelist of 79 pre-game features. NBA statistics are taken only from the latest NBA game strictly before the target date; the as-of join excludes same-date records. Official PDK lags are recomputed chronologically from prior valid PDK targets.

Build audit: `data/processed/dunkest_pdk_game_training_2020-26_v3_build_audit.json`.

## 2. Walk-forward validation

Each fold trains on earlier seasons and tests on a later season. The 2025/26 fold trains only on the prior five seasons (93,766 rows) and tests on 18,412 labeled player-games. During test-season evaluation, it is an online one-step-ahead setting: earlier games from the same test season can contribute to later rows' lagged history, never the current or future target.

| Test season | Training rows | Test rows | RF MAE | Previous-10 mean MAE | RF RMSE | Previous-10 mean RMSE |
|---|---:|---:|---:|---:|---:|---:|
| 2022/23 | 36,084 | 19,165 | 7.5783 | 7.7689 | 9.8425 | 10.1134 |
| 2023/24 | 55,249 | 18,927 | 7.5971 | 7.7652 | 9.8381 | 10.1003 |
| 2024/25 | 74,176 | 19,590 | 7.5886 | 7.7920 | 9.8831 | 10.1795 |
| **2025/26** | **93,766** | **18,412** | **7.5775** | **7.7886** | **9.8563** | **10.1539** |

For 2025/26, Random Forest improves MAE by 0.2112 PDK (2.71%) and reduces RMSE by about 0.298 PDK versus the previous-10 mean. The fold uses no 2025/26 labels to fit the model.

All validation safeguards passed:
- lag1 PDK value mismatches: 0
- lag1 PDK missingness mismatches: 0
- duplicate player/date rows in test seasons: 0
- smoke test on the fitted V3 artefact: 50/50 finite predictions.

Files:
- `data/processed/dunkest_pdk_game_walk_forward_metrics_2020-26_v3.csv`
- `data/processed/dunkest_pdk_game_walk_forward_predictions_2020-26_v3.csv`
- `data/processed/dunkest_pdk_game_walk_forward_audit_2020-26_v3.json`

## 3. Error slices and feature importance

The walk-forward predictions show where the aggregate gain does and does not hold.

| Target PDK band | RF MAE | Previous-10 MAE | Better overall |
|---|---:|---:|---|
| Below 5 | 7.77 | 7.47 | Previous-10 baseline |
| 5–10 | 5.56 | 5.92 | Random Forest |
| 10–20 | 5.23 | 5.96 | Random Forest |
| 20–30 | 7.25 | 7.70 | Random Forest |
| 30+ | 14.25 | 13.72 | Previous-10 baseline |

The model's largest transformed feature importance is `prev10_pdk_mean` (about 68.8%), followed by `prev5_pdk_mean` (about 9.2%) and previous-game/rolling NBA minutes. This confirms that recent PDK form dominates the learned signal; extra NBA boxscore features add signal but do not radically change the problem.

Diagnostics:
- `data/processed/dunkest_pdk_game_walk_forward_cohorts_2020-26_v3.csv`
- `data/processed/dunkest_pdk_historical_random_forest_2020-26_v3_feature_importance.csv`

## 4. Trained artefact

- Model: `data/processed/dunkest_pdk_historical_random_forest_2020-26_v3.joblib`
- Metadata: `data/processed/dunkest_pdk_historical_random_forest_2020-26_v3.json`
- Training set: `data/processed/dunkest_pdk_game_training_2020-26_v3.parquet`
- Feature whitelist/schema: `data/processed/dunkest_pdk_game_training_2020-26_v3_feature_schema.csv`

Parameters are kept consistent with earlier RF experiments: 160 trees, max depth 9, minimum leaf size 5, max features 0.8, random state 42. The saved artifact is fitted on all 112,178 labels available through 2025/26. Its evaluation estimates come from the separate expanding-season folds, not from in-sample score.

## 5. Historical limits and interpretation

The older Dunkest weekly-round endpoint still does not expose data for season IDs 1 (2018/19) and 3 (2019/20). A different official endpoint returns dated records for those seasons, but every record has `gameValidForDunkest=False`; they remain usable as prior NBA boxscore history where identity is verified, not as official target labels. The 2025/26 PDK proxy audit also shows why the official feed should remain the target source.

V3 is a player-game PDK model. It does not optimize lineup selection, coach scoring, credit budget, price change, injuries, or transfers. It is not loaded by the production training pipeline and has not replaced the current model. Before considering deployment, evaluate V3 prospectively on 2026/27 rounds as they finish, monitor error by player cohort and target range, and retain a simple rolling-mean fallback for low/high-score tails.

## 6. Reproduction

From `~/Documents/Dunkest`:

```bash
./.venv/bin/python -m py_compile scripts/build_dunkest_pdk_training_dataset_v3.py scripts/validate_dunkest_historical_pdk_training_v3.py scripts/train_dunkest_historical_pdk_model_v3.py
PYTHONPATH="$PWD/src" ./.venv/bin/python scripts/build_dunkest_pdk_training_dataset_v3.py
PYTHONPATH="$PWD/src" ./.venv/bin/python scripts/validate_dunkest_historical_pdk_training_v3.py
PYTHONPATH="$PWD/src" ./.venv/bin/python scripts/train_dunkest_historical_pdk_model_v3.py
PYTHONPATH="$PWD/src" ./.venv/bin/python -m pytest -q
```

All three scripts refuse to overwrite existing versioned outputs (the builder, validator and trainer). The commands above show the execution order for a clean reproduction; because this V3 run has already generated its artifacts, do not run them unchanged again unless you first archive the existing outputs or deliberately create a new version suffix for every dependent path.

## 7. Production safeguard

No production predictor, feature-builder, optimizer, or current lineup-browser code was changed for V3. Existing unrelated edits in the working tree were left as they were. V3 is stored in new versioned dataset/model/report files.
