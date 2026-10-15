#!/usr/bin/env python3
"""Multi-season production feature ablation for proxy vs official PDK history."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.config import Settings
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import train_models
from dunkest.rules.pdk import pdk_from_boxscore_row

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HIST = DATA / "raw/nba_historical_logs_2018-25_v1"
TEAM_PATH = DATA / "processed/team_game_logs_2018-26_v1.parquet"
OFFICIAL_PATH = DATA / "processed/dunkest_pdk_game_training_2020-26_v3.parquet"
OUT = ROOT / "reports/audit"
STEM = "dunkest_production_pdk_history_source_ablation_20261013_v2_multiseason"
METRICS = OUT / f"{STEM}_metrics.csv"
PRED = OUT / f"{STEM}_predictions.csv"
AUDIT = OUT / f"{STEM}.json"
REPORT = OUT / f"{STEM}.md"
SEASONS = [
    ("7", "2021-22", HIST / "nba_player_game_logs_2021-22.parquet"),
    ("9", "2022-23", HIST / "nba_player_game_logs_2022-23.parquet"),
    ("13", "2023-24", HIST / "nba_player_game_logs_2023-24.parquet"),
    ("19", "2024-25", HIST / "nba_player_game_logs_2024-25.parquet"),
    ("25", "2025-26", DATA / "processed/player_game_logs_2025-26.parquet"),
]
for path in (METRICS, PRED, AUDIT, REPORT):
    if path.exists():
        raise SystemExit(f"Refusing to overwrite versioned artifact: {path}")
for path in [TEAM_PATH, OFFICIAL_PATH, *[p for _,_,p in SEASONS]]:
    if not path.is_file():
        raise SystemExit(f"Required input missing: {path}")

official = pd.read_parquet(OFFICIAL_PATH, columns=[
    "season_id", "game_date", "nba_GAME_ID", "nba_PLAYER_ID", "nba_TEAM_ABBREVIATION",
    "nba_match_status", "target_pdk"
])
official["season_id"] = official.season_id.astype(str)
official["game_date"] = pd.to_datetime(official.game_date, errors="coerce").dt.normalize()
official["nba_GAME_ID"] = official.nba_GAME_ID.astype(str).str.strip()
official["nba_PLAYER_ID"] = official.nba_PLAYER_ID.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
official["nba_TEAM_ABBREVIATION"] = official.nba_TEAM_ABBREVIATION.astype(str).str.upper().str.strip()
official["target_pdk"] = pd.to_numeric(official.target_pdk, errors="coerce")
official = official.loc[
    official.nba_match_status.eq("matched_player_date_opponent")
    & official.game_date.notna()
    & official.nba_GAME_ID.ne("nan")
    & official.nba_PLAYER_ID.ne("nan")
    & official.target_pdk.notna()
].copy()
keys = ["PLAYER_ID", "GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION"]
team_logs = pd.read_parquet(TEAM_PATH)
team_logs["GAME_DATE"] = pd.to_datetime(team_logs["GAME_DATE"], errors="coerce")

def normalize_id(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

def prepare_logs(path: Path, sid: str, season: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    logs = pd.read_parquet(path)
    required = set(keys + ["PLAYER_NAME", "WL", "PTS", "MIN", "FGM", "FGA", "FG3M", "FTM", "FTA",
        "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PLUS_MINUS", "GAME_DATE", "MATCHUP"])
    missing = sorted(required - set(logs.columns))
    if missing:
        raise RuntimeError(f"{season} logs missing columns: {missing}")
    logs = logs.copy()
    logs["PLAYER_ID"] = normalize_id(logs["PLAYER_ID"])
    logs["GAME_ID"] = normalize_id(logs["GAME_ID"])
    logs["GAME_DATE"] = pd.to_datetime(logs["GAME_DATE"], errors="coerce").dt.normalize()
    logs["TEAM_ABBREVIATION"] = logs["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    logs["PLAYER_NAME"] = logs["PLAYER_NAME"].astype(str).str.strip()
    for stat in ["PTS", "MIN", "FGM", "FGA", "FG3M", "FTM", "FTA", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PLUS_MINUS", "BLKA"]:
        if stat not in logs:
            logs[stat] = 0.0
        logs[stat] = pd.to_numeric(logs[stat], errors="coerce").fillna(0.0)
    logs["PDK"] = logs.apply(
        lambda row: pdk_from_boxscore_row(row, str(row.get("WL", "")).strip().upper() == "W"),
        axis=1,
    )
    lab = official.loc[official.season_id.eq(sid), [
        "game_date", "nba_GAME_ID", "nba_PLAYER_ID", "nba_TEAM_ABBREVIATION", "target_pdk"
    ]].copy()
    lab = lab.rename(columns={
        "game_date": "GAME_DATE", "nba_GAME_ID": "GAME_ID", "nba_PLAYER_ID": "PLAYER_ID",
        "nba_TEAM_ABBREVIATION": "TEAM_ABBREVIATION", "target_pdk": "PDK_OFFICIAL_VALID",
    })
    lab["PLAYER_ID"] = normalize_id(lab["PLAYER_ID"])
    lab["GAME_ID"] = normalize_id(lab["GAME_ID"])
    lab["GAME_DATE"] = pd.to_datetime(lab["GAME_DATE"], errors="coerce").dt.normalize()
    lab["TEAM_ABBREVIATION"] = lab["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    if lab.duplicated(keys).any():
        raise RuntimeError(f"Official labels duplicate NBA identity keys for {season}.")
    logs = logs.merge(lab[keys + ["PDK_OFFICIAL_VALID"]], on=keys, how="left", validate="one_to_one")
    logs["PDK_OFFICIAL_VALID"] = pd.to_numeric(logs["PDK_OFFICIAL_VALID"], errors="coerce")
    n_official = int(logs["PDK_OFFICIAL_VALID"].notna().sum())
    expected = int(official.loc[official.season_id.eq(sid), "target_pdk"].notna().sum())
    if n_official < 1000:
        raise RuntimeError(f"{season}: only {n_official} official labels attached.")
    official_history = logs.copy()
    official_history["PDK"] = official_history["PDK_OFFICIAL_VALID"].where(
        official_history["PDK_OFFICIAL_VALID"].notna(), official_history["PDK"]
    )
    audit = {
        "season_id": sid, "season": season, "nba_log_rows": len(logs),
        "official_labels_attached": n_official, "official_source_rows": expected,
        "official_label_coverage_of_source": n_official / expected if expected else None,
        "proxy_pdk_rows": int(logs["PDK"].notna().sum()),
    }
    return logs, official_history, audit

def score_rows(mode: str, season: str, logs: pd.DataFrame) -> tuple[dict, pd.DataFrame, dict]:
    settings = Settings(
        season=season, feature_season=season, training_target="target_pdk_official",
        data_dir=str(DATA), use_schedule=True, use_matchup=True, use_injuries=False,
    )
    print(f"[{season}] build {mode} features", flush=True)
    feats = build_feature_matrix(settings, logs, team_logs, injuries=pd.DataFrame(),
                                 schedule=None, team_overrides={}, target_gameweek=None)
    official_y = pd.to_numeric(feats.get("target_pdk_official"), errors="coerce")
    count = int(official_y.notna().sum())
    if count < 1000:
        raise RuntimeError(f"{season} {mode}: only {count} official target rows after feature build.")
    print(f"[{season}] train {mode} model stack ({count:,} official labels)", flush=True)
    models, oof = train_models(settings, feats, target_column="target_pdk_official")
    y = official_y.loc[oof.index]
    valid = oof.notna() & y.notna() & np.isfinite(oof.to_numpy(dtype=float, na_value=np.nan))
    idx = oof.index[valid]
    actual = y.loc[idx].to_numpy(float)
    pred = oof.loc[idx].to_numpy(float)
    err = pred - actual
    metrics = {
        "season": season, "mode": mode, "n_official_labels": count, "n_oof": len(actual),
        "mae": float(mean_absolute_error(actual, pred)),
        "rmse": float(np.sqrt(mean_squared_error(actual, pred))),
        "bias_pred_minus_actual": float(err.mean()),
        "within_3_pdk_pct": float((np.abs(err) <= 3).mean() * 100),
        "within_5_pdk_pct": float((np.abs(err) <= 5).mean() * 100),
        "model_weights": json.dumps(models.get("_weights", {}), sort_keys=True),
        "projection_weights": json.dumps(models.get("_projection_weights", {}), sort_keys=True),
    }
    out = pd.DataFrame({
        "season": season, "mode": mode,
        "player_name": feats.loc[idx, "PLAYER_NAME"].astype(str).to_numpy(),
        "game_date": pd.to_datetime(feats.loc[idx, "GAME_DATE"], errors="coerce").dt.strftime("%Y-%m-%d").to_numpy(),
        "game_id": feats.loc[idx, "NBA_GAME_ID"].astype(str).to_numpy(),
        "actual_pdk_official": actual, "predicted_pdk_oof": pred,
        "error": err, "abs_error": np.abs(err),
        "history_games": pd.to_numeric(feats.loc[idx, "n_games"], errors="coerce").to_numpy(),
    })
    feat_audit = {
        "rows": len(feats), "official_targets": count,
        "feature_source_proxy_rows": int(pd.to_numeric(logs["PDK"], errors="coerce").notna().sum()),
        "feature_source_official_rows": int(pd.to_numeric(logs["PDK_OFFICIAL_VALID"], errors="coerce").notna().sum()),
    }
    print(f"[{season}] finished {mode}: n={len(actual):,}, MAE={metrics['mae']:.4f}", flush=True)
    return metrics, out, feat_audit

all_metrics, all_preds, season_audit = [], [], {}
for sid, season, path in SEASONS:
    proxy_logs, official_logs, source_audit = prepare_logs(path, sid, season)
    season_audit[season] = {"source": source_audit}
    for mode, logs in (("proxy_history", proxy_logs), ("official_history_with_proxy_fallback", official_logs)):
        metrics, preds, feat_audit = score_rows(mode, season, logs)
        all_metrics.append(metrics)
        all_preds.append(preds)
        season_audit[season][mode] = feat_audit
metrics_df = pd.DataFrame(all_metrics)
pred_df = pd.concat(all_preds, ignore_index=True)
wide = pred_df.pivot_table(
    index=["season","player_name","game_date","game_id","actual_pdk_official"],
    columns="mode", values="abs_error", aggfunc="first"
).dropna().reset_index()
wide["delta_official_minus_proxy"] = (
    wide["official_history_with_proxy_fallback"] - wide["proxy_history"]
)
validation_seasons = [s for s in ["2021-22","2022-23","2023-24","2024-25"] if s in set(wide.season)]
rng = np.random.default_rng(20261013)
B = 5000
boot_by_season = {}
for season in validation_seasons:
    sub = wide[wide.season.eq(season)]
    clusters = sub.game_date.unique()
    groups = [np.flatnonzero(sub.game_date.to_numpy() == c) for c in clusters]
    vals = sub.delta_official_minus_proxy.to_numpy(float)
    reps = np.empty(B)
    for b in range(B):
        pick = rng.integers(0, len(groups), size=len(groups))
        reps[b] = vals[np.concatenate([groups[i] for i in pick])].mean()
    boot_by_season[season] = reps
macro_boot = np.mean(np.vstack([boot_by_season[s] for s in validation_seasons]), axis=0)
macro_delta = float(np.mean([
    wide.loc[wide.season.eq(s), "delta_official_minus_proxy"].mean() for s in validation_seasons
]))
paired = {
    "validation_seasons": validation_seasons,
    "paired_rows_validation": int(wide.season.isin(validation_seasons).sum()),
    "delta_mae_official_minus_proxy_macro_season": macro_delta,
    "ci95_macro_season": [float(np.quantile(macro_boot,.025)), float(np.quantile(macro_boot,.975))],
    "bootstrap_fraction_official_better": float(np.mean(macro_boot < 0)),
    "bootstrap_replicates": B, "resampling_unit": "whole game date within each held-out season",
    "secondary_2025_26_delta_mae": float(wide.loc[wide.season.eq("2025-26"), "delta_official_minus_proxy"].mean())
        if wide.season.eq("2025-26").any() else None,
    "per_season_delta_mae": {s: float(wide.loc[wide.season.eq(s),"delta_official_minus_proxy"].mean())
        for s in sorted(wide.season.unique())},
}
metrics_df.to_csv(METRICS, index=False)
pred_df.to_csv(PRED, index=False)
audit = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "protocol": "Per-season chronological OOF using the production feature builder and train_models. Same official supervised labels in both arms. Challenger changes only the PDK history/baseline source to official valid PDK where available, retaining the NBA-derived proxy elsewhere.",
    "source_audit": season_audit, "metrics": metrics_df.to_dict("records"),
    "paired_bootstrap": paired, "production_changed": False,
    "limitations": [
        "This is a within-season temporal OOF ablation, not a project-wide untouched season holdout.",
        "2025/26 is descriptive only and excluded from validation feature-selection bootstrap because it has already been inspected by other experiments.",
        "The internal OOF trainer has fold-local model weights, but its own Ridge tuning protocol and projection calibration are part of the production code under test.",
        "Game-level metrics do not establish better lineup, coach, injury, or transfer-malus decisions."
    ],
    "outputs": {"metrics": str(METRICS.relative_to(ROOT)), "predictions": str(PRED.relative_to(ROOT)),
                "audit": str(AUDIT.relative_to(ROOT)), "report": str(REPORT.relative_to(ROOT))}
}
AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str)+"\n", encoding="utf-8")
lines = [
    "# Multi-season production PDK history-source ablation", "",
    f"Generated UTC: {audit['generated_at_utc']}", "",
    "## Protocol", "",
    "- Seasons: 2021/22–2025/26. Each season is evaluated with its own expanding chronological OOF folds using the production feature builder and model trainer.",
    "- Both arms use identical verified official PDK target labels.",
    "- Proxy arm uses NBA-boxscore PDK for rolling features/baselines.",
    "- Challenger uses official Dunkest PDK for rolling features wherever a verified match exists, with proxy fallback for unmatched NBA games.",
    "- 2025/26 is descriptive only and excluded from the validation-season bootstrap.",
    "- Production files/configuration and raw datasets were not modified.", "",
    "## Metrics by season and feature source", "", metrics_df.to_string(index=False), "",
    "## Paired validation bootstrap", "",
    f"- Validation seasons: {', '.join(validation_seasons)}.",
    f"- Paired validation rows: {paired['paired_rows_validation']:,}.",
    f"- Macro-season delta MAE (official-history minus proxy-history): {macro_delta:.4f}.",
    f"- 95% date-cluster bootstrap interval: [{paired['ci95_macro_season'][0]:.4f}, {paired['ci95_macro_season'][1]:.4f}].",
    f"- Bootstrap fraction favoring official history: {paired['bootstrap_fraction_official_better']:.4f}.",
    f"- Secondary 2025/26 delta MAE: {paired['secondary_2025_26_delta_mae']}.", "",
    "## Decision", "",
    "Promote official PDK history only if the validation-season improvement is consistent and the confidence interval supports it. The 2025/26 secondary fold is not used to choose the change, and the frozen 2026/27 GW1 run remains untouched.", "",
    "## Limitations", "",
    *[f"- {x}" for x in audit["limitations"]], "",
    "## Artifacts", "",
    f"- Metrics: {METRICS.relative_to(ROOT)}",
    f"- Predictions: {PRED.relative_to(ROOT)}",
    f"- Audit JSON: {AUDIT.relative_to(ROOT)}", ""
]
REPORT.write_text("\n".join(lines), encoding="utf-8")
print(json.dumps({"status":"completed","metrics":metrics_df.to_dict("records"),"paired_bootstrap":paired,
                  "artifacts":[str(p.relative_to(ROOT)) for p in (METRICS,PRED,AUDIT,REPORT)]}, indent=2, default=str))
