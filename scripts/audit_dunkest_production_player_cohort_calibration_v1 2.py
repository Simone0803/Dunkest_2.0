#!/usr/bin/env python3
"""Cohort-level diagnostics for the exact production player-forecast walk-forward."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.config import Settings
from dunkest.models.multiseason_training import adapt_certified_training_rows, DEFAULT_DATASET
from dunkest.names import player_key

ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS = ROOT / "reports/audit/dunkest_production_trainer_walk_forward_20261014_v1_predictions.csv"
ROOKIE_LABELS = ROOT / "data/rookie_official_pdk.csv"
OUT = ROOT / "reports/audit"
STAMP = "dunkest_production_player_cohort_calibration_20261015_v1"
METRICS = OUT / f"{STAMP}_metrics.csv"
CALIBRATION = OUT / f"{STAMP}_prediction_bands.csv"
REPORT = OUT / f"{STAMP}.md"
AUDIT = OUT / f"{STAMP}.json"

def score(g: pd.DataFrame, pred_col: str = "prediction_production_ensemble") -> dict:
    y = pd.to_numeric(g.target_pdk, errors="coerce").to_numpy(float)
    p = pd.to_numeric(g[pred_col], errors="coerce").to_numpy(float)
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    err = p - y
    return {"n": int(len(y)), "mae": float(np.mean(np.abs(err))) if len(err) else np.nan,
            "rmse": float(np.sqrt(np.mean(err ** 2))) if len(err) else np.nan,
            "bias_pred_minus_actual": float(np.mean(err)) if len(err) else np.nan,
            "mean_predicted": float(np.mean(p)) if len(err) else np.nan,
            "mean_actual": float(np.mean(y)) if len(err) else np.nan}

def main() -> None:
    for path in (METRICS, CALIBRATION, REPORT, AUDIT):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing artifact: {path.relative_to(ROOT)}")
    settings = Settings.from_yaml()
    source_path = settings.data_path / DEFAULT_DATASET
    adapted = adapt_certified_training_rows(pd.read_parquet(source_path))
    required = ["season_id", "GAME_ID", "PLAYER_ID", "GAME_DATE", "PLAYER_NAME",
                "target_pdk_official", "history_games_before_target",
                "team_changed_from_previous_game", "nba_PLAYER_ID"]
    missing = sorted(set(required) - set(adapted.columns))
    if missing:
        raise RuntimeError(f"Production-adapted data lacks cohort keys: {missing}")
    adapted["season_id"] = adapted.season_id.astype(str)
    adapted["GAME_ID"] = adapted.GAME_ID.astype(str)
    adapted["PLAYER_ID"] = adapted.PLAYER_ID.astype(str)
    adapted["player_key"] = adapted.PLAYER_NAME.map(player_key)
    adapted["season_start_year"] = pd.to_numeric(adapted.season_label.astype(str).str.slice(0, 4), errors="coerce").astype("Int64")
    rookie = pd.read_csv(ROOKIE_LABELS)
    rookie["player_key"] = rookie["player_key"].astype(str)
    rookie["draft_year"] = pd.to_numeric(rookie.draft_year, errors="coerce").astype("Int64")
    rookie_keys = rookie[["player_key", "draft_year"]].dropna().drop_duplicates()
    adapted = adapted.merge(rookie_keys.assign(official_draft_class_rookie=True),
        left_on=["player_key", "season_start_year"], right_on=["player_key", "draft_year"],
        how="left", validate="many_to_one")
    adapted["official_draft_class_rookie"] = adapted.official_draft_class_rookie.fillna(False).astype(bool)
    preds = pd.read_csv(PREDICTIONS)
    preds["season_id"] = preds.season_id.astype(str)
    preds["game_id"] = preds.game_id.astype(str)
    preds["player_id"] = preds.player_id.astype(str)
    joined = preds.merge(adapted[["season_id", "GAME_ID", "PLAYER_ID", "team_changed_from_previous_game",
        "official_draft_class_rookie", "nba_PLAYER_ID", "nba_TEAM_ABBREVIATION"]],
        left_on=["season_id", "game_id", "player_id"], right_on=["season_id", "GAME_ID", "PLAYER_ID"],
        how="left", validate="one_to_one", indicator=True)
    unmatched = int(joined["_merge"].ne("both").sum())
    if unmatched:
        raise RuntimeError(f"{unmatched} production predictions failed to join to their certified source rows.")
    joined = joined.drop(columns=["_merge", "GAME_ID", "PLAYER_ID"])
    joined["team_changed_from_previous_game"] = pd.to_numeric(joined.team_changed_from_previous_game, errors="coerce").fillna(0).astype(bool)
    joined["low_history_le_5"] = pd.to_numeric(joined.history_games_before_target, errors="coerce").fillna(0).le(5)
    joined["actual_ge25"] = pd.to_numeric(joined.target_pdk, errors="coerce").ge(25)
    joined["actual_ge30"] = pd.to_numeric(joined.target_pdk, errors="coerce").ge(30)
    cohorts = {
        "all": pd.Series(True, index=joined.index),
        "official_draft_class_rookie": joined.official_draft_class_rookie,
        "low_history_le_5": joined.low_history_le_5,
        "history_gt_5": ~joined.low_history_le_5,
        "team_changed_from_previous_nba_game": joined.team_changed_from_previous_game,
        "no_team_change_from_previous_nba_game": ~joined.team_changed_from_previous_game,
        "actual_pdk_ge25": joined.actual_ge25,
        "actual_pdk_ge30": joined.actual_ge30,
    }
    rows = []
    for fold, g in joined.groupby("fold_season", sort=True):
        for cohort, mask in cohorts.items():
            part = g.loc[mask.reindex(g.index, fill_value=False)]
            rows.append({"fold_season": str(fold), "cohort": cohort, "candidate": "production_ensemble", **score(part)})
            baseline = part.loc[pd.to_numeric(part.baseline_prev10, errors="coerce").notna()]
            if not baseline.empty:
                rows.append({"fold_season": str(fold), "cohort": cohort, "candidate": "baseline_prev10", **score(baseline, "baseline_prev10")})
    joined["prediction_band"] = pd.cut(pd.to_numeric(joined.prediction_production_ensemble, errors="coerce"),
        bins=[-np.inf, 5, 10, 15, 20, 25, np.inf], labels=["<5", "5-10", "10-15", "15-20", "20-25", "25+"], right=False)
    band_rows = []
    for (fold, band), g in joined.groupby(["fold_season", "prediction_band"], observed=False, dropna=False):
        if pd.isna(band):
            continue
        m = score(g)
        band_rows.append({"fold_season": str(fold), "prediction_band": str(band), **m, "mean_error": m["bias_pred_minus_actual"]})
    metrics, bands = pd.DataFrame(rows), pd.DataFrame(band_rows)
    metrics.to_csv(METRICS, index=False)
    bands.to_csv(CALIBRATION, index=False)
    audit = {"created_utc": datetime.now(timezone.utc).isoformat(),
        "source_predictions": str(PREDICTIONS.relative_to(ROOT)), "source_dataset": str(source_path.relative_to(ROOT)),
        "rookie_labels": str(ROOKIE_LABELS.relative_to(ROOT)), "test_folds": sorted(joined.fold_season.astype(str).unique()),
        "n_predictions": int(len(joined)), "unmatched_source_rows": unmatched,
        "cohort_definitions": {
            "official_draft_class_rookie": "player name key matches the official rookie-label file and draft year equals target season start year",
            "low_history_le_5": "at most five prior observed Dunkest rows; not synonymous with rookie",
            "team_changed_from_previous_nba_game": "production adapter's past-only team transition feature",
            "prediction_bands": "fixed bins of production ensemble point forecast"},
        "metrics": metrics.to_dict("records"), "prediction_bands": bands.to_dict("records"),
        "uses_exact_production_trainer_predictions": True, "uses_historical_full_lineups": False,
        "uses_2025_26_holdout": False, "uses_2026_27_prospective_bundle": False, "production_model_changed": False}
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Production player forecast: cohort and score-band diagnostics — V1", "",
        f"Generated UTC: {audit['created_utc']}", "",
        "This report evaluates individual-player forecasts from the exact production trainer's existing chronological out-of-sample predictions. It is not a historical lineup backtest. The 2025/26 holdout and frozen 2026/27 prospective bundle are excluded.", "",
        "## Cohort metrics", "", metrics.to_string(index=False, float_format=lambda x: f"{x:.4f}"), "",
        "## Prediction-band calibration", "", bands.to_string(index=False, float_format=lambda x: f"{x:.4f}"), "",
        "## Interpretation guardrails", "",
        "- Official draft-class rookie labels require a name-key match and draft year equal to the target season start year; unmatched players are not guessed to be rookies.",
        "- Low-history is a separate proxy cohort and is not called a rookie cohort.",
        "- Team-change cohort comes from the adapter's chronological, past-only team-transition feature.",
        "- High-score cohorts condition on the realized target and diagnose errors; they are not deployable selection features.",
        "- No production model, weights, configuration, historical labels, or frozen prospective bundle was changed.", "",
        "## Artifacts", "", f"- Metrics: {METRICS.relative_to(ROOT)}",
        f"- Prediction-band diagnostics: {CALIBRATION.relative_to(ROOT)}", f"- Audit JSON: {AUDIT.relative_to(ROOT)}", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("COHORT_AUDIT_COMPLETE", len(joined), "rows", "unmatched", unmatched, flush=True)
    print("\nCOHORT METRICS\n", metrics.to_string(index=False), flush=True)
    print("\nPREDICTION BANDS\n", bands.to_string(index=False), flush=True)
    print("REPORT", REPORT.relative_to(ROOT), flush=True)

if __name__ == "__main__":
    main()
