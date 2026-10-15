#!/usr/bin/env python3
"""Compare proxy-target and official-target training on identical 2025/26 rows.

Isolated experiment only: no production model/config changes and no saved model.
Both models use the same pre-game features and chronological OOF cutoffs; metrics
are evaluated against official PDK on the intersection of OOF predictions.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from dunkest.config import Settings
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import train_models

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
LOGS_PATH = PROCESSED / "player_game_logs_2025-26_official_pdk_overlay_v4.parquet"
TEAM_LOGS_PATH = PROCESSED / "team_game_logs_2025-26.parquet"
OUT_DIR = ROOT / "reports" / "audit"
PREDICTIONS_PATH = OUT_DIR / "proxy_vs_official_target_oof_2025-26_v1.csv"
METRICS_PATH = OUT_DIR / "proxy_vs_official_target_comparison_2025-26_v1.json"
REPORT_PATH = OUT_DIR / "proxy_vs_official_target_comparison_2025-26_v1.md"


def score_metrics(actual: pd.Series, pred: pd.Series, name: str) -> dict:
    valid = actual.notna() & pred.notna() & np.isfinite(actual) & np.isfinite(pred)
    y = actual.loc[valid].astype(float)
    p = pred.loc[valid].astype(float)
    if y.empty:
        return {"model": name, "n": 0}
    return {
        "model": name,
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "bias_pred_minus_actual": float((p - y).mean()),
        "r2": float(r2_score(y, p)) if len(y) > 1 else None,
        "p90_absolute_error": float(np.quantile(np.abs(p - y), 0.90)),
    }


def main() -> None:
    for path in (PREDICTIONS_PATH, METRICS_PATH, REPORT_PATH):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing output: {path}")
    for path in (LOGS_PATH, TEAM_LOGS_PATH):
        if not path.exists():
            raise SystemExit(f"Required input is missing: {path}")

    logs = pd.read_parquet(LOGS_PATH)
    team_logs = pd.read_parquet(TEAM_LOGS_PATH)
    required = {
        "PLAYER_NAME", "GAME_DATE", "GAME_ID", "TEAM_ABBREVIATION", "PDK",
        "PDK_OFFICIAL_VALID", "gameValidForDunkest", "MIN",
    }
    if not required.issubset(logs.columns):
        raise SystemExit(f"Missing source columns: {sorted(required - set(logs.columns))}")
    official_finite = pd.to_numeric(logs["PDK_OFFICIAL_VALID"], errors="coerce").notna()
    if not logs.loc[official_finite, "gameValidForDunkest"].eq(True).all():
        raise SystemExit("Official labels exist on a row not marked gameValidForDunkest=True.")

    settings = Settings.from_yaml(
        use_schedule=False,
        use_injuries=False,
        use_matchup=True,
        training_target="target_pdk",
    )
    features = build_feature_matrix(
        settings,
        logs,
        team_logs,
        injuries=pd.DataFrame(),
        schedule=pd.DataFrame(),
        target_gameweek=settings.target_gameweek,
    )
    inference = features.get("is_inference", pd.Series(False, index=features.index)).fillna(False).astype(bool)
    features = features.loc[~inference].copy()
    features["GAME_DATE"] = pd.to_datetime(features["GAME_DATE"], errors="coerce")
    for column in ("target_pdk", "target_pdk_official"):
        features[column] = pd.to_numeric(features[column], errors="coerce")
    sample = features.loc[
        features["target_pdk"].notna() & features["target_pdk_official"].notna()
    ].copy()
    if sample.empty:
        raise SystemExit("No common rows have both proxy and official PDK labels.")
    identity = ["PLAYER_NAME", "GAME_DATE", "NBA_GAME_ID", "TEAM_ABBREVIATION"]
    if sample.duplicated(identity).any():
        raise SystemExit("Duplicate player/game identities in the common comparison sample.")
    if sample["target_pdk_official"].isna().any() or sample["target_pdk"].isna().any():
        raise SystemExit("Unexpected null target after common-row filtering.")

    # Explicit targets bypass the production auto-selector; this is deliberately
    # an isolated comparison and does not write a production model artifact.
    proxy_models, proxy_oof = train_models(settings, sample, target_column="target_pdk")
    official_models, official_oof = train_models(settings, sample, target_column="target_pdk_official")
    del proxy_models, official_models

    common = sample.copy()
    common["oof_pred_trained_on_proxy"] = proxy_oof.reindex(common.index)
    common["oof_pred_trained_on_official"] = official_oof.reindex(common.index)
    common = common.loc[
        common["oof_pred_trained_on_proxy"].notna()
        & common["oof_pred_trained_on_official"].notna()
        & common["target_pdk_official"].notna()
    ].copy()
    if common.empty:
        raise SystemExit("The two target modes have no common out-of-fold rows.")

    actual_official = common["target_pdk_official"]
    metrics = [
        score_metrics(actual_official, common["oof_pred_trained_on_proxy"], "model_trained_on_proxy_target__evaluated_vs_official"),
        score_metrics(actual_official, common["oof_pred_trained_on_official"], "model_trained_on_official_target__evaluated_vs_official"),
        score_metrics(common["target_pdk"], common["oof_pred_trained_on_proxy"], "model_trained_on_proxy_target__evaluated_vs_proxy"),
        score_metrics(actual_official, common["pdk_mean_10"], "baseline_proxy_previous_10_mean__evaluated_vs_official"),
        score_metrics(actual_official, common["expected_pdk_minutes_model"], "baseline_minutes_projection__evaluated_vs_official"),
    ]
    target_delta = common["target_pdk_official"] - common["target_pdk"]
    cohort_rows = []
    bins = [(-np.inf, 5, "<5"), (5, 10, "5-10"), (10, 20, "10-20"), (20, 30, "20-30"), (30, np.inf, "30+")]
    for lower, upper, label in bins:
        mask = common["target_pdk_official"].ge(lower) & common["target_pdk_official"].lt(upper)
        if not mask.any():
            continue
        for prediction_col, model_name in (("oof_pred_trained_on_proxy", "trained_on_proxy"), ("oof_pred_trained_on_official", "trained_on_official")):
            row = score_metrics(common.loc[mask, "target_pdk_official"], common.loc[mask, prediction_col], model_name)
            row["official_target_band"] = label
            cohort_rows.append(row)

    out_cols = identity + [
        "OPPONENT", "is_home", "target_pdk", "target_pdk_official",
        "pdk_mean_10", "expected_pdk_minutes_model",
        "oof_pred_trained_on_proxy", "oof_pred_trained_on_official",
    ]
    predictions = common[[c for c in out_cols if c in common.columns]].copy()
    predictions["GAME_DATE"] = predictions["GAME_DATE"].dt.strftime("%Y-%m-%d")
    predictions.to_csv(PREDICTIONS_PATH, index=False)

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "season": "2025-26",
        "inputs": {"player_logs_with_official_overlay": str(LOGS_PATH), "team_logs": str(TEAM_LOGS_PATH)},
        "feature_policy": "Same production feature builder and feature whitelist for both target modes; current-game target columns are excluded from FEATURE_COLS. PDK rolling features are based on prior proxy PDK values in both arms.",
        "target_policy": "Compare explicit target_pdk vs target_pdk_official on identical rows where both labels are finite; all official labels must have gameValidForDunkest=True.",
        "validation_policy": "Use train_models' identical date-ordered out-of-fold cutoffs; evaluate both predictions on the intersection of rows with finite predictions from both arms, against official PDK for the primary comparison.",
        "counts": {
            "source_player_log_rows": int(len(logs)),
            "source_official_label_rows": int(official_finite.sum()),
            "common_rows_before_oof": int(len(sample)),
            "common_oof_rows": int(len(common)),
            "unique_oof_dates": int(common["GAME_DATE"].nunique()),
            "oof_date_min": common["GAME_DATE"].min().strftime("%Y-%m-%d"),
            "oof_date_max": common["GAME_DATE"].max().strftime("%Y-%m-%d"),
            "duplicate_player_game_identities": int(common.duplicated(identity).sum()),
        },
        "proxy_minus_official_target_delta": {
            "mean": float((common["target_pdk"] - common["target_pdk_official"]).mean()),
            "mae": float(np.abs(target_delta).mean()),
            "rmse": float(np.sqrt(np.mean(np.square(target_delta)))),
            "p90_absolute_difference": float(np.quantile(np.abs(target_delta), 0.90)),
        },
        "metrics": metrics,
        "cohort_metrics_by_official_target_band": cohort_rows,
        "outputs": [str(PREDICTIONS_PATH), str(METRICS_PATH), str(REPORT_PATH)],
        "limitations": [
            "This is an isolated within-season temporal OOF comparison, not a full expanding-season evaluation.",
            "It isolates the target choice while holding the production feature builder fixed; proxy-trained predictions are evaluated against official PDK to measure their usefulness for the official target.",
            "Both arms use proxy-derived historical PDK features. The separate historical V3 model uses official-target lags, so its metrics should not be directly combined with this comparison.",
            "No production config, code path, source parquet, saved model, temporal split, or backtest was changed.",
        ],
    }
    METRICS_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Proxy-target vs official-target training — 2025/26 (v1)", "",
        f"- Common labelled rows before OOF: **{len(sample):,}**",
        f"- Identical OOF evaluation rows: **{len(common):,}** across {common['GAME_DATE'].nunique()} dates ({common['GAME_DATE'].min():%Y-%m-%d} to {common['GAME_DATE'].max():%Y-%m-%d})",
        "- Evaluation target: official PDK, restricted to rows with a verified official label and `gameValidForDunkest=True`.",
        "", "## Main comparison", "", "| Model/predictor | N | MAE vs official | RMSE vs official | Bias | R² | P90 absolute error |", "|---|---:|---:|---:|---:|---:|---:|"
    ]
    for m in metrics:
        if m["model"].endswith("evaluated_vs_proxy"):
            continue
        lines.append(f"| {m['model']} | {m['n']} | {m['mae']:.4f} | {m['rmse']:.4f} | {m['bias_pred_minus_actual']:.4f} | {m['r2']:.4f} | {m['p90_absolute_error']:.4f} |")
    lines += ["", "## Error by official target band", "", "| Official PDK band | Model | N | MAE | RMSE | Bias |", "|---|---|---:|---:|---:|---:|"]
    for m in cohort_rows:
        lines.append(f"| {m['official_target_band']} | {m['model']} | {m['n']} | {m['mae']:.4f} | {m['rmse']:.4f} | {m['bias_pred_minus_actual']:.4f} |")
    lines += ["", "## Label difference", "", f"- Mean proxy-minus-official difference: **{report['proxy_minus_official_target_delta']['mean']:.4f} PDK**", f"- MAE between proxy and official labels: **{report['proxy_minus_official_target_delta']['mae']:.4f} PDK**", f"- RMSE between proxy and official labels: **{report['proxy_minus_official_target_delta']['rmse']:.4f} PDK**", f"- P90 absolute label difference: **{report['proxy_minus_official_target_delta']['p90_absolute_difference']:.4f} PDK**", "", "## Limits and safety", "", "This experiment uses identical chronological OOF cutoffs and the same official-valid rows for both target modes. It isolates target choice under the production feature builder, so both arms use proxy-derived lag features. It is not a full multi-season validation and does not alter production configuration, model artefacts, source data, or existing backtests.", ""]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "metrics": metrics, "target_delta": report["proxy_minus_official_target_delta"], "outputs": report["outputs"]}, indent=2))


if __name__ == "__main__":
    main()
