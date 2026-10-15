# Dunkest project follow-up — 2026-10-12 (v2)

## Completed in this follow-up

- **Schedule mapping:** regular-season schedule IDs confirmed for 2022/23 (`1`), 2023/24 (`8`), 2024/25 (`19`), with a sampled 2025/26 schedule (`36`). Current 2026/27 config uses schedule `57`.
- **Historical calendar search:** surveyed 3,920 read-only schedule/matchday pairs and probed public configuration/list routes. The schedule collection route returns `401 UNAUTHENTICATED`; no public enumeration route was recovered. No pre-2022/23 NBA regular-season calendar was found. Seasons 2018/19–2021/22 remain unresolved, not proven absent.
- **Status-aware archive comparison:** DET–WAS on 2023-02-01 is `postponed`; excluding it, all 2,080 2022/23 played-game team sides and flags match. In 2023/24, all 2,028 team sides match; 2,027/2,028 flags agree.
- **Cross-endpoint discrepancy:** six player-level requests for BOS–CLE on 2023-12-12 all report `gameValidForDunkest=false`; the schedule API says Boston valid and Cleveland invalid. Raw source fields remain untouched and are not treated as equivalent.
- **2024/25 validation:** all 2,076 archive-backed team sides and validity flags match after handling two postponed records and one stale `playing` status.
- **Target-mode experiment:** 7,384 identical out-of-fold rows show mixed results. Proxy-trained MAE/RMSE = 7.5510/9.8782; official-trained = 7.5651/9.8461. No clear overall winner.
- **Training integration test:** added a test proving explicit official-target selection changes the supervised label while preserving the same feature set and excluding targets from predictors.
- **Quality gate:** full suite **213 passed**; 6,800 warnings, predominantly PuLP deprecations.

## Safeguards

No original parquet, official PDK target, `gameValidForDunkest`, production config, model artifact, temporal split, or existing backtest was changed. `PDK` and official PDK remain separate. `training_target: auto` is unchanged pending an explicit decision; the audit notes that it may select official labels once the coverage threshold is met.

## Main files

- `dunkest_schedule_season_id_inventory_v7.md`
- `dunkest_historical_schedule_coarse_survey_v1.md`
- `dunkest_historical_endpoint_discovery_v1.md`
- `dunkest_official_schedule_vs_archive_validation_v2_status_aware.md`
- `dunkest_bos_cle_validity_cross_endpoint_check_v1.md`
- `dunkest_schedule_2024-25_archive_validation_v3.md`
- `proxy_vs_official_target_comparison_2025-26_v2.md`
- `official_pdk_target_mode_review_v2.md`
- `tests/test_official_pdk_training_target_integration.py`

## Next safe steps

1. Seek a supported historical calendar export or authenticated app workflow for 2018/19–2021/22; do not guess IDs or bypass authentication.
2. Resolve the BOS–CLE schedule/player validity mismatch with documented source semantics before using schedule `is_valid` as a substitute for `gameValidForDunkest`.
3. Leave production target mode and existing backtests unchanged until the historical label semantics are resolved and target-mode comparisons are repeated across seasons.
