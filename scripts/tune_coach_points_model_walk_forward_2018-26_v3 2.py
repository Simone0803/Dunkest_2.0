from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

from dunkest.models.coach import TEAM_VOLATILITY_PRIOR_GAMES

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "processed" / "team_game_logs_2018-26_v1.parquet"
OUT_DIR = ROOT / "reports" / "audit"
PRED_OUT = OUT_DIR / "coach_points_model_tuning_walk_forward_2018-26_v3.csv"
METRICS_OUT = OUT_DIR / "coach_points_model_tuning_walk_forward_2018-26_v3.json"
VALIDATION_SEASONS = {"2024-25"}
FINAL_HOLDOUT_SEASONS = {"2025-26"}
HALF_LIFE_GRID = (8.0, 15.0, 30.0)
PRIOR_GAMES = 8.0


def _shrunk_recent_mean(
    group: pd.DataFrame, column: str, league_mean: float, half_life_games: float
) -> float:
    values = pd.to_numeric(
        group.sort_values("game_date", kind="stable")[column], errors="coerce"
    ).dropna()
    if values.empty:
        return float(league_mean)
    age = np.arange(len(values) - 1, -1, -1, dtype=float)
    weights = np.exp2(-age / half_life_games)
    weights /= weights.sum()
    recent = float(np.average(values.to_numpy(dtype=float), weights=weights))
    reliability = len(values) / (len(values) + PRIOR_GAMES)
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


