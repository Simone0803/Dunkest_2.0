#!/usr/bin/env python3
"""Train score calibration maps on earlier OOF seasons and evaluate once on 2025/26."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "dunkest_pdk_game_walk_forward_predictions_2020-26_v3.csv"
OUT = ROOT / "reports" / "audit"
TRAIN_SEASONS = {"2022-23", "2023-24", "2024-25"}
TEST_SEASON = "2025-26"
WEIGHTS = {"random_forest": 0.60, "ridge": 0.35, "baseline_prev10_mean": 0.05}

def metric(name, y, p, split):
    err = p-y
    return {"split": split, "method": name, "n": int(len(y)),
        "mae": float(mean_absolute_error(y,p)),
        "rmse": float(np.sqrt(mean_squared_error(y,p))),
        "bias_pred_minus_actual": float(np.mean(err)),
        "actual_mean": float(np.mean(y)), "predicted_mean": float(np.mean(p))}

def main():
    if not SOURCE.exists():
        raise SystemExit(f"Missing OOF predictions: {SOURCE}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = OUT / f"dunkest_pdk_score_calibration_{stamp}.md"
    csv_path = OUT / f"dunkest_pdk_score_calibration_{stamp}.csv"
    json_path = OUT / f"dunkest_pdk_score_calibration_{stamp}.json"
    df = pd.read_csv(SOURCE)
    df = df.loc[df["prediction_season"].isin(TRAIN_SEASONS | {TEST_SEASON})].copy()
    needed = ["target_pdk", *WEIGHTS]
    for col in needed:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[needed].isna().any().any():
        raise SystemExit("Null values found in target or base predictions.")
    df["ensemble_raw"] = sum(w * df[col] for col,w in WEIGHTS.items())
    train = df.loc[df["prediction_season"].isin(TRAIN_SEASONS)].copy()
    test = df.loc[df["prediction_season"].eq(TEST_SEASON)].copy()
    if train.empty or test.empty:
        raise SystemExit("Missing calibration or final holdout fold.")
    ytr = train["target_pdk"].to_numpy(dtype=float)
    yte = test["target_pdk"].to_numpy(dtype=float)
    rows=[]
    calibrated = {}
    for base in ["random_forest", "ensemble_raw"]:
        xtr = train[base].to_numpy(dtype=float)
        xte = test[base].to_numpy(dtype=float)
        rows.append(metric(base+"_raw", yte, xte, "final_holdout_2025-26"))
        # Linear calibration is intentionally simple and extrapolates linearly.
        lin = LinearRegression().fit(xtr.reshape(-1,1), ytr)
        plin = lin.predict(xte.reshape(-1,1))
        rows.append(metric(base+"_linear_calibration", yte, plin, "final_holdout_2025-26"))
        calibrated[base+"_linear"] = {"intercept": float(lin.intercept_), "slope": float(lin.coef_[0])}
        # Isotonic mapping is monotone and constrained to observed training target range.
        iso = IsotonicRegression(out_of_bounds="clip").fit(xtr, ytr)
        piso = iso.predict(xte)
        rows.append(metric(base+"_isotonic_calibration", yte, piso, "final_holdout_2025-26"))
        calibrated[base+"_isotonic"] = {"threshold_count": int(len(iso.X_thresholds_))}
    metrics = pd.DataFrame(rows)
    metrics.to_csv(csv_path,index=False)
    payload={"created_utc":datetime.now(timezone.utc).isoformat(),
        "source_predictions":str(SOURCE.relative_to(ROOT)),
        "calibration_train_seasons":sorted(TRAIN_SEASONS),"final_holdout_season":TEST_SEASON,
        "ensemble_weights":WEIGHTS,"parameters":calibrated,
        "final_holdout_used_for_fit_or_selection":False,
        "metrics":rows,
        "caveats":[
          "Calibration maps are fitted only on earlier walk-forward prediction folds, never on 2025/26 targets.",
          "This is a separate game-level experiment and does not change production inference.",
          "Calibration may improve aggregate MAE while worsening subgroups; inspect residuals before any integration.",
          "The final holdout should be considered consumed for this calibration experiment and not reused for further iterative tuning."
        ]}
    json_path.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    lines=["# Dunkest PDK score calibration experiment","",
        f"Created UTC: {payload['created_utc']}","",
        "## Protocol","",
        "- Fit linear and isotonic calibration mappings on walk-forward predictions from 2022/23–2024/25.",
        "- Evaluated once on the untouched 2025/26 final fold.",
        "- No production files/configuration were changed.",
        "- Ensemble base weights: 0.60 Random Forest, 0.35 Ridge, 0.05 previous-10 mean.","",
        "## Final holdout metrics","",metrics.to_string(index=False,float_format=lambda x:f"{x:.4f}"),"",
        "## Calibration parameters","",json.dumps(calibrated,indent=2),"",
        "## Caveats","",*[f"- {c}" for c in payload["caveats"]],"",
        "## Artifacts","",f"- Metrics CSV: {csv_path.relative_to(ROOT)}",f"- Audit JSON: {json_path.relative_to(ROOT)}",""]
    report_path.write_text("\n".join(lines),encoding="utf-8")
    print("REPORT",report_path); print("CSV",csv_path); print("JSON",json_path)
    print(metrics.to_string(index=False))

if __name__=="__main__":
    main()
