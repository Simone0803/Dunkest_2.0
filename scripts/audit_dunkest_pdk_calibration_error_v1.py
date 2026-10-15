#!/usr/bin/env python3
"""Post-hoc calibration/error audit for walk-forward game-level Dunkest PDK predictions."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "dunkest_pdk_game_walk_forward_predictions_2020-26_v3.csv"
OUT = ROOT / "reports" / "audit"
WEIGHTS = {"random_forest": 0.60, "ridge": 0.35, "baseline_prev10_mean": 0.05}
MODELS = ["random_forest", "ridge", "baseline_prev10_mean", "tuned_convex_ensemble"]

def metrics(frame, model, pred_col, group_name, group_value):
    y = frame["target_pdk"].to_numpy(dtype=float)
    p = frame[pred_col].to_numpy(dtype=float)
    err = p - y
    return {"group": group_name, "group_value": str(group_value), "model": model, "n": len(frame),
            "actual_mean": float(np.mean(y)), "predicted_mean": float(np.mean(p)),
            "mae": float(mean_absolute_error(y, p)),
            "rmse": float(np.sqrt(mean_squared_error(y, p))),
            "bias_pred_minus_actual": float(np.mean(err)),
            "within_3_pdk_pct": float(np.mean(np.abs(err) <= 3.0) * 100),
            "within_5_pdk_pct": float(np.mean(np.abs(err) <= 5.0) * 100)}

def main():
    if not SOURCE.exists():
        raise SystemExit(f"Missing OOF predictions: {SOURCE}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = OUT / f"dunkest_pdk_calibration_error_audit_{stamp}.md"
    csv_path = OUT / f"dunkest_pdk_calibration_error_audit_{stamp}.csv"
    json_path = OUT / f"dunkest_pdk_calibration_error_audit_{stamp}.json"
    df = pd.read_csv(SOURCE)
    required = {"prediction_season", "target_pdk", *WEIGHTS}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")
    df = df.loc[df["prediction_season"].isin(["2022-23", "2023-24", "2024-25", "2025-26"])].copy()
    for col in ["target_pdk", *WEIGHTS]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[["target_pdk", *WEIGHTS]].isna().any().any():
        raise SystemExit("Null target or prediction values; refusing silent row drops.")
    df["tuned_convex_ensemble"] = sum(w * df[col] for col, w in WEIGHTS.items())
    df["actual_pdk_band"] = pd.cut(df["target_pdk"], bins=[-np.inf, 0, 5, 10, 15, 20, 30, np.inf],
        labels=["<=0", "(0,5]", "(5,10]", "(10,15]", "(15,20]", "(20,30]", ">30"], right=True).astype(str)
    rows = []
    for season, group in df.groupby("prediction_season", sort=True):
        for model in MODELS:
            rows.append(metrics(group, model, model, "season", season))
    for band, group in df.groupby("actual_pdk_band", observed=False, sort=False):
        if len(group) >= 100:
            for model in MODELS:
                rows.append(metrics(group, model, model, "realized_pdk_band", band))
    for model in MODELS:
        temp = df[["target_pdk", model]].copy()
        temp["prediction_bin"] = pd.qcut(temp[model], q=10, duplicates="drop")
        for band, group in temp.groupby("prediction_bin", observed=True, sort=True):
            y = group["target_pdk"].to_numpy(dtype=float)
            p = group[model].to_numpy(dtype=float)
            rows.append({"group": "predicted_decile", "group_value": str(band), "model": model, "n": len(group),
                "actual_mean": float(np.mean(y)), "predicted_mean": float(np.mean(p)),
                "mae": float(mean_absolute_error(y, p)), "rmse": float(np.sqrt(mean_squared_error(y, p))),
                "bias_pred_minus_actual": float(np.mean(p-y)),
                "within_3_pdk_pct": float(np.mean(np.abs(p-y) <= 3.0)*100),
                "within_5_pdk_pct": float(np.mean(np.abs(p-y) <= 5.0)*100)})
    result = pd.DataFrame(rows)
    result.to_csv(csv_path, index=False)
    holdout = result.loc[(result["group"] == "season") & (result["group_value"] == "2025-26")].copy()
    holdout = holdout[["model", "n", "actual_mean", "predicted_mean", "mae", "rmse", "bias_pred_minus_actual", "within_3_pdk_pct", "within_5_pdk_pct"]]
    realized = result.loc[result["group"] == "realized_pdk_band"].copy()
    lines = ["# Dunkest PDK calibration and error audit", "",
        f"Created UTC: {datetime.now(timezone.utc).isoformat()}", "",
        "## Scope and safeguards", "",
        "- Stored expanding-window walk-forward predictions only; no fitting or weight selection.",
        "- 2025/26 is descriptive final holdout, not a tuning input.",
        "- Realized-score bands are post-hoc diagnostics, not deployable pre-game features.",
        "- Ensemble weights: 0.60 Random Forest / 0.35 Ridge / 0.05 previous-10 mean.", "",
        "## Final holdout summary (2025/26)", "", holdout.to_string(index=False, float_format=lambda x: f"{x:.4f}"), "",
        "## Realized PDK bands", "",
        realized[["group_value", "model", "n", "actual_mean", "predicted_mean", "mae", "bias_pred_minus_actual"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"), "",
        "## Interpretation cautions", "",
        "- Conditioning on realized PDK changes the sample; use these results to diagnose errors, not to claim prospective performance.",
        "- If ensemble improvement is negligible, do not change production weights based on this audit alone.",
        "- Production validation still needs pre-game lineup/coach/price/injury snapshots linked to realized full-lineup PDK and transfer penalties.", "",
        "## Artifacts", "", f"- Detailed metrics: {csv_path.relative_to(ROOT)}", f"- Machine-readable audit: {json_path.relative_to(ROOT)}", ""]
    payload = {"created_utc": datetime.now(timezone.utc).isoformat(), "source_predictions": str(SOURCE.relative_to(ROOT)),
        "final_holdout_season": "2025-26", "ensemble_weights": WEIGHTS, "no_model_fitting_or_tuning": True,
        "metrics": rows, "interpretation_cautions": ["Realized-score bands are post-hoc diagnostics only.",
        "2025/26 holdout must not be reused for tuning.", "Game-level PDK results do not validate full-lineup or coach optimization."]}
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("REPORT", report_path); print("CSV", csv_path); print("JSON", json_path)
    print("\nHOLDOUT 2025/26"); print(holdout.to_string(index=False))
    print("\nBY REALIZED PDK BAND"); print(realized[["group_value", "model", "n", "mae", "bias_pred_minus_actual"]].to_string(index=False))

if __name__ == "__main__":
    main()
