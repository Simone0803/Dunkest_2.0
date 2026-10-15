# Dunkest project follow-up — 2026-10-12 (v1)

## Work completed

1. **Official schedule mapping and archive validation**
   - Confirmed regular-season schedule IDs: `1` (2022/23), `8` (2023/24), `19` (2024/25), and sampled `36` (2025/26). Current 2026/27 league config reports schedule `57`.
   - Ran a read-only coarse survey of 3,920 schedule/matchday pairs across schedule IDs 1–49 and 80 sampled global matchday IDs. NBA-like records were found under schedules 1, 3 (playoffs sample), 8, 19 and 36.
   - No 2018/19–2021/22 regular-season calendar was found in that sample. This remains unresolved, not proof of absence.
   - Status-aware matching explains the apparent DET–WAS gap on 2023-02-01: the official record is `postponed`.
   - For 2022/23, all 2,080 team sides from played games and all validity flags match the local archive. For 2023/24, all 2,028 team sides match; 2,027/2,028 flags agree.
   - Investigated BOS–CLE on 2023-12-12 using six player IDs against `/api/player/games`. The schedule endpoint reports Boston valid and Cleveland invalid, while all six sampled player-level rows and local archive rows have `gameValidForDunkest=false`. This is retained as a cross-endpoint semantic/data discrepancy; no source values were rewritten.
   - For 2024/25, the two `postponed` records are excluded and one stale `playing` status is retained explicitly. All 2,076 archive-backed team sides and validity flags agree.

2. **Target-mode experiment**
   - Compared proxy-target and official-target training on identical rows, features and temporal cutoffs in 2025/26.
   - On 7,384 identical OOF rows evaluated against official PDK: proxy-trained MAE 7.5510 / RMSE 9.8782; official-trained MAE 7.5651 / RMSE 9.8461. Results are mixed; they do not establish a clear overall winner.
   - Both models use proxy-derived historical PDK features, so this is an isolated target-choice comparison and not directly comparable to the multi-season V3 experiment that rebuilds lags from official targets.

3. **Training-target integration test**
   - Added `tests/test_official_pdk_training_target_integration.py` to verify that explicitly selecting `target_pdk_official` changes the supervised label while keeping the same predictor feature set and excluding target columns from `FEATURE_COLS`.
   - Full suite: **213 passed**, 6,800 warnings (mostly PuLP deprecations and one live-market freshness warning).

## Safeguards preserved

- No original player-game parquet, official PDK target, `gameValidForDunkest`, production config, model artifact, temporal split, or existing backtest was changed.
- `PDK` remains separate from `PDK_OFFICIAL_VALID` / `target_pdk_official`.
- No proxy or reconstructed score was substituted for official PDK.
- `training_target: auto` remains unchanged pending an explicit target-mode decision; the audit documents that it can choose official targets when coverage exceeds the configured threshold.

## Main reports

- `dunkest_schedule_season_id_inventory_v7.md`
- `dunkest_historical_schedule_coarse_survey_v1.md`
- `dunkest_official_schedule_vs_archive_validation_v2_status_aware.md`
- `dunkest_bos_cle_validity_cross_endpoint_check_v1.md`
- `dunkest_schedule_2024-25_archive_validation_v3.md`
- `proxy_vs_official_target_comparison_2025-26_v2.md`
- `official_pdk_target_mode_review_v2.md`

## Recommended next investigation

- Search for supported historical calendar exports or app endpoints for 2018/19–2021/22; do not infer schedule IDs from stats API season IDs.
- Clarify the BOS–CLE schedule-level `is_valid` discrepancy with independent official evidence before treating schedule-level validity as equivalent to player-level `gameValidForDunkest`.
- Keep production target mode and backtest unchanged until these questions are resolved and the target-mode comparison is repeated across seasons with matched semantics.
