from __future__ import annotations

from copy import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dunkest.backtest.metrics import BacktestReport, compute_backtest_metrics
from dunkest.config import Settings
from dunkest.data.access import (
    get_player_data,
    get_team_data,
)
from dunkest.data.dunkest.fixtures import (
    check_backtest_readiness,
    get_fixture_mapping,
    load_post_match_results_archive,
    load_pre_match_snapshot,
)
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import train_models
from dunkest.models.rookie_prior import load_college_rookie_priors
from dunkest.pipeline.forecast import build_player_forecast
from dunkest.models.coach import predict_coach_points
from dunkest.names import player_key
from dunkest.optimize.milp import optimize_top_k_lineups
from dunkest.pipeline.ablation import run_ablation_summary
from dunkest.pipeline.importance import feature_importance_summary
from dunkest.rules.roster import player_contribution_multiplier
from dunkest.backtest.realized_scoring import score_realized_team

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


def _archived_coach_scores(results: pd.DataFrame) -> dict[str, float]:
    """Read finite coach outcomes from the same immutable post-match archive."""
    required = {"coach", "actual_coach_pdk", "nba_game_id"}
    if results.empty or not required.issubset(results.columns):
        return {}
    scores = pd.to_numeric(results["actual_coach_pdk"], errors="coerce")
    keys = results["coach"].map(player_key)
    valid = (
        keys.ne("")
        & results["nba_game_id"].notna()
        & np.isfinite(scores.to_numpy(dtype=float, na_value=np.nan))
    )
    rows = pd.DataFrame({"key": keys.loc[valid], "score": scores.loc[valid].astype(float)})
    duplicates = rows["key"].duplicated(keep=False)
    if duplicates.any():
        conflicts = rows.loc[duplicates].groupby("key")["score"].nunique()
        ambiguous = set(conflicts[conflicts > 1].index)
        rows = rows.loc[~rows["key"].isin(ambiguous)].drop_duplicates("key", keep="last")
    return dict(zip(rows["key"], rows["score"]))


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
        supplied_multiplier = pd.to_numeric(player.get("score_multiplier", float("nan")), errors="coerce")
        multiplier = (
            float(supplied_multiplier)
            if pd.notna(supplied_multiplier)
            else player_contribution_multiplier(
                slot in {"Starter", "Captain"}, slot == "Sixth Man", slot == "Captain"
            )
        )
        if not np.isfinite(multiplier) or multiplier < 0:
            return float("nan"), False
        score += value * multiplier
    return score - solution.num_transfers * transfer_penalty, True



