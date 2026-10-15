from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr, logit, expit
from sklearn.linear_model import LogisticRegression

from dunkest.models.coach import (
    TEAM_FORM_HALF_LIFE_GAMES,
    TEAM_FORM_PRIOR_GAMES,
    TEAM_VOLATILITY_PRIOR_GAMES,
)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "processed" / "team_game_logs_2025-26.parquet"
OUT_DIR = ROOT / "reports" / "audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _weighted_shrunk(values: pd.Series, league_mean: float) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return float(league_mean)
    age = np.arange(len(values) - 1, -1, -1, dtype=float)
    weights = np.exp2(-age / TEAM_FORM_HALF_LIFE_GAMES)
    weights /= weights.sum()
    recent = float(np.average(values.to_numpy(dtype=float), weights=weights))
    return float(league_mean + len(values) / (len(values) + TEAM_FORM_PRIOR_GAMES) * (recent - league_mean))


def _probability_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "n": int(len(y)),
        "brier": float(np.mean((p - y) ** 2)),
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "accuracy": float(np.mean((p >= 0.5) == y)),
        "mean_predicted_probability": float(np.mean(p)),
        "actual_win_rate": float(np.mean(y)),
        "mean_absolute_probability_error": float(np.mean(np.abs(p - y))),
    }


