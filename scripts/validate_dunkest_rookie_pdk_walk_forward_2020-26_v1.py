#!/usr/bin/env python3
"""Walk-forward evaluation for draft-year rookie cohorts against official Dunkest PDK.

Uses the separately versioned verified training dataset, matches rookie cohorts by
normalized name, trains only on seasons strictly before each test season, and
never changes production models or source datasets. Missing/non-matched players
are reported, not assigned fabricated labels.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
ROOKIE_PATH = ROOT / "data/rookie_college.csv"
HOLDOUT_PATH = ROOT / "data/processed/dunkest_pdk_holdout_2025-26_predictions_v1.csv"
OUT_DIR = ROOT / "reports/audit"
STAMP = "20261012_v1"
PRED_PATH = OUT_DIR / f"dunkest_rookie_pdk_walk_forward_predictions_{STAMP}.csv"
METRICS_PATH = OUT_DIR / f"dunkest_rookie_pdk_walk_forward_metrics_{STAMP}.csv"
AUDIT_PATH = OUT_DIR / f"dunkest_rookie_pdk_walk_forward_audit_{STAMP}.json"
REPORT_PATH = OUT_DIR / f"dunkest_rookie_pdk_walk_forward_{STAMP}.md"
OUTPUTS = [PRED_PATH, METRICS_PATH, AUDIT_PATH, REPORT_PATH]

SEASON_ORDER = [("5", 2020, "2020-21"), ("7", 2021, "2021-22"),
                ("9", 2022, "2022-23"), ("13", 2023, "2023-24"),
                ("19", 2024, "2024-25"), ("25", 2025, "2025-26")]

sys.path.insert(0, str(ROOT / "scripts"))
from validate_dunkest_historical_pdk_training_v2 import (  # noqa: E402
    CATEGORICAL_FEATURES, NUMERIC_FEATURES, TARGET, make_model,
)


def norm_name(value: object) -> str:
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def markdown_table(frame: pd.DataFrame) -> str:
    """Render a Markdown table without requiring optional `tabulate`."""
    view = frame.copy().fillna("")
    columns = [str(c) for c in view.columns]
    rows = [[str(value).replace("|", "\\|").replace("\n", " ") for value in row]
            for row in view.astype(str).itertuples(index=False, name=None)]
    widths = [max(len(columns[i]), *(len(row[i]) for row in rows)) for i in range(len(columns))]
    head = "| " + " | ".join(columns[i].ljust(widths[i]) for i in range(len(columns))) + " |"
    rule = "| " + " | ".join("-" * widths[i] for i in range(len(columns))) + " |"
    body = ["| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(columns))) + " |" for row in rows]
    return "\n".join([head, rule, *body])


def score(y: pd.Series, pred: pd.Series, model: str, season: str, segment: str) -> dict:
    valid = y.notna() & pred.notna()
    actual = y.loc[valid].to_numpy(dtype=float)
    predicted = pred.loc[valid].to_numpy(dtype=float)
    if len(actual) == 0:
        return {"season": season, "model": model, "segment": segment, "n": 0,
                "mae": np.nan, "rmse": np.nan, "bias_pred_minus_actual": np.nan, "r2": np.nan}
    return {"season": season, "model": model, "segment": segment, "n": len(actual),
            "mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
            "bias_pred_minus_actual": float(np.mean(predicted - actual)),
            "r2": float(r2_score(actual, predicted)) if len(actual) > 1 else np.nan}


def main() -> None:
    existing = [str(p) for p in OUTPUTS if p.exists()]
    if existing:
        raise SystemExit("Refusing to overwrite existing audit outputs: " + ", ".join(existing))
    df = pd.read_parquet(DATA_PATH).copy()
    rookies = pd.read_csv(ROOKIE_PATH, usecols=["player_name", "draft_year"])
    df["season_id"] = df["season_id"].astype(str)
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")
    df["player_key_norm"] = df["dunkest_player_name"].map(norm_name)
    rookies["draft_year"] = pd.to_numeric(rookies["draft_year"], errors="coerce")
    rookies["player_key_norm"] = rookies["player_name"].map(norm_name)
    if rookies.duplicated(["player_key_norm", "draft_year"]).any():
        # Duplicate identity within the same draft class cannot be safely resolved.
        dupes = rookies.loc[rookies.duplicated(["player_key_norm", "draft_year"], keep=False), "player_name"].tolist()
        raise SystemExit(f"Ambiguous normalized rookie identities within draft class: {dupes[:10]}")
    rookies = rookies.rename(columns={"player_name": "rookie_source_name"})
    cohort_rows = []
    predictions = []
    metric_rows = []
    coverage_rows = []
    features = NUMERIC_FEATURES + CATEGORICAL_FEATURES

    for season_id, draft_year, season_name in SEASON_ORDER:
        season = df.loc[df["season_id"].eq(season_id)].copy()
        season = season.merge(rookies, on="player_key_norm", how="inner")
        season = season.loc[season["draft_year"].eq(draft_year)].copy()
        if season.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
            raise SystemExit(f"Duplicate rookie player-game rows after draft-year filtering in {season_name}.")
        # Use a strictly earlier-season training set, never any target from the held-out season.
        train = df.loc[df["season_id"].isin([sid for sid, _, _ in SEASON_ORDER if int(sid) < int(season_id)])].copy()
        # Season IDs are not chronological integers for all leagues; enforce explicit ordering instead.
        current_idx = next(i for i, (sid, _, _) in enumerate(SEASON_ORDER) if sid == season_id)
        prior_ids = {item[0] for item in SEASON_ORDER[:current_idx]}
        train = df.loc[df["season_id"].isin(prior_ids)].copy()
        if season.empty:
            coverage_rows.append({"season": season_name, "draft_year": draft_year, "rookie_players_matched": 0,
                                  "rookie_rows": 0, "train_seasons": ";".join(x[2] for x in SEASON_ORDER[:current_idx]),
                                  "status": "no matched official rows"})
            continue
        season["rookie_game_index"] = season.groupby("player_key_norm")["game_date"].rank(method="first").astype(int)
        season["experience_segment"] = np.where(season["history_games_before_target"].fillna(0).eq(0),
                                                "no_prior_official_pdk", "prior_official_pdk_available")
        if train.empty:
            coverage_rows.append({"season": season_name, "draft_year": draft_year,
                                  "rookie_players_matched": int(season["player_key_norm"].nunique()),
                                  "rookie_rows": int(len(season)), "train_seasons": "",
                                  "status": "skipped: no earlier verified training season"})
            continue
        model = make_model("random_forest", NUMERIC_FEATURES, CATEGORICAL_FEATURES)
        model.fit(train[features], train[TARGET].astype(float).to_numpy())
        season["prediction_random_forest_walk_forward"] = model.predict(season[features])
        train_median = float(train[TARGET].median())
        season["prediction_baseline_prev10_walk_forward"] = pd.to_numeric(
            season["prev10_pdk_mean"], errors="coerce").fillna(train_median)
        # For 2025/26 also preserve the fixed holdout prediction already generated by the fixed 2020-25 model.
        if season_id == "25":
            holdout = pd.read_csv(HOLDOUT_PATH)
            holdout["player_key_norm"] = holdout["dunkest_player_name"].map(norm_name)
            holdout["game_date"] = pd.to_datetime(holdout["game_date"], errors="coerce")
            holdout["gameId"] = holdout["gameId"].astype(str)
            season["gameId"] = season["gameId"].astype(str)
            season["dunkest_player_id"] = season["dunkest_player_id"].astype(str)
            holdout["dunkest_player_id"] = holdout["dunkest_player_id"].astype(str)
            season = season.merge(
                holdout[["gameId", "dunkest_player_id", "prediction_random_forest", "prediction_baseline_prev10"]].rename(
                    columns={"prediction_random_forest": "prediction_random_forest_fixed_holdout",
                             "prediction_baseline_prev10": "prediction_baseline_prev10_fixed_holdout"}),
                on=["gameId", "dunkest_player_id"], how="left", validate="one_to_one")
        train_seasons = [name for sid, _, name in SEASON_ORDER[:current_idx]]
        coverage_rows.append({"season": season_name, "draft_year": draft_year,
                              "rookie_players_matched": int(season["player_key_norm"].nunique()),
                              "rookie_rows": int(len(season)), "train_seasons": ";".join(train_seasons),
                              "status": "evaluated"})
        for model_col, model_name in [
            ("prediction_random_forest_walk_forward", "random_forest_walk_forward"),
            ("prediction_baseline_prev10_walk_forward", "baseline_prev10_walk_forward"),
        ]:
            metric_rows.append(score(season[TARGET], season[model_col], model_name, season_name, "all_rookie_games"))
            for segment, group in season.groupby("experience_segment", dropna=False):
                metric_rows.append(score(group[TARGET], group[model_col], model_name, season_name, str(segment)))
            early = season.loc[season["rookie_game_index"].le(3)]
            metric_rows.append(score(early[TARGET], early[model_col], model_name, season_name, "first_3_dunkest_games"))
        if season_id == "25":
            for model_col, model_name in [
                ("prediction_random_forest_fixed_holdout", "random_forest_fixed_2020_25_holdout"),
                ("prediction_baseline_prev10_fixed_holdout", "baseline_prev10_fixed_2020_25_holdout"),
            ]:
                metric_rows.append(score(season[TARGET], pd.to_numeric(season[model_col], errors="coerce"),
                                         model_name, season_name, "all_rookie_games"))
                early = season.loc[season["rookie_game_index"].le(3)]
                metric_rows.append(score(early[TARGET], pd.to_numeric(early[model_col], errors="coerce"),
                                         model_name, season_name, "first_3_dunkest_games"))
        keep = ["season_id", "season_label", "game_date", "gameId", "dunkest_player_id", "dunkest_player_name",
                "rookie_source_name", "draft_year", "target_pdk", "history_games_before_target", "nba_history_games_before_target",
                "lag1_pdk", "prev10_pdk_mean", "rookie_game_index", "experience_segment",
                "prediction_random_forest_walk_forward", "prediction_baseline_prev10_walk_forward"]
        if season_id == "25":
            keep += ["prediction_random_forest_fixed_holdout", "prediction_baseline_prev10_fixed_holdout"]
        predictions.append(season[keep].copy())

    if not predictions:
        raise SystemExit("No rookie outcomes matched official target data.")
    pred_df = pd.concat(predictions, ignore_index=True)
    metrics = pd.DataFrame(metric_rows)
    coverage = pd.DataFrame(coverage_rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pred_df.to_csv(PRED_PATH, index=False)
    metrics.to_csv(METRICS_PATH, index=False)
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "official_training_data": str(DATA_PATH.relative_to(ROOT)),
        "rookie_cohort_source": str(ROOKIE_PATH.relative_to(ROOT)),
        "fixed_holdout_predictions": str(HOLDOUT_PATH.relative_to(ROOT)),
        "target": "target_pdk from verified official Dunkest PDK training dataset only",
        "cohort_matching": "Normalized player name and draft_year matched to the NBA season immediately after the draft; this is a proxy for the typical rookie season, not a verified debut-season label for players with delayed NBA debuts.",
        "evaluation_protocol": "For each season after 2020/21, fit on verified official target rows from strictly earlier seasons and score matched first-season NBA players. 2025/26 additionally reports the existing fixed 2020/21–2024/25 holdout model. The online features are pregame features and can use earlier valid same-season outcomes only.",
        "no_synthetic_labels": True,
        "no_source_data_overwritten": True,
        "coverage": coverage.to_dict(orient="records"),
        "metrics": metrics.to_dict(orient="records"),
        "limitations": [
            "Cohort matching is name-based because rookie_college.csv does not contain NBA/Dunkest player IDs; unmatched names are excluded and listed in coverage.",
            "The walk-forward models train on all official rows from earlier seasons, not only veterans, and test only the current draft cohort. Draft year is a proxy for rookie season; players with delayed NBA debuts may be missed or misclassified.",
            "For seasons before 2025/26, these are season-level expanding-window tests, not a frozen pre-season forecast; within-season lag features are online one-step-ahead.",
            "The available official Dunkest training dataset begins in 2020/21 because 2018/19 and 2019/20 PDK validity flags remain unresolved.",
        ],
    }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = ["# Rookie-specific official PDK walk-forward validation", "",
            f"Created: {audit['created_utc']}", "",
            "## Method", "",
            "- Draft-year cohorts are matched by normalized player name to the NBA season immediately after the draft; this approximates the typical rookie season but does not identify every delayed NBA debut.",
            "- Each model is fit only on verified official PDK outcomes from strictly earlier seasons.",
            "- Outcomes are the official `target_pdk`; no reconstructed or synthetic targets are created.",
            "- Reports all rookie games, first three Dunkest games, and whether prior valid PDK history exists.",
            "- 2025/26 additionally scores the existing fixed holdout model trained on 2020/21–2024/25.",
            "- Unmatched names and seasons without an earlier training set are reported rather than imputed.", "",
            "## Cohort coverage", "", markdown_table(coverage), "",
            "## Metrics", "", markdown_table(metrics), "",
            "## Important interpretation", "",
            "These metrics evaluate game-score forecasting for players in their first NBA season. They do not by themselves estimate the probability a prospect will receive minutes: rows without a verified official target are intentionally excluded, and the source rookie table does not reliably distinguish DNP/zero-minute outcomes from missing data. Use the `no_prior_official_pdk` segment to evaluate first-game uncertainty, but do not infer participation calibration from that segment alone.", "",
            "## Artifacts", "",
            f"- Per-game predictions: `{PRED_PATH.relative_to(ROOT)}`",
            f"- Metrics: `{METRICS_PATH.relative_to(ROOT)}`",
            f"- Audit: `{AUDIT_PATH.relative_to(ROOT)}`", ""]
    REPORT_PATH.write_text("\n".join(rows), encoding="utf-8")
    print("COVERAGE\n", coverage.to_string(index=False))
    print("\nMETRICS\n", metrics.to_string(index=False))
    print("\nREPORT", REPORT_PATH)


if __name__ == "__main__":
    main()
