# Historical PDK model integration — 20261012T162434Z_7a50d394

## What changed

- Integrated the separate historical Random Forest artifact into the production player-prediction path.
- The inference adapter constructs the same 79 curated pre-game features from official valid Dunkest PDK history and NBA box-score logs; history is filtered strictly before each target fixture date.
- Configurable blend weight: **20%** (`historical_pdk_blend_weight: 0.20`) for players with at least 3 valid historical Dunkest targets or at least 20 prior NBA games; existing production forecast keeps 80% weight.
- The historical RF score is scaled to current allocated minutes before blending. Of 127 players assigned zero minutes, 0 receive a positive scaled historical component.
- 83 players without sufficient history stay on the existing production path. If model artifacts/data are absent, the main production prediction continues without the secondary model.
- Run manifest includes the blend configuration and fingerprints for the model artifact and training/history inputs: **PASS**.

## Independent holdout results (2025/26)

The RF was fit only on valid official target labels from 2020/21–2024/25 and evaluated on 18,412 valid target rows in 2025/26. Evaluation is online one-step-ahead within the season.

| Model | MAE | RMSE | Bias | R² |
|---|---:|---:|---:|---:|
| Historical Random Forest | 7.5775 | 9.8563 | -0.1725 | 0.4214 |
| Previous-10 PDK baseline | 7.7886 | 10.1539 | -0.0479 | 0.3859 |

Holdout MAE improves by 0.2112 PDK (2.71%) versus the simple baseline. This does **not** prove the 20% blend improves over the old production ensemble; the current production predictor still needs a verified walk-forward comparison.

## 2026/27 G1 smoke run

- Run artifacts: `data/predictions/20261012T162434Z_7a50d394/`
- Market rows: 552; rows blended: 469; weight distribution: `{"0.2": 469, "0.0": 83}`.
- Mean player projection change versus the no-blend run: 0.315 PDK; mean absolute change: 0.329 PDK. These are changes in predictions, **not an accuracy metric**.

Top-k lineups:

1. **212.0 projected PDK** — Aaron Gordon, Aday Mara, Darius Acuff Jr, Demar Derozan, Keaton Wagler, Kyrie Irving, Marvin Bagley III, Ty Jerome, Walker Kessler, Yaxel Lendeborg
2. **202.1 projected PDK** — Aaron Gordon, Aday Mara, Damian Lillard, Darius Acuff Jr, Joan Beringer, Kyrie Irving, Marvin Bagley III, Ty Jerome, Yaxel Lendeborg, Zach Edey
3. **200.5 projected PDK** — Aday Mara, Darius Acuff Jr, Izaiyah Nelson, Jayson Tatum, Joan Beringer, Keaton Wagler, Kyrie Irving, Ty Jerome, Walker Kessler, Yaxel Lendeborg


Player-level comparison: `reports/audit/dunkest_historical_pdk_blend_player_comparison_20261012T162434Z_7a50d394_v1.csv`

## Target-label limitation

NBA box-score logs from 2018/19 and 2019/20 contribute to the strictly-past history features, but their Dunkest PDK values are not used as supervised labels: the available archive marks all those rows `gameValidForDunkest=False`. No proxy scores were substituted. Supervised official PDK target training therefore starts in 2020/21.

## Verification

- Full suite: **222 passed, 0 failed**.
- `py_compile` and `git diff --check` passed.
- No original dataset was overwritten; no commit, reset, or revert was performed.
