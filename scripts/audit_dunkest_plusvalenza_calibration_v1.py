#!/usr/bin/env python3
"""Audit official plusvalenza coverage and sequential OOF probability calibration."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from dunkest.models.capital_gain import fit_capital_gain_model
from dunkest.data.access import _plusvalenza_season_team_coverage

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/plusvalenza_history_multiseason_26_pre_gw0_5y_nba_v4.parquet"
OUT = ROOT / "reports/audit"
STAMP = "dunkest_plusvalenza_calibration_20261015_v1"
REPORT = OUT / f"{STAMP}.md"
JSON = OUT / f"{STAMP}.json"
SEASON_LABELS = {"5": "2020-21", "7": "2021-22", "9": "2022-23", "13": "2023-24", "19": "2024-25"}

def main() -> None:
    for path in (REPORT, JSON):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing artifact: {path.relative_to(ROOT)}")
    if not DATA.exists():
        raise FileNotFoundError(f"Corrected official history is missing: {DATA.relative_to(ROOT)}")
    history = pd.read_parquet(DATA)
    coverage = _plusvalenza_season_team_coverage(history)
    gameweeks = {str(int(k)): int(v) for k, v in history.groupby("season_id").gameweek.nunique().items()}
    fitted = fit_capital_gain_model(history)
    diag = fitted.get("probability_calibration_diagnostics", {})
    season_diag = diag.get("by_season_id", {})
    season_rows = []
    for season_id, values in season_diag.items():
        season_rows.append({"season_id": season_id, "season": SEASON_LABELS.get(season_id, season_id), **values})
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(DATA.relative_to(ROOT)),
        "source_rows": int(len(history)),
        "model_rows": int(fitted["rows"]),
        "walk_forward_validation_rows": int(fitted["validation_rows"]),
        "season_team_coverage": coverage,
        "gameweeks_by_season_id": gameweeks,
        "excluded_incomplete_seasons": fitted["excluded_incomplete_seasons"],
        "delta_cr_mae": float(fitted["mae"]),
        "delta_cr_baseline_mae": float(fitted["baseline_mae"]),
        "probability_calibration_training_rows": int(fitted.get("probability_calibration_training_rows", 0)),
        "probability_calibration_diagnostics": diag,
        "season_labels": SEASON_LABELS,
        "interpretation": {
            "probability_calibration_scope": "past-only OOF calibration of gain/flat/loss conversion probabilities using observed official PDK as input",
            "not_certified": "end-to-end plusvalenza probabilities from predicted PDK quantiles; historical pre-lock score forecasts are not available in this dataset",
            "data_policy": "official observed Dunkest stats only; no synthetic missing gameweeks or reconstructed CR values",
        },
    }
    JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = [
        "# Plusvalenza history and probability calibration — V1", "",
        f"Generated UTC: {audit['created_utc']}", "",
        "## Official data coverage", "",
        f"- Rows returned by official Dunkest stats endpoint: {len(history):,}",
        f"- Seasons with verified broad NBA-team coverage: {len(coverage)}",
        f"- Distinct teams per season: {coverage}",
        f"- Observed gameweeks per season: { {SEASON_LABELS.get(k, k): v for k, v in gameweeks.items()} }",
        f"- Incomplete seasons excluded from fitting: {fitted['excluded_incomplete_seasons']}",
        "- The previous archive contained non-NBA/partial seasons with only two NBA team codes. The v4 collector now requires at least 28 distinct NBA teams at season discovery and does not reuse those old v3 caches.", "",
        "## ΔCR point forecast", "",
        f"- Training rows after validation: {fitted['rows']:,}",
        f"- Past-only walk-forward validation rows: {fitted['validation_rows']:,}",
        f"- MAE: {fitted['mae']:.6f} CR",
        f"- Training-window-mean baseline MAE: {fitted['baseline_mae']:.6f} CR",
        f"- Mean calibrated OOF residual: {float(pd.Series(fitted['residuals']).mean()):.6f} CR", "",
        "## Gain / flat / loss probability calibration", "",
        f"- Probability calibrator training rows: {fitted.get('probability_calibration_training_rows', 0):,}",
        f"- Sequential past-only OOF rows evaluated after calibration burn-in: {diag.get('n', 0):,}",
        f"- Actual gain rate: {diag.get('actual_gain_rate', float('nan')):.4%}",
        f"- Raw mean gain probability: {diag.get('raw_gain_probability_mean', float('nan')):.4%} (bias {diag.get('raw_gain_bias_percentage_points', float('nan')):+.3f} percentage points)",
        f"- Calibrated mean gain probability: {diag.get('calibrated_gain_probability_mean', float('nan')):.4%} (bias {diag.get('calibrated_gain_bias_percentage_points', float('nan')):+.3f} percentage points)",
        f"- Multiclass Brier: {diag.get('raw_multiclass_brier', float('nan')):.6f} raw → {diag.get('calibrated_multiclass_brier', float('nan')):.6f} calibrated",
        f"- Multiclass log loss: {diag.get('raw_multiclass_log_loss', float('nan')):.6f} raw → {diag.get('calibrated_multiclass_log_loss', float('nan')):.6f} calibrated",
        "",
        "## Per-season sequential calibration", "",
        pd.DataFrame(season_rows).to_string(index=False, float_format=lambda x: f"{x:.5f}") if season_rows else "No season-level diagnostics available.", "",
        "## Limits", "",
        "- The calibration layer is trained only on earlier out-of-fold probability forecasts and observed official plusvalenza outcomes; it does not use the row being evaluated.",
        "- The OOF calibration audit conditions on the observed official PDK score. It validates the CR conversion probabilities, not the full end-to-end probability when PDK itself is uncertain.",
        "- Production still combines this calibrated conversion probability with the score-forecast distribution. End-to-end calibration would require historical pre-lock PDK forecast snapshots; none were fabricated.",
        "- The 2026/27 GW1 prospective bundle was not read, trained on, or tuned.", "",
        "## Artifact", "", str(JSON.relative_to(ROOT)), "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("REPORT", REPORT.relative_to(ROOT), flush=True)
    print("METRICS", json.dumps({k: audit[k] for k in ("source_rows","model_rows","walk_forward_validation_rows","delta_cr_mae","delta_cr_baseline_mae","probability_calibration_training_rows","probability_calibration_diagnostics")}, default=str), flush=True)

if __name__ == "__main__":
    main()
