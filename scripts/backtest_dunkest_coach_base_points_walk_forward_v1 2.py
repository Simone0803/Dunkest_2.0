#!/usr/bin/env python3
"""Reconstruct Dunkest coach base-score outcomes and test walk-forward forecasts.

Historical coach credit markets are not archived, so labels are the official
coach scoring rule with equal coach credits (coefficient 1.0). This isolates the
part reconstructable from final NBA results; it does NOT pretend to recover the
historical credit-difference multiplier.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, mean_squared_error

from dunkest.rules.coach import coach_points_from_game

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/team_game_logs_2018-26_v1.parquet"
OUT = ROOT / "reports/audit"
STEM = "dunkest_coach_base_points_walk_forward_2018-26_v1"
OUTCOMES = OUT / f"{STEM}_outcomes.csv"
PREDICTIONS = OUT / f"{STEM}_predictions.csv"
METRICS = OUT / f"{STEM}_metrics.csv"
AUDIT = OUT / f"{STEM}.json"
REPORT = OUT / f"{STEM}.md"
TEST_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]


def make_outcomes(raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.copy()
    d["GAME_DATE"] = pd.to_datetime(d["GAME_DATE"], errors="coerce")
    d["GAME_ID"] = d["GAME_ID"].astype(str)
    d["TEAM_ABBREVIATION"] = d["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    for c in ("PTS", "MIN", "REB", "AST"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["SEASON"] = d["SEASON"].astype(str)
    d = d.dropna(subset=["GAME_DATE", "GAME_ID", "TEAM_ABBREVIATION", "PTS", "SEASON"])
    d = d.drop_duplicates(["SEASON", "GAME_ID", "TEAM_ABBREVIATION"], keep=False)
    counts = d.groupby(["SEASON", "GAME_ID"])["TEAM_ABBREVIATION"].nunique()
    valid = set(counts[counts.eq(2)].index)
    d = d.loc[pd.MultiIndex.from_frame(d[["SEASON", "GAME_ID"]]).isin(valid)].copy()

    paired = []
    for (season, game_id), game in d.groupby(["SEASON", "GAME_ID"], sort=False):
        game = game.drop_duplicates("TEAM_ABBREVIATION")
        if len(game) != 2:
            continue
        a, b = game.iloc[0], game.iloc[1]
        overtime = bool(max(float(a["MIN"] or 0), float(b["MIN"] or 0)) > 240) if pd.notna(a["MIN"]) and pd.notna(b["MIN"]) else None
        if overtime is None:
            continue
        for own, opp in ((a, b), (b, a)):
            matchup = str(own.get("MATCHUP", ""))
            paired.append({
                "season": season, "game_id": str(game_id), "game_date": own["GAME_DATE"],
                "team": str(own["TEAM_ABBREVIATION"]), "opponent": str(opp["TEAM_ABBREVIATION"]),
                "team_points": float(own["PTS"]), "opponent_points": float(opp["PTS"]),
                "team_rebounds": float(own["REB"]) if pd.notna(own["REB"]) else np.nan,
                "opponent_rebounds": float(opp["REB"]) if pd.notna(opp["REB"]) else np.nan,
                "team_assists": float(own["AST"]) if pd.notna(own["AST"]) else np.nan,
                "opponent_assists": float(opp["AST"]) if pd.notna(opp["AST"]) else np.nan,
                "overtime": overtime,
                "is_home": bool("vs." in matchup),
                "actual_base_coach_pdk": coach_points_from_game(
                    float(own["PTS"]), float(opp["PTS"]), 10.0, 10.0, overtime=overtime
                ),
            })
    out = pd.DataFrame(paired).sort_values(["game_date", "game_id", "team"]).reset_index(drop=True)
    if out.empty:
        raise RuntimeError("No valid paired team outcomes found.")
    if out.duplicated(["season", "game_id", "team"]).any():
        raise RuntimeError("Duplicate team-game outcome keys remain after pairing.")
    return out


def add_pregame_features(outcomes: pd.DataFrame) -> pd.DataFrame:
    d = outcomes.copy().sort_values(["game_date", "game_id", "team"]).reset_index(drop=True)
    # Per-team features are shifted before rolling; no same-day game outcome can enter.
    d["team_margin"] = d["team_points"] - d["opponent_points"]
    d["team_win"] = (d["team_points"] > d["opponent_points"]).astype(float)
    d["team_base_score"] = pd.to_numeric(d["actual_base_coach_pdk"], errors="coerce")
    for source, prefix in (("team_points", "team_pts"), ("opponent_points", "team_allowed_pts"),
                           ("team_margin", "team_margin"), ("team_win", "team_win_rate"),
                           ("team_base_score", "team_base_score"), ("overtime", "team_overtime_rate")):
        vals = pd.to_numeric(d[source], errors="coerce")
        prior = vals.groupby(d["team"]).shift(1)
        d[f"{prefix}_lag1"] = prior
        for window in (5, 10):
            d[f"{prefix}_prev{window}"] = prior.groupby(d["team"]).transform(
                lambda s: s.rolling(window, min_periods=1).mean()
            )
    prior_date = d.groupby("team")["game_date"].shift(1)
    d["team_rest_days"] = (d["game_date"] - prior_date).dt.total_seconds() / 86400.0
    d["team_games_before"] = d.groupby("team").cumcount()

    own_features = [c for c in d.columns if c.startswith(("team_pts_", "team_allowed_pts_", "team_margin_", "team_win_rate_", "team_base_score_", "team_overtime_rate_"))] + ["team_rest_days", "team_games_before"]
    own = d[["season", "game_id", "team"] + own_features].copy()
    own = own.rename(columns={"team": "opponent"})
    own = own.rename(columns={c: "opp_" + c for c in own_features})
    d = d.merge(own, on=["season", "game_id", "opponent"], how="left", validate="one_to_one")
    d["opponent_games_before"] = d["opp_team_games_before"]
    return d


def make_model(features: list[str]) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("model", ExtraTreesRegressor(n_estimators=180, min_samples_leaf=15, max_features=0.9,
                                       random_state=42, n_jobs=-1)),
    ])


def score_metrics(actual: np.ndarray, pred: np.ndarray, season: str, family: str) -> dict:
    err = np.asarray(pred, float) - np.asarray(actual, float)
    return {"test_season": season, "method": family, "n": int(len(actual)),
            "mae": float(mean_absolute_error(actual, pred)),
            "rmse": float(np.sqrt(mean_squared_error(actual, pred))),
            "bias_pred_minus_actual": float(err.mean())}


def main() -> int:
    for p in (OUTCOMES, PREDICTIONS, METRICS, AUDIT, REPORT):
        if p.exists():
            raise SystemExit(f"Refusing to overwrite versioned artifact: {p}")
    raw = pd.read_parquet(INPUT)
    outcomes = make_outcomes(raw)
    d = add_pregame_features(outcomes)
    features = [c for c in d.columns if c.endswith(("_lag1", "_prev5", "_prev10")) or c in {
        "is_home", "team_rest_days", "team_games_before", "opponent_games_before"}]
    # Convert booleans to numeric for sklearn.
    d["is_home"] = d["is_home"].astype(int)
    trainable_seasons = sorted(d["season"].unique(), key=lambda x: (int(x[:4]), x))
    metrics, predictions, folds = [], [], []
    for test_season in TEST_SEASONS:
        if test_season not in trainable_seasons:
            continue
        test_idx = d["season"].eq(test_season)
        test = d.loc[test_idx].copy()
        train = d.loc[(d["game_date"] < test["game_date"].min()) & ~test_idx].copy()
        if train.empty or test.empty:
            folds.append({"season": test_season, "status": "skipped", "train_rows": len(train), "test_rows": len(test)})
            continue
        y_train = train["actual_base_coach_pdk"].to_numpy(float)
        y_test = test["actual_base_coach_pdk"].to_numpy(float)
        model = make_model(features)
        model.fit(train[features], y_train)
        pred = model.predict(test[features])
        for name, p in (
            ("model_pregame_team_form", pred),
            ("baseline_previous5_base_score", test["team_base_score_prev5"].fillna(float(np.median(y_train))).to_numpy(float)),
            ("baseline_previous10_base_score", test["team_base_score_prev10"].fillna(float(np.median(y_train))).to_numpy(float)),
            ("baseline_train_median", np.full(len(test), float(np.median(y_train)))),
        ):
            metrics.append(score_metrics(y_test, p, test_season, name))
            for i, (_, row) in enumerate(test.iterrows()):
                predictions.append({"season": test_season, "game_date": row["game_date"].strftime("%Y-%m-%d"),
                    "game_id": row["game_id"], "team": row["team"], "opponent": row["opponent"],
                    "team_points": row["team_points"], "opponent_points": row["opponent_points"],
                    "overtime": bool(row["overtime"]), "actual_base_coach_pdk": y_test[i],
                    "predicted_base_coach_pdk": float(p[i]), "method": name})
        folds.append({"season": test_season, "status": "evaluated", "train_rows": len(train), "test_rows": len(test),
                      "train_seasons": sorted(train["season"].unique().tolist()),
                      "test_games": int(test["game_id"].nunique()),
                      "test_overtime_games": int(test.loc[test["overtime"], "game_id"].nunique())})
    m = pd.DataFrame(metrics)
    p = pd.DataFrame(predictions)
    outcomes.to_csv(OUTCOMES, index=False)
    p.to_csv(PREDICTIONS, index=False)
    m.to_csv(METRICS, index=False)
    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "input": str(INPUT.relative_to(ROOT)),
        "outcome_rows": len(outcomes), "games": int(outcomes["game_id"].nunique()),
        "overtime_games": int(outcomes.loc[outcomes["overtime"], "game_id"].nunique()),
        "target_definition": "Coach scoring rule applied to verified final team scores, margin, thresholds and overtime, with coach CR=opponent coach CR=10 so the credit-difference coefficient equals 1.0.",
        "not_claimed": "These are reconstructed neutral-credit base scores, not exact historical credit-adjusted coach PDK; historical coach CR markets are absent from local archives.",
        "feature_policy": "Team and opponent rolling features are shifted by one game and are based only on prior games. All games on the same date are excluded from each other's history.",
        "test_seasons": TEST_SEASONS, "folds": folds, "metrics": m.to_dict("records"),
        "production_changed": False,
        "limitations": ["Historical coach CR values are not present, so the credit-difference multiplier cannot be validated historically.",
                         "The reconstructed base score follows the current repository's coach scoring rules; historical rule-version changes are not independently verified."]
    }
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Historical Dunkest coach base-score reconstruction — V1", "",
        f"Generated (UTC): {audit['generated_at_utc']}", "",
        "## What is reconstructed", "",
        "For each NBA game and each team, the current Dunkest coach scoring rules are applied to final team points, margin, threshold bonuses/penalties and overtime. Coach credits are set equal on both sides, so the credit-difference multiplier is exactly 1.0. This isolates the base coach score that is recoverable from the NBA boxscore.", "",
        "It is **not** an exact historical credit-adjusted coach score: historical coach CR prices are not archived in the local data.", "",
        f"- Games reconstructed: {audit['games']:,}", f"- Team-game coach outcome rows: {audit['outcome_rows']:,}", f"- Overtime games: {audit['overtime_games']:,}", "",
        "## Chronological model evaluation", "", m.to_string(index=False), "",
        "The model predicts neutral-credit base coach PDK from prior team/offensive/defensive form. Test-season outcomes are never used to fit that season's model; rolling features within the test season use only earlier game dates.", "",
        "## Limitations", "",
        "1. Exact historical coach PDK still requires historical coach CR and opponent coach CR, or a validated reconstruction of those prices.",
        "2. The base score uses the current repository scoring rules; historical rule changes have not been independently verified.",
        "3. This evaluates coach score prediction, not a full budget-constrained player-plus-coach lineup optimizer.", "",
        "## Artifacts", "", f"- Reconstructed outcomes: `{OUTCOMES.relative_to(ROOT)}`", f"- Walk-forward predictions: `{PREDICTIONS.relative_to(ROOT)}`", f"- Metrics: `{METRICS.relative_to(ROOT)}`", f"- Audit JSON: `{AUDIT.relative_to(ROOT)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "games": audit["games"], "overtime_games": audit["overtime_games"],
        "metrics": m.to_dict("records"), "outputs": [str(x.relative_to(ROOT)) for x in (OUTCOMES, PREDICTIONS, METRICS, AUDIT, REPORT)]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
