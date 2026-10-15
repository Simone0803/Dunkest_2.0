from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr, ndtri
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
TEAM_LOGS = ROOT / "data" / "processed" / "team_game_logs_2018-26_v1.parquet"
PDK_TRAINING = ROOT / "data" / "processed" / "dunkest_pdk_game_training_2020-26_v3.parquet"
BASE_FORECASTS = ROOT / "reports" / "audit" / "coach_points_model_tuning_walk_forward_2018-26_v3.csv"
OUT_DIR = ROOT / "reports" / "audit"
PRED_OUT = OUT_DIR / "coach_roster_strength_proxy_walk_forward_2020-26_v1.csv"
METRICS_OUT = OUT_DIR / "coach_roster_strength_proxy_walk_forward_2020-26_v1.json"
TRAIN_SEASONS = {"2020-21", "2021-22", "2022-23", "2023-24"}
VALIDATION_SEASONS = {"2024-25"}
FINAL_HOLDOUT_SEASONS = {"2025-26"}
MIN_PLAYERS_PER_TEAM_GAME = 7
MIN_PRIOR_PDK_GAMES = 3
RIDGE_ALPHA = 10.0


def _metrics(frame: pd.DataFrame, probability_col: str, predicted_points_col: str) -> dict:
    p = np.clip(frame[probability_col].to_numpy(float), 1e-6, 1 - 1e-6)
    y = frame["actual_home_win"].to_numpy(float)
    predicted_margin = frame[predicted_points_col].to_numpy(float)
    actual_margin = frame["actual_margin"].to_numpy(float)
    return {
        "games": int(len(frame)),
        "brier": float(np.mean((p - y) ** 2)),
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "accuracy": float(np.mean((p >= 0.5) == y)),
        "margin_mae": float(np.mean(np.abs(predicted_margin - actual_margin))),
    }