def _walk_forward_predictions(raw: pd.DataFrame, half_life_games: float) -> pd.DataFrame:
    d = raw.copy()
    d["GAME_DATE"] = pd.to_datetime(d["GAME_DATE"], errors="coerce")
    d["TEAM_ABBREVIATION"] = d["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    d["GAME_ID"] = d["GAME_ID"].astype(str)
    d["PTS"] = pd.to_numeric(d["PTS"], errors="coerce")
    d["is_home"] = d["MATCHUP"].astype(str).str.contains(r"vs\.", regex=True)
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
            league_mean = float(hist["team_points"].mean())
            league_sd = float(np.clip(hist["team_points"].std(ddof=1), 8.0, 18.0))
            profiles: dict[str, dict[str, float]] = {}
            score_sds: dict[str, float] = {}
            for team, group in hist.groupby("team"):
                group = group.sort_values("game_date", kind="stable")
                n = len(group)
                profiles[team] = {
                    "offense": _shrunk_recent_mean(group, "team_points", league_mean, half_life_games),
                    "defense_allowed": _shrunk_recent_mean(group, "opponent_points", league_mean, half_life_games),
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
                hp = profiles.get(home_team, {"offense": league_mean, "defense_allowed": league_mean, "games": 0})
                ap = profiles.get(away_team, {"offense": league_mean, "defense_allowed": league_mean, "games": 0})
                ha = 0.0 if neutral_site else home_advantage
                expected_home = hp["offense"] + ap["defense_allowed"] - league_mean + ha
                expected_away = ap["offense"] + hp["defense_allowed"] - league_mean - ha
                sd_home, sd_away = score_sds.get(home_team, league_sd), score_sds.get(away_team, league_sd)
                margin_sd = max(float(np.sqrt(sd_home**2 + sd_away**2 - 2 * score_correlation * sd_home * sd_away)), 5.0)
                actual_home_points, actual_away_points = float(h["PTS"]), float(a["PTS"])
                forecasts.append({
                    "half_life_games": half_life_games,
                    "season": str(season), "date": date, "game_id": str(game_id),
                    "home_team": home_team, "away_team": away_team,
                    "predicted_home_points": float(expected_home),
                    "predicted_away_points": float(expected_away),
                    "predicted_margin": float(expected_home - expected_away),
                    "predicted_home_win_probability": float(ndtr((expected_home - expected_away) / margin_sd)),
                    "actual_home_points": actual_home_points,
                    "actual_away_points": actual_away_points,
                    "actual_margin": actual_home_points - actual_away_points,
                    "actual_home_win": float(actual_home_points > actual_away_points),
                    "home_games_seen": int(hp["games"]), "away_games_seen": int(ap["games"]),
                    "home_advantage_estimate": float(ha), "neutral_site": bool(neutral_site),
                })

        # Append only after all games on this date have been forecast.
        for (_, _), game in same_day.groupby(["SEASON", "GAME_ID"], sort=False):
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
            home_flag, away_flag = (None, None) if neutral_site else (True, False)
            history.extend([
                {"team": str(h["TEAM_ABBREVIATION"]), "team_points": float(h["PTS"]), "opponent_points": float(a["PTS"]), "game_date": date, "game_id": str(h["GAME_ID"]), "is_home": home_flag},
                {"team": str(a["TEAM_ABBREVIATION"]), "team_points": float(a["PTS"]), "opponent_points": float(h["PTS"]), "game_date": date, "game_id": str(a["GAME_ID"]), "is_home": away_flag},
            ])
    result = pd.DataFrame(forecasts)
    if result.empty:
        raise RuntimeError("No forecasts generated; inspect team logs and matchup labels.")
    return result.sort_values(["date", "game_id"], kind="stable").reset_index(drop=True)


def _period_metrics(group: pd.DataFrame) -> dict:
    p = group["predicted_home_win_probability"].to_numpy(float)
    y = group["actual_home_win"].to_numpy(float)
    margin = group["predicted_margin"].to_numpy(float)
    actual_margin = group["actual_margin"].to_numpy(float)
    return {
        "games": int(len(group)),
        **_metrics(y, p),
        "home_points_mae": float(np.mean(np.abs(group["predicted_home_points"] - group["actual_home_points"]))),
        "away_points_mae": float(np.mean(np.abs(group["predicted_away_points"] - group["actual_away_points"]))),
        "margin_mae": float(np.mean(np.abs(margin - actual_margin))),
        "mean_margin_bias": float(np.mean(margin - actual_margin)),
    }


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Historical team logs not found: {INPUT}")
    raw = pd.read_parquet(INPUT)
    required = {"SEASON", "GAME_ID", "GAME_DATE", "MATCHUP", "TEAM_ABBREVIATION", "PTS"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise SystemExit(f"Input is missing columns: {missing}")

    frames = []
    for half_life in HALF_LIFE_GRID:
        print(f"Running walk-forward with half-life={half_life:g} games...", flush=True)
        frames.append(_walk_forward_predictions(raw, half_life))
    predictions = pd.concat(frames, ignore_index=True)
    validation = predictions.loc[predictions["season"].isin(VALIDATION_SEASONS)]
    holdout = predictions.loc[predictions["season"].isin(FINAL_HOLDOUT_SEASONS)]
    if validation.empty or holdout.empty:
        raise RuntimeError("Validation or final holdout split is empty.")

    candidate_results = []
    for half_life in HALF_LIFE_GRID:
        v = validation.loc[validation["half_life_games"].eq(half_life)]
        candidate_results.append({
            "half_life_games": half_life,
            "validation": _period_metrics(v),
            "final_holdout": _period_metrics(holdout.loc[holdout["half_life_games"].eq(half_life)]),
        })
    selected = min(candidate_results, key=lambda x: (x["validation"]["brier"], x["validation"]["log_loss"]))
    selected_half_life = float(selected["half_life_games"])
    selected_holdout = holdout.loc[holdout["half_life_games"].eq(selected_half_life)]
    baseline_validation = validation.loc[validation["half_life_games"].eq(15.0)]
    baseline_holdout = holdout.loc[holdout["half_life_games"].eq(15.0)]

    report = {
        "scope": "NBA regular season 2018-19 through 2025-26; strict chronological walk-forward",
        "input": str(INPUT.relative_to(ROOT)),
        "model": "recency-weighted and league-shrunk team points for/against; win probability from normal approximation of point margin",
        "fixed_prior_games": PRIOR_GAMES,
        "candidate_half_lives_games": list(HALF_LIFE_GRID),
        "selection_rule": "minimum 2024-25 validation Brier score, log loss as tie-break; 2025-26 excluded from selection",
        "validation_seasons": sorted(VALIDATION_SEASONS),
        "final_holdout_seasons": sorted(FINAL_HOLDOUT_SEASONS),
        "selected_half_life_games": selected_half_life,
        "candidate_results": candidate_results,
        "selected_model_validation": selected["validation"],
        "selected_model_final_holdout": selected["final_holdout"],
        "current_setting_half_life_15_validation": _period_metrics(baseline_validation),
        "current_setting_half_life_15_final_holdout": _period_metrics(baseline_holdout),
        "selected_vs_current_validation_brier_delta": selected["validation"]["brier"] - _period_metrics(baseline_validation)["brier"],
        "selected_vs_current_holdout_brier_delta": selected["final_holdout"]["brier"] - _period_metrics(baseline_holdout)["brier"],
        "production_changed": False,
        "limitations": [
            "This audit evaluates the team score/base probability component, not current roster adjustments or injuries.",
            "Only the recency half-life is tuned; the shrinkage prior remains fixed at 8 games.",
            "The 2025-26 holdout is reported only after selecting the setting on 2024-25 validation.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(PRED_OUT, index=False)
    METRICS_OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "selected_half_life_games": selected_half_life,
        "candidate_results": candidate_results,
        "selected_vs_current_validation_brier_delta": report["selected_vs_current_validation_brier_delta"],
        "selected_vs_current_holdout_brier_delta": report["selected_vs_current_holdout_brier_delta"],
        "outputs": [str(PRED_OUT), str(METRICS_OUT)],
    }, indent=2))
    print(f"\nDetailed predictions: {PRED_OUT}")
    print(f"Detailed metrics: {METRICS_OUT}")


if __name__ == "__main__":
    main()
