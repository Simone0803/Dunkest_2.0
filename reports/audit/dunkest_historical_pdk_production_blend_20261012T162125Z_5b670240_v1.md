# Historical PDK model integration — 20261012T162125Z_5b670240

## Integration

- Loaded the versioned historical Random Forest artifact in the production player prediction path.
- Constructed its 79 pre-game features from official valid Dunkest PDK history and NBA box-score logs, filtered strictly before each target fixture date.
- Blend weight: **20%** for players with at least 3 valid Dunkest PDK targets or at least 20 prior NBA games; the existing production projection retains 80% weight.
- Historical model scores are scaled by the current minutes allocator before blending. This preserves the role/minute constraint: **127 players were allocated zero minutes and 0 received a positive scaled historical component**.
- Players without sufficient historical information remain on the existing production path. Missing model artifacts/data cause the secondary model to be skipped rather than blocking the main forecast.
- Run manifest fingerprints now include the model artifact, its metadata, the training dataset, and NBA history manifest.

## Independent historical holdout (2025/26)

The historical model was trained on official target labels from 2020/21–2024/25 and evaluated on 18,412 valid target rows in 2025/26. This was an online one-step-ahead holdout, not a pre-season batch forecast.

| Model | MAE | RMSE | Bias | R² |
|---|---:|---:|---:|---:|
| Historical Random Forest | 7.5775 | 9.8563 | -0.1725 | 0.4214 |
| Previous-10 PDK baseline | 7.7886 | 10.1539 | -0.0479 | 0.3859 |

The historical model's holdout MAE is 0.2112 PDK (2.71%) lower than the simple baseline. This does **not** establish that the 20% blend improves on the previous production ensemble; a verified production-model walk-forward comparison is still required.

## Current 2026/27 G1 smoke run

- Run directory: `data/predictions/20261012T162125Z_5b670240/`
- Market players: 552
- Players blended: 469 (weight distribution: `{"0.2": 469, "0.0": 83}`)
- Mean player projection change versus the no-blend run: 0.317 PDK; mean absolute change: 0.329 PDK. This is a projection change, **not an accuracy measurement**.
- Structural lineup optimization completed; budgets/rosters remain subject to the existing optimizer constraints.

Top-k lineups from the integrated run:

1. **212.0 projected PDK** — Aaron Gordon, Aday Mara, Darius Acuff Jr, Demar Derozan, Keaton Wagler, Kyrie Irving, Marvin Bagley III, Ty Jerome, Walker Kessler, Yaxel Lendeborg
2. **202.1 projected PDK** — Aaron Gordon, Aday Mara, Damian Lillard, Darius Acuff Jr, Joan Beringer, Kyrie Irving, Marvin Bagley III, Ty Jerome, Yaxel Lendeborg, Zach Edey
3. **200.5 projected PDK** — Aday Mara, Darius Acuff Jr, Izaiyah Nelson, Jayson Tatum, Joan Beringer, Keaton Wagler, Kyrie Irving, Ty Jerome, Walker Kessler, Yaxel Lendeborg


Player-level audit CSV: `reports/audit/dunkest_historical_pdk_blend_player_comparison_20261012T162125Z_5b670240_v1.csv`

## Historical target limitation

2018/19 and 2019/20 NBA logs are included as strictly past NBA-stat history. Their Dunkest PDK labels are not used because the available archive marks all those rows `gameValidForDunkest=False`. Official target-label training therefore starts in 2020/21; no proxy targets were substituted.

## Validation

- Full test suite: 222 passed before the final metadata-only fingerprint addition; rerun after final changes.
- No historical source dataset was overwritten, and no Git commit/reset was performed.
