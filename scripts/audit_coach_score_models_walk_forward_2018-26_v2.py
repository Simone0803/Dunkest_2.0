from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

from dunkest.models.coach import (
    TEAM_FORM_HALF_LIFE_GAMES,
    TEAM_FORM_PRIOR_GAMES,
    TEAM_VOLATILITY_PRIOR_GAMES,
)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "processed" / "team_game_logs_2018-26_v1.parquet"
OUT_DIR = ROOT / "reports" / "audit"
PRED_OUT = OUT_DIR / "coach_score_models_walk_forward_2018-26_v2.csv"
METRICS_OUT = OUT_DIR / "coach_score_models_walk_forward_2018-26_v2.json"
TRAIN_SEASONS = {"2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24"}
VALIDATION_SEASONS = {"2024-25"}
FINAL_HOLDOUT_SEASONS = {"2025-26"}
BLEND_GRID = np.round(np.linspace(0.0, 1.0, 11), 2)


def _shrunk_recent_mean(
    group: pd.DataFrame, column: str, league_mean: float
) -> float:
    values = pd.to_numeric(
        group.sort_values("game_date", kind="stable")[column], errors="coerce"
    ).dropna()
    if values.empty:
        return float(league_mean)
    age = np.arange(len(values) - 1, -1, -1, dtype=float)
    weights = np.exp2(-age / TEAM_FORM_HALF_LIFE_GAMES)
    weights /= weights.sum()
    recent = float(np.average(values.to_numpy(dtype=float), weights=weights))
    reliability = len(values) / (len(values) + TEAM_FORM_PRIOR_GAMES)
    return float(league_mean + reliability * (recent - league_mean))


def _metrics(actual: np.ndarray, probability: np.ndarray) -> dict[str, float | int]:
    p = np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)
    y = np.asarray(actual, dtype=float)
    return {
        "n": int(len(y)),
        "brier": float(np.mean((p - y) ** 2)),
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "accuracy": float(np.mean((p >= 0.5) == y)),
        "mean_predicted_home_win_probability": float(p.mean()),
        "actual_home_win_rate": float(y.mean()),
    }


