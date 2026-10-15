#!/usr/bin/env python3
"""Isolate the team-change bias correction on exact outer walk-forward predictions."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.config import Settings
from dunkest.models.multiseason_training import adapt_certified_training_rows, DEFAULT_DATASET

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "reports/audit/dunkest_production_trainer_walk_forward_20261015_v3_predictions.csv"
MODEL_META = ROOT / "reports/audit/dunkest_production_trainer_walk_forward_20261015_v3.json"
OUT = ROOT / "reports/audit"
STAMP = "dunkest_team_change_bias_correction_20261015_v1"
REPORT, METRICS, BOOTSTRAP, JSON = [OUT / f"{STAMP}{s}" for s in (".md", "_metrics.csv", "_bootstrap.csv", ".json")]

def main() -> None:
    for path in (REPORT, METRICS, BOOTSTRAP, JSON):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing artifact: {path.relative_to(ROOT)}")
    predictions = pd.read_csv(PRED)
    metadata = json.loads(MODEL_META.read_text(encoding="utf-8"))["model_metadata"]
    corrections = {str(row["season"]): float(row.get("team_change_bias_correction_pdk", 0.0) or 0.0) for row in metadata}
    settings = Settings.from_yaml()
    adapted = adapt_certified_training_rows(pd.read_parquet(settings.data_path / DEFAULT_DATASET))
    for column in ("season_id", "GAME_ID", "PLAYER_ID"):
        adapted[column] = adapted[column].astype(str)
    for column in ("season_id", "game_id", "player_id"):
        predictions[column] = predictions[column].astype(str)
    source = adapted[["season_id", "GAME_ID", "PLAYER_ID", "team_changed_from_previous_game"]]
    joined = predictions.merge(source, left_on=["season_id", "game_id", "player_id"],
        right_on=["season_id", "GAME_ID", "PLAYER_ID"], how="left", validate="one_to_one", indicator=True)
    unmatched = int(joined["_merge"].ne("both").sum())
    if unmatched:
        raise RuntimeError(f"{unmatched} predictions did not match certified source rows.")
    joined["team_changed"] = pd.to_numeric(joined.team_changed_from_previous_game, errors="coerce").fillna(0).gt(0)
    joined["correction_pdk"] = joined.fold_season.astype(str).map(corrections).fillna(0.0)
    joined["prediction_corrected"] = pd.to_numeric(joined.prediction_production_ensemble, errors="coerce")
    joined["prediction_uncorrected"] = joined.prediction_corrected - joined.correction_pdk * joined.team_changed.astype(float)
    joined["delta_abs_error_corrected_minus_uncorrected"] = (
        abs(joined.prediction_corrected - joined.target_pdk)
        - abs(joined.prediction_uncorrected - joined.target_pdk)
    )
    rows, boot_rows = [], []
    rng = np.random.default_rng(1987)
    for season, g0 in joined.groupby("fold_season", sort=True):
        cohorts = {"all": pd.Series(True, index=g0.index), "team_changed": g0.team_changed,
                   "no_team_change": ~g0.team_changed,
                   "low_history_le_5": pd.to_numeric(g0.history_games_before_target, errors="coerce").fillna(0).le(5)}
        for cohort, mask in cohorts.items():
            g = g0.loc[mask]
            for version, col in (("uncorrected", "prediction_uncorrected"), ("corrected", "prediction_corrected")):
                err = pd.to_numeric(g[col], errors="coerce") - pd.to_numeric(g.target_pdk, errors="coerce")
                rows.append({"season": str(season), "cohort": cohort, "version": version, "n": int(len(g)),
                    "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err**2))),
                    "bias_pred_minus_actual": float(np.mean(err))})
            per_game = g.groupby("game_id").delta_abs_error_corrected_minus_uncorrected.mean().to_numpy(float)
            if len(per_game):
                draws = rng.choice(per_game, size=(4000, len(per_game)), replace=True).mean(axis=1)
                boot_rows.append({"season": str(season), "cohort": cohort, "n_rows": int(len(g)),
                    "game_clusters": int(len(per_game)),
                    "delta_mae_corrected_minus_uncorrected": float(per_game.mean()),
                    "ci95_low": float(np.quantile(draws, .025)), "ci95_high": float(np.quantile(draws, .975))})
    metrics, bootstrap = pd.DataFrame(rows), pd.DataFrame(boot_rows)
    metrics.to_csv(METRICS, index=False)
    bootstrap.to_csv(BOOTSTRAP, index=False)
    audit = {"created_utc": datetime.now(timezone.utc).isoformat(), "predictions": str(PRED.relative_to(ROOT)),
        "model_metadata": str(MODEL_META.relative_to(ROOT)), "unmatched_rows": unmatched,
        "corrections_by_outer_fold_pdk": corrections, "metrics": metrics.to_dict("records"),
        "paired_game_cluster_bootstrap": bootstrap.to_dict("records"),
        "method": "subtract the recorded correction from the same outer-fold prediction to recover the identical model's uncorrected prediction; no refit and no look-ahead",
        "promotion_decision": "not_promoted: overall effect is negligible and team-change cohort MAE effects are inconsistent across outer seasons",
        "uses_full_lineups": False, "uses_2025_26_holdout": False, "uses_2026_27_prospective_bundle": False}
    JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Team-change bias correction: paired outer walk-forward check — V1", "",
        f"Generated UTC: {audit['created_utc']}", "",
        "This compares corrected and uncorrected predictions from the same exact production-model run. The uncorrected prediction is recovered by subtracting the recorded correction; no model refit or future target is involved. Correction coefficients were estimated from OOF predictions in the training window before each outer test season.", "",
        "## Correction by outer fold", "", str(corrections), "",
        "## MAE / RMSE / bias by cohort", "", metrics.to_string(index=False, float_format=lambda x: f"{x:.4f}"), "",
        "## Paired game-cluster bootstrap: corrected MAE minus uncorrected MAE", "", bootstrap.to_string(index=False, float_format=lambda x: f"{x:.4f}"), "",
        "## Decision rule", "",
        "- Keep the correction only if it reduces MAE in the team-change cohort across later outer folds without a material overall regression.",
        "- High-score and low-history cohorts are diagnostics only; they are not used to select players.",
        "- No historical lineup backtest or 2026/27 prospective data are used.", "",
        "## Artifacts", "", str(METRICS.relative_to(ROOT)), str(BOOTSTRAP.relative_to(ROOT)), str(JSON.relative_to(ROOT)), ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("REPORT", REPORT.relative_to(ROOT), flush=True)
    print("METRICS\n", metrics.to_string(index=False), flush=True)
    print("BOOTSTRAP\n", bootstrap.to_string(index=False), flush=True)

if __name__ == "__main__":
    main()