def main() -> None:
    raw = pd.read_parquet(INPUT)
    required = {"Game_ID", "GAME_DATE", "MATCHUP", "TEAM_ABBREVIATION", "PTS"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise SystemExit(f"Missing columns in {INPUT}: {missing}")

    d = raw.copy()
    d["game_id"] = d["Game_ID"].astype(str)
    d["date"] = pd.to_datetime(d["GAME_DATE"], errors="coerce")
    d["team"] = d["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    d["points"] = pd.to_numeric(d["PTS"], errors="coerce")
    d["is_home"] = d["MATCHUP"].astype(str).str.contains(r"vs\.", regex=True)
    d = d.dropna(subset=["date", "points"])
    # Keep only complete two-team games; never use a game's scores until after
    # its date has been forecast.
    game_sizes = d.groupby("game_id")["team"].nunique()
    d = d.loc[d["game_id"].isin(game_sizes[game_sizes == 2].index)].copy()
    d = d.sort_values(["date", "game_id", "team"], kind="stable")

    historical: list[dict] = []
    predictions: list[dict] = []
    for date, same_day in d.groupby("date", sort=True):
        if historical:
            hist = pd.DataFrame(historical)
            league_mean = float(hist["team_points"].mean())
            league_sd = float(np.clip(hist["team_points"].std(ddof=1), 8, 18))
            profile: dict[str, dict[str, float]] = {}
            score_sd: dict[str, float] = {}
            for team, group in hist.groupby("team"):
                group = group.sort_values("game_date", kind="stable")
                n = len(group)
                profile[team] = {
                    "offense": _weighted_shrunk(group["team_points"], league_mean),
                    "defense_allowed": _weighted_shrunk(group["opponent_points"], league_mean),
                    "games": n,
                }
                sample_sd = float(group["team_points"].std(ddof=1)) if n > 1 else league_sd
                if not np.isfinite(sample_sd):
                    sample_sd = league_sd
                variance = ((n - 1) * sample_sd**2 + TEAM_VOLATILITY_PRIOR_GAMES * league_sd**2) / (
                    max(n - 1, 0) + TEAM_VOLATILITY_PRIOR_GAMES
                )
                score_sd[team] = float(np.clip(np.sqrt(variance), 8, 18))

            game_pairs = hist.drop_duplicates("game_id")
            # Estimate home advantage only from games completed before this date.
            paired = hist.pivot_table(index="game_id", columns="is_home", values="team_points", aggfunc="first")
            home_adv = 0.0
            if False in paired and True in paired:
                margins = (paired[True] - paired[False]).dropna()
                if len(margins) >= 10:
                    home_adv = float(np.clip(margins.mean() / 2.0, -3.0, 3.0))
            rho = 0.1
            if len(paired) >= 10:
                complete_pairs = paired.dropna(subset=[False, True])
                if len(complete_pairs) >= 10:
                    estimate = complete_pairs[False].corr(complete_pairs[True])
                    if np.isfinite(estimate):
                        rho = float(np.clip(estimate, -0.4, 0.6))

            for game_id, game in same_day.groupby("game_id", sort=False):
                if len(game) != 2:
                    continue
                home = game.loc[game["is_home"]]
                away = game.loc[~game["is_home"]]
                if len(home) != 1 or len(away) != 1:
                    continue
                h, a = home.iloc[0], away.iloc[0]
                ht, at = h["team"], a["team"]
                hprof = profile.get(ht, {"offense": league_mean, "defense_allowed": league_mean, "games": 0})
                aprof = profile.get(at, {"offense": league_mean, "defense_allowed": league_mean, "games": 0})
                hpts = hprof["offense"] + aprof["defense_allowed"] - league_mean + home_adv
                apts = aprof["offense"] + hprof["defense_allowed"] - league_mean - home_adv
                hsd, asd = score_sd.get(ht, league_sd), score_sd.get(at, league_sd)
                margin_sd = max(float(np.sqrt(hsd**2 + asd**2 - 2 * rho * hsd * asd)), 5.0)
                p_home = float(ndtr((hpts - apts) / margin_sd))
                actual_home = float(h["points"] > a["points"])
                predictions.append({
                    "date": date, "game_id": game_id, "home_team": ht, "away_team": at,
                    "predicted_home_points": hpts, "predicted_away_points": apts,
                    "predicted_margin": hpts - apts, "predicted_home_win_probability": p_home,
                    "actual_home_points": float(h["points"]), "actual_away_points": float(a["points"]),
                    "actual_home_win": actual_home, "home_games_seen": hprof["games"],
                    "away_games_seen": aprof["games"],
                })

        # Only after every same-day forecast is recorded are these results added
        # to the history for later dates.
        rows = same_day.to_dict("records")
        by_game = {gid: g for gid, g in same_day.groupby("game_id", sort=False)}
        for game_id, game in by_game.items():
            if len(game) != 2:
                continue
            home = game.loc[game["is_home"]]
            away = game.loc[~game["is_home"]]
            if len(home) != 1 or len(away) != 1:
                continue
            h, a = home.iloc[0], away.iloc[0]
            historical.append({"team": h["team"], "team_points": float(h["points"]),
                               "opponent_points": float(a["points"]), "game_date": date,
                               "game_id": game_id, "is_home": True})
            historical.append({"team": a["team"], "team_points": float(a["points"]),
                               "opponent_points": float(h["points"]), "game_date": date,
                               "game_id": game_id, "is_home": False})

    pred = pd.DataFrame(predictions)
    if pred.empty:
        raise SystemExit("No complete forecastable games were generated.")
    # Ignore the first 10 calendar days only for the primary score, when the
    # teams have little in-season evidence; also report all games separately.
    pred["absolute_margin_error"] = (pred["predicted_margin"] - (pred["actual_home_points"] - pred["actual_away_points"])).abs()
    pred["squared_margin_error"] = (pred["predicted_margin"] - (pred["actual_home_points"] - pred["actual_away_points"])) ** 2
    actual = pred["actual_home_win"].to_numpy(dtype=float)
    probability = pred["predicted_home_win_probability"].to_numpy(dtype=float)
    eligible = pred[["home_games_seen", "away_games_seen"]].min(axis=1).to_numpy() >= 5

    # Chronological calibration experiment: the final 30% of game dates is a
    # holdout and is never used to fit the Platt/logistic calibration.
    dates = sorted(pred["date"].drop_duplicates())
    split_index = max(1, min(len(dates) - 1, int(len(dates) * 0.70)))
    calibration_cutoff = dates[split_index]
    train_mask = pred["date"].lt(calibration_cutoff).to_numpy()
    holdout_mask = ~train_mask
    calibration_model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=2000)
    calibration_model.fit(logit(np.clip(probability[train_mask], 1e-5, 1 - 1e-5)).reshape(-1, 1), actual[train_mask])
    calibrated_probability = calibration_model.predict_proba(
        logit(np.clip(probability[holdout_mask], 1e-5, 1 - 1e-5)).reshape(-1, 1)
    )[:, 1]
    holdout_actual = actual[holdout_mask]
    holdout_raw_probability = probability[holdout_mask]
    calibration_holdout = {
        "train_period_end_exclusive": str(pd.Timestamp(calibration_cutoff).date()),
        "holdout_start_inclusive": str(pd.Timestamp(calibration_cutoff).date()),
        "train_games": int(train_mask.sum()),
        "holdout_games": int(holdout_mask.sum()),
        "raw_holdout": _probability_metrics(holdout_actual, holdout_raw_probability),
        "platt_calibrated_holdout": _probability_metrics(holdout_actual, calibrated_probability),
        "platt_parameters": {
            "slope": float(calibration_model.coef_[0, 0]),
            "intercept": float(calibration_model.intercept_[0]),
        },
        "deployment_decision": "diagnostic only; do not deploy from a single-season split",
    }

    metrics = {
        "scope": "2025-26 season; strict date-level walk-forward; all games on a date forecast before any results from that date are added",
        "input": str(INPUT.relative_to(ROOT)),
        "total_forecast_games": int(len(pred)),
        "chronological_calibration_holdout": calibration_holdout,
        "forecast_date_range": [str(pred["date"].min().date()), str(pred["date"].max().date())],
        "first_10_calendar_days_excluded_from_primary": "No; primary metrics include all games, with a separate >=5 prior games/team cohort",
        "all_games": _probability_metrics(actual, probability),
        "teams_with_at_least_5_prior_games": _probability_metrics(actual[eligible], probability[eligible]) if eligible.any() else {},
        "constant_50_percent_baseline_brier": float(np.mean((0.5 - actual) ** 2)),
        "constant_50_percent_baseline_log_loss": float(-np.mean(actual * np.log(0.5) + (1 - actual) * np.log(0.5))),
        "margin_mae": float(pred["absolute_margin_error"].mean()),
        "margin_rmse": float(np.sqrt(pred["squared_margin_error"].mean())),
        "calibration_bins": [],
        "limitations": [
            "Single-season diagnostic, not sufficient to tune or deploy a probability calibration.",
            "The walk-forward forecast models points scored/allowed; it does not include the current roster adjustment or archived pre-match injury reports.",
            "Probabilities use a normal approximation to score-margin uncertainty, not the exact production Monte Carlo.",
        ],
    }
    bins = pd.cut(pred["predicted_home_win_probability"], bins=np.linspace(0, 1, 11), include_lowest=True)
    for interval, group in pred.groupby(bins, observed=True):
        metrics["calibration_bins"].append({
            "bin": str(interval), "n": int(len(group)),
            "mean_predicted": float(group["predicted_home_win_probability"].mean()),
            "actual_win_rate": float(group["actual_home_win"].mean()),
        })
    csv_path = OUT_DIR / "coach_win_probability_walk_forward_2025-26.csv"
    json_path = OUT_DIR / "coach_win_probability_walk_forward_2025-26.json"
    pred.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    print(f"\nPredictions: {csv_path}")
    print(f"Metrics: {json_path}")


if __name__ == "__main__":
    main()
