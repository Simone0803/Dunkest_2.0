# Dunkest project follow-up — 2026-10-13 (v25)

This update deliberately returns to the core objective: improve predictive accuracy. It supersedes the emphasis of the previous continuation; the pre-lock inventory is background context only, not the primary workstream. See v24 and earlier reports for prior experiments.

## 19. Train-only predictive model search

Added and executed:
- `scripts/tune_dunkest_pdk_predictor_train_only_v1.py`
- `reports/audit/dunkest_pdk_train_only_search_20261013_train_only_v1.md`
- `reports/audit/dunkest_pdk_train_only_search_20261013_train_only_v1_metrics.csv`
- `reports/audit/dunkest_pdk_train_only_search_20261013_train_only_v1_predictions.csv`
- `reports/audit/dunkest_pdk_train_only_search_20261013_train_only_v1.json`
- `reports/audit/dunkest_pdk_train_only_search_20261013_train_only_v1_paired_bootstrap.json`

The search used only official-valid target seasons 2020/21–2024/25. Expanding-origin validation folds are 2022/23, 2023/24 and 2024/25; every fold trains on earlier seasons only. Season 2025/26 was filtered out before fitting and scoring. A lag-1 PDK integrity check found zero mismatches.

Compared Extra Trees with leaf sizes 8 and 12, and histogram gradient boosting, using:
- existing curated PDK/NBA lag and rolling-form features;
- additional prior NBA-history coverage and prior-game match flags;
- explicit recent-form trends (previous 3 vs 10 PDK, and recent minutes trends).

## 20. Results and decision

Best candidate by pooled player-game MAE: `history_flags_trends / ExtraTrees(min_samples_leaf=12)`.

| Candidate | Weighted OOF MAE | Weighted OOF RMSE |
|---|---:|---:|
| Extra Trees leaf 12 + history flags/trends | 7.56075 | 9.83512 |
| Extra Trees leaf 12, existing features | 7.56323 | 9.84024 |
| Extra Trees leaf 8 + history flags/trends | 7.56975 | 9.83910 |
| Extra Trees leaf 8, existing features | 7.56989 | 9.84343 |
| Histogram gradient boosting + history flags/trends | 7.57351 | 9.84060 |
| Histogram gradient boosting, existing features | 7.58171 | 9.84347 |

The added history/trend features improve the best Extra Trees candidate by only **0.00247 MAE** versus the same estimator with the original feature set. A paired bootstrap resampling 475 complete target-date clusters gave a 95% interval for the MAE difference of **[-0.00678, +0.00182]**, which includes zero. The candidate is also selected on these same folds, so this interval is descriptive rather than independent confirmation.

**Decision: no production promotion.** The experiment was model-focused and narrows the search, but its incremental feature gain is too small and uncertain to justify replacing the existing model. The strongest existing result remains the tuned Extra Trees/ensemble work from earlier reports; the next meaningful gain likely requires improving the forecast of minutes/role/usage and the high-score tail, then evaluating those changes on the same chronological folds. Participation must not be trained by treating absent historical rows as confirmed non-appearances.

## 21. Verification and safety

- Search predictions and metrics were generated for 57,662 paired player-game validation rows across three folds.
- The 2025/26 holdout was not loaded by this experiment.
- No production source, configuration, model artifact, or ensemble weight was changed.
- `git diff --check` passed after the experiment and report generation.
- No commit or push was performed.
