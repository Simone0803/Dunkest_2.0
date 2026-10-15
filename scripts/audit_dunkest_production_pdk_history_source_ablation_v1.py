#!/usr/bin/env python3
"""Production-pipeline ablation: proxy PDK history vs verified official PDK history.

Uses only the frozen 2025/26 prior-season archive and official labels. The production
feature builder/model trainer are reused unchanged; only the PDK history series is
replaced with official labels where present (proxy fallback otherwise) in the challenger.
This is an experiment and does not change production inputs or configuration.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.config import Settings
from dunkest.data.dunkest.official_pdk import attach_official_pdk_labels, OFFICIAL_LABEL
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import train_models

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PLAYER = DATA / "processed/player_game_logs_2025-26.parquet"
TEAM = DATA / "processed/team_game_logs_2025-26.parquet"
OUT = ROOT / "reports/audit"
STEM = "dunkest_production_pdk_history_source_ablation_20261013_v1"
METRICS, PRED, AUDIT, REPORT = [OUT / f"{STEM}.{ext}" for ext in ("csv", "predictions.csv", "json", "md")]
# First path is CSV metrics; second path is predictions with a named suffix.
METRICS = OUT / f"{STEM}_metrics.csv"
PRED = OUT / f"{STEM}_predictions.csv"
AUDIT = OUT / f"{STEM}.json"
REPORT = OUT / f"{STEM}.md"
for path in (METRICS, PRED, AUDIT, REPORT):
    if path.exists():
        raise SystemExit(f"Refusing to overwrite versioned artifact: {path}")
if not PLAYER.is_file() or not TEAM.is_file():
    raise SystemExit(f"Required season logs missing: {PLAYER} / {TEAM}")
raw = pd.read_parquet(PLAYER)
team_logs = pd.read_parquet(TEAM)
raw = attach_official_pdk_labels(raw, DATA, "2025-26")
if OFFICIAL_LABEL not in raw:
    raise SystemExit("Official PDK labels were not attached; fail closed.")
raw[OFFICIAL_LABEL] = pd.to_numeric(raw[OFFICIAL_LABEL], errors="coerce")
label_count = int(np.isfinite(raw[OFFICIAL_LABEL].to_numpy(dtype=float, na_value=np.nan)).sum())
if label_count < 1000:
    raise SystemExit(f"Only {label_count} official labels; below minimum gate.")
proxy_pdk = pd.to_numeric(raw["PDK"], errors="coerce")
official = raw[OFFICIAL_LABEL]
hybrid_pdk = official.where(official.notna(), proxy_pdk)
raw_official_history = raw.copy()
raw_official_history["PDK"] = hybrid_pdk
settings = Settings(
    season="2025-26",
    data_dir=str(DATA),
    training_target="target_pdk_official",
    use_schedule=True,
    use_matchup=True,
    use_injuries=False,
)
records = []
prediction_frames = []
feature_audits = {}
for mode, logs in (("proxy_history", raw), ("official_history_with_proxy_fallback", raw_official_history)):
    print(f"Building production features for {mode}...", flush=True)
    features = build_feature_matrix(settings, logs, team_logs, injuries=pd.DataFrame(),
                                    schedule=None, team_overrides={}, target_gameweek=None)
    if "target_pdk_official" not in features:
        raise SystemExit("Production feature matrix lost official labels.")
    # Record whether official-history mode actually changes relevant historical predictors.
    feature_cols = [c for c in ["pdk_mean_3","pdk_mean_5","pdk_mean_10","pdk_mean_15",
        "pdk_std_5","pdk_median_5","pdk_season_mean","pdk_per_min_season",
        "player_opp_pdk_per_min","expected_pdk_minutes_model"] if c in features]
    feature_audits[mode] = {
        "feature_rows": len(features),
        "finite_official_targets": int(pd.to_numeric(features["target_pdk_official"], errors="coerce").notna().sum()),
        "feature_columns": feature_cols,
        "target_date_max": str(pd.to_datetime(features["GAME_DATE"], errors="coerce").max()),
    }
    print(f"Training production model stack for {mode}...", flush=True)
    models, oof = train_models(settings, features, target_column="target_pdk_official")
    target = pd.to_numeric(features.loc[oof.index, "target_pdk_official"], errors="coerce")
    valid = oof.notna() & target.notna() & np.isfinite(oof.to_numpy(dtype=float, na_value=np.nan))
    idx = oof.index[valid]
    y = target.loc[idx].to_numpy(float)
    pred = oof.loc[idx].to_numpy(float)
    if len(y) < 1000:
        raise SystemExit(f"Only {len(y)} valid OOF predictions for {mode}; expected >=1000.")
    err = pred-y
    row = {
        "mode": mode, "n_oof": int(len(y)), "mae": float(mean_absolute_error(y,pred)),
        "rmse": float(np.sqrt(mean_squared_error(y,pred))), "bias_pred_minus_actual": float(err.mean()),
        "actual_mean": float(y.mean()), "predicted_mean": float(pred.mean()),
        "within_3_pdk_pct": float((np.abs(err)<=3).mean()*100),
        "within_5_pdk_pct": float((np.abs(err)<=5).mean()*100),
        "selected_model_weights": json.dumps(models.get("_weights", {}), sort_keys=True),
        "projection_weights": json.dumps(models.get("_projection_weights", {}), sort_keys=True),
        "official_target_rows_in_matrix": feature_audits[mode]["finite_official_targets"],
    }
    records.append(row)
    frame = pd.DataFrame({
        "mode": mode, "index": idx.to_numpy(),
        "player_name": features.loc[idx, "PLAYER_NAME"].astype(str).to_numpy(),
        "game_date": pd.to_datetime(features.loc[idx, "GAME_DATE"], errors="coerce").dt.strftime("%Y-%m-%d").to_numpy(),
        "game_id": features.loc[idx, "NBA_GAME_ID"].astype(str).to_numpy(),
        "actual_pdk_official": y, "predicted_pdk_oof": pred,
        "error": err, "abs_error": np.abs(err),
        "history_games": pd.to_numeric(features.loc[idx, "n_games"], errors="coerce").to_numpy(),
    })
    prediction_frames.append(frame)
    print(f"Finished {mode}: n={len(y):,}, MAE={row['mae']:.4f}, RMSE={row['rmse']:.4f}", flush=True)

metrics = pd.DataFrame(records)
# Paired comparison on identical game/index rows only.
wide = prediction_frames[0].merge(
    prediction_frames[1], on=["index","player_name","game_date","game_id","actual_pdk_official"],
    suffixes=("_proxy","_official"), validate="one_to_one"
)
wide["delta_abs_error_official_minus_proxy"] = wide.abs_error_official - wide.abs_error_proxy
rng = np.random.default_rng(20261013)
B = 5000
# Cluster by calendar date: all player rows from a target date stay together.
wide["date_cluster"] = wide.game_date
clusters = wide.date_cluster.unique()
cluster_rows = [np.flatnonzero(wide.date_cluster.to_numpy() == c) for c in clusters]
boot = np.empty(B)
deltas = wide.delta_abs_error_official_minus_proxy.to_numpy(float)
for b in range(B):
    pick = rng.integers(0, len(cluster_rows), size=len(cluster_rows))
    boot[b] = deltas[np.concatenate([cluster_rows[i] for i in pick])].mean()
paired = {
    "paired_rows": len(wide), "date_clusters": int(wide.date_cluster.nunique()),
    "delta_mae_official_minus_proxy": float(deltas.mean()),
    "delta_mae_ci95": [float(np.quantile(boot,.025)), float(np.quantile(boot,.975))],
    "bootstrap_fraction_official_better": float(np.mean(boot < 0)),
    "bootstrap_replicates": B, "resampling_unit": "whole game date",
}
metrics.to_csv(METRICS, index=False)
pd.concat(prediction_frames, ignore_index=True).to_csv(PRED, index=False)
audit = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "data": str(PLAYER.relative_to(ROOT)), "official_overlay_rows": label_count,
    "label_policy": "Explicit verified official PDK target; no proxy-target fallback. PDK history challenger uses official PDK where present and the original proxy only for unmatched rows.",
    "feature_policy": "Production build_feature_matrix and train_models reused unchanged. Each variant receives the same official supervised targets; only the PDK values available to rolling history/baseline feature generation differ.",
    "feature_audits": feature_audits, "metrics": metrics.to_dict("records"), "paired_bootstrap": paired,
    "production_changed": False,
    "limitations": [
        "This is a temporal OOF ablation within 2025/26, not a new untouched season holdout; that season has already been inspected by other experiments.",
        "The OOF output follows the current production trainer's expanding date folds and fold-local ensemble weighting. It does not validate full lineup scores.",
        "Official PDK overlays may be incomplete; proxy values are used only as history fallback when an official label is absent.",
    ],
    "outputs": {"metrics": str(METRICS.relative_to(ROOT)), "predictions": str(PRED.relative_to(ROOT)),
                "audit": str(AUDIT.relative_to(ROOT)), "report": str(REPORT.relative_to(ROOT))}
}
AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str)+"\n", encoding="utf-8")
lines = [
    "# Production PDK history-source ablation", "",
    f"Generated UTC: {audit['generated_at_utc']}", "",
    "## Protocol", "",
    "- Same 2025/26 player/team logs and verified official PDK target labels in both arms.",
    "- Proxy arm uses the current production PDK history column as-is.",
    "- Challenger replaces the PDK history column with verified official PDK wherever available, retaining proxy values only where the overlay is missing.",
    "- Both arms use the unchanged production feature builder and trainer, including chronological OOF folds and fold-local model weighting.",
    "- No production code/configuration was changed.", "",
    "## Results", "", metrics.to_string(index=False), "",
    "## Paired date-cluster bootstrap", "",
    f"- Paired predictions: {paired['paired_rows']:,} over {paired['date_clusters']:,} game dates.",
    f"- Delta MAE (official-history minus proxy-history): {paired['delta_mae_official_minus_proxy']:.4f}.",
    f"- 95% interval: [{paired['delta_mae_ci95'][0]:.4f}, {paired['delta_mae_ci95'][1]:.4f}].",
    f"- Bootstrap fraction favoring official history: {paired['bootstrap_fraction_official_better']:.4f}.", "",
    "## Decision rule", "",
    "Treat this as an ablation on a previously examined season, not as a final independent holdout. Only consider a production change if official-history features consistently improve the expanding-origin folds and the inference path is covered by tests. Do not tune on the frozen 2026/27 GW1 prospective holdout.", "",
    "## Limitations", "",
    *[f"- {x}" for x in audit["limitations"]], "",
]
REPORT.write_text("\n".join(lines), encoding="utf-8")
print(json.dumps({"status":"completed","metrics":metrics.to_dict("records"),"paired_bootstrap":paired,
                  "artifacts":[str(p.relative_to(ROOT)) for p in (METRICS,PRED,AUDIT,REPORT)]}, indent=2, default=str))
