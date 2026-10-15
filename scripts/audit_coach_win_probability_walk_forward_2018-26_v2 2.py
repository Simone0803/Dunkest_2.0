from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logit
from sklearn.linear_model import LogisticRegression

from dunkest.models.coach import (
    _simulate_matchup_scores,
    TEAM_FORM_HALF_LIFE_GAMES,
    TEAM_FORM_PRIOR_GAMES,
    TEAM_VOLATILITY_PRIOR_GAMES,
)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "processed" / "team_game_logs_2018-26_v1.parquet"
OUT_DIR = ROOT / "reports" / "audit"
PRED_OUT = OUT_DIR / "coach_win_probability_walk_forward_2018-26_v2.csv"
METRICS_OUT = OUT_DIR / "coach_win_probability_walk_forward_2018-26_v2.json"
TRAIN_SEASONS = {"2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24"}
VALIDATION_SEASONS = {"2024-25"}
FINAL_HOLDOUT_SEASONS = {"2025-26"}


def _shrunk_recent_mean(group: pd.DataFrame, column: str, league_mean: float) -> float:
    values = pd.to_numeric(group.sort_values("game_date", kind="stable")[column], errors="coerce").dropna()
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


def _calibration_bins(actual: np.ndarray, probability: np.ndarray) -> list[dict]:
    frame = pd.DataFrame({"actual": actual, "probability": probability})
    frame["bin"] = pd.cut(frame["probability"], bins=np.linspace(0, 1, 11), include_lowest=True)
    result = []
    for interval, group in frame.groupby("bin", observed=True):
        result.append({
            "bin": str(interval),
            "n": int(len(group)),
            "mean_predicted": float(group["probability"].mean()),
            "actual_win_rate": float(group["actual"].mean()),
        })
    return result