def main() -> None:
    for path in (TEAM_LOGS, PDK_TRAINING, BASE_FORECASTS):
        if not path.exists():
            raise SystemExit(f"Required input not found: {path}")

    team_logs = pd.read_parquet(TEAM_LOGS, columns=[
        "SEASON", "GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION", "PTS"
    ])
    team_logs["SEASON"] = team_logs["SEASON"].astype(str)
    team_logs["GAME_ID"] = team_logs["GAME_ID"].astype(str)
    team_logs["TEAM_ABBREVIATION"] = team_logs["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()

    pdk = pd.read_parquet(PDK_TRAINING, columns=[
        "season_label", "game_date", "nba_GAME_ID", "nba_TEAM_ABBREVIATION",
        "target_pdk", "dunkest_player_id"
    ])
    pdk["nba_GAME_ID"] = pdk["nba_GAME_ID"].astype(str)
    pdk["nba_TEAM_ABBREVIATION"] = pdk["nba_TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    pdk["target_pdk"] = pd.to_numeric(pdk["target_pdk"], errors="coerce")
    pdk["game_date"] = pd.to_datetime(pdk["game_date"], errors="coerce")
    pdk = pdk.dropna(subset=["target_pdk", "game_date"])
    pdk = pdk.loc[
        pdk["nba_GAME_ID"].str.lower().ne("nan")
        & pdk["nba_TEAM_ABBREVIATION"].ne("NAN")
    ]
    team_pdk = pdk.groupby(
        ["nba_GAME_ID", "nba_TEAM_ABBREVIATION", "game_date"], as_index=False
    ).agg(
        team_pdk=("target_pdk", "sum"),
        player_count=("dunkest_player_id", "nunique"),
    )
    team_pdk = team_pdk.loc[team_pdk["player_count"].ge(MIN_PLAYERS_PER_TEAM_GAME)].copy()
    team_pdk = team_pdk.sort_values(["game_date", "nba_GAME_ID", "nba_TEAM_ABBREVIATION"], kind="stable")

    # Feature for a game is built strictly from prior valid team-game PDK totals.
    team_pdk["pdk_roll5"] = team_pdk.groupby("nba_TEAM_ABBREVIATION")["team_pdk"].transform(
        lambda values: values.shift(1).rolling(5, min_periods=MIN_PRIOR_PDK_GAMES).mean()
    )
    daily_league = team_pdk.groupby("game_date")["team_pdk"].mean().sort_index()
    daily_prior_league_mean = daily_league.shift(1).expanding(min_periods=1).mean()
    team_pdk["league_pdk_mean_before_date"] = team_pdk["game_date"].map(daily_prior_league_mean)
    team_pdk["pdk_strength_delta"] = team_pdk["pdk_roll5"] - team_pdk["league_pdk_mean_before_date"]

    forecasts = pd.read_csv(BASE_FORECASTS, dtype={"game_id": str, "season": str})
    forecasts = forecasts.loc[forecasts["half_life_games"].eq(15.0)].copy()
    forecasts["date"] = pd.to_datetime(forecasts["date"], errors="coerce")
    if forecasts.duplicated(["season", "game_id"]).any():
        raise RuntimeError("Expected exactly one baseline forecast per game at half-life 15.")
    forecasts["margin_sd"] = np.nan
    base_margin = forecasts["predicted_margin"].to_numpy(float)
    base_p = np.clip(forecasts["predicted_home_win_probability"].to_numpy(float), 1e-5, 1 - 1e-5)
    z = ndtri(base_p)
    usable = np.abs(z) > 1e-3
    forecasts.loc[usable, "margin_sd"] = base_margin[usable] / z[usable]
    forecasts["margin_sd"] = forecasts["margin_sd"].where(
        np.isfinite(forecasts["margin_sd"]) & forecasts["margin_sd"].gt(5.0), 17.0
    )

    # Two rows per game allow a single team-level residual model to learn how
    # trailing team fantasy output relates to that team's next NBA score.
    sides = []
    for side in ("home", "away"):
        other = "away" if side == "home" else "home"
        sides.append(pd.DataFrame({
            "season": forecasts["season"],
            "date": forecasts["date"],
            "game_id": forecasts["game_id"],
            "team": forecasts[f"{side}_team"].astype(str).str.upper(),
            "opponent": forecasts[f"{other}_team"].astype(str).str.upper(),
            "actual_points": forecasts[f"actual_{side}_points"].astype(float),
            "baseline_points": forecasts[f"predicted_{side}_points"].astype(float),
            "actual_home_win": forecasts["actual_home_win"].astype(float),
            "actual_margin": forecasts["actual_margin"].astype(float),
            "baseline_margin": forecasts["predicted_margin"].astype(float),
            "baseline_probability": forecasts["predicted_home_win_probability"].astype(float),
            "margin_sd": forecasts["margin_sd"].astype(float),
            "side": side,
        }))
    team_rows = pd.concat(sides, ignore_index=True)
    pdk_features = team_pdk[[
        "nba_GAME_ID", "nba_TEAM_ABBREVIATION", "game_date",
        "team_pdk", "player_count", "pdk_roll5", "league_pdk_mean_before_date",
        "pdk_strength_delta",
    ]].rename(columns={
        "nba_GAME_ID": "game_id",
        "nba_TEAM_ABBREVIATION": "team",
        "game_date": "pdk_game_date",
    })
    team_rows = team_rows.merge(
        pdk_features.drop(columns=["pdk_game_date"]),
        on=["game_id", "team"], how="left", validate="many_to_one"
    )
    opponent_features = pdk_features[[
        "game_id", "team", "pdk_roll5", "pdk_strength_delta", "player_count"
    ]].rename(columns={
        "team": "opponent",
        "pdk_roll5": "opponent_pdk_roll5",
        "pdk_strength_delta": "opponent_pdk_strength_delta",
        "player_count": "opponent_pdk_player_count",
    })
    team_rows = team_rows.merge(
        opponent_features, on=["game_id", "opponent"], how="left", validate="many_to_one"
    )
    train_mask = team_rows["season"].isin(TRAIN_SEASONS)
    validation_mask = team_rows["season"].isin(VALIDATION_SEASONS)
    holdout_mask = team_rows["season"].isin(FINAL_HOLDOUT_SEASONS)
    complete_feature_mask = (
        team_rows["pdk_strength_delta"].notna()
        & team_rows["opponent_pdk_strength_delta"].notna()
    )
    fit_mask = train_mask & complete_feature_mask
    if fit_mask.sum() < 1000:
        raise RuntimeError(f"Too few historical team-games to fit PDK proxy model: {fit_mask.sum()}")

    features = ["pdk_strength_delta", "opponent_pdk_strength_delta"]
    model = Ridge(alpha=RIDGE_ALPHA, fit_intercept=True)
    model.fit(team_rows.loc[fit_mask, features], (
        team_rows.loc[fit_mask, "actual_points"] - team_rows.loc[fit_mask, "baseline_points"]
    ))
    team_rows["pdk_residual_adjustment"] = 0.0
    team_rows.loc[complete_feature_mask, "pdk_residual_adjustment"] = model.predict(
        team_rows.loc[complete_feature_mask, features]
    )
    team_rows["adjusted_points"] = team_rows["baseline_points"] + team_rows["pdk_residual_adjustment"]

    # Reassemble home/away scores and retain a matched-coverage cohort for fair
    # baseline-vs-adjusted comparison. Missing PDK features leave baseline intact.
    home_rows = team_rows.loc[team_rows["side"].eq("home")].set_index(["season", "game_id"])
    away_rows = team_rows.loc[team_rows["side"].eq("away")].set_index(["season", "game_id"])
    result = forecasts.set_index(["season", "game_id"]).copy()
    result["home_pdk_strength_delta"] = home_rows["pdk_strength_delta"]
    result["away_pdk_strength_delta"] = away_rows["pdk_strength_delta"]
    result["home_pdk_player_count"] = home_rows["player_count"]
    result["away_pdk_player_count"] = away_rows["player_count"]
    result["home_pdk_adjustment"] = home_rows["pdk_residual_adjustment"]
    result["away_pdk_adjustment"] = away_rows["pdk_residual_adjustment"]
    result["adjusted_home_points"] = home_rows["adjusted_points"]
    result["adjusted_away_points"] = away_rows["adjusted_points"]
    result["adjusted_margin"] = result["adjusted_home_points"] - result["adjusted_away_points"]
    result["adjusted_home_win_probability"] = ndtr(
        result["adjusted_margin"].to_numpy(float) / result["margin_sd"].to_numpy(float)
    )
    result["pdk_features_available"] = (
        result["home_pdk_strength_delta"].notna() & result["away_pdk_strength_delta"].notna()
    )
    result = result.reset_index()

    reports = {}
    for label, season_set in (
        ("validation_2024_25", VALIDATION_SEASONS),
        ("final_holdout_2025_26", FINAL_HOLDOUT_SEASONS),
    ):
        group = result.loc[result["season"].isin(season_set)]
        matched = group.loc[group["pdk_features_available"]]
        reports[label] = {
            "all_games": {
                "baseline": _metrics(group, "predicted_home_win_probability", "predicted_margin"),
                "adjusted_with_baseline_fallback": _metrics(
                    group, "adjusted_home_win_probability", "adjusted_margin"
                ),
            },
            "matched_pdk_feature_games": {
                "games": int(len(matched)),
                "coverage": float(len(matched) / len(group)) if len(group) else 0.0,
                "baseline": _metrics(matched, "predicted_home_win_probability", "predicted_margin"),
                "adjusted": _metrics(matched, "adjusted_home_win_probability", "adjusted_margin"),
                "mean_absolute_home_adjustment": float(matched["home_pdk_adjustment"].abs().mean()),
                "mean_absolute_away_adjustment": float(matched["away_pdk_adjustment"].abs().mean()),
            },
        }

    report = {
        "scope": "Historical team PDK output used as a lagged proxy for team/roster strength; training 2020-21 through 2023-24, validation 2024-25, final holdout 2025-26",
        "sources": {
            "team_logs": str(TEAM_LOGS.relative_to(ROOT)),
            "verified_pdk_player_game_training": str(PDK_TRAINING.relative_to(ROOT)),
            "baseline_forecasts": str(BASE_FORECASTS.relative_to(ROOT)),
        },
        "feature_definition": "Sum verified official player-game PDK by NBA game/team; require >=7 matched players; use the mean of the prior five available team-game PDK sums (minimum three), centered against the historical league mean available before that date",
        "fit": {
            "method": "Ridge regression on team-game point residuals after the walk-forward baseline forecast",
            "alpha": RIDGE_ALPHA,
            "training_seasons": sorted(TRAIN_SEASONS),
            "training_team_game_rows": int(fit_mask.sum()),
            "coefficients": {name: float(value) for name, value in zip(features, model.coef_)},
            "intercept": float(model.intercept_),
            "minimum_players_per_team_game": MIN_PLAYERS_PER_TEAM_GAME,
            "minimum_prior_pdk_games": MIN_PRIOR_PDK_GAMES,
        },
        "validation": reports["validation_2024_25"],
        "final_holdout": reports["final_holdout_2025_26"],
        "decision": (
            "candidate improves both Brier and log loss on validation; review holdout before considering production"
            if reports["validation_2024_25"]["matched_pdk_feature_games"]["adjusted"]["brier"]
            < reports["validation_2024_25"]["matched_pdk_feature_games"]["baseline"]["brier"]
            and reports["validation_2024_25"]["matched_pdk_feature_games"]["adjusted"]["log_loss"]
            < reports["validation_2024_25"]["matched_pdk_feature_games"]["baseline"]["log_loss"]
            else "do not deploy: PDK-based roster-strength proxy does not improve both Brier and log loss on validation"
        ),
        "limitations": [
            "This is a historical aggregate-PDK proxy, not a true archived pre-game Dunkest roster or price snapshot.",
            "The model uses only past PDK totals for features and walk-forward baseline residuals for training; same-game PDK is never a feature.",
            "The 2025-26 season was not used to fit or choose the proxy model.",
            "No production predictor or optimizer was changed.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(PRED_OUT, index=False)
    METRICS_OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "fit": report["fit"],
        "validation": report["validation"],
        "final_holdout": report["final_holdout"],
        "decision": report["decision"],
        "outputs": [str(PRED_OUT), str(METRICS_OUT)],
    }, indent=2))
    print(f"\nDetailed predictions: {PRED_OUT}")
    print(f"Detailed metrics: {METRICS_OUT}")


if __name__ == "__main__":
    main()
