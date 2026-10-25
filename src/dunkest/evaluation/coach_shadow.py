"""Offline coach roster-adjustment comparisons through the production scorer.

This module is deliberately not imported by the forecast pipeline or optimizer.
It creates in-memory diagnostic rows only; callers decide whether and where to
persist them. The shrinkage prior is an explicit experiment parameter and must
be selected on development folds, never on a final evaluation period.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from dunkest.models.coach import predict_coach_points


def _utc_day(value: object, label: str) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise ValueError(f"{label} must be a valid timestamp")
    return parsed.normalize()


def _past_only(frame: pd.DataFrame | None, *, label: str, cutoff_day: pd.Timestamp) -> pd.DataFrame | None:
    if frame is None:
        return None
    if frame.empty:
        return frame.copy()
    date_column = next((column for column in ("GAME_DATE", "game_date") if column in frame), None)
    if date_column is None:
        raise ValueError(f"{label} has no game-date column; point-in-time filtering is impossible")
    dates = pd.to_datetime(frame[date_column], errors="coerce", utc=True)
    if dates.isna().any():
        raise ValueError(f"{label} contains unparseable game dates")
    # NBA caches often contain date-only GAME_DATE values. Excluding the whole
    # forecast day avoids treating midnight-normalized same-day results as
    # pregame information when the true tip/end timestamp is unavailable.
    return frame.loc[dates < cutoff_day].copy()


def _team_pdk_evidence(
    player_logs: pd.DataFrame,
    team_logs: pd.DataFrame,
    *,
    season_start_day: pd.Timestamp,
) -> tuple[pd.Series, dict[str, dict[str, float]]]:
    player_game_id = "GAME_ID" if "GAME_ID" in player_logs else "Game_ID"
    team_game_id = "Game_ID" if "Game_ID" in team_logs else "GAME_ID"
    player_date_column = next((column for column in ("GAME_DATE", "game_date") if column in player_logs), None)
    team_date_column = next((column for column in ("GAME_DATE", "game_date") if column in team_logs), None)
    if not {player_game_id, "TEAM_ABBREVIATION", "PDK"}.issubset(player_logs.columns) or player_date_column is None:
        raise ValueError("player_logs lacks game id, team, PDK, or GAME_DATE")
    if not {team_game_id, "TEAM_ABBREVIATION", "PTS"}.issubset(team_logs.columns) or team_date_column is None:
        raise ValueError("team_logs lacks game id, team, PTS, or GAME_DATE")

    p = player_logs.assign(
        game_id=player_logs[player_game_id].astype(str),
        team_code=player_logs["TEAM_ABBREVIATION"].astype(str).str.strip().str.upper(),
        pdk=pd.to_numeric(player_logs["PDK"], errors="coerce"),
        game_day=pd.to_datetime(player_logs[player_date_column], errors="coerce", utc=True).dt.normalize(),
    )
    pdk_by_game = p.groupby(["game_id", "team_code", "game_day"], as_index=False)["pdk"].sum()
    t = team_logs.assign(
        game_id=team_logs[team_game_id].astype(str),
        team_code=team_logs["TEAM_ABBREVIATION"].astype(str).str.strip().str.upper(),
        points=pd.to_numeric(team_logs["PTS"], errors="coerce"),
        game_day=pd.to_datetime(team_logs[team_date_column], errors="coerce", utc=True).dt.normalize(),
    )
    if pdk_by_game["game_day"].isna().any() or t["game_day"].isna().any():
        raise ValueError("coach evidence contains unparseable game dates")
    paired = pdk_by_game.merge(
        t[["game_id", "team_code", "game_day", "points"]],
        on=["game_id", "team_code", "game_day"], how="inner",
    ).dropna(subset=["pdk", "points"])
    history_mean = paired.groupby("team_code")["pdk"].mean()

    current = paired.loc[paired["game_day"].ge(season_start_day)]
    team_games = t.loc[t["game_day"].ge(season_start_day)].drop_duplicates(
        ["game_id", "team_code"]
    ).groupby("team_code").size()
    paired_games = current.drop_duplicates(["game_id", "team_code"]).groupby("team_code").size()
    evidence: dict[str, dict[str, float]] = {}
    for team in set(team_games.index) | set(paired_games.index):
        n_team = int(team_games.get(team, 0))
        n_paired = int(paired_games.get(team, 0))
        coverage = min(1.0, n_paired / n_team) if n_team else 0.0
        evidence[str(team)] = {
            "current_season_team_games": float(n_team),
            "current_season_paired_pdk_games": float(n_paired),
            "current_season_pair_coverage": float(coverage),
        }
    return history_mean, evidence


def _shrink_roster_forecasts(
    forecasts: pd.DataFrame,
    history_mean: pd.Series,
    evidence: dict[str, dict[str, float]],
    prior_games: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    if not {"team", "expected_pdk"}.issubset(forecasts.columns):
        raise ValueError("player_forecasts must contain team and expected_pdk")
    result = forecasts.copy()
    result["_team_code"] = result["team"].astype(str).str.strip().str.upper()
    result["_expected_pdk"] = pd.to_numeric(result["expected_pdk"], errors="coerce")
    if result["_expected_pdk"].isna().any():
        raise ValueError("player_forecasts contains missing or nonnumeric expected_pdk")

    weights: dict[str, float] = {}
    for team, indices in result.groupby("_team_code", sort=False).groups.items():
        baseline = history_mean.get(team)
        team_evidence = evidence.get(team, {})
        n = float(team_evidence.get("current_season_paired_pdk_games", 0.0))
        coverage = float(team_evidence.get("current_season_pair_coverage", 0.0))
        weight = (n / (n + prior_games)) * coverage if n > 0 else 0.0
        weights[str(team)] = float(weight)
        if baseline is None or not np.isfinite(float(baseline)) or weight >= 1.0:
            continue
        projected_total = float(result.loc[indices, "_expected_pdk"].sum())
        # Preserve within-team player weights and shrink only the aggregate
        # roster signal that is passed to the existing coach model.
        if projected_total <= 0.0:
            continue
        target_total = float(baseline) + weight * (projected_total - float(baseline))
        if target_total < 0.0:
            continue
        result.loc[indices, "expected_pdk"] = (
            result.loc[indices, "_expected_pdk"] * (target_total / projected_total)
        )
    return result.drop(columns=["_team_code", "_expected_pdk"]), weights


def _comparison_id(row: pd.Series, season_id: str, gameweek: int) -> tuple[str, bool]:
    game_id = str(row.get("nba_game_id", "")).strip()
    if game_id.casefold() not in {"", "nan", "none", "<na>"}:
        identity = f"{season_id}|{int(gameweek)}|{game_id}|{row.get('dunkest_turn', '')}|{str(row.get('team', '')).upper()}"
        verified = str(row.get("coach_projection_source", "")) == "verified_matchup"
    else:
        teams = sorted([str(row.get("team", "")).upper(), str(row.get("opponent", "")).upper()])
        date = pd.to_datetime(row.get("matchup_date"), errors="coerce", utc=True)
        date_token = date.isoformat() if pd.notna(date) else "unknown-date"
        identity = f"{season_id}|{int(gameweek)}|{date_token}|{teams}|{row.get('dunkest_turn', '')}"
        verified = False
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"coach-shadow-{digest}", verified


def compare_coach_roster_variants(
    coach_df: pd.DataFrame,
    *,
    team_logs: pd.DataFrame,
    upcoming_schedule: pd.DataFrame,
    player_logs: pd.DataFrame,
    player_forecasts: pd.DataFrame,
    season_id: str,
    gameweek: int,
    forecast_timestamp_utc: str,
    current_season_start_utc: str,
    shrinkage_prior_games: float,
) -> pd.DataFrame:
    """Return current/no-roster/shrunk coach forecasts as diagnostic long data.

    All variants reuse ``predict_coach_points`` and share the same point-in-time
    input rows. ``shrinkage_prior_games`` is deliberately mandatory: it is a
    development-fold parameter, not an implicit production default. The output
    is marked shadow-only and is never consumed by the optimizer.
    """
    prior = float(shrinkage_prior_games)
    if not np.isfinite(prior) or prior <= 0.0:
        raise ValueError("shrinkage_prior_games must be finite and greater than zero")
    cutoff_day = _utc_day(forecast_timestamp_utc, "forecast_timestamp_utc")
    season_start_day = _utc_day(current_season_start_utc, "current_season_start_utc")
    if season_start_day >= cutoff_day:
        raise ValueError("current-season start must precede the forecast day")

    past_team_logs = _past_only(team_logs, label="team_logs", cutoff_day=cutoff_day)
    past_player_logs = _past_only(player_logs, label="player_logs", cutoff_day=cutoff_day)
    assert past_team_logs is not None and past_player_logs is not None
    if past_team_logs.empty or past_player_logs.empty:
        raise ValueError("point-in-time team and player logs are required for coach variants")
    if player_forecasts is None or player_forecasts.empty:
        raise ValueError("player forecasts are required for roster-adjustment variants")

    history_mean, evidence = _team_pdk_evidence(
        past_player_logs, past_team_logs, season_start_day=season_start_day
    )
    shrunk_forecasts, shrinkage_weights = _shrink_roster_forecasts(
        player_forecasts, history_mean, evidence, prior
    )
    common = {
        "team_logs": past_team_logs,
        "upcoming_schedule": upcoming_schedule,
        "gameweek": int(gameweek),
    }
    variants = (
        ("production_current", predict_coach_points(
            coach_df, player_logs=past_player_logs, player_forecasts=player_forecasts, **common
        )),
        ("no_roster_adjustment", predict_coach_points(
            coach_df, player_logs=past_player_logs, player_forecasts=None, **common
        )),
        ("roster_shrinkage", predict_coach_points(
            coach_df, player_logs=past_player_logs, player_forecasts=shrunk_forecasts, **common
        )),
    )

    rows: list[dict] = []
    for variant, forecast in variants:
        for _, row in forecast.iterrows():
            comparison_id, identity_verified = _comparison_id(row, str(season_id), int(gameweek))
            team = str(row.get("team", "")).strip().upper()
            opponent = str(row.get("opponent", "")).strip().upper()
            team_evidence = evidence.get(team, {})
            opponent_evidence = evidence.get(opponent, {})
            rows.append({
                "comparison_observation_id": comparison_id,
                "variant": variant,
                "season_id": str(season_id),
                "gameweek": int(gameweek),
                "forecast_timestamp_utc": pd.to_datetime(forecast_timestamp_utc, utc=True).isoformat(),
                "nba_game_id": row.get("nba_game_id"),
                "dunkest_turn": row.get("dunkest_turn"),
                "team": team,
                "opponent": opponent,
                "coach": row.get("coach"),
                "matchup_identity_verified": bool(identity_verified),
                "matchup_projection_available": bool(row.get("matchup_projection_available", False)),
                "coach_projection_source": row.get("coach_projection_source"),
                "expected_team_pts": row.get("expected_team_pts"),
                "expected_opp_pts": row.get("expected_opp_pts"),
                "expected_margin": row.get("expected_margin"),
                "win_probability": row.get("win_probability"),
                "expected_coach_pdk": row.get("expected_coach_pdk"),
                "team_roster_points_adjustment": row.get("team_roster_points_adjustment"),
                "opponent_roster_points_adjustment": row.get("opponent_roster_points_adjustment"),
                "team_current_season_paired_games": int(team_evidence.get("current_season_paired_pdk_games", 0)),
                "team_current_season_pair_coverage": float(team_evidence.get("current_season_pair_coverage", 0.0)),
                "team_shrinkage_weight": float(shrinkage_weights.get(team, 0.0)),
                "opponent_current_season_paired_games": int(opponent_evidence.get("current_season_paired_pdk_games", 0)),
                "opponent_current_season_pair_coverage": float(opponent_evidence.get("current_season_pair_coverage", 0.0)),
                "opponent_shrinkage_weight": float(shrinkage_weights.get(opponent, 0.0)),
                "shrinkage_prior_games": prior,
                "optimizer_input": False,
            })
    return pd.DataFrame(rows)
