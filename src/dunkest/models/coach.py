from __future__ import annotations

import hashlib
import logging

import numpy as np
import pandas as pd

from dunkest.rules.coach import coach_coefficient, coach_points_from_outcomes

TEAM_FORM_HALF_LIFE_GAMES = 15.0
TEAM_FORM_PRIOR_GAMES = 8.0
TEAM_VOLATILITY_PRIOR_GAMES = 10.0
MAX_ROSTER_POINTS_ADJUSTMENT = 6.0
logger = logging.getLogger(__name__)


def _recent_shrunk_mean(
    group: pd.DataFrame,
    column: str,
    league_mean: float,
    date_column: str = "GAME_DATE",
) -> float:
    """Recency-weight a team metric and shrink it toward its league baseline."""
    group = group.sort_values(date_column, kind="stable")
    values = pd.to_numeric(group[column], errors="coerce").dropna()
    if values.empty:
        return float(league_mean)
    age = np.arange(len(values) - 1, -1, -1, dtype=float)
    weights = np.exp2(-age / TEAM_FORM_HALF_LIFE_GAMES)
    weights /= weights.sum()
    recent = float(np.average(values.to_numpy(dtype=float), weights=weights))
    reliability = len(values) / (len(values) + TEAM_FORM_PRIOR_GAMES)
    return float(league_mean + reliability * (recent - league_mean))


def _team_profiles(results: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float], float]:
    """Estimate recent team scoring profiles, shrinking small samples to league averages."""
    league_points = float(results["team_points"].mean())
    league_sd = float(results["team_points"].std(ddof=1)) if len(results) > 1 else 12.0
    league_sd = float(np.clip(league_sd if np.isfinite(league_sd) else 12.0, 8.0, 18.0))
    rows: list[dict] = []
    score_sds: dict[str, float] = {}
    for team, group in results.groupby("team"):
        group = group.sort_values("game_date", kind="stable")
        n = len(group)
        rows.append({
            "team": team,
            "offense": _recent_shrunk_mean(
                group, "team_points", league_points, date_column="game_date"
            ),
            "defense_allowed": _recent_shrunk_mean(
                group, "opponent_points", league_points, date_column="game_date"
            ),
            "games": n,
        })
        sample_sd = float(group["team_points"].std(ddof=1)) if n > 1 else league_sd
        sample_variance = sample_sd**2 if np.isfinite(sample_sd) else league_sd**2
        degrees = max(n - 1, 0)
        shrunk_variance = (
            degrees * sample_variance + TEAM_VOLATILITY_PRIOR_GAMES * league_sd**2
        ) / (degrees + TEAM_VOLATILITY_PRIOR_GAMES)
        score_sds[str(team)] = float(np.clip(np.sqrt(shrunk_variance), 8.0, 18.0))
    profile = pd.DataFrame(rows).set_index("team") if rows else pd.DataFrame()
    return profile, score_sds, league_sd


def _coach_score_distribution(
    team_pts: float,
    opp_pts: float,
    coach_cr: float,
    opponent_coach_cr: float,
    team_sd: float,
    opponent_sd: float,
    score_correlation: float,
    matchup_key: str,
    overtime_probability: float = 0.0,
) -> np.ndarray:
    """Simulate Dunkest coach scores under plausible game outcomes."""
    seed = int.from_bytes(hashlib.sha256(matchup_key.encode("utf-8")).digest()[:4], "big")
    rng = np.random.default_rng(seed)
    draws = 8192
    z_team = rng.standard_normal(draws)
    z_opp_independent = rng.standard_normal(draws)
    rho = float(np.clip(score_correlation, -0.4, 0.6))
    z_opp = rho * z_team + np.sqrt(1.0 - rho * rho) * z_opp_independent
    team_scores = np.maximum(np.rint(team_pts + max(team_sd, 5.0) * z_team), 0)
    opponent_scores = np.maximum(np.rint(opp_pts + max(opponent_sd, 5.0) * z_opp), 0)
    overtime_probability = float(np.clip(overtime_probability, 0.0, 0.25))
    overtime = rng.random(draws) < overtime_probability
    return np.asarray(coach_points_from_outcomes(
        team_scores, opponent_scores, coach_cr, opponent_coach_cr, overtime
    ), dtype=float)


def _expected_coach_pdk(
    team_pts: float,
    opp_pts: float,
    coach_cr: float,
    opponent_coach_cr: float,
    team_sd: float,
    opponent_sd: float,
    score_correlation: float,
    matchup_key: str,
    overtime_probability: float = 0.0,
) -> float:
    """Average the Dunkest score over plausible game outcomes, not only the mean."""
    return float(np.mean(_coach_score_distribution(
        team_pts, opp_pts, coach_cr, opponent_coach_cr, team_sd,
        opponent_sd, score_correlation, matchup_key, overtime_probability,
    )))