def _compare_risk_objectives(
    players: pd.DataFrame,
    coaches: pd.DataFrame,
    settings: Settings,
    realized_map: dict[str, float],
    gameweek: int,
    current_roster: list[str] | None = None,
    current_coach: str | None = None,
    realized_coach_map: dict[str, float] | None = None,
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
            if current_roster is None and current_coach is None:
                solutions = optimize_top_k_lineups(
                    players, coaches, comparison_settings, k=1
                )
            else:
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
        coach_actual = (
            (realized_coach_map or {}).get(player_key(solution.coach), float("nan"))
        )
        realized_team_score = (
            realized_score + coach_actual
            if complete and np.isfinite(coach_actual) else float("nan")
        )
        rows.append({
            "gameweek": gameweek,
            "objective": objective,
            "risk_lambda": risk_lambda,
            "expected_player_score": solution.expected_player_pdk,
            "expected_coach_score": solution.expected_coach_pdk,
            "realized_player_score": realized_score,
            "realized_coach_score": coach_actual,
            "realized_team_score": realized_team_score,
            "player_actuals_complete": complete,
            "captain": solution.captain,
            "captain_schedule": json.dumps(solution.meta.get("captain_schedule", {}), ensure_ascii=False, sort_keys=True),
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


def _load_historical_market_snapshot(path: Path | pd.DataFrame, gameweek: int) -> pd.DataFrame:
    required = {
        "player_name", "team_code", "role", "cr", "gameweek", "lineup_group", "status"
    }
    if isinstance(path, pd.DataFrame):
        snapshot = path.copy()
        source_label = "immutable PRE_MATCH player_market.parquet"
    else:
        if not path.exists():
            raise ValueError(
                f"Backtest non valido per GW{gameweek}: snapshot listino mancante ({path}). "
                "Raccogli il listino prepartita per questo turno prima di eseguire il backtest."
            )
        snapshot = pd.read_parquet(path)
        source_label = str(path)
    missing = sorted(required.difference(snapshot.columns))
    if missing:
        raise ValueError(
            f"Backtest non valido per GW{gameweek}: snapshot listino incompleto "
            f"({source_label}); colonne mancanti: {', '.join(missing)}."
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
            f"({source_label}); {len(snapshot)} righe, minimo {MIN_HISTORICAL_MARKET_PLAYERS}. "
            "Verifica nomi, team, ruoli, CR e gameweek archiviati."
        )
    return snapshot.set_index("_key", drop=False)


def _historical_candidate_pool(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Build the forecast universe from the frozen pregame market, not result rows."""
    required = {"player_name", "team_code", "role", "cr"}
    missing = sorted(required.difference(snapshot.columns))
    if missing:
        raise ValueError(
            "Backtest non valido: snapshot mercato senza colonne per il pool "
            f"pregara ({', '.join(missing)})."
        )
    market_columns = [
        column for column in (
            "player_name", "team_code", "role", "cr", "lineup_group",
            "status", "dunkest_turn", "gameweek",
        )
        if column in snapshot.columns
    ]
    out = snapshot[market_columns].reset_index(drop=True).copy()
    out["position"] = out["role"]
    # Result/season-stat fields deliberately do not enter the forecast pool.
    # They are consumed separately by _realized_player_scores after prediction.
    return out


def run_walk_forward_backtest(
    settings: Settings, from_gw: int, to_gw: int
) -> tuple[pd.DataFrame, BacktestReport, dict]:
    readiness = {
        gw: check_backtest_readiness(settings, gw)
        for gw in range(from_gw, to_gw + 1)
    }
    # Starting after GW1 without a fixture-linked carried roster would make
    # the first evaluated round appear transfer-free. Fail closed instead of
    # publishing an optimistic score with an unknown starting state.
    if from_gw > 1 and (not settings.current_roster or not settings.current_coach):
        readiness[from_gw]["backtest_ready"] = False
        readiness[from_gw].setdefault("checks", {})["INITIAL_ROSTER"] = {
            "pass": False,
            "reason": (
                "backtest starts after GW1 but no explicit initial current_roster/current_coach "
                "was supplied; transfer malus cannot be reconstructed"
            ),
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
    selected_strategy = None
    forecast_metric_rows: list[dict] = []
    risk_comparison_rows: list[dict] = []
    selected_strategy = None
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
        prematch_archive = load_pre_match_snapshot(settings, gw)
        if prematch_archive is None:
            # Readiness should already have failed closed; retain a defensive
            # guard in case the archive changes between preflight and replay.
            raise RuntimeError(f"GW{gw}: immutable PRE_MATCH archive disappeared or failed hash/timing validation")
        archive_tables = prematch_archive["tables"]
        archived_mapping = archive_tables["_verified_fixture_mapping"].copy()
        archived_mapping = archived_mapping.rename(columns={
            "game_datetime_utc": "GAME_DATE",
            "nba_game_id": "NBA_GAME_ID",
        })
        archived_mapping["GAME_ID"] = archived_mapping["NBA_GAME_ID"].astype(str)
        archived_mapping["HOME_TEAM"] = archived_mapping["home_team"].astype(str).str.upper()
        archived_mapping["AWAY_TEAM"] = archived_mapping["away_team"].astype(str).str.upper()
        archived_mapping["GAME_DATE"] = pd.to_datetime(archived_mapping["GAME_DATE"], errors="coerce", utc=True)
        archived_gw = pd.to_numeric(archived_mapping["dunkest_gameweek"], errors="coerce").eq(gw)
        round_schedule = pd.concat([
            schedule.loc[pd.to_numeric(schedule["dunkest_gameweek"], errors="coerce").ne(gw)],
            archived_mapping.loc[archived_gw],
        ], ignore_index=True, sort=False)
        gw_games = round_schedule.loc[
            pd.to_numeric(round_schedule["dunkest_gameweek"], errors="coerce").eq(gw)
            & round_schedule["fantasy_eligible"].fillna(False).astype(bool)
        ]
        if gw_games.empty:
            raise RuntimeError(f"GW{gw}: verified PRE_MATCH archive contains no eligible fixture rows")
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
            schedule=round_schedule,
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

        # Outcomes come only from the hash-verified immutable post-match
        # archive that satisfied readiness. Never refetch today's aggregate
        # Dunkest table for a historical round.
        outcome_archive = load_post_match_results_archive(settings, gw)
        if outcome_archive is None:
            continue
        market_snapshot = _load_historical_market_snapshot(
            archive_tables["_normalized_player_market"], gw
        )
        # The market and injuries are read from the exact same immutable
        # pre-lock archive. Mutable processed/current snapshots are never used
        # as fallback for an archive-backed replay.
        historical_injuries = archive_tables["injuries.parquet"].copy()
        archived_player_results = outcome_archive["players"].copy()
        archived_player_results["gameweek_stats_available"] = True
        realized_map = _realized_player_scores(archived_player_results)
        # Keep archived outcomes out of inference, and do not let result-row
        # coverage shrink the candidate pool from the pregame market snapshot.
        historical_candidate_pool = _historical_candidate_pool(market_snapshot)
        # The same forecast/filter function is used live and in backtests.
        # Only archived point-in-time priors may be supplied here; current
        # market/PLUS state is intentionally not backfilled into old rounds.
        historical_rookie_priors = load_college_rookie_priors(
            settings.data_path / "rookie_college.csv"
        )
        historical_market_value = historical_candidate_pool.copy()
        forecast = build_player_forecast(
            round_settings,
            models,
            feats,
            historical_candidate_pool,
            historical_injuries,
            market_value_history=historical_market_value,
            plusvalenza_history=pd.DataFrame(),
            college_rookie_priors=historical_rookie_priors,
            require_injury_snapshot=True,
        )
        preds = forecast.eligible.copy()
        metric_frame = preds.copy()
        if "player_name" in metric_frame and "expected_pdk" in metric_frame:
            metric_frame["expected_pdk"] = pd.to_numeric(metric_frame["expected_pdk"], errors="coerce")
            metric_frame = metric_frame.loc[
                np.isfinite(metric_frame["expected_pdk"])
                & metric_frame["player_name"].map(player_key).ne("")
            ].copy()
            n_predictions = int(len(metric_frame))
            metric_frame["actual_pdk"] = metric_frame["player_name"].map(
                lambda name: realized_map.get(player_key(name), np.nan)
            )
            metric_frame = metric_frame.loc[
                np.isfinite(pd.to_numeric(metric_frame["actual_pdk"], errors="coerce"))
            ].copy()
            if n_predictions:
                n_scored = int(len(metric_frame))
                error = metric_frame["expected_pdk"] - metric_frame["actual_pdk"]
                interval = metric_frame[[column for column in ("p10", "p90") if column in metric_frame]].apply(
                    pd.to_numeric, errors="coerce"
                )
                valid_interval = interval.dropna() if {"p10", "p90"}.issubset(interval.columns) else pd.DataFrame()
                forecast_metric_rows.append({
                    "gameweek": gw,
                    "evaluation_split": "holdout" if gw >= holdout_start_gw else "selection",
                    "n_predictions": n_predictions,
                    "n_player_games": n_scored,
                    "n_missing_actual": n_predictions - n_scored,
                    "actual_coverage": n_scored / n_predictions,
                    "mae": float(np.mean(np.abs(error))) if n_scored else float("nan"),
                    "rmse": float(np.sqrt(np.mean(np.square(error)))) if n_scored else float("nan"),
                    "bias": float(np.mean(error)) if n_scored else float("nan"),
                    "p10_coverage": float(metric_frame.loc[valid_interval.index, "actual_pdk"].ge(valid_interval["p10"]).mean()) if not valid_interval.empty else float("nan"),
                    "p90_coverage": float(metric_frame.loc[valid_interval.index, "actual_pdk"].le(valid_interval["p90"]).mean()) if not valid_interval.empty else float("nan"),
                    "interval_80_coverage": float((metric_frame.loc[valid_interval.index, "actual_pdk"].ge(valid_interval["p10"]) & metric_frame.loc[valid_interval.index, "actual_pdk"].le(valid_interval["p90"])).mean()) if not valid_interval.empty else float("nan"),
                    "mean_interval_width": float((valid_interval["p90"] - valid_interval["p10"]).mean()) if not valid_interval.empty else float("nan"),
                    "forecast_degradations": ";".join(forecast.degradations),
                })

        coach_market = archive_tables["coach_market.parquet"].copy()
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
        realized_coach_map = (
            _archived_coach_scores(outcome_archive["coaches"])
            if historical_coach_market_available else {}
        )
        risk_rows = (
            _compare_risk_objectives(
                preds, coach_df, round_settings, realized_map, gw,
                current_roster=round_settings.current_roster,
                current_coach=round_settings.current_coach,
                realized_coach_map=realized_coach_map,
            )
            if carried_roster_known else []
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
            selection_frame["realized_team_score"] = pd.to_numeric(
                selection_frame.get("realized_team_score"), errors="coerce"
            )
            selection_frame = selection_frame.dropna(subset=["realized_team_score"])
            if not selection_frame.empty:
                means = selection_frame.groupby(
                    ["objective", "risk_lambda"], dropna=False, as_index=False
                )["realized_team_score"].mean()
                chosen = means.sort_values(
                    ["realized_team_score", "objective", "risk_lambda"],
                    ascending=[False, True, True], kind="stable"
                ).iloc[0]
                selected_strategy = {
                    "objective": str(chosen["objective"]),
                    "risk_lambda": float(chosen["risk_lambda"]) if pd.notna(chosen["risk_lambda"]) else None,
                    "selection_mean_realized_team_score": float(chosen["realized_team_score"]),
                    "selection_gameweeks": sorted(selection_frame["gameweek"].unique().tolist()),
                }
                round_settings.optimizer_objective = selected_strategy["objective"]
                if selected_strategy["risk_lambda"] is not None:
                    round_settings.risk_lambda = selected_strategy["risk_lambda"]
        # Evaluate the same stateful transfer policy as the live optimizer.
        # GW1 has no previous roster; subsequent rounds must pay for every
        # incoming player and coach using the roster carried from the prior GW.
        lineups = optimize_top_k_lineups(
            preds,
            coach_df,
            round_settings,
            current_roster=round_settings.current_roster if carried_roster_known else None,
            current_coach=round_settings.current_coach if carried_roster_known else None,
            k=3,
        )
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
            # Capital-gain forecasts are not realized game points and must not
            # influence the hindsight optimum for fantasy-score evaluation.
            hindsight["expected_plusvalenza"] = 0.0
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
        oracle_settings = copy(round_settings)
        oracle_settings.optimizer_objective = "expected_value"
        oracle_settings.risk_lambda = 0.0
        ex_post_lineups = optimize_top_k_lineups(
            hindsight,
            coach_hindsight,
            oracle_settings,
            current_roster=round_settings.current_roster if carried_roster_known else None,
            current_coach=round_settings.current_coach if carried_roster_known else None,
            k=1,
        ) if not hindsight.empty and coach_hindsight_complete and carried_roster_known else []
        ex_post_score = float("nan")
        ex_post_player_score = float("nan")
        if ex_post_lineups:
            ex_sol = ex_post_lineups[0]
            ex_post_player_score = -ex_sol.num_transfers * round_settings.transfer_penalty
            for _, player in ex_sol.players.iterrows():
                slot = str(player.get("slot", "Bench"))
                value = realized_map.get(player_key(player["player_name"]))
                if value is not None:
                    supplied_multiplier = pd.to_numeric(player.get("score_multiplier", float("nan")), errors="coerce")
                    multiplier = (
                        float(supplied_multiplier)
                        if pd.notna(supplied_multiplier)
                        else player_contribution_multiplier(
                            slot in {"Starter", "Captain"}, slot == "Sixth Man", slot == "Captain"
                        )
                    )
                    ex_post_player_score += float(value) * multiplier
            ex_post_score = ex_post_player_score + float(
                realized_coach_map[player_key(ex_sol.coach)]
            )


        for rank, sol in enumerate(lineups, start=1):
            actuals: dict[str, float] = {}
            for _, player in sol.players.iterrows():
                key = player_key(player["player_name"])
                if key in realized_map:
                    actuals[key] = float(realized_map[key])
            complete = set(sol.players["player_name"].map(player_key)).issubset(actuals)
            coach_score = realized_coach_map.get(player_key(sol.coach), float("nan"))
            coach_actuals_complete = bool(
                historical_coach_market_available
                and not coach_df.empty
                and "coach" in coach_df
                and coach_df["coach"].map(player_key).isin(realized_coach_map).all()
            )
            coach_hit = (
                float(coach_score >= max(realized_coach_map.values()))
                if np.isfinite(coach_score) and coach_actuals_complete else float("nan")
            )
            transfer_count = float(sol.num_transfers) if carried_roster_known else float("nan")
            realized = score_realized_team(
                sol.players,
                actuals,
                actual_coach_score=coach_score,
                transfer_count=transfer_count,
                transfer_penalty=round_settings.transfer_penalty,
                coach_fixture_verified=bool(historical_coach_market_available and np.isfinite(coach_score)),
            )
            complete = bool(complete and realized.complete)
            player_score_before_transfers = realized.player_score_before_transfers
            transfer_malus = realized.transfer_malus
            player_score = player_score_before_transfers - transfer_malus if realized.complete else float("nan")
            team_score = realized.team_score if realized.complete else float("nan")
            captain_hit = float("nan")
            captain_schedule = sol.meta.get("captain_schedule", {})
            captain_hits = []
            if captain_schedule and "dunkest_turn" in sol.players:
                player_turns = pd.to_numeric(sol.players["dunkest_turn"], errors="coerce")
                expected_minutes = pd.to_numeric(sol.players["expected_min"], errors="coerce")
                for turn, captain_name in captain_schedule.items():
                    eligible = sol.players.loc[
                        player_turns.ge(int(turn)) & expected_minutes.ge(round_settings.optimizer_captain_min_minutes)
                    ]
                    cap_key = player_key(captain_name)
                    eligible_scores = eligible["player_name"].map(player_key).map(actuals).dropna()
                    if cap_key in actuals and not eligible_scores.empty:
                        captain_hits.append(float(actuals[cap_key] >= eligible_scores.max()))
            else:
                captain_row = sol.players.loc[sol.players["slot"].eq("Captain")]
                eligible = sol.players.loc[
                    sol.players["slot"].isin({"Starter", "Captain"})
                    & pd.to_numeric(sol.players["expected_min"], errors="coerce").ge(round_settings.optimizer_captain_min_minutes)
                ]
                if not captain_row.empty:
                    cap_key = player_key(captain_row.iloc[0]["player_name"])
                    eligible_scores = eligible["player_name"].map(player_key).map(actuals).dropna()
                    if cap_key in actuals and not eligible_scores.empty:
                        captain_hits.append(float(actuals[cap_key] >= eligible_scores.max()))
            if captain_hits:
                captain_hit = float(np.mean(captain_hits))
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
                "ex_post_player_optimum": ex_post_player_score,
                "captain": sol.captain,
                "captain_schedule": json.dumps(captain_schedule, ensure_ascii=False, sort_keys=True),
                "coach": sol.coach,
                "num_transfers": transfer_count,
                "captain_hit": captain_hit, "coach_hit": coach_hit,
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
        "selected_holdout_strategy": selected_strategy,
    }
    return results, report, extras
