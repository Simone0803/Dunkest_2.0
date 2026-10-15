#!/usr/bin/env python3
"""Tune a convex ensemble on pre-2025/26 walk-forward folds; evaluate final holdout once."""
from __future__ import annotations
import itertools, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "dunkest_pdk_game_walk_forward_predictions_2020-26_v3.csv"
OUT = ROOT / "reports" / "audit"
STEP = 0.05
VALIDATION_SEASONS = {"2022-23", "2023-24", "2024-25"}
FINAL_TEST_SEASON = "2025-26"
MODELS = ("random_forest", "ridge", "baseline_prev10_mean")

def score(frame, prediction, model, split):
    y = frame["target_pdk"].to_numpy(dtype=float)
    err = prediction - y
    return {"split": split, "model": model, "n": len(y),
            "mae": float(mean_absolute_error(y, prediction)),
            "rmse": float(np.sqrt(mean_squared_error(y, prediction))),
            "bias_pred_minus_actual": float(np.mean(err))}

def md_table(frame):
    view = frame.copy().round(4)
    cols = [str(c) for c in view.columns]
    rows = [[str(v) for v in row] for row in view.itertuples(index=False, name=None)]
    widths = [max([len(cols[i])] + [len(row[i]) for row in rows]) for i in range(len(cols))]
    return "\n".join(
        ["| " + " | ".join(cols[i].ljust(widths[i]) for i in range(len(cols))) + " |",
         "| " + " | ".join("-" * widths[i] for i in range(len(cols))) + " |"]
        + ["| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(cols))) + " |" for row in rows])

def main():
    if not DATA.exists():
        raise SystemExit(f"Missing out-of-fold predictions: {DATA}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    metrics_path = OUT / f"dunkest_ensemble_weights_walk_forward_{stamp}.csv"
    report_path = OUT / f"dunkest_ensemble_weights_walk_forward_{stamp}.md"
    audit_path = OUT / f"dunkest_ensemble_weights_walk_forward_{stamp}.json"
    df = pd.read_csv(DATA)
    required = {"prediction_season", "target_pdk", *MODELS}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Missing prediction columns: {missing}")
    df = df.loc[df["prediction_season"].isin(VALIDATION_SEASONS | {FINAL_TEST_SEASON})].copy()
    for col in ["target_pdk", *MODELS]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[["target_pdk", *MODELS]].isna().any().any():
        raise SystemExit("Null targets/predictions in selected folds; refusing silent row drops.")
    if set(df["prediction_season"].unique()) != VALIDATION_SEASONS | {FINAL_TEST_SEASON}:
        raise SystemExit("One or more required validation/final folds are missing.")
    val = df.loc[df["prediction_season"].isin(VALIDATION_SEASONS)].copy()
    test = df.loc[df["prediction_season"].eq(FINAL_TEST_SEASON)].copy()
    grid = np.round(np.arange(0.0, 1.0 + STEP / 2, STEP), 8)
    candidates = []
    values = val[list(MODELS)].to_numpy(dtype=float)
    y_val = val["target_pdk"].to_numpy(dtype=float)
    for w in itertools.product(grid, repeat=3):
        if np.isclose(sum(w), 1.0):
            candidates.append((float(mean_absolute_error(y_val, values @ np.asarray(w))), tuple(float(x) for x in w)))
    candidates.sort(key=lambda item: (item[0], item[1]))
    best_mae, best_weights = candidates[0]
    weights = dict(zip(MODELS, best_weights))
    def blend(frame):
        return sum(weights[name] * frame[name].to_numpy(dtype=float) for name in MODELS)
    rows = []
    for split_name, frame in (("validation_2022-23_to_2024-25", val), ("final_holdout_2025-26", test)):
        for name in MODELS:
            rows.append(score(frame, frame[name].to_numpy(dtype=float), name, split_name))
        rows.append(score(frame, blend(frame), "tuned_convex_ensemble", split_name))
    metrics = pd.DataFrame(rows)
    metrics.to_csv(metrics_path, index=False)
    limitations = [
        "Saved fold predictions are expanding-window out-of-fold predictions; this tunes ensemble weights, not RF/Ridge hyperparameters.",
        "The 2025/26 final holdout is evaluated after selection and must not be reused for further tuning.",
        "Game-level PDK metrics do not directly validate lineup optimization, coaches, prices, injuries, or transfer penalties.",
        "Supervised labels start in 2020/21 because 2018/19–2019/20 archive rows have unverified/false Dunkest-valid flags; those seasons remain available as prior NBA feature history."
    ]
    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_predictions": str(DATA.relative_to(ROOT)),
        "validation_seasons": sorted(VALIDATION_SEASONS),
        "final_test_season": FINAL_TEST_SEASON,
        "validation_objective": "pooled MAE",
        "grid_step": STEP,
        "chosen_weights": weights,
        "validation_ensemble_mae": best_mae,
        "candidate_weight_combinations": len(candidates),
        "no_final_test_used_for_tuning": True,
        "limitations": limitations,
        "metrics": metrics.to_dict(orient="records")
    }
    audit_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = [
        "# Walk-forward ensemble-weight tuning", "",
        f"Created UTC: {payload['created_utc']}", "",
        "## Protocol", "",
        "- Weights selected only on expanding-window out-of-fold folds from 2022/23–2024/25.",
        "- Objective: minimize pooled MAE over those validation folds.",
        "- Convex weights searched on a 0.05 grid across Random Forest, Ridge, and previous-10 PDK mean.",
        "- Weights are frozen before evaluating the 2025/26 final holdout.",
        "- Offline comparison only; production configuration is unchanged.", "",
        "## Selected weights", "",
        *[f"- {name}: {weight:.2f}" for name, weight in weights.items()],
        f"- Validation ensemble MAE: {best_mae:.4f} over {len(val):,} player-game rows.",
        f"- Weight combinations evaluated: {len(candidates):,}.", "",
        "## Metrics", "", md_table(metrics), "",
        "## Caveats", "", *[f"- {item}" for item in limitations], "",
        "## Artifacts", "",
        f"- Metrics CSV: {metrics_path.relative_to(ROOT)}",
        f"- Audit JSON: {audit_path.relative_to(ROOT)}", ""
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")
    print("REPORT", report_path)
    print("METRICS", metrics_path)
    print("AUDIT", audit_path)
    print("WEIGHTS", json.dumps(weights))
    print(metrics.to_string(index=False))
    print("FINAL TEST USED FOR TUNING: False")

if __name__ == "__main__":
    main()