def _roster_point_adjustments(
    player_logs: pd.DataFrame | None,
    team_logs: pd.DataFrame | None,
    player_forecasts: pd.DataFrame | None,
) -> dict[str, float]:
    if (
        player_logs is None
        or player_logs.empty
        or team_logs is None
        or team_logs.empty
        or player_forecasts is None
        or player_forecasts.empty
    ):
        return {}
    player_game_id = "GAME_ID" if "GAME_ID" in player_logs else "Game_ID"
    team_game_id = "Game_ID" if "Game_ID" in team_logs else "GAME_ID"
    if not {player_game_id, "TEAM_ABBREVIATION", "PDK"}.issubset(player_logs.columns):
        return {}
    if not {team_game_id, "TEAM_ABBREVIATION", "PTS"}.issubset(team_logs.columns):
        return {}
    if not {"team", "expected_pdk"}.issubset(player_forecasts.columns):
        return {}

    historical_pdk = (
        player_logs.assign(
            game_id=player_logs[player_game_id].astype(str),
            team_code=player_logs["TEAM_ABBREVIATION"].astype(str).str.upper(),
            pdk=pd.to_numeric(player_logs["PDK"], errors="coerce"),
        )
        .groupby(["game_id", "team_code"], as_index=False)["pdk"]
        .sum()
    )
    historical_points = team_logs.assign(
        game_id=team_logs[team_game_id].astype(str),
        team_code=team_logs["TEAM_ABBREVIATION"].astype(str).str.upper(),
        points=pd.to_numeric(team_logs["PTS"], errors="coerce"),
    )[["game_id", "team_code", "points"]]
    paired = historical_pdk.merge(historical_points, on=["game_id", "team_code"]).dropna()
    if len(paired) < 40:
        return {}
    pdk_values = paired["pdk"].to_numpy(dtype=float)
    point_values = paired["points"].to_numpy(dtype=float)
    variance = float(np.var(pdk_values))
    if variance <= 0:
        return {}
    slope = float(np.mean((pdk_values - pdk_values.mean()) * (point_values - point_values.mean())) / variance)
    slope = float(np.clip(slope, 0.0, 0.5))
    historical_by_team = historical_pdk.groupby("team_code")["pdk"].mean()
    forecast_rows = player_forecasts.assign(
        team_code=player_forecasts["team"].astype(str).str.upper(),
        expected_pdk=pd.to_numeric(player_forecasts["expected_pdk"], errors="coerce").fillna(0.0),
    )
    projected_by_team = forecast_rows.groupby("team_code")["expected_pdk"].sum()
    teams_with_playing_projection = set(
        forecast_rows.loc[forecast_rows["expected_pdk"].gt(0.0), "team_code"]
    )
    # A team with every player at zero is usually a missing/unreliable roster
    # forecast (for example, a stale pre-season OUT list). Treat it as unknown
    # and retain the historical team profile instead of applying a full-team
    # collapse to the coach projection.
    common = projected_by_team.index.intersection(historical_by_team.index)
    common = pd.Index([team for team in common if team in teams_with_playing_projection])
    roster_deltas = projected_by_team.loc[common] - historical_by_team.loc[common]
    league_delta = float(roster_deltas.mean()) if not roster_deltas.empty else 0.0
    return {
        team: float(np.clip(
            (roster_deltas[team] - league_delta) * slope,
            -MAX_ROSTER_POINTS_ADJUSTMENT,
            MAX_ROSTER_POINTS_ADJUSTMENT,
        ))
        for team in common
    }


