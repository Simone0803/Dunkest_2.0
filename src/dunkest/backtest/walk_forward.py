from __future__ import annotations

from copy import copy
from pathlib import Path

import numpy as np
import pandas as pd

from dunkest.backtest.metrics import BacktestReport, compute_backtest_metrics
from dunkest.config import Settings
from dunkest.data.access import (
    get_dunkest_data,
    get_player_data,
    get_team_data,
)
from dunkest.data.dunkest.fixtures import check_backtest_readiness, get_fixture_mapping
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import predict_players, train_models
from dunkest.models.coach import predict_coach_points
from dunkest.names import player_key
from dunkest.optimize.milp import optimize_top_k_lineups
from dunkest.pipeline.ablation import run_ablation_summary
from dunkest.pipeline.importance import feature_importance_summary
from dunkest.rules.roster import player_contribution_multiplier
from dunkest.rules.coach import coach_points_from_game

MIN_HISTORICAL_MARKET_PLAYERS = 250


def _realized_player_scores(dk: pd.DataFrame) -> dict[str, float]:
    """Return only finite realized scores with valid normalized player identities."""
    required = {"actual_pdk", "player_name", "gameweek_stats_available"}
    if not required.issubset(dk.columns):
        return {}
    if not dk["gameweek_stats_available"].fillna(False).astype(bool).any():
        return {}
    actual_pdk = pd.to_numeric(dk["actual_pdk"], errors="coerce")
    keys = dk["player_name"].map(player_key)
    valid = keys.ne("") & np.isfinite(actual_pdk.to_numpy(dtype=float, na_value=np.nan))
    valid_rows = pd.DataFrame({"key": keys.loc[valid], "score": actual_pdk.loc[valid].astype(float)})
    # Duplicate normalized identities with conflicting outcomes are ambiguous;
    # exclude them instead of silently letting row order choose the score.
    duplicated = valid_rows["key"].duplicated(keep=False)
    if duplicated.any():
        conflicting = valid_rows.loc[duplicated].groupby("key")["score"].nunique()
        ambiguous = set(conflicting[conflicting > 1].index)
        valid_rows = valid_rows.loc[~valid_rows["key"].isin(ambiguous)]
        valid_rows = valid_rows.drop_duplicates("key", keep="last")
    return dict(zip(valid_rows["key"], valid_rows["score"]))


_POST_MATCH_MARKET_COLUMNS = (
    "pdk", "prior_pdk", "actual_pdk", "target_pdk", "target_min",
    "plus", "official_plusvalenza", "gameweek_stats_available",
    "game_status_final", "final_score", "home_score", "away_score",
)


def _mask_post_match_market_outcomes(dk: pd.DataFrame) -> pd.DataFrame:
    """Remove same-round outcomes from the input used to generate historical forecasts."""
    out = dk.copy()
    for column in _POST_MATCH_MARKET_COLUMNS:
        if column in out.columns:
            out[column] = np.nan
    return out


def _realized_player_score(
    solution, realized_map: dict[str, float], transfer_penalty: float
) -> tuple[float, bool]:
    selected_keys = solution.players["player_name"].map(player_key)
    complete = selected_keys.isin(realized_map).all()
    if not complete:
        return float("nan"), False
    score = 0.0
    for _, player in solution.players.iterrows():
        value = float(realized_map[player_key(player["player_name"])])
        slot = str(player.get("slot", "Bench"))
        score += value * player_contribution_multiplier(
            slot in {"Starter", "Captain"}, slot == "Sixth Man", slot == "Captain"
        )
    return score - solution.num_transfers * transfer_penalty, True



