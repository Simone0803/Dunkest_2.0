#!/usr/bin/env python3
"""Compare simple past-only PDK baselines with a saved multi-season OOS run.

This analysis reuses saved held-out predictions. It does not refit models or
read 2025/26 or prospective 2026/27 evaluation data.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
MINUTES = ROOT / "data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
PREDICTIONS = ROOT / "reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v1_predictions.csv"
STEM = "dunkest_multiseason_temporal_baselines_20261018_v1"
OUT = ROOT / "reports/audit" / STEM
BASELINES = {
    "previous_3_official_pdk_mean": "pdk_mean_3",
    "previous_5_official_pdk_mean": "pdk_mean_5",
    "previous_10_official_pdk_mean": "pdk_mean_10",
    "past_season_official_pdk_mean": "pdk_season_mean",
    "past_official_pdk_per_min_x_previous_5_nba_minutes": None,
}
MODEL_METHOD = "all_prior_seasons_low_history_weighted"
TEST_SEASONS = ("2022-23", "2023-24", "2024-25")
BOOTSTRAP_REPLICATES = 10_000
SEED = 20261018


def score(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    error = predicted - actual
    return {
        "n": int(len(actual)),
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "bias_pred_minus_actual": float(error.mean()),
    }


def date_cluster_bootstrap(frame: pd.DataFrame, rng: np.random.Generator) -> dict[str, object]:
    season_bootstraps = []
    season_deltas: dict[str, float] = {}
    for season, group in frame.groupby("season_label", sort=True):
        day_means = (
            group.groupby("game_date", sort=False)["delta_abs_error_model_minus_baseline"]
            .mean()
            .to_numpy(dtype=float)
        )
        season_deltas[str(season)] = float(group["delta_abs_error_model_minus_baseline"].mean())
        picks = rng.integers(0, len(day_means), size=(BOOTSTRAP_REPLICATES, len(day_means)))
        season_bootstraps.append(day_means[picks].mean(axis=1))
    macro = np.vstack(season_bootstraps).mean(axis=0)
    return {
        "season_deltas_model_minus_baseline": season_deltas,
        "equal_season_macro_delta_model_minus_baseline": float(np.mean(list(season_deltas.values()))),
        "ci95_equal_season_macro": [float(np.quantile(macro, 0.025)), float(np.quantile(macro, 0.975))],
        "bootstrap_fraction_model_lower_mae": float(np.mean(macro < 0.0)),
    }


def main() -> None:
    outputs = [OUT.with_suffix(".json"), OUT.with_suffix(".md"), OUT.with_name(OUT.name + "_metrics.csv")]
    if any(path.exists() for path in outputs):
        raise SystemExit(f"Refusing to overwrite versioned outputs for {STEM}.")
    for path in (DATASET, MINUTES, PREDICTIONS):
        if not path.is_file():
            raise FileNotFoundError(f"Required, previously saved input is missing: {path}")

    from dunkest.models.multiseason_training import adapt_certified_training_rows

    raw = pd.read_parquet(DATASET)
    minute_labels = pd.read_parquet(
        MINUTES,
        columns=["nba_GAME_ID", "nba_PLAYER_ID", "nba_MIN", "nba_match_status"],
    )
    data = adapt_certified_training_rows(raw, minutes_labels=minute_labels, include_2025_26=False)
    data = data.loc[data["season_label"].isin(TEST_SEASONS)].copy()
    data["_join_date"] = pd.to_datetime(data["GAME_DATE"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    data["_join_player"] = data["PLAYER_ID"].astype(str).str.replace(r"\.0$", "", regex=True)
    data["_join_game"] = data["GAME_ID"].astype(str).str.replace(r"\.0$", "", regex=True)

    predictions = pd.read_csv(PREDICTIONS)
    model = predictions.loc[
        predictions["method"].eq(MODEL_METHOD)
        & predictions["test_season"].isin(TEST_SEASONS)
    ].copy()
    model["_join_date"] = pd.to_datetime(model["game_date"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    model["_join_player"] = model["player_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    model["_join_game"] = model["game_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    join_keys = ["test_season", "_join_date", "_join_player", "_join_game"]
    model = model.rename(columns={"test_season": "season_label"})
    join_keys[0] = "season_label"
    if model.duplicated(join_keys).any() or data.duplicated(join_keys).any():
        raise ValueError("Duplicate held-out player/game identities prevent a paired baseline comparison.")
    merged = model.merge(
        data,
        on=join_keys,
        how="left",
        validate="one_to_one",
        suffixes=("_prediction", "_feature"),
        indicator=True,
    )
    if len(merged) != len(model) or not merged["_merge"].eq("both").all():
        raise ValueError("Saved predictions do not map one-to-one to certified adapter rows.")
    actual_model = pd.to_numeric(merged["actual_pdk"], errors="coerce").to_numpy(float)
    actual_target = pd.to_numeric(merged["target_pdk_official"], errors="coerce").to_numpy(float)
    if not np.allclose(actual_model, actual_target, equal_nan=False, atol=1e-9, rtol=0):
        raise ValueError("Saved prediction targets disagree with the certified official PDK labels.")
    merged["model_prediction"] = pd.to_numeric(merged["predicted_pdk"], errors="coerce")
    merged["game_date"] = merged["_join_date"]

    metrics: list[dict[str, object]] = []
    bootstrap: dict[str, object] = {}
    rng = np.random.default_rng(SEED)
    for name, column in BASELINES.items():
        if column is None:
            baseline = (
                pd.to_numeric(merged["pdk_per_min_season"], errors="coerce")
                * pd.to_numeric(merged["prev5_nba_min_mean"], errors="coerce")
            )
        else:
            baseline = pd.to_numeric(merged[column], errors="coerce")
        evaluated = merged.loc[
            np.isfinite(baseline.to_numpy(dtype=float, na_value=np.nan))
            & np.isfinite(merged["model_prediction"].to_numpy(dtype=float, na_value=np.nan))
        ].copy()
        evaluated["baseline_prediction"] = baseline.loc[evaluated.index].to_numpy(dtype=float)
        evaluated["baseline_name"] = name
        evaluated["delta_abs_error_model_minus_baseline"] = (
            np.abs(evaluated["model_prediction"] - evaluated["actual_pdk"])
            - np.abs(evaluated["baseline_prediction"] - evaluated["actual_pdk"])
        )
        baseline_metrics = score(
            evaluated["actual_pdk"].to_numpy(float),
            evaluated["baseline_prediction"].to_numpy(float),
        )
        model_metrics = score(
            evaluated["actual_pdk"].to_numpy(float),
            evaluated["model_prediction"].to_numpy(float),
        )
        folds = []
        for season, fold in evaluated.groupby("season_label", sort=True):
            folds.append({
                "test_season": str(season),
                **score(fold["actual_pdk"].to_numpy(float), fold["baseline_prediction"].to_numpy(float)),
                "model_mae_same_rows": float(mean_absolute_error(fold["actual_pdk"], fold["model_prediction"])),
                "delta_mae_model_minus_baseline": float(fold["delta_abs_error_model_minus_baseline"].mean()),
                "coverage_of_model_test_rows": float(len(fold) / int((merged["season_label"] == season).sum())),
            })
        bootstrap[name] = date_cluster_bootstrap(evaluated, rng)
        metrics.append({
            "baseline": name,
            "rows": int(len(evaluated)),
            "coverage_of_model_test_rows": float(len(evaluated) / len(merged)),
            "baseline_metrics": baseline_metrics,
            "model_metrics_on_same_rows": model_metrics,
            "delta_mae_model_minus_baseline": float(evaluated["delta_abs_error_model_minus_baseline"].mean()),
            "folds": folds,
        })

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": "Saved all-prior-seasons low-history-weighted predictions are paired to the exact certified held-out adapter rows. Simple baselines use only strictly prior official PDK and NBA-minute history. No models are refit.",
        "test_seasons": list(TEST_SEASONS),
        "model_method": MODEL_METHOD,
        "model_rows": int(len(merged)),
        "baseline_definitions": {
            "previous_3_official_pdk_mean": "pdk_mean_3",
            "previous_5_official_pdk_mean": "pdk_mean_5",
            "previous_10_official_pdk_mean": "pdk_mean_10",
            "past_season_official_pdk_mean": "pdk_season_mean from the shared official-only history contract",
            "past_official_pdk_per_min_x_previous_5_nba_minutes": "pdk_per_min_season * prev5_nba_min_mean; both inputs are past-only",
        },
        "metrics": metrics,
        "paired_date_cluster_bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": SEED,
            "resampling_unit": "game date within each test season, then equal-season macro average",
            "results": bootstrap,
        },
        "limitations": [
            "Historical validation folds are not a pristine project-wide holdout.",
            "Coverage differs across simple baselines because players without enough prior official history have no direct seasonal/rate estimate; model metrics are reported on each baseline's same rows.",
            "Player-score comparisons do not validate coach scores, lineup policy, credits, injuries or transfer strategy.",
            "2025/26 and 2026/27 prospective outcomes were not loaded or used.",
        ],
        "outputs": {
            "metrics": str(outputs[2].relative_to(ROOT)),
            "json": str(outputs[0].relative_to(ROOT)),
            "report": str(outputs[1].relative_to(ROOT)),
        },
    }
    flat_rows = []
    for item in metrics:
        for fold in item["folds"]:
            flat_rows.append({
                "baseline": item["baseline"],
                "test_season": fold["test_season"],
                "n": fold["n"],
                "coverage_of_model_test_rows": fold["coverage_of_model_test_rows"],
                "baseline_mae": fold["mae"],
                "baseline_rmse": fold["rmse"],
                "baseline_bias": fold["bias_pred_minus_actual"],
                "model_mae_same_rows": fold["model_mae_same_rows"],
                "delta_mae_model_minus_baseline": fold["delta_mae_model_minus_baseline"],
            })
    pd.DataFrame(flat_rows).to_csv(outputs[2], index=False)
    outputs[0].write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Multi-season player PDK: temporal baselines — 2026-10-18 V1", "",
        f"Generated UTC: {result['generated_at_utc']}", "",
        "## Method", "",
        f"- Reused {len(merged):,} saved OOS player-game predictions from the current production multi-season adapter.",
        "- Test seasons: 2022/23, 2023/24 and 2024/25. No refit, 2025/26 holdout, or prospective GW1 results were used.",
        "- Baselines use only prior official PDK and strictly prior NBA minutes. For each baseline, model metrics use the identical rows with a finite baseline.",
        "- Paired uncertainty resamples game dates within each season, then averages seasons equally.", "",
        "## Pooled paired results", "",
        "| Baseline | Rows | Coverage | Baseline MAE | Model MAE on same rows | Δ MAE (model − baseline) | 95% date-cluster interval |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in metrics:
        ci = bootstrap[item["baseline"]]["ci95_equal_season_macro"]
        lines.append(
            f"| {item['baseline']} | {item['rows']:,} | {item['coverage_of_model_test_rows']:.1%} | "
            f"{item['baseline_metrics']['mae']:.4f} | {item['model_metrics_on_same_rows']['mae']:.4f} | "
            f"{item['delta_mae_model_minus_baseline']:.4f} | [{ci[0]:.4f}, {ci[1]:.4f}] |"
        )
    lines += ["", "## Per-season metrics", "", "| Baseline | Season | N | Coverage | Baseline MAE | Model MAE on same rows | Δ MAE |", "|---|---|---:|---:|---:|---:|---:|"]
    for row in flat_rows:
        lines.append(
            f"| {row['baseline']} | {row['test_season']} | {row['n']:,} | {row['coverage_of_model_test_rows']:.1%} | "
            f"{row['baseline_mae']:.4f} | {row['model_mae_same_rows']:.4f} | {row['delta_mae_model_minus_baseline']:.4f} |"
        )
    lines += ["", "## Interpretation and limits", "", *[f"- {item}" for item in result["limitations"]], "", "## Reproduction", "", "```bash", "PYTHONPATH=src .venv/bin/python scripts/audit_dunkest_multiseason_temporal_baselines_20261018_v1.py", "```", "", "## Artifacts", "", *[f"- `{path.relative_to(ROOT)}`" for path in outputs], ""]
    outputs[1].write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "metrics": metrics, "paired_date_cluster_bootstrap": bootstrap}, indent=2))


if __name__ == "__main__":
    main()
