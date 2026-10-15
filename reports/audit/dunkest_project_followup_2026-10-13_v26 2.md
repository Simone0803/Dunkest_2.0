# Dunkest project follow-up — 2026-10-13 (v26)

## 22. High-score tail and past-only residual correction

Added and executed the exploratory experiment:
- `scripts/experiment_dunkest_past_only_residual_correction_v1.py`
- `reports/audit/dunkest_20261013_past_only_residual_correction_v1.md`
- companion metrics, prediction and JSON audit files in `reports/audit/`.

The experiment starts from saved expanding-origin OOF predictions for the V6 rest/schedule model. It trains a second-stage residual model only on earlier-season OOF errors: 2023/24 is fitted from 2022/23; 2024/25 is fitted from 2022/23 and 2023/24. No 2025/26 or frozen 2026/27 predictions are loaded.

### Results

| Correction | 2023/24 MAE | 2024/25 MAE | Date-cluster 95% CI for ΔMAE in 2023/24 | Date-cluster 95% CI for ΔMAE in 2024/25 |
|---|---:|---:|---:|---:|
| Raw V6 prediction | 7.46376 | 7.46322 | — | — |
| Ridge residual | 7.48407 | 7.46852 | [+0.00824, +0.03163] | [−0.00544, +0.01583] |
| HistGradientBoosting residual | 7.45159 | 7.46267 | [−0.01889, −0.00511] | [−0.01178, +0.01088] |
| Extra Trees residual | 7.45464 | 7.45330 | [−0.01567, −0.00243] | [−0.02115, +0.00138] |

Negative ΔMAE means the corrected predictions improve. The high-score segment is where the hypothesis is most relevant: for actual PDK ≥25, raw MAE was 12.879 in 2023/24 and 12.553 in 2024/25. Extra Trees residual correction worsened that segment in 2023/24 (MAE 13.028) but improved it in 2024/25 (11.956). HistGradientBoosting showed a similar lack of stability: slightly worse on the actual ≥25 segment in 2023/24 (12.935) and better in 2024/25 (11.989). For actual PDK ≥30, both tree corrections improved the 2024/25 segment, but worsened it in 2023/24.

### Decision

**Do not promote the correction to production.** The correction has some promising season-specific signal, especially in 2024/25 high scores, but its effect is not stable across seasons. The paired bootstrap intervals also include zero for the 2024/25 overall comparison. This supports further model work rather than a production change.

The next model-focused step should be to separate expected opportunity from conversion: build past-only forecasts for minutes/role and usage/box-score rates, then combine those forecasts into a PDK expectation. A residual model based only on existing aggregate prediction, lagged CR and opponent summaries is not enough to consistently recover the high-score tail. Any such feature construction must use only information available before the target game and must not infer non-appearance from missing historical rows.

## 23. Verification and safety

- Script compiles and ran successfully; `git diff --check` passed.
- Three methods were evaluated on two expanding-origin validation seasons; target 2025/26 was not loaded.
- No production source, configuration, model artifact, ensemble weights, or frozen prospective GW1 snapshot was modified.
- No commit or push was performed.