def _normalize_schedule_frame(schedule: pd.DataFrame, gameweek: int | None) -> pd.DataFrame:
    """Accept Dunkest fixture mappings or raw NBA schedule frames."""
    if schedule is None or schedule.empty:
        return pd.DataFrame(columns=["GAME_DATE", "HOME_TEAM", "AWAY_TEAM"])
    games = schedule.copy()
    if gameweek is not None and {"dunkest_gameweek", "fantasy_eligible"}.issubset(games.columns):
        games = games.loc[
            pd.to_numeric(games["dunkest_gameweek"], errors="coerce").eq(int(gameweek))
            & games["fantasy_eligible"].fillna(False).astype(bool)
        ].copy()
        games = games.rename(columns={
            "nba_game_id": "NBA_GAME_ID",
            "game_datetime_utc": "GAME_DATE",
            "home_team": "HOME_TEAM",
            "away_team": "AWAY_TEAM",
        })
        games["HOME_TEAM_ELIGIBLE"] = games.get(
            "home_team_eligible", games["fantasy_eligible"]
        ).fillna(False).astype(bool)
        games["AWAY_TEAM_ELIGIBLE"] = games.get(
            "away_team_eligible", games["fantasy_eligible"]
        ).fillna(False).astype(bool)
    else:
        games = games.rename(columns={
            "nba_game_id": "NBA_GAME_ID",
            "GAME_ID": "NBA_GAME_ID",
            "game_datetime_utc": "GAME_DATE",
            "home_team": "HOME_TEAM",
            "away_team": "AWAY_TEAM",
        })
    required = {"GAME_DATE", "HOME_TEAM", "AWAY_TEAM"}
    if not required.issubset(games.columns):
        return pd.DataFrame(columns=["GAME_DATE", "HOME_TEAM", "AWAY_TEAM"])
    if "HOME_TEAM_ELIGIBLE" not in games:
        games["HOME_TEAM_ELIGIBLE"] = True
    if "AWAY_TEAM_ELIGIBLE" not in games:
        games["AWAY_TEAM_ELIGIBLE"] = True
    return games


