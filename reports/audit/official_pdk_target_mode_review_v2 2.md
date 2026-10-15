# Official PDK target-mode review (v2)

## Current default

- Resolved settings: `season=2026-27`, `feature_season=2025-26`, `training_target=auto`.
- In `predictor.py`, `auto` selects `target_pdk_official` when at least 1,000 finite official labels exist.
- The strict NBA-matched 2025/26 overlay contains **24,424 rows**, of which **18,412** have `gameValidForDunkest=True` and finite `PDK_OFFICIAL_VALID`; the remaining 5,369 matched-but-invalid rows and 643 unmatched rows have no finite official target.
- The wider official Dunkest source contains **21,889 valid-flag rows**. Of these, **18,412** have a verified NBA player/date/opponent match; **3,477** were deliberately excluded rather than force-matched.
- Therefore the current production default is not proxy-only: it can select official labels when the overlay is attached.

## Separation and feature history

- `target_pdk_official` is carried as a target column and is not part of the model feature whitelist.
- Production rolling/lag features are still computed from the proxy `PDK` column. The isolated historical V3 experiment instead rebuilds lags from prior official PDK targets.
- This is not direct target leakage, but the production target-selection path and isolated V3 validation do not use identical historical-target semantics.

## Verification

- Focused tests: **16 passed** (`test_official_pdk_labels.py`, `test_temporal_validation.py`, `test_reliability_regressions.py`).
- No code, configuration, source parquet, official labels, model artefacts, temporal splits, or backtests were changed.

## Decision to resolve

The project direction was to keep proxy PDK as the default until official schedule/target semantics are fully verified. The current config says `training_target: auto`, which can select official PDK by default. I left this unchanged to avoid silently altering production behavior. Before production use, explicitly decide whether to retain `auto` or pin the default to `target_pdk`; if official-target mode is retained, validate production proxy-history features separately from the official-lag V3 experiment.