def _walk_forward_predictions(raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.copy()
    d["GAME_DATE"] = pd.to_datetime(d["GAME_DATE"], errors="coerce")
    d["TEAM_ABBREVIATION"] = d["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    d["GAME_ID"] = d["GAME_ID"].astype(str)
    d["PTS"] = pd.to_numeric(d["PTS"], errors="coerce")
    d["MIN"] = pd.to_numeric(d.get("MIN", np.nan), errors="coerce")
    d["is_home"] = d["MATCHUP"].astype(str).str.contains(r"vs\.", regex=True)
    d = d.dropna(subset=["GAME_DATE", "PTS", "SEASON"])
    d = d.sort_values(["GAME_DATE", "GAME_ID", "TEAM_ABBREVIATION"], kind="stable")
    game_team_count = d.groupby(["SEASON", "GAME_ID"])["TEAM_ABBREVIATION"].nunique()
    complete = set(game_team_count[game_team_count.eq(2)].index)
    d = d.loc[pd.MultiIndex.from_frame(d[["SEASON", "GAME_ID"]]).isin(complete)].copy()

    history: list[dict] = []
    forecasts: list[dict] = []
    for date, same_day in d.groupby("GAME_DATE", sort=True):
        if history:
            hist = pd.DataFrame(history)
            league_mean = float(hist["team_points"].mean())
            league_sd = float(np.clip(hist["team_points"].std(ddof=1), 8.0, 18.0))
            prior_games = hist.drop_duplicates(["season", "game_id"])
            overtime_probability = float((prior_games["overtime"].sum() + 1.0) / (len(prior_games) + 25.0))
            profiles: dict[str, dict[str, float]] = {}
            score_sds: dict[str, float] = {}
            for team, group in hist.groupby("team"):
                group = group.sort_values("game_date", kind="stable")
                n = len(group)
                profiles[team] = {
                    "offense": _shrunk_recent_mean(group, "team_points", league_mean),
                    "defense_allowed": _shrunk_recent_mean(group, "opponent_points", league_mean),
                    "games": n,
                }
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
                home_margin = (paired[True] - paired[False]).dropna()
                if len(home_margin) >= 10:
                    home_advantage = float(np.clip(home_margin.mean() / 2.0, -3.0, 3.0))
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
                    # Neutral-site games are labeled away for both teams. Use a
                    # deterministic orientation, but never award home advantage.
                    ordered = game.sort_values("TEAM_ABBREVIATION", kind="stable")
                    h, a = ordered.iloc[0], ordered.iloc[1]
                    neutral_site = True
                else:
                    continue
                home_team, away_team = str(h["TEAM_ABBREVIATION"]), str(a["TEAM_ABBREVIATION"])
                home_profile = profiles.get(home_team, {"offense": league_mean, "defense_allowed": league_mean, "games": 0})
                away_profile = profiles.get(away_team, {"offense": league_mean, "defense_allowed": league_mean, "games": 0})
                applied_home_advantage = 0.0 if neutral_site else home_advantage
                expected_home = home_profile["offense"] + away_profile["defense_allowed"] - league_mean + applied_home_advantage
                expected_away = away_profile["offense"] + home_profile["defense_allowed"] - league_mean - applied_home_advantage
                home_sd = score_sds.get(home_team, league_sd)
                away_sd = score_sds.get(away_team, league_sd)
                margin_sd = max(float(np.sqrt(home_sd**2 + away_sd**2 - 2 * score_correlation * home_sd * away_sd)), 5.0)
                simulated_home, simulated_away, _ = _simulate_matchup_scores(
                    expected_home, expected_away, home_sd, away_sd, score_correlation,
                    f"{season}-{game_id}-coach-winprob-v2", overtime_probability, draws=8192,
                )
                simulated_home_win_probability = float(np.mean(simulated_home > simulated_away))
                forecasts.append({
                    "season": str(season),
                    "date": date,
                    "game_id": str(game_id),
                    "home_team": home_team,
                    "away_team": away_team,
                    "predicted_home_points": float(expected_home),
                    "predicted_away_points": float(expected_away),
                    "predicted_margin": float(expected_home - expected_away),
                    "predicted_home_win_probability": simulated_home_win_probability,
                    "overtime_probability_prior": float(overtime_probability),
                    "actual_home_points": float(h["PTS"]),
                    "actual_away_points": float(a["PTS"]),
                    "actual_home_win": float(h["PTS"] > a["PTS"]),
                    "home_games_seen": int(home_profile["games"]),
                    "away_games_seen": int(away_profile["games"]),
                    "home_advantage_estimate": float(applied_home_advantage),
                    "neutral_site": bool(neutral_site),
                    "score_correlation_estimate": float(score_correlation),
                })

        # Append same-date outcomes only after all games for that date were forecast.
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
            overtime = bool(game["MIN"].gt(240).any()) if game["MIN"].notna().any() else False
            history.append({
                "season": str(season), "team": str(h["TEAM_ABBREVIATION"]),
                "team_points": float(h["PTS"]), "opponent_points": float(a["PTS"]),
                "game_date": date, "game_id": str(game_id),
                "is_home": home_flag, "overtime": overtime,
            })
            history.append({
                "season": str(season), "team": str(a["TEAM_ABBREVIATION"]),
                "team_points": float(a["PTS"]), "opponent_points": float(h["PTS"]),
                "game_date": date, "game_id": str(game_id),
                "is_home": away_flag, "overtime": overtime,
            })
    result = pd.DataFrame(forecasts)
    if result.empty:
        raise RuntimeError("No forecasts generated; inspect team game log schema and matchup labels.")
    return result.sort_values(["date", "game_id"], kind="stable").reset_index(drop=True)


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Historical team logs not found: {INPUT}")
    raw = pd.read_parquet(INPUT)
    required = {"SEASON", "GAME_ID", "GAME_DATE", "MATCHUP", "TEAM_ABBREVIATION", "PTS", "MIN"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise SystemExit(f"Input is missing columns: {missing}")
    pred = _walk_forward_predictions(raw)
    p = pred["predicted_home_win_probability"].to_numpy(dtype=float)
    y = pred["actual_home_win"].to_numpy(dtype=float)
    pred["absolute_margin_error"] = (
        pred["predicted_margin"] - (pred["actual_home_points"] - pred["actual_away_points"])
    ).abs()

    # Calibration protocol is fixed in advance; the raw probability now uses the production Monte Carlo score simulator and a past-only overtime prior: train only through 2023-24,
    # inspect 2024-25 validation, then report 2025-26 final holdout once.
    train_mask = pred["season"].isin(TRAIN_SEASONS) & (
        pred[["home_games_seen", "away_games_seen"]].min(axis=1) >= 5
    )
    validation_mask = pred["season"].isin(VALIDATION_SEASONS)
    holdout_mask = pred["season"].isin(FINAL_HOLDOUT_SEASONS)
    if not train_mask.any() or not validation_mask.any() or not holdout_mask.any():
        raise RuntimeError("Calibration train, validation, or final holdout split is empty.")
    calibrator = LogisticRegression(C=1e6, solver="lbfgs", max_iter=2000)
    calibrator.fit(logit(np.clip(p[train_mask], 1e-5, 1 - 1e-5)).reshape(-1, 1), y[train_mask])
    pred["platt_calibrated_probability"] = np.nan
    apply_mask = validation_mask | holdout_mask
    pred.loc[apply_mask, "platt_calibrated_probability"] = calibrator.predict_proba(
        logit(np.clip(p[apply_mask], 1e-5, 1 - 1e-5)).reshape(-1, 1)
    )[:, 1]

    season_metrics: dict[str, dict] = {}
    for season, group in pred.groupby("season", sort=True):
        actual = group["actual_home_win"].to_numpy(dtype=float)
        raw_probability = group["predicted_home_win_probability"].to_numpy(dtype=float)
        season_metrics[str(season)] = {
            "raw": _metrics(actual, raw_probability),
            "raw_calibration_bins": _calibration_bins(actual, raw_probability),
            "margin_mae": float(group["absolute_margin_error"].mean()),
            "games": int(len(group)),
            "date_range": [str(group["date"].min().date()), str(group["date"].max().date())],
        }
        if season in VALIDATION_SEASONS or season in FINAL_HOLDOUT_SEASONS:
            calibrated = group["platt_calibrated_probability"].to_numpy(dtype=float)
            season_metrics[str(season)]["platt_calibrated"] = _metrics(actual, calibrated)

    def period_report(mask: pd.Series) -> dict:
        group = pred.loc[mask]
        return {
            "games": int(len(group)),
            "raw": _metrics(group["actual_home_win"].to_numpy(float), group["predicted_home_win_probability"].to_numpy(float)),
            "platt_calibrated": _metrics(group["actual_home_win"].to_numpy(float), group["platt_calibrated_probability"].to_numpy(float)),
        }

    validation = period_report(validation_mask)
    final_holdout = period_report(holdout_mask)
    validation_brier_delta = validation["platt_calibrated"]["brier"] - validation["raw"]["brier"]
    validation_logloss_delta = validation["platt_calibrated"]["log_loss"] - validation["raw"]["log_loss"]
    if validation_brier_delta < 0 and validation_logloss_delta < 0:
        validation_decision = "candidate improves both Brier and log loss on 2024-25 validation; inspect final holdout before any production change"
    elif validation_brier_delta > 0 and validation_logloss_delta > 0:
        validation_decision = "candidate worsens both Brier and log loss on 2024-25 validation; do not deploy"
    else:
        validation_decision = "mixed validation result; do not deploy without more seasons"

    metrics = {
        "scope": "NBA regular season 2018-19 through 2025-26; strict chronological walk-forward; every game on a date is forecast before that date's results enter history",
        "input": str(INPUT.relative_to(ROOT)),
        "final_holdout_policy": "2025-26 was excluded from calibration fitting and all model-selection decisions; evaluated only after the fixed calibrator was trained on seasons through 2023-24 and validation was measured on 2024-25",
        "calibration_fit_seasons": sorted(TRAIN_SEASONS),
        "calibration_training_games": int(train_mask.sum()),
        "validation_seasons": sorted(VALIDATION_SEASONS),
        "validation": validation,
        "final_holdout_seasons": sorted(FINAL_HOLDOUT_SEASONS),
        "probability_method": "production _simulate_matchup_scores; past-only overtime rate; chronological team-point mean/volatility/correlation; calibration split unchanged",
        "final_holdout": final_holdout,
        "validation_decision": validation_decision,
        "calibration_parameters": {
            "method": "Platt scaling / logistic regression on logit(raw probability)",
            "slope": float(calibrator.coef_[0, 0]),
            "intercept": float(calibrator.intercept_[0]),
        },
        "season_metrics": season_metrics,
        "all_games_raw": _metrics(y, p),
        "constant_50_percent_baseline_brier": float(np.mean((0.5 - y) ** 2)),
        "constant_50_percent_baseline_log_loss": float(-np.mean(y * np.log(0.5) + (1 - y) * np.log(0.5))),
        "limitations": [
            "This evaluates the team-score/base probability component, not the current-roster adjustment or pre-game injuries.",
            "Probabilities use a normal approximation for score margin, not the production rounded-score Monte Carlo.",
            "One validation season and one final holdout season are useful evidence but not enough to guarantee calibration stability.",
            "No production model was changed by this audit.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pred.to_csv(PRED_OUT, index=False)
    METRICS_OUT.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({
        "all_games_raw": metrics["all_games_raw"],
        "constant_50_percent_baseline_brier": metrics["constant_50_percent_baseline_brier"],
        "calibration_training_games": metrics["calibration_training_games"],
        "validation": validation,
        "final_holdout": final_holdout,
        "validation_decision": validation_decision,
        "calibration_parameters": metrics["calibration_parameters"],
        "season_summary": {
            season: {
                "games": values["games"],
                "raw_brier": values["raw"]["brier"],
                "raw_log_loss": values["raw"]["log_loss"],
                "raw_accuracy": values["raw"]["accuracy"],
                "margin_mae": values["margin_mae"],
            } for season, values in season_metrics.items()
        },
        "outputs": [str(PRED_OUT), str(METRICS_OUT)],
    }, indent=2))
    print(f"\nDetailed predictions: {PRED_OUT}")
    print(f"Detailed metrics: {METRICS_OUT}")


if __name__ == "__main__":
    main()