def _next_game_context(
    coaches: pd.DataFrame,
    team_logs: pd.DataFrame | None,
    schedule: pd.DataFrame | None,
    player_logs: pd.DataFrame | None,
    player_forecasts: pd.DataFrame | None,
    gameweek: int | None = None,
) -> pd.DataFrame:
    out = coaches.copy()
    if "coach_projection_source" not in out:
        out["coach_projection_source"] = "no_verified_matchup"
    if "matchup_projection_available" not in out:
        out["matchup_projection_available"] = False
    # Prefer a real schedule when available; otherwise still project from
    # opponents already attached to the coach market (get_coach_data).
    schedule = _normalize_schedule_frame(
        schedule if schedule is not None else pd.DataFrame(), gameweek
    )
    if team_logs is None or team_logs.empty:
        # The opener often has no current-season team logs yet. The verified
        # Dunkest fixture still identifies the opponent, so retain that
        # matchup and use a neutral scoring baseline; historical-only rows
        # remain explicitly unprojected.
        if not schedule.empty:
            team_to_coach = dict(zip(out.get("team", pd.Series(dtype=str)).astype(str).str.upper(), out.get("coach", pd.Series(dtype=str))))
            team_to_cr = dict(zip(
                out.get("team", pd.Series(dtype=str)).astype(str).str.upper(),
                pd.to_numeric(out.get("coach_cr", pd.Series(dtype=float)), errors="coerce"),
            ))
            games = schedule.sort_values("GAME_DATE")
            for idx, row in out.iterrows():
                team = str(row.get("team", "")).strip().upper()
                candidates = games.loc[
                    (games["HOME_TEAM"].eq(team) & games["HOME_TEAM_ELIGIBLE"])
                    | (games["AWAY_TEAM"].eq(team) & games["AWAY_TEAM_ELIGIBLE"])
                ]
                if candidates.empty:
                    continue
                game = candidates.iloc[0]
                opponent = str(
                    game["AWAY_TEAM"] if game["HOME_TEAM"] == team else game["HOME_TEAM"]
                )
                out.at[idx, "opponent"] = opponent
                out.at[idx, "opponent_coach"] = team_to_coach.get(opponent, "")
                out.at[idx, "opponent_coach_cr"] = team_to_cr.get(opponent, np.nan)
                out.at[idx, "expected_team_pts"] = 112.0
                out.at[idx, "expected_opp_pts"] = 112.0
                out.at[idx, "matchup_projection_available"] = True
                out.at[idx, "coach_projection_source"] = (
                    "verified_matchup"
                    if bool(game.get("mapping_verified", False))
                    else "unverified_matchup"
                )
                if "NBA_GAME_ID" in game.index:
                    out.at[idx, "nba_game_id"] = game["NBA_GAME_ID"]
        return out
    has_existing_opponents = (
        "opponent" in out.columns
        and out["opponent"].astype(str).str.strip().ne("").any()
        and out["opponent"].astype(str).str.upper().str.strip().isin({"NAN", "NONE"}).eq(False).any()
    )
    if schedule.empty and not has_existing_opponents:
        return out
    game_id_col = "Game_ID" if "Game_ID" in team_logs else "GAME_ID"
    required_logs = {game_id_col, "TEAM_ABBREVIATION", "PTS"}
    if not required_logs.issubset(team_logs.columns):
        return out

    game_rows: list[dict] = []
    for _, game in team_logs.groupby(game_id_col):
        if len(game) != 2:
            continue
        teams = game.to_dict("records")
        raw_minutes = pd.to_numeric(
            pd.Series([row.get("MIN") for row in teams]), errors="coerce"
        )
        if raw_minutes.isna().all():
            # Some NBA endpoints serialize minutes as ``240:00``.
            raw_minutes = pd.to_timedelta(
                pd.Series([row.get("MIN") for row in teams]), errors="coerce"
            ).dt.total_seconds().div(60.0)
        # NBA team logs report 240 regulation minutes; any excess indicates
        # overtime. Missing MIN is left unknown rather than guessed.
        overtime = bool(raw_minutes.gt(240.0).any()) if raw_minutes.notna().any() else False
        for team in teams:
            opponent = next(row for row in teams if row["TEAM_ABBREVIATION"] != team["TEAM_ABBREVIATION"])
            game_rows.append(
                {
                    "team": str(team["TEAM_ABBREVIATION"]).upper(),
                    "team_points": pd.to_numeric(team["PTS"], errors="coerce"),
                    "opponent_points": pd.to_numeric(opponent["PTS"], errors="coerce"),
                    "game_id": str(team.get(game_id_col, "")),
                    "game_date": pd.to_datetime(team.get("GAME_DATE"), errors="coerce"),
                    "is_home": (
                        str(team.get("MATCHUP", "")).lower().find("vs.") >= 0
                        if "MATCHUP" in team_logs.columns else np.nan
                    ),
                    "overtime": overtime,
                }
            )
    if not game_rows:
        return out
    results = pd.DataFrame(game_rows).dropna(
        subset=["team_points", "opponent_points", "game_date"]
    )
    if results.empty:
        return out
    profile, team_score_sds, score_sd = _team_profiles(results)
    overtime_by_game = results.drop_duplicates("game_id").get(
        "overtime", pd.Series(False, index=results.drop_duplicates("game_id").index)
    ).astype(bool)
    # Light Beta prior stabilizes the estimate for a short or partial history.
    overtime_probability = float((overtime_by_game.sum() + 1.0) / (len(overtime_by_game) + 25.0))
    score_correlation = 0.1
    paired_scores = results.groupby("game_id")["team_points"].apply(list)
    paired_scores = paired_scores.loc[paired_scores.map(len).eq(2)]
    if len(paired_scores) >= 10:
        pair_values = np.asarray(paired_scores.tolist(), dtype=float)
        if np.isfinite(pair_values).all() and np.all(np.std(pair_values, axis=0) > 1e-9):
            estimate = np.corrcoef(pair_values[:, 0], pair_values[:, 1])[0, 1]
            if np.isfinite(estimate):
                score_correlation = float(np.clip(estimate, -0.4, 0.6))

    # Estimate home advantage from completed games when the NBA log exposes
    # matchup orientation; older/synthetic logs keep the neutral-court value.
    home_advantage = 0.0
    oriented = results.dropna(subset=["is_home"])
    home_by_game = oriented.loc[oriented["is_home"].astype(bool)].set_index("game_id")["team_points"]
    away_by_game = oriented.loc[~oriented["is_home"].astype(bool)].set_index("game_id")["team_points"]
    shared_games = home_by_game.index.intersection(away_by_game.index)
    if len(shared_games) >= 10:
        home_advantage = float(
            np.clip((home_by_game.loc[shared_games] - away_by_game.loc[shared_games]).mean() / 2.0,
                    -3.0, 3.0)
        )

    # If the team log includes box-score possession components, compare
    # offensive/defensive efficiency at an expected shared game pace.
    pace_by_team: dict[str, float] = {}
    efficiency_available = {"FGA", "FTA", "OREB", "TOV"}.issubset(team_logs.columns)
    if efficiency_available:
        raw = team_logs.copy()
        raw["team_code"] = raw["TEAM_ABBREVIATION"].astype(str).str.upper()
        raw["game_id"] = raw[game_id_col].astype(str)
        for column in ("FGA", "FTA", "OREB", "TOV", "PTS"):
            raw[column] = pd.to_numeric(raw[column], errors="coerce")
        raw["GAME_DATE"] = pd.to_datetime(raw["GAME_DATE"], errors="coerce")
        raw["possessions"] = raw["FGA"] + 0.44 * raw["FTA"] - raw["OREB"] + raw["TOV"]
        raw = raw.loc[raw["possessions"].gt(0) & raw["GAME_DATE"].notna()].copy()
        efficiency_available = not raw.empty
    if efficiency_available:
        raw["off_eff"] = 100.0 * raw["PTS"] / raw["possessions"]
        paired_stats = raw[["game_id", "team_code", "possessions", "PTS"]].merge(
            raw[["game_id", "team_code", "possessions", "PTS"]],
            on="game_id",
            suffixes=("", "_opponent"),
        )
        paired_stats = paired_stats.loc[
            paired_stats["team_code"].ne(paired_stats["team_code_opponent"])
        ].drop_duplicates(["game_id", "team_code"])
        raw = raw.merge(
            paired_stats[["game_id", "team_code", "PTS_opponent"]],
            on=["game_id", "team_code"],
            how="left",
        )
        # Defensive efficiency is opponent points allowed per own defensive
        # possession. Own PTS here would turn defense into a second offense rating.
        raw["def_eff_allowed"] = 100.0 * raw["PTS_opponent"] / raw["possessions"]
        if raw["def_eff_allowed"].notna().any():
            league_off_eff = float(raw["off_eff"].mean())
            league_def_eff = float(raw["def_eff_allowed"].mean())
            league_pace = float(raw["possessions"].mean())
            efficiency_rows: list[dict] = []
            pace_by_team: dict[str, float] = {}
            for team, group in raw.groupby("team_code"):
                efficiency_rows.append({
                    "team_code": team,
                    "off_eff": _recent_shrunk_mean(group, "off_eff", league_off_eff),
                    "def_eff_allowed": _recent_shrunk_mean(
                        group, "def_eff_allowed", league_def_eff
                    ),
                })
                pace_by_team[team] = _recent_shrunk_mean(
                    group, "possessions", league_pace
                )
            efficiency = pd.DataFrame(efficiency_rows).set_index("team_code")
            profile = profile.join(efficiency, how="left")
        else:
            efficiency_available = False
            league_pace = np.nan
            pace_by_team = {}
    if not efficiency_available:
        league_pace = np.nan
        pace_by_team = {}
    point_adjustments = _roster_point_adjustments(
        player_logs, team_logs, player_forecasts
    )
    profile["roster_points_adjustment"] = pd.Series(point_adjustments).reindex(
        profile.index
    ).fillna(0.0)
    profile["roster_projection_available"] = profile.index.isin(point_adjustments)
    if player_forecasts is not None and not player_forecasts.empty:
        missing_roster_forecasts = sorted(
            set(profile.index.astype(str)) - set(point_adjustments)
        )
        if missing_roster_forecasts:
            logger.warning(
                "Current roster-strength adjustment unavailable for teams %s; coach projections use prior team profiles for them.",
                ", ".join(missing_roster_forecasts),
            )
    league_points = float(results["team_points"].mean())

    games = schedule.copy()
    if not games.empty:
        if gameweek is None and "NBA_WEEK_NUMBER" in games:
            games = games.loc[
                pd.to_numeric(games["NBA_WEEK_NUMBER"], errors="coerce").gt(0)
            ]
        games["GAME_DATE"] = pd.to_datetime(games["GAME_DATE"], errors="coerce", utc=True)
        if getattr(games["GAME_DATE"].dtype, "tz", None) is not None:
            games["GAME_DATE"] = games["GAME_DATE"].dt.tz_convert("UTC").dt.tz_localize(None)
        games["HOME_TEAM"] = games["HOME_TEAM"].astype(str).str.upper().str.strip()
        games["AWAY_TEAM"] = games["AWAY_TEAM"].astype(str).str.upper().str.strip()
        if "GAME_STATUS" in games:
            games = games.loc[pd.to_numeric(games["GAME_STATUS"], errors="coerce").ne(3)]
        games = games.dropna(subset=["GAME_DATE"]).sort_values("GAME_DATE")

    team_to_coach = dict(zip(out["team"].astype(str).str.upper(), out["coach"]))
    team_to_cr = dict(zip(out["team"].astype(str).str.upper(), pd.to_numeric(out["coach_cr"], errors="coerce")))
    matchups: dict[str, tuple[str, pd.Series]] = {}
    for _, game in games.iterrows():
        sides = []
        if bool(game.get("HOME_TEAM_ELIGIBLE", True)):
            sides.append((game["HOME_TEAM"], game["AWAY_TEAM"]))
        if bool(game.get("AWAY_TEAM_ELIGIBLE", True)):
            sides.append((game["AWAY_TEAM"], game["HOME_TEAM"]))
        for team, opponent in sides:
            matchups[team] = (opponent, game)

    # When the coach market already identifies a specific opponent, use that
    # fixture. A team can play multiple times in a Dunkest round, and taking
    # the first NBA schedule row may silently score a different matchup.
    # If the schedule frame is empty/mismatched, still honour the market opponent
    # so prior-season team strength can score the known Dunkest matchup.
    for _, row in out.iterrows():
        team = str(row.get("team", "")).strip().upper()
        opponent = str(row.get("opponent", "")).strip().upper()
        if not team or not opponent or opponent in {"NAN", "NONE"}:
            continue
        if not games.empty:
            selected = games.loc[
                (games["HOME_TEAM"].eq(team) & games["AWAY_TEAM"].eq(opponent))
                | (games["HOME_TEAM"].eq(opponent) & games["AWAY_TEAM"].eq(team))
            ]
            if not selected.empty:
                requested_date = pd.to_datetime(row.get("date"), errors="coerce", utc=True)
                if pd.notna(requested_date):
                    if getattr(requested_date, "tzinfo", None) is not None:
                        requested_date = requested_date.tz_convert("UTC").tz_localize(None)
                    fixture_dates = pd.to_datetime(
                        selected["GAME_DATE"], errors="coerce"
                    ).dt.date
                    date_matches = selected.loc[fixture_dates.eq(requested_date.date())]
                    if not date_matches.empty:
                        selected = date_matches
                matchups[team] = (opponent, selected.iloc[0])
                continue
        # Synthetic fixture from the coach market alone. Home court is unknown
        # unless the market row already carries it; leave both sides neutral.
        known_home = row.get("is_home")
        if pd.notna(known_home):
            is_home = bool(known_home)
            home_team, away_team = (team, opponent) if is_home else (opponent, team)
        else:
            home_team, away_team = team, opponent
        synthetic = pd.Series({
            "GAME_DATE": pd.to_datetime(row.get("date") or row.get("matchup_date"), errors="coerce"),
            "HOME_TEAM": home_team,
            "AWAY_TEAM": away_team,
            "NBA_GAME_ID": row.get("nba_game_id", pd.NA),
            "dunkest_gameweek": row.get("dunkest_gameweek", row.get("giornata", gameweek)),
            "dunkest_turn": row.get("dunkest_turn"),
            "_neutral_home": pd.isna(known_home),
        })
        matchups[team] = (opponent, synthetic)

    for idx, row in out.iterrows():
        team = str(row.get("team", "")).strip().upper()
        matchup = matchups.get(team)
        if matchup is None:
            continue
        opponent, game = matchup
        out.at[idx, "opponent"] = opponent
        out.at[idx, "opponent_coach"] = team_to_coach.get(
            opponent, row.get("opponent_coach", "")
        )
        out.at[idx, "opponent_coach_cr"] = team_to_cr.get(
            opponent,
            pd.to_numeric(row.get("opponent_coach_cr"), errors="coerce"),
        )
        matchup_date = pd.to_datetime(game.get("GAME_DATE"), errors="coerce", utc=True)
        if pd.notna(matchup_date) and getattr(matchup_date, "tzinfo", None) is not None:
            matchup_date = matchup_date.tz_convert("UTC").tz_localize(None)
        out.at[idx, "matchup_date"] = matchup_date
        if "NBA_GAME_ID" in game.index and pd.notna(game.get("NBA_GAME_ID")):
            out.at[idx, "nba_game_id"] = game["NBA_GAME_ID"]
        if "dunkest_gameweek" in game.index and pd.notna(game.get("dunkest_gameweek")):
            out.at[idx, "dunkest_gameweek"] = game["dunkest_gameweek"]
        if "dunkest_turn" in game.index and pd.notna(game.get("dunkest_turn")):
            out.at[idx, "dunkest_turn"] = game["dunkest_turn"]
        is_home = str(team) == str(game["HOME_TEAM"]).upper()
        neutral_home = bool(game.get("_neutral_home", False))
        out.at[idx, "is_home"] = np.nan if neutral_home else is_home
        if team not in profile.index or opponent not in profile.index:
            continue
        own_profile = profile.loc[team]
        opponent_profile = profile.loc[opponent]
        if efficiency_available and pd.notna(own_profile.get("off_eff")) and pd.notna(
            opponent_profile.get("def_eff_allowed")
        ):
            pace = float(np.nanmean([pace_by_team.get(team, np.nan), pace_by_team.get(opponent, np.nan), league_pace]))
            expected_team = (
                (own_profile["off_eff"] + opponent_profile["def_eff_allowed"]) / 2.0
            ) * pace / 100.0
            expected_opp = (
                (opponent_profile["off_eff"] + own_profile["def_eff_allowed"]) / 2.0
            ) * pace / 100.0
        else:
            expected_team = own_profile["offense"] + opponent_profile["defense_allowed"] - league_points
            expected_opp = opponent_profile["offense"] + own_profile["defense_allowed"] - league_points
        expected_team += own_profile["roster_points_adjustment"]
        expected_opp += opponent_profile["roster_points_adjustment"]
        ha = 0.0 if neutral_home else home_advantage
        out.at[idx, "expected_team_pts"] = expected_team + (ha if is_home else -ha)
        out.at[idx, "expected_opp_pts"] = expected_opp - (ha if is_home else -ha)
        out.at[idx, "team_recent_games"] = int(own_profile["games"])
        out.at[idx, "opponent_recent_games"] = int(opponent_profile["games"])
        out.at[idx, "team_roster_points_adjustment"] = float(
            own_profile["roster_points_adjustment"]
        )
        out.at[idx, "opponent_roster_points_adjustment"] = float(
            opponent_profile["roster_points_adjustment"]
        )
        out.at[idx, "net_roster_strength_adjustment"] = float(
            own_profile["roster_points_adjustment"]
            - opponent_profile["roster_points_adjustment"]
        )
        out.at[idx, "team_roster_projection_available"] = bool(
            own_profile["roster_projection_available"]
        )
        out.at[idx, "opponent_roster_projection_available"] = bool(
            opponent_profile["roster_projection_available"]
        )
        out.at[idx, "roster_projection_status"] = (
            "current_roster" if own_profile["roster_projection_available"]
            and opponent_profile["roster_projection_available"]
            else "historical_profile_fallback"
        )
        out.at[idx, "matchup_projection_available"] = True
        out.at[idx, "coach_projection_source"] = (
            "verified_matchup"
            if bool(game.get("mapping_verified", False))
            else "unverified_matchup"
        )
        out.at[idx, "team_score_sd"] = team_score_sds.get(team, score_sd)
        out.at[idx, "opponent_score_sd"] = team_score_sds.get(opponent, score_sd)
        out.at[idx, "score_correlation"] = score_correlation
        out.at[idx, "overtime_probability"] = overtime_probability
    return out