def _realized_coach_scores(
    coach_market: pd.DataFrame, team_logs: pd.DataFrame, gw_games: pd.DataFrame
) -> dict[str, float]:
    """Compute official coach points from verified final scores and archived coach credits."""
    required = {"coach", "team", "coach_cr", "opponent", "opponent_coach_cr"}
    game_col = "Game_ID" if "Game_ID" in team_logs else "GAME_ID" if "GAME_ID" in team_logs else None
    if coach_market.empty or not required.issubset(coach_market.columns) or game_col is None:
        return {}
    if not {"TEAM_ABBREVIATION", "PTS"}.issubset(team_logs.columns):
        return {}
    logs = team_logs.copy()
    logs["_game_id"] = logs[game_col].astype(str)
    logs["_team"] = logs["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    logs["_pts"] = pd.to_numeric(logs["PTS"], errors="coerce")
    logs["_minutes"] = pd.to_numeric(logs.get("MIN", pd.Series(np.nan, index=logs.index)), errors="coerce")
    if logs["_minutes"].isna().all() and "MIN" in logs:
        logs["_minutes"] = pd.to_timedelta(logs["MIN"], errors="coerce").dt.total_seconds() / 60.0
    allowed_ids = set(gw_games.get("nba_game_id", pd.Series(dtype=str)).astype(str))
    scores = {}
    for _, row in coach_market.iterrows():
        name = str(row.get("coach", "")).strip()
        team = str(row.get("team", "")).strip().upper()
        opponent = str(row.get("opponent", "")).strip().upper()
        coach_cr = pd.to_numeric(pd.Series([row.get("coach_cr")]), errors="coerce").iloc[0]
        opponent_cr = pd.to_numeric(pd.Series([row.get("opponent_coach_cr")]), errors="coerce").iloc[0]
        if not name or not team or not opponent or not np.isfinite(coach_cr) or not np.isfinite(opponent_cr):
            continue
        game_id = str(row.get("nba_game_id", "")).strip()
        candidates = logs.loc[logs["_game_id"].eq(game_id)] if game_id not in {"", "nan", "None", "<NA>"} else logs.iloc[0:0]
        if game_id and allowed_ids and game_id not in allowed_ids:
            continue
        if candidates.empty:
            pairs = gw_games.loc[
                (gw_games["HOME_TEAM"].eq(team) & gw_games["AWAY_TEAM"].eq(opponent))
                | (gw_games["HOME_TEAM"].eq(opponent) & gw_games["AWAY_TEAM"].eq(team))
            ]
            for target_id in pairs.get("nba_game_id", pd.Series(dtype=str)).astype(str):
                candidates = logs.loc[logs["_game_id"].eq(target_id)]
                if not candidates.empty:
                    break
        own = candidates.loc[candidates["_team"].eq(team)]
        opp = candidates.loc[candidates["_team"].eq(opponent)]
        if own.empty or opp.empty:
            continue
        own_pts = float(own["_pts"].iloc[0]) if pd.notna(own["_pts"].iloc[0]) else np.nan
        opp_pts = float(opp["_pts"].iloc[0]) if pd.notna(opp["_pts"].iloc[0]) else np.nan
        if not np.isfinite(own_pts) or not np.isfinite(opp_pts):
            continue
        minutes = pd.concat([own["_minutes"], opp["_minutes"]], ignore_index=True)
        overtime = bool(minutes.gt(240.0).any()) if minutes.notna().any() else False
        scores[player_key(name)] = coach_points_from_game(
            own_pts, opp_pts, float(coach_cr), float(opponent_cr), overtime
        )
    return scores

def _compare_risk_objectives(
    players: pd.DataFrame,
    coaches: pd.DataFrame,
    settings: Settings,
    realized_map: dict[str, float],
    gameweek: int,
    current_roster: list[str] | None = None,
    current_coach: str | None = None,
) -> list[dict]:
    if not realized_map:
        return []
    configurations = [("expected_value", None)] + [
        ("risk_adjusted", risk_lambda)
        for risk_lambda in sorted(set(settings.optimizer_risk_lambda_grid))
    ]
    rows = []
    for objective, risk_lambda in configurations:
        comparison_settings = copy(settings)
        comparison_settings.optimizer_objective = objective
        if risk_lambda is not None:
            comparison_settings.risk_lambda = risk_lambda
        try:
            solutions = optimize_top_k_lineups(
                players, coaches, comparison_settings,
                current_roster=current_roster, current_coach=current_coach, k=1
            )
        except ValueError as exc:
            rows.append({
                "gameweek": gameweek,
                "objective": objective,
                "risk_lambda": risk_lambda,
                "realized_player_score": float("nan"),
                "player_actuals_complete": False,
                "solver_error": str(exc),
            })
            continue
        if not solutions:
            continue
        solution = solutions[0]
        realized_score, complete = _realized_player_score(
            solution, realized_map, comparison_settings.transfer_penalty
        )
        rows.append({
            "gameweek": gameweek,
            "objective": objective,
            "risk_lambda": risk_lambda,
            "expected_player_score": solution.expected_player_pdk,
            "expected_coach_score": solution.expected_coach_pdk,
            "realized_player_score": realized_score,
            "player_actuals_complete": complete,
            "captain": solution.captain,
            "coach": solution.coach,
            "solver_status": solution.meta["solver"]["status"],
            "solver_time_seconds": solution.meta["solver"]["solve_time_seconds"],
        })
    return rows


def _neutral_coaches(games: pd.DataFrame, minimum_cr: float) -> pd.DataFrame:
    home_valid = games.get("home_team_eligible", games.get("fantasy_eligible", True))
    away_valid = games.get("away_team_eligible", games.get("fantasy_eligible", True))
    teams = set(games.loc[pd.Series(home_valid, index=games.index).fillna(False).astype(bool), "HOME_TEAM"].astype(str))
    teams.update(games.loc[pd.Series(away_valid, index=games.index).fillna(False).astype(bool), "AWAY_TEAM"].astype(str))
    teams = sorted(teams)
    return pd.DataFrame({
        "coach": [f"Neutral coach {team}" for team in teams],
        "team": teams,
        "coach_cr": float(minimum_cr),
        "expected_coach_pdk": 0.0,
        "opponent": "",
    })


def _load_historical_market_snapshot(path: Path, gameweek: int) -> pd.DataFrame:
    required = {
        "player_name", "team_code", "role", "cr", "gameweek", "lineup_group", "status"
    }
    if not path.exists():
        raise ValueError(
            f"Backtest non valido per GW{gameweek}: snapshot listino mancante ({path}). "
            "Raccogli il listino prepartita per questo turno prima di eseguire il backtest."
        )

    snapshot = pd.read_parquet(path)
    missing = sorted(required.difference(snapshot.columns))
    if missing:
        raise ValueError(
            f"Backtest non valido per GW{gameweek}: snapshot listino incompleto "
            f"({path}); colonne mancanti: {', '.join(missing)}."
        )

    snapshot = snapshot.copy()
    snapshot["player_name"] = snapshot["player_name"].astype(str).str.strip()
    snapshot["team_code"] = snapshot["team_code"].astype(str).str.strip().str.upper()
    snapshot["role"] = snapshot["role"].astype(str).str.strip().str.upper()
    snapshot["cr"] = pd.to_numeric(snapshot["cr"], errors="coerce")
    snapshot["gameweek"] = pd.to_numeric(snapshot["gameweek"], errors="coerce")
    snapshot["_key"] = snapshot["player_name"].map(player_key)
    invalid = (
        snapshot["player_name"].isin({"", "nan"})
        | snapshot["team_code"].isin({"", "NAN"})
        | ~snapshot["role"].isin({"G", "F", "C"})
        | ~np.isfinite(snapshot["cr"])
        | snapshot["gameweek"].ne(gameweek)
    )
    duplicate_names = snapshot["_key"].duplicated(keep=False)
    if invalid.any() or duplicate_names.any() or len(snapshot) < MIN_HISTORICAL_MARKET_PLAYERS:
        raise ValueError(
            f"Backtest non valido per GW{gameweek}: snapshot listino incompleto o non valido "
            f"({path}); {len(snapshot)} righe, minimo {MIN_HISTORICAL_MARKET_PLAYERS}. "
            "Verifica nomi, team, ruoli, CR e gameweek archiviati."
        )
    return snapshot.set_index("_key", drop=False)


def _apply_historical_market_snapshot(
    players: pd.DataFrame, snapshot: pd.DataFrame
) -> pd.DataFrame:
    out = players.copy()
    out["_key"] = out["player_name"].map(player_key)
    out = out.loc[out["_key"].isin(snapshot.index)].copy()
    for source, target in (
        ("cr", "cr"),
        ("team_code", "team_code"),
        ("role", "role"),
        ("role", "position"),
        ("lineup_group", "lineup_group"),
        ("status", "status"),
    ):
        out[target] = out["_key"].map(snapshot[source])
    if len(out) < MIN_HISTORICAL_MARKET_PLAYERS:
        raise ValueError(
            "Backtest non valido: il listino storico si allinea a meno di "
            f"{MIN_HISTORICAL_MARKET_PLAYERS} giocatori nei dati Dunkest "
            f"({len(out)} allineati)."
        )
    return out


def run_walk_forward_backtest(
    settings: Settings, from_gw: int, to_gw: int
) -> tuple[pd.DataFrame, BacktestReport, dict]:
    readiness = {
        gw: check_backtest_readiness(settings, gw)
        for gw in range(from_gw, to_gw + 1)
    }
    if any(not item["backtest_ready"] for item in readiness.values()):
        # A partial dataset must not be turned into apparently valid lineup
        # metrics. Keep the per-input evidence visible to the caller.
        empty = pd.DataFrame()
        return empty, compute_backtest_metrics(empty), {"readiness": readiness, "backtest_ready": False}

    player_logs = get_player_data(settings)
    team_logs = get_team_data(settings)
    if (
        "data_source" in player_logs
        and player_logs["data_source"].astype(str).eq("synthetic_dunkest_market").any()
    ) or (
        "OPPONENT" in player_logs
        and player_logs["OPPONENT"].astype(str).eq("OPP").any()
    ):
        raise ValueError(
            "Backtest non valido con log sintetici: raccogli log NBA reali prima di calcolare le metriche."
        )
    schedule = get_fixture_mapping(settings)
    rows: list[dict] = []
    forecast_metric_rows: list[dict] = []
    risk_comparison_rows: list[dict] = []
    carried_roster: list[str] = []
    carried_coach: str | None = None
    carried_roster_known = from_gw == 1
    holdout_count = max(1, int(np.ceil((to_gw - from_gw + 1) * 0.20)))
    holdout_start_gw = max(from_gw, to_gw - holdout_count + 1)
    last_feats = pd.DataFrame()

    if schedule.empty or "dunkest_gameweek" not in schedule:
        empty = pd.DataFrame()
        return empty, compute_backtest_metrics(empty), {"readiness": readiness, "backtest_ready": False}
    schedule = schedule.copy()
    schedule["GAME_DATE"] = pd.to_datetime(schedule["game_datetime_utc"], errors="coerce", utc=True)
    schedule["NBA_GAME_ID"] = schedule["nba_game_id"].astype(str)
    schedule["GAME_ID"] = schedule["nba_game_id"].astype(str)
    schedule["HOME_TEAM"] = schedule["home_team"].astype(str).str.upper()
    schedule["AWAY_TEAM"] = schedule["away_team"].astype(str).str.upper()

    for gw in range(from_gw, to_gw + 1):
        gw_games = schedule.loc[
            pd.to_numeric(schedule["dunkest_gameweek"], errors="coerce").eq(gw)
            & schedule["fantasy_eligible"].fillna(False).astype(bool)
        ]
        if gw_games.empty:
            continue
        cutoff = gw_games["GAME_DATE"].min()
        cutoff_date = cutoff.date()
        prior_players = player_logs.loc[
            pd.to_datetime(player_logs["GAME_DATE"], errors="coerce").dt.date.lt(cutoff_date)
        ].copy()
        prior_teams = team_logs.loc[
            pd.to_datetime(team_logs["GAME_DATE"], errors="coerce").dt.date.lt(cutoff_date)
        ].copy() if not team_logs.empty else team_logs
        round_settings = copy(settings)
        round_settings.target_gameweek = gw
        round_settings.current_roster = list(carried_roster)
        round_settings.current_coach = carried_coach

        # Current injury reports cannot be applied to historical rounds.
        feats = build_feature_matrix(
            round_settings, prior_players, prior_teams, pd.DataFrame(),
            schedule=schedule,
            team_overrides=None,
            target_gameweek=gw,
            include_completed_schedule=True,
        )
        last_feats = feats
        if feats.empty:
            continue
        train_mask = ~feats.get("is_inference", pd.Series(False, index=feats.index)).fillna(False).astype(bool)
        train_mask &= pd.to_datetime(feats["GAME_DATE"], errors="coerce").dt.date.lt(cutoff_date)
        train_feats = feats.loc[train_mask]
        if train_feats.empty:
            continue
        models, _ = train_models(round_settings, train_feats)

        # Re-fetch each historical GW without today's Lineups market. This
        # prevents current prices/team assignments from overriding archived
        # gameweek data; only the historical Dunkest API data is eligible here.
        dk = get_dunkest_data(
            round_settings, gw, force_refresh=True, use_live_market=False
        )
        if dk.empty:
            continue
        market_snapshot_path = settings.data_path / "processed" / (
            f"player_credits_{settings.season_id}_gw{gw}.parquet"
        )
        market_snapshot = _load_historical_market_snapshot(market_snapshot_path, gw)
        # The archived market defines who was selectable and their actual
        # pregame metadata. Current API values must never fill historical gaps.
        dk = _apply_historical_market_snapshot(dk, market_snapshot)
        injury_snapshot_path = settings.data_path / "processed" / (
            f"injuries_{settings.season_id}_gw{gw}.parquet"
        )
        historical_injuries_available = injury_snapshot_path.exists()
        historical_injuries = (
            pd.read_parquet(injury_snapshot_path)
            if historical_injuries_available else pd.DataFrame()
        )
        if dk.empty:
            continue
        realized_map = _realized_player_scores(dk)
        # The GW table contains outcomes. Do not pass those scores into inference.
        dk_for_prediction = _mask_post_match_market_outcomes(dk)
        preds = predict_players(
            round_settings, models, feats, dk_for_prediction, historical_injuries
        )
        metric_frame = preds.copy()
        if "player_name" in metric_frame and "expected_pdk" in metric_frame:
            metric_frame["actual_pdk"] = metric_frame["player_name"].map(
                lambda name: realized_map.get(player_key(name), np.nan)
            )
            metric_frame["expected_pdk"] = pd.to_numeric(metric_frame["expected_pdk"], errors="coerce")
            metric_frame = metric_frame.loc[
                np.isfinite(pd.to_numeric(metric_frame["actual_pdk"], errors="coerce"))
                & np.isfinite(metric_frame["expected_pdk"])
            ].copy()
            if not metric_frame.empty:
                error = metric_frame["expected_pdk"] - metric_frame["actual_pdk"]
                interval = metric_frame[[column for column in ("p10", "p90") if column in metric_frame]].apply(
                    pd.to_numeric, errors="coerce"
                )
                valid_interval = interval.dropna() if {"p10", "p90"}.issubset(interval.columns) else pd.DataFrame()
                forecast_metric_rows.append({
                    "gameweek": gw,
                    "evaluation_split": "holdout" if gw >= holdout_start_gw else "selection",
                    "n_player_games": int(len(metric_frame)),
                    "mae": float(np.mean(np.abs(error))),
                    "rmse": float(np.sqrt(np.mean(np.square(error)))),
                    "bias": float(np.mean(error)),
                    "p10_coverage": float(metric_frame.loc[valid_interval.index, "actual_pdk"].ge(valid_interval["p10"]).mean()) if not valid_interval.empty else float("nan"),
                    "p90_coverage": float(metric_frame.loc[valid_interval.index, "actual_pdk"].le(valid_interval["p90"]).mean()) if not valid_interval.empty else float("nan"),
                    "interval_80_coverage": float((metric_frame.loc[valid_interval.index, "actual_pdk"].ge(valid_interval["p10"]) & metric_frame.loc[valid_interval.index, "actual_pdk"].le(valid_interval["p90"])).mean()) if not valid_interval.empty else float("nan"),
                    "mean_interval_width": float((valid_interval["p90"] - valid_interval["p10"]).mean()) if not valid_interval.empty else float("nan"),
                })

        coach_snapshot_path = settings.data_path / "processed" / (
            f"coach_market_{settings.season_id}_gw{gw}.parquet"
        )
        coach_market = (
            pd.read_parquet(coach_snapshot_path)
            if coach_snapshot_path.exists() else pd.DataFrame()
        )
        historical_coach_market_available = not coach_market.empty
        if historical_coach_market_available:
            # Keep the historical matchup row even though the NBA schedule
            # now marks it completed; all player/team logs remain cut off
            # before that game's date.
            coach_schedule = schedule.drop(columns=["GAME_STATUS"], errors="ignore")
            coach_df = predict_coach_points(
                coach_market,
                team_logs=prior_teams if not prior_teams.empty else None,
                upcoming_schedule=coach_schedule,
                player_logs=prior_players if not prior_players.empty else None,
                player_forecasts=preds,
                gameweek=gw,
                use_model=round_settings.use_coach_model,
            )
        else:
            # No historical coach list is available for this round; don't use
            # today's prices to fill the gap.
            coach_df = _neutral_coaches(gw_games, round_settings.min_cr)
        risk_rows = _compare_risk_objectives(
            preds, coach_df, round_settings, realized_map, gw,
            current_roster=round_settings.current_roster,
            current_coach=round_settings.current_coach,
        )
        for risk_row in risk_rows:
            risk_row["evaluation_split"] = "holdout" if gw >= holdout_start_gw else "selection"
        risk_comparison_rows.extend(risk_rows)
        selected_strategy = None
        if gw >= holdout_start_gw and risk_comparison_rows:
            selection_frame = pd.DataFrame(risk_comparison_rows)
            selection_frame = selection_frame.loc[
                selection_frame.get("evaluation_split", pd.Series(index=selection_frame.index, dtype=str)).eq("selection")
            ]
            selection_frame["realized_player_score"] = pd.to_numeric(
                selection_frame.get("realized_player_score"), errors="coerce"
            )
            selection_frame = selection_frame.dropna(subset=["realized_player_score"])
            if not selection_frame.empty:
                means = selection_frame.groupby(
                    ["objective", "risk_lambda"], dropna=False, as_index=False
                )["realized_player_score"].mean()
                chosen = means.sort_values(
                    ["realized_player_score", "objective", "risk_lambda"],
                    ascending=[False, True, True], kind="stable"
                ).iloc[0]
                selected_strategy = {
                    "objective": str(chosen["objective"]),
                    "risk_lambda": float(chosen["risk_lambda"]) if pd.notna(chosen["risk_lambda"]) else None,
                    "selection_mean_realized_player_score": float(chosen["realized_player_score"]),
                    "selection_gameweeks": sorted(selection_frame["gameweek"].unique().tolist()),
                }
                round_settings.optimizer_objective = selected_strategy["objective"]
                if selected_strategy["risk_lambda"] is not None:
                    round_settings.risk_lambda = selected_strategy["risk_lambda"]
        lineups = optimize_top_k_lineups(preds, coach_df, round_settings, k=3)
        realized_coach_map = _realized_coach_scores(coach_market, team_logs, gw_games) if historical_coach_market_available else {}
        # An ex-post optimum is meaningful only if every candidate in the
        # prediction universe has a finite realized score. Assigning missing
        # outcomes zero would silently bias the hindsight optimum.
        hindsight_complete = bool(
            realized_map
            and "player_name" in preds
            and preds["player_name"].map(player_key).ne("").all()
            and preds["player_name"].map(player_key).isin(realized_map).all()
        )
        hindsight = preds.copy()
        if hindsight_complete:
            hindsight["expected_pdk"] = hindsight["player_name"].map(
                lambda name: realized_map[player_key(name)]
            )
            hindsight["p10"] = hindsight["expected_pdk"]
            hindsight["p50"] = hindsight["expected_pdk"]
            hindsight["p90"] = hindsight["expected_pdk"]
        else:
            hindsight = pd.DataFrame()
        if not hindsight.empty:
            hindsight["p_play"] = 1.0
            hindsight["status"] = "Available"
            hindsight["expected_min"] = 40.0
        coach_hindsight_complete = bool(
            historical_coach_market_available
            and not coach_df.empty
            and "coach" in coach_df
            and coach_df["coach"].map(player_key).isin(realized_coach_map).all()
        )
        coach_hindsight = coach_df.copy()
        if coach_hindsight_complete:
            coach_hindsight["expected_coach_pdk"] = coach_hindsight["coach"].map(
                lambda name: realized_coach_map[player_key(name)]
            )
        else:
            coach_hindsight = pd.DataFrame()
        ex_post_lineups = optimize_top_k_lineups(
            hindsight, coach_hindsight, round_settings, k=1
        ) if not hindsight.empty and coach_hindsight_complete and carried_roster_known else []
        ex_post_score = float("nan")
        if ex_post_lineups:
            ex_sol = ex_post_lineups[0]
            ex_post_score = -ex_sol.num_transfers * round_settings.transfer_penalty
            for _, player in ex_sol.players.iterrows():
                slot = str(player.get("slot", "Bench"))
                value = realized_map.get(player_key(player["player_name"]))
                if value is not None:
                    ex_post_score += float(value) * player_contribution_multiplier(
                        slot in {"Starter", "Captain"}, slot == "Sixth Man", slot == "Captain"
                    )
            ex_post_score += float(realized_coach_map[player_key(ex_sol.coach)])


        for rank, sol in enumerate(lineups, start=1):
            actuals: dict[str, float] = {}
            player_score_before_transfers = 0.0
            for _, player in sol.players.iterrows():
                key = player_key(player["player_name"])
                if key not in realized_map:
                    continue
                actuals[key] = float(realized_map[key])
                slot = str(player.get("slot", "Bench"))
                player_score_before_transfers += actuals[key] * player_contribution_multiplier(
                    slot in {"Starter", "Captain"}, slot == "Sixth Man", slot == "Captain"
                )
            complete = set(sol.players["player_name"].map(player_key)).issubset(actuals)
            coach_score = realized_coach_map.get(player_key(sol.coach), float("nan"))
            transfer_count = float(sol.num_transfers) if carried_roster_known else float("nan")
            transfer_malus = transfer_count * round_settings.transfer_penalty if np.isfinite(transfer_count) else float("nan")
            player_score = (
                player_score_before_transfers - transfer_malus
                if complete and np.isfinite(transfer_malus) else float("nan")
            )
            team_score = (
                player_score + coach_score
                if np.isfinite(player_score) and np.isfinite(coach_score) else float("nan")
            )
            captain_hit = float("nan")
            captain_row = sol.players.loc[sol.players["slot"].eq("Captain")]
            eligible = sol.players.loc[
                sol.players["slot"].isin({"Starter", "Captain"})
                & pd.to_numeric(sol.players["expected_min"], errors="coerce").ge(22.0)
            ]
            if not captain_row.empty:
                cap_key = player_key(captain_row.iloc[0]["player_name"])
                eligible_scores = eligible["player_name"].map(player_key).map(actuals).dropna()
                if cap_key in actuals and not eligible_scores.empty:
                    captain_hit = float(actuals[cap_key] >= eligible_scores.max())
            rows.append({
                "gameweek": gw, "rank": rank,
                "evaluation_split": "holdout" if gw >= holdout_start_gw else "selection",
                "optimizer_objective": round_settings.optimizer_objective,
                "risk_lambda": round_settings.risk_lambda,
                "expected_team_pdk": sol.expected_team_pdk,
                "realized_player_score_before_transfers": player_score_before_transfers if complete else float("nan"),
                "realized_player_score": player_score,
                "realized_coach_score": coach_score,
                "transfer_malus": transfer_malus,
                "realized_team_score": team_score,
                "ex_post_optimum": ex_post_score,
                "ex_post_player_optimum": ex_post_score,
                "captain": sol.captain, "coach": sol.coach,
                "num_transfers": transfer_count,
                "captain_hit": captain_hit, "coach_hit": float("nan"),
                "player_actuals_complete": complete,
                "actual_score_complete": bool(np.isfinite(team_score)),
                "coach_score_available": bool(np.isfinite(coach_score)),
                "historical_market_available": True,
                "historical_market_rows": len(market_snapshot),
                "historical_coach_market_available": historical_coach_market_available,
                "historical_injuries_available": historical_injuries_available,
                "transfer_count_available": carried_roster_known,
            })
        # Simulate a live policy by carrying the rank-1 roster and coach into the next GW.
        if lineups:
            carried_roster = lineups[0].players["player_name"].astype(str).tolist()
            carried_coach = str(lineups[0].coach)
            carried_roster_known = True

    results = pd.DataFrame(rows)
    report = compute_backtest_metrics(results)
    ablation_settings = copy(settings)
    ablation_settings.target_gameweek = to_gw
    extras = {
        "readiness": readiness,
        "backtest_ready": True,
        "ablation": run_ablation_summary(
            ablation_settings,
            player_logs,
            team_logs,
            pd.DataFrame(),
            schedule=schedule,
            target_gameweek=to_gw,
        ),
        "importance": feature_importance_summary(settings, last_feats),
        "risk_comparison": pd.DataFrame(risk_comparison_rows),
        "forecast_metrics": pd.DataFrame(forecast_metric_rows),
        "holdout_start_gameweek": holdout_start_gw,
        "selection_gameweeks": list(range(from_gw, holdout_start_gw)),
        "holdout_gameweeks": list(range(holdout_start_gw, to_gw + 1)),
        "selected_holdout_strategy": selected_strategy if "selected_strategy" in locals() else None,
    }
    return results, report, extras