def _walk_forward_predictions(raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.copy()
    d["GAME_DATE"] = pd.to_datetime(d["GAME_DATE"], errors="coerce")
    d["TEAM_ABBREVIATION"] = d["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    d["GAME_ID"] = d["GAME_ID"].astype(str)
    d["PTS"] = pd.to_numeric(d["PTS"], errors="coerce")
    d["is_home"] = d["MATCHUP"].astype(str).str.contains(r"vs\.", regex=True)

    # Estimate possessions using standard box-score components. Rows without
    # complete possession inputs remain eligible for the points-only baseline.
    for column in ("FGA", "FTA", "OREB", "TOV"):
        if column not in d:
            d[column] = np.nan
        d[column] = pd.to_numeric(d[column], errors="coerce")
    d["possessions"] = d["FGA"] + 0.44 * d["FTA"] - d["OREB"] + d["TOV"]
    d.loc[~d["possessions"].gt(0), "possessions"] = np.nan

    d = d.dropna(subset=["GAME_DATE", "PTS", "SEASON"])
    d = d.sort_values(["GAME_DATE", "GAME_ID", "TEAM_ABBREVIATION"], kind="stable")
    counts = d.groupby(["SEASON", "GAME_ID"])["TEAM_ABBREVIATION"].nunique()
    complete = set(counts[counts.eq(2)].index)
    d = d.loc[pd.MultiIndex.from_frame(d[["SEASON", "GAME_ID"]]).isin(complete)].copy()

    history: list[dict] = []
    forecasts: list[dict] = []
    for date, same_day in d.groupby("GAME_DATE", sort=True):
        if history:
            hist = pd.DataFrame(history)
            league_points = float(hist["team_points"].mean())
            league_sd = float(np.clip(hist["team_points"].std(ddof=1), 8.0, 18.0))
            league_possessions = float(hist["possessions"].mean()) if hist["possessions"].notna().any() else np.nan
            valid_eff = hist.loc[
                hist["possessions"].gt(0) & hist["opponent_points"].notna()
            ].copy()
            valid_eff["off_eff"] = 100.0 * valid_eff["team_points"] / valid_eff["possessions"]
            valid_eff["def_eff_allowed"] = 100.0 * valid_eff["opponent_points"] / valid_eff["possessions"]
            league_off_eff = float(valid_eff["off_eff"].mean()) if not valid_eff.empty else np.nan
            league_def_eff = float(valid_eff["def_eff_allowed"].mean()) if not valid_eff.empty else np.nan

            profiles: dict[str, dict[str, float]] = {}
            score_sds: dict[str, float] = {}
            for team, group in hist.groupby("team"):
                group = group.sort_values("game_date", kind="stable")
                n = len(group)
                profile = {
                    "offense": _shrunk_recent_mean(group, "team_points", league_points),
                    "defense_allowed": _shrunk_recent_mean(group, "opponent_points", league_points),
                    "games": n,
                    "off_eff": np.nan,
                    "def_eff_allowed": np.nan,
                    "pace": np.nan,
                }
                eff_group = valid_eff.loc[valid_eff["team"].eq(team)]
                if not eff_group.empty and np.isfinite(league_off_eff) and np.isfinite(league_def_eff):
                    profile["off_eff"] = _shrunk_recent_mean(eff_group, "off_eff", league_off_eff)
                    profile["def_eff_allowed"] = _shrunk_recent_mean(eff_group, "def_eff_allowed", league_def_eff)
                    if np.isfinite(league_possessions):
                        profile["pace"] = _shrunk_recent_mean(eff_group, "possessions", league_possessions)
                profiles[team] = profile

                sample_sd = float(group["team_points"].std(ddof=1)) if n > 1 else league_sd
                if not np.isfinite(sample_sd):
                    sample_sd = league_sd
                degrees = max(n - 1, 0)
                variance = (
                    degrees * sample_sd**2 + TEAM_VOLATILITY_PRIOR_GAMES * league_sd**2
                ) / (degrees + TEAM_VOLATILITY_PRIOR_GAMES)
                score_sds[team] = float(np.clip(np.sqrt(variance), 8.0, 18.0))

            paired = hist.pivot_table(index="game_id", columns="is_home", values="team_points", aggfunc="first")
            home_advantage = 0.0
            if False in paired and True in paired:
                margins = (paired[True] - paired[False]).dropna()
                if len(margins) >= 10:
                    home_advantage = float(np.clip(margins.mean() / 2.0, -3.0, 3.0))
            score_correlation = 0.1
            if False in paired and True in paired:
                complete_pairs = paired.dropna(subset=[False, True])
                if len(complete_pairs) >= 10:
                    estimate = complete_pairs[False].corr(complete_pairs[True])
                    if np.isfinite(estimate):
                        score_correlation = float(np.clip(estimate, -0.4, 0.6))

            for (season, game_id), game in same_day.groupby(["SEASON", "GAME_ID"], sort=False):
                if len(game) != 2:
                    continue
                home = game.loc[game["is_home"]]
                away = game.loc[~game["is_home"]]
                neutral_site = False
                if len(home) == 1 and len(away) == 1:
                    h, a = home.iloc[0], away.iloc[0]
                elif len(home) == 0 and len(away) == 2:
                    ordered = game.sort_values("TEAM_ABBREVIATION", kind="stable")
                    h, a = ordered.iloc[0], ordered.iloc[1]
                    neutral_site = True
                else:
                    continue
                home_team, away_team = str(h["TEAM_ABBREVIATION"]), str(a["TEAM_ABBREVIATION"])
                hp = profiles.get(home_team, {"offense": league_points, "defense_allowed": league_points, "games": 0})
                ap = profiles.get(away_team, {"offense": league_points, "defense_allowed": league_points, "games": 0})
                ha = 0.0 if neutral_site else home_advantage

                points_home = hp["offense"] + ap["defense_allowed"] - league_points + ha
                points_away = ap["offense"] + hp["defense_allowed"] - league_points - ha

                efficiency_available = all(
                    np.isfinite(value) and value > 0
                    for value in (
                        hp.get("off_eff", np.nan), ap.get("off_eff", np.nan),
                        hp.get("def_eff_allowed", np.nan), ap.get("def_eff_allowed", np.nan),
                        hp.get("pace", np.nan), ap.get("pace", np.nan),
                        league_possessions,
                    )
                ) and np.isfinite(league_off_eff) and np.isfinite(league_def_eff)
                if efficiency_available:
                    pace = float(np.mean([hp["pace"], ap["pace"], league_possessions]))
                    efficiency_home = (
                        (hp["off_eff"] + ap["def_eff_allowed"]) / 2.0
                    ) * pace / 100.0 + ha
                    efficiency_away = (
                        (ap["off_eff"] + hp["def_eff_allowed"]) / 2.0
                    ) * pace / 100.0 - ha
                else:
                    efficiency_home, efficiency_away = points_home, points_away

                sd_home = score_sds.get(home_team, league_sd)
                sd_away = score_sds.get(away_team, league_sd)
                margin_sd = max(float(np.sqrt(sd_home**2 + sd_away**2 - 2 * score_correlation * sd_home * sd_away)), 5.0)
                actual_home_points, actual_away_points = float(h["PTS"]), float(a["PTS"])
                forecasts.append({
                    "season": str(season), "date": date, "game_id": str(game_id),
                    "home_team": home_team, "away_team": away_team,
                    "predicted_home_points": float(points_home),
                    "predicted_away_points": float(points_away),
                    "predicted_margin": float(points_home - points_away),
                    "predicted_home_win_probability": float(ndtr((points_home - points_away) / margin_sd)),
                    "efficiency_home_points": float(efficiency_home),
                    "efficiency_away_points": float(efficiency_away),
                    "efficiency_margin": float(efficiency_home - efficiency_away),
                    "efficiency_home_win_probability": float(ndtr((efficiency_home - efficiency_away) / margin_sd)),
                    "efficiency_features_available": bool(efficiency_available),
                    "actual_home_points": actual_home_points,
                    "actual_away_points": actual_away_points,
                    "actual_margin": actual_home_points - actual_away_points,
                    "actual_home_win": float(actual_home_points > actual_away_points),
                    "home_games_seen": int(hp["games"]), "away_games_seen": int(ap["games"]),
                    "home_advantage_estimate": float(ha), "neutral_site": bool(neutral_site),
                    "score_correlation_estimate": float(score_correlation),
                    "margin_sd": float(margin_sd),
                })

        # Strict temporal order: today's results enter the history only after all
        # forecasts for this date have been created.
        for (season, game_id), game in same_day.groupby(["SEASON", "GAME_ID"], sort=False):
            if len(game) != 2:
                continue
            home = game.loc[game["is_home"]]
            away = game.loc[~game["is_home"]]
            neutral_site = False
            if len(home) == 1 and len(away) == 1:
                h, a = home.iloc[0], away.iloc[0]
            elif len(home) == 0 and len(away) == 2:
                ordered = game.sort_values("TEAM_ABBREVIATION", kind="stable")
                h, a = ordered.iloc[0], ordered.iloc[1]
                neutral_site = True
            else:
                continue
            home_flag = None if neutral_site else True
            away_flag = None if neutral_site else False
            for own, opp, flag in ((h, a, home_flag), (a, h, away_flag)):
                history.append({
                    "team": str(own["TEAM_ABBREVIATION"]),
                    "team_points": float(own["PTS"]),
                    "opponent_points": float(opp["PTS"]),
                    "possessions": float(own["possessions"]) if pd.notna(own["possessions"]) else np.nan,
                    "game_date": date, "game_id": str(game_id), "is_home": flag,
                })
    result = pd.DataFrame(forecasts)
    if result.empty:
        raise RuntimeError("No forecasts generated; inspect team logs and matchup labels.")
    return result.sort_values(["date", "game_id"], kind="stable").reset_index(drop=True)


def _model_metrics(group: pd.DataFrame, home_points: str, away_points: str, probability: str) -> dict:
    actual_margin = group["actual_margin"].to_numpy(float)
    predicted_margin = group[home_points].to_numpy(float) - group[away_points].to_numpy(float)
    actual_home = group["actual_home_points"].to_numpy(float)
    actual_away = group["actual_away_points"].to_numpy(float)
    pred_home = group[home_points].to_numpy(float)
    pred_away = group[away_points].to_numpy(float)
    return {
        "games": int(len(group)),
        "home_points_mae": float(np.mean(np.abs(pred_home - actual_home))),
        "away_points_mae": float(np.mean(np.abs(pred_away - actual_away))),
        "combined_team_points_mae": float(np.mean(np.abs(pred_home - actual_home) + np.abs(pred_away - actual_away)) / 2.0),
        "margin_mae": float(np.mean(np.abs(predicted_margin - actual_margin))),
        "brier": _metrics(group["actual_home_win"].to_numpy(float), group[probability].to_numpy(float))["brier"],
        "log_loss": _metrics(group["actual_home_win"].to_numpy(float), group[probability].to_numpy(float))["log_loss"],
        "accuracy": _metrics(group["actual_home_win"].to_numpy(float), group[probability].to_numpy(float))["accuracy"],
    }


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Historical team logs not found: {INPUT}")
    raw = pd.read_parquet(INPUT)
    required = {"SEASON", "GAME_ID", "GAME_DATE", "MATCHUP", "TEAM_ABBREVIATION", "PTS"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise SystemExit(f"Input is missing columns: {missing}")
    pred = _walk_forward_predictions(raw)
    pred["validation_season"] = pred["season"].isin(VALIDATION_SEASONS)
    pred["final_holdout_season"] = pred["season"].isin(FINAL_HOLDOUT_SEASONS)

    # Select a single blend weight using 2024-25 only. 2025-26 remains untouched
    # until the blend is frozen. Alpha=0 is points-only; alpha=1 is efficiency-only.
    validation = pred.loc[pred["validation_season"]].copy()
    holdout = pred.loc[pred["final_holdout_season"]].copy()
    if validation.empty or holdout.empty:
        raise RuntimeError("Validation or final holdout split is empty.")
    blend_results = []
    for alpha in BLEND_GRID:
        margin = (
            (1.0 - alpha) * validation["predicted_margin"].to_numpy(float)
            + alpha * validation["efficiency_margin"].to_numpy(float)
        )
        p = ndtr(margin / validation["margin_sd"].to_numpy(float))
        m = _metrics(validation["actual_home_win"].to_numpy(float), p)
        actual_margin = validation["actual_margin"].to_numpy(float)
        blend_results.append({
            "alpha_efficiency": float(alpha),
            "brier": m["brier"], "log_loss": m["log_loss"],
            "accuracy": m["accuracy"],
            "margin_mae": float(np.mean(np.abs(margin - actual_margin))),
        })
    # Probability quality is the primary objective; use log loss as a tie-break.
    best = min(blend_results, key=lambda item: (item["brier"], item["log_loss"], item["alpha_efficiency"]))
    alpha = float(best["alpha_efficiency"])
    pred["selected_blend_margin"] = (
        (1.0 - alpha) * pred["predicted_margin"] + alpha * pred["efficiency_margin"]
    )
    pred["selected_blend_home_points"] = (
        (1.0 - alpha) * pred["predicted_home_points"] + alpha * pred["efficiency_home_points"]
    )
    pred["selected_blend_away_points"] = (
        (1.0 - alpha) * pred["predicted_away_points"] + alpha * pred["efficiency_away_points"]
    )
    pred["selected_blend_home_win_probability"] = ndtr(
        pred["selected_blend_margin"].to_numpy(float) / pred["margin_sd"].to_numpy(float)
    )

    period_metrics = {}
    for label, mask in (
        ("validation_2024_25", pred["validation_season"]),
        ("final_holdout_2025_26", pred["final_holdout_season"]),
    ):
        group = pred.loc[mask]
        period_metrics[label] = {
            "points_only": _model_metrics(group, "predicted_home_points", "predicted_away_points", "predicted_home_win_probability"),
            "efficiency_only": _model_metrics(group, "efficiency_home_points", "efficiency_away_points", "efficiency_home_win_probability"),
            "selected_blend": _model_metrics(group, "selected_blend_home_points", "selected_blend_away_points", "selected_blend_home_win_probability"),
        }

    season_metrics = {}
    for season, group in pred.groupby("season", sort=True):
        season_metrics[str(season)] = {
            "games": int(len(group)),
            "points_only": _model_metrics(group, "predicted_home_points", "predicted_away_points", "predicted_home_win_probability"),
            "efficiency_only": _model_metrics(group, "efficiency_home_points", "efficiency_away_points", "efficiency_home_win_probability"),
            "selected_blend": _model_metrics(group, "selected_blend_home_points", "selected_blend_away_points", "selected_blend_home_win_probability"),
            "efficiency_features_available_rate": float(group["efficiency_features_available"].mean()),
            "date_range": [str(group["date"].min().date()), str(group["date"].max().date())],
        }

    decision = (
        "blend improves Brier and log loss on validation; holdout result reported separately"
        if period_metrics["validation_2024_25"]["selected_blend"]["brier"] < period_metrics["validation_2024_25"]["points_only"]["brier"]
        and period_metrics["validation_2024_25"]["selected_blend"]["log_loss"] < period_metrics["validation_2024_25"]["points_only"]["log_loss"]
        else "selected blend does not improve both Brier and log loss on validation; keep points-only baseline"
    )
    report = {
        "scope": "NBA regular season 2018-19 through 2025-26; strict walk-forward; forecasts for all games on a date precede same-date results entering history",
        "input": str(INPUT.relative_to(ROOT)),
        "method": "Compare recency-weighted/shrunk points-only score estimates with box-score possession/efficiency estimates; select blend weight on 2024-25 validation only",
        "fit_seasons": sorted(TRAIN_SEASONS),
        "validation_seasons": sorted(VALIDATION_SEASONS),
        "final_holdout_seasons": sorted(FINAL_HOLDOUT_SEASONS),
        "blend_selection_objective": "minimum validation Brier score, then log loss, among alpha in 0.0..1.0 by 0.1; alpha=0 points-only, alpha=1 efficiency-only",
        "selected_alpha_efficiency": alpha,
        "validation_blend_grid": blend_results,
        "period_metrics": period_metrics,
        "season_metrics": season_metrics,
        "decision": decision,
        "limitations": [
            "This audit covers team score expectations and base win probabilities, not current roster adjustments, injuries, or the production coach-score Monte Carlo.",
            "Possessions use FGA + 0.44*FTA - OREB + TOV and therefore remain an estimate.",
            "2025-26 was not used to choose the blend weight.",
            "No production predictor was changed by this audit.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pred.to_csv(PRED_OUT, index=False)
    METRICS_OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "selected_alpha_efficiency": alpha,
        "validation_grid": blend_results,
        "period_metrics": period_metrics,
        "decision": decision,
        "outputs": [str(PRED_OUT), str(METRICS_OUT)],
    }, indent=2))
    print(f"\nDetailed predictions: {PRED_OUT}")
    print(f"Detailed metrics: {METRICS_OUT}")


if __name__ == "__main__":
    main()