def predict_coach_points(
    coach_df: pd.DataFrame,
    team_logs: pd.DataFrame | None = None,
    upcoming_schedule: pd.DataFrame | None = None,
    player_logs: pd.DataFrame | None = None,
    player_forecasts: pd.DataFrame | None = None,
    gameweek: int | None = None,
    use_model: bool = True,
) -> pd.DataFrame:
    if coach_df.empty:
        return pd.DataFrame(columns=["coach", "team", "opponent", "coach_cr", "expected_coach_pdk"])
    if not use_model:
        df = coach_df.copy()
        for column in (
            "expected_coach_pdk", "p10_coach_pdk", "p50_coach_pdk", "p90_coach_pdk"
        ):
            df[column] = 0.0
        df["matchup_projection_available"] = False
        return df
    df = _next_game_context(
        coach_df, team_logs, upcoming_schedule, player_logs, player_forecasts,
        gameweek=gameweek,
    )
    if "opponent_coach_cr" not in df:
        df["opponent_coach_cr"] = float("nan")
    # Before the current matchup exists, use prior-season team PDK if available.
    # Missing opponent market data means a neutral CR gap. Coach prices affect
    # only the official scoring coefficient; they never imply team strength.
    df["opponent_coach_cr"] = pd.to_numeric(
        df["opponent_coach_cr"], errors="coerce"
    ).fillna(pd.to_numeric(df["coach_cr"], errors="coerce"))
    df["expected_margin"] = 0.0
    # If no matchup/team data exists, use a neutral NBA scoring baseline and
    # preserve a real prior-season coach score below. Do not turn CR into points.
    default_team_pts = pd.Series(112.0, index=df.index)
    default_opp_pts = pd.Series(112.0, index=df.index)
    df["expected_team_pts"] = pd.to_numeric(
        df.get("expected_team_pts", pd.Series(float("nan"), index=df.index)), errors="coerce"
    ).fillna(default_team_pts)
    df["expected_opp_pts"] = pd.to_numeric(
        df.get("expected_opp_pts", pd.Series(float("nan"), index=df.index)), errors="coerce"
    ).fillna(default_opp_pts)
    df["expected_margin"] = df["expected_team_pts"] - df["expected_opp_pts"]
    if "matchup_projection_available" not in df:
        df["matchup_projection_available"] = False
    if "team_score_sd" not in df:
        df["team_score_sd"] = 12.0
    if "opponent_score_sd" not in df:
        df["opponent_score_sd"] = 12.0
    if "score_correlation" not in df:
        df["score_correlation"] = 0.1
    if "overtime_probability" not in df:
        df["overtime_probability"] = 0.0
    def coach_score_summary(row: pd.Series) -> pd.Series:
        scores = _coach_score_distribution(
            float(row["expected_team_pts"]),
            float(row["expected_opp_pts"]),
            float(row["coach_cr"]),
            float(row["opponent_coach_cr"]),
            float(row["team_score_sd"]),
            float(row["opponent_score_sd"]),
            float(row["score_correlation"]),
            f"{row.get('team', '')}-{row.get('opponent', '')}",
            float(row["overtime_probability"]),
        )
        cr_diff = abs(float(row["coach_cr"]) - float(row["opponent_coach_cr"]))
        coach_is_higher = float(row["coach_cr"]) >= float(row["opponent_coach_cr"])
        positive_coefficient = coach_coefficient(cr_diff, coach_is_higher, True)
        negative_coefficient = coach_coefficient(cr_diff, coach_is_higher, False)
        team_scores_mean = float(row["expected_team_pts"])
        opponent_scores_mean = float(row["expected_opp_pts"])
        return pd.Series({
            "expected_coach_pdk": float(np.mean(scores)),
            "p10_coach_pdk": float(np.quantile(scores, 0.10)),
            "p50_coach_pdk": float(np.quantile(scores, 0.50)),
            "p90_coach_pdk": float(np.quantile(scores, 0.90)),
            "win_probability": np.nan,
            "expected_total_pts": team_scores_mean + opponent_scores_mean,
            "p_team_120_plus": np.nan,
            "p_opponent_95_or_less": np.nan,
            "p_overtime": float(row["overtime_probability"]),
            "coach_positive_coefficient": positive_coefficient,
            "coach_negative_coefficient": negative_coefficient,
        })

    score_summary = df.apply(coach_score_summary, axis=1)
    df[score_summary.columns] = score_summary
    has_projection = df["matchup_projection_available"].fillna(False).astype(bool)
    prior = pd.to_numeric(
        df.get("prior_coach_pdk", pd.Series(float("nan"), index=df.index)),
        errors="coerce",
    )
    keep_historical = ~has_projection if gameweek is None else pd.Series(False, index=df.index)
    df.loc[~has_projection & ~keep_historical, "expected_coach_pdk"] = 0.0
    df.loc[keep_historical, "expected_coach_pdk"] = prior.fillna(0.0)
    for column in ("p10_coach_pdk", "p50_coach_pdk", "p90_coach_pdk"):
        df.loc[~has_projection & ~keep_historical, column] = 0.0
        df.loc[keep_historical, column] = prior.fillna(0.0)
    df.loc[~has_projection & ~keep_historical, "coach_projection_source"] = "no_verified_matchup"
    df.loc[keep_historical, "coach_projection_source"] = "prior_only"
    df.loc[~has_projection, "win_probability"] = np.nan
    df["expected_margin"] = df["expected_team_pts"] - df["expected_opp_pts"]
    # Monte Carlo diagnostics use the same seeded scenario construction as
    # the score distribution above.
    for idx, row in df.iterrows():
        if not bool(row["matchup_projection_available"]):
            continue
        seed_key = f"{row.get('team', '')}-{row.get('opponent', '')}"
        seed = int.from_bytes(hashlib.sha256(seed_key.encode("utf-8")).digest()[:4], "big")
        rng = np.random.default_rng(seed)
        count = 8192
        rho = float(np.clip(row["score_correlation"], -0.4, 0.6))
        z_team = rng.standard_normal(count)
        z_opp = rho * z_team + np.sqrt(1.0 - rho * rho) * rng.standard_normal(count)
        team_scores = np.maximum(np.rint(float(row["expected_team_pts"]) + max(float(row["team_score_sd"]), 5.0) * z_team), 0)
        opponent_scores = np.maximum(np.rint(float(row["expected_opp_pts"]) + max(float(row["opponent_score_sd"]), 5.0) * z_opp), 0)
        df.at[idx, "win_probability"] = float(np.mean(team_scores > opponent_scores))
        df.at[idx, "p_team_120_plus"] = float(np.mean(team_scores >= 120))
        df.at[idx, "p_opponent_95_or_less"] = float(np.mean(opponent_scores <= 95))
        df.at[idx, "expected_margin"] = float(np.mean(team_scores - opponent_scores))
        df.at[idx, "expected_total_pts"] = float(np.mean(team_scores + opponent_scores))
    return df
