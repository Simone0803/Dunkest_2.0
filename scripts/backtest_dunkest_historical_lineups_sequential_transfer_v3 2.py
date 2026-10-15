#!/usr/bin/env python3
"""Restricted-universe historical lineup experiment using prior-round CR.

The candidate pool for target round r is sourced exclusively from archived rows
in round r-1. Current-round outcomes are used only for scoring and to link the
known schedule/team identity; they are never passed to the optimizer as scores.
Coach price is unavailable historically, so coach CR is fixed to 10 and coach
scores use the reconstructed neutral-credit base-score model. Results are an
explicit proxy experiment, not a claim of complete historical market coverage.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from dunkest.config import Settings
from dunkest.names import player_key
from dunkest.optimize.milp import optimize_top_k_lineups
from dunkest.rules.roster import player_contribution_multiplier

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet"
COACH_PREDICTIONS = ROOT / "reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_predictions.csv"
OUT = ROOT / "reports/audit"
STEM = "dunkest_historical_lineups_sequential_transfer_strict_20261014_v1"
METRICS = OUT / f"{STEM}_metrics.csv"
ROUNDS = OUT / f"{STEM}_rounds.csv"
LINEUPS = OUT / f"{STEM}_lineups.csv"
AUDIT = OUT / f"{STEM}.json"
REPORT = OUT / f"{STEM}.md"
VALID_SEASONS = ["5", "7", "9", "13", "19"]
TEST_SEASONS = ["9", "13", "19"]
TRANSFER_PENALTIES = [0.0, 2.5, 5.0]
OFFICIAL_TRANSFER_PENALTY = 5.0

spec = importlib.util.spec_from_file_location(
     "historical_credit_matchup_model_v6",
    ROOT / "scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v6_rest_schedule.py",
)
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load the leakage-safe player feature builder.")
player_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(player_module)


def make_model(numeric: list[str], categorical: list[str]) -> Pipeline:
    pre = ColumnTransformer([
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True))]), numeric),
        ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")),
                           ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
    ])
    return Pipeline([("preprocess", pre), ("model", ExtraTreesRegressor(
        n_estimators=180, min_samples_leaf=8, max_features=0.85, random_state=42, n_jobs=-1,
    ))])


def candidate_history_features(raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.copy()
    d["season_id"] = d["source_season_id"].astype(str)
    d["player_key"] = d["player_name"].astype(str).map(player_key)
    d["source_week"] = pd.to_numeric(d["source_week"], errors="coerce")
    d["source_round"] = pd.to_numeric(d["source_round"], errors="coerce")
    round_order = d[["season_id", "source_week", "source_round"]].drop_duplicates().sort_values(
        ["season_id", "source_week", "source_round"]
    )
    round_order["round_index"] = round_order.groupby("season_id").cumcount() + 1
    d = d.merge(round_order, on=["season_id", "source_week", "source_round"], how="left", validate="many_to_one")
    d = d.sort_values(["season_id", "player_key", "round_index"], kind="stable").reset_index(drop=True)
    numeric_sources = {
        "cr": "lag1_cr", "target_pdk_round_total": "lag1_pdk", "min_avg": "lag1_min_avg",
        "min_tot": "lag1_min_tot", "plus": "lag1_plus", "gp": "lag1_gp",
        "pts_avg": "lag1_pts_avg", "reb_avg": "lag1_reb_avg", "ast_avg": "lag1_ast_avg",
        "stl_avg": "lag1_stl_avg", "blk_avg": "lag1_blk_avg", "tov_avg": "lag1_tov_avg",
        "plus_minus_avg": "lag1_plus_minus_avg",
    }
    for source, dest in numeric_sources.items():
        d[dest] = pd.to_numeric(d[source], errors="coerce")
    for window in (3, 5, 10):
        d[f"prev{window}_pdk_mean"] = d.groupby(["season_id", "player_key"])["target_pdk_round_total"].transform(
            lambda s: pd.to_numeric(s, errors="coerce").rolling(window, min_periods=1).mean()
        )
        d[f"prev{window}_min_mean"] = d.groupby(["season_id", "player_key"])["min_avg"].transform(
            lambda s: pd.to_numeric(s, errors="coerce").rolling(window, min_periods=1).mean()
        )
    d["history_rounds_before_target"] = d.groupby(["season_id", "player_key"]).cumcount() + 1
    d["credit_age_rounds"] = 1
    d["prior_round_present"] = 1
    d["lagged_role"] = d["role"].astype(object).where(d["role"].notna(), np.nan)
    d["lagged_team"] = d["team_code"].astype(object).where(d["team_code"].notna(), np.nan)
    d["target_round_index"] = d["round_index"] + 1
    return d


def latest_prior_candidates(candidate_rows: pd.DataFrame, target_round: int) -> pd.DataFrame:
    """Return one latest strictly pre-target row per player, with lag age metadata."""
    candidates = candidate_rows.loc[pd.to_numeric(candidate_rows["round_index"], errors="coerce").lt(target_round)].sort_values(
        ["round_index", "player_key"], kind="stable"
    ).drop_duplicates("player_key", keep="last").copy()
    candidates["target_round_index"] = int(target_round)
    candidates["credit_age_rounds"] = int(target_round) - pd.to_numeric(candidates["round_index"], errors="coerce")
    candidates["prior_round_present"] = candidates["credit_age_rounds"].eq(1).astype(int)
    return candidates


def score_lineup(solution, actual_player_scores: dict[str, float], actual_coach_scores: dict[str, float]) -> tuple[float, float, float]:
    player_score = 0.0
    for _, player in solution.players.iterrows():
        key = player_key(player["player_name"])
        score = float(actual_player_scores.get(key, np.nan))
        if not np.isfinite(score):
            return float("nan"), float("nan"), float("nan")
        slot = str(player.get("slot", "Bench"))
        player_score += score * player_contribution_multiplier(
            slot in {"Starter", "Captain"}, slot == "Sixth Man", slot == "Captain"
        )
    coach_team = str(solution.meta.get("selected_coach_team", ""))
    if not coach_team:
        coach_name = str(solution.coach)
        coach_team = coach_name.rsplit(" ", 1)[-1]
    coach_score = float(actual_coach_scores.get(coach_team, np.nan))
    return player_score, coach_score, player_score + coach_score if np.isfinite(coach_score) else np.nan


def main() -> int:
    for path in (METRICS, ROUNDS, LINEUPS, AUDIT, REPORT):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite versioned artifact: {path}")
    if not INPUT.is_file() or not COACH_PREDICTIONS.is_file():
        raise FileNotFoundError(f"Required input missing: {INPUT} or {COACH_PREDICTIONS}")

    raw = pd.read_parquet(INPUT)
    raw["source_season_id"] = raw["source_season_id"].astype(str)
    raw = raw.loc[raw["source_season_id"].isin(VALID_SEASONS)].copy()
    raw["target_pdk_round_total"] = pd.to_numeric(raw["target_pdk_round_total"], errors="coerce")
    raw = raw.loc[np.isfinite(raw["target_pdk_round_total"])].copy()
    base_features = player_module.build_features(raw)
    feature_rows, matchup_audit = player_module.attach_matchup_features(base_features, raw)
    feature_rows, rest_audit = player_module.attach_rest_schedule_features(feature_rows)
    # Use the same canonical identity function as the optimizer for all joins.
    feature_rows["player_key"] = feature_rows["player_name"].astype(str).map(player_key)
    # Keep round identity and high-confidence matchup date metadata.
    round_meta = feature_rows[["season_id", "round_index", "source_week", "source_round", "target_date", "date_confidence"]].drop_duplicates()
    round_meta = round_meta.loc[round_meta["target_date"].notna()].copy()
    team_matchups = feature_rows.loc[feature_rows["target_opponent"].notna(), [
        "season_id", "round_index", "team_code_key", "target_opponent",
        "opp_def_allowed_pts_prev10", "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10",
        "opp_def_allowed_stl_prev10", "opp_def_allowed_blk_prev10", "opp_def_allowed_tov_prev10",
        "opp_pace_prev10", "opp_possessions_allowed_prev10", "opp_def_allowed_pts_prev5",
        "opp_def_allowed_reb_prev5", "opp_def_allowed_ast_prev5", "opp_pace_prev5",
        "team_days_since_game_v6", "opponent_days_since_game_v6", "team_games_prior7d_v6",
        "opponent_games_prior7d_v6", "team_back_to_back_v6", "opponent_back_to_back_v6",
        "rest_advantage_days_v6",
    ]].drop_duplicates(["season_id", "round_index", "team_code_key"])

    # Training features are all lagged. Matchup model is fitted separately for each held-out season.
    form_numeric = ["lag1_pdk", "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean",
        "lag1_min_avg", "prev3_min_mean", "prev5_min_mean", "lag1_plus", "lag1_pts_avg",
        "lag1_reb_avg", "lag1_ast_avg", "lag1_stl_avg", "lag1_blk_avg", "lag1_tov_avg",
        "lag1_plus_minus_avg", "lag1_gp", "history_rounds_before_target", "credit_age_rounds",
        "prior_round_present", "lag1_cr"]
    matchup_numeric = ["opp_def_allowed_pts_prev10", "opp_def_allowed_reb_prev10",
        "opp_def_allowed_ast_prev10", "opp_def_allowed_stl_prev10", "opp_def_allowed_blk_prev10",
        "opp_def_allowed_tov_prev10", "opp_pace_prev10", "opp_possessions_allowed_prev10",
        "opp_def_allowed_pts_prev5", "opp_def_allowed_reb_prev5", "opp_def_allowed_ast_prev5",
        "opp_pace_prev5"]
    rest_numeric = ["team_days_since_game_v6", "opponent_days_since_game_v6",
        "team_games_prior7d_v6", "opponent_games_prior7d_v6", "team_back_to_back_v6",
        "opponent_back_to_back_v6", "rest_advantage_days_v6"]
    numeric_v2 = form_numeric + matchup_numeric
    numeric_v6 = numeric_v2 + rest_numeric
    categorical = ["lagged_role", "target_opponent"]
    coach = pd.read_csv(COACH_PREDICTIONS)
    coach = coach.loc[coach["method"].eq("model_pregame_team_form")].copy()
    coach["season"] = coach["season"].astype(str)
    coach["game_date"] = pd.to_datetime(coach["game_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    coach["team"] = coach["team"].astype(str).str.upper().str.strip()
    coach["opponent"] = coach["opponent"].astype(str).str.upper().str.strip()

    candidate_rows = candidate_history_features(raw)

    metrics_rows, round_rows, lineup_rows = [], [], []
    for test_season in TEST_SEASONS:
        train = feature_rows.loc[feature_rows["season_id"].isin(VALID_SEASONS[:VALID_SEASONS.index(test_season)]) & feature_rows["target_opponent"].notna()].copy()
        test_rounds = round_meta.loc[round_meta["season_id"].eq(test_season)].sort_values("round_index")
        if train.empty or test_rounds.empty:
            continue
        model_v2 = make_model(numeric_v2, categorical)
        model_v2.fit(train[numeric_v2 + categorical], train["target_pdk_round_total"].to_numpy(float))
        model_v6 = make_model(numeric_v6, categorical)
        model_v6.fit(train[numeric_v6 + categorical], train["target_pdk_round_total"].to_numpy(float))
        train_median = float(pd.to_numeric(train["target_pdk_round_total"], errors="coerce").median())
        season_candidates = candidate_rows.loc[candidate_rows["season_id"].eq(test_season)].copy()
        # Join realized outcomes from the archived round table, not the predictor feature subset.
        # Unavailable labels remain unknown and are excluded from strict paired metrics.
        season_observed = season_candidates.copy()
        carry_state = {penalty: {"roster": None, "coach": None} for penalty in TRANSFER_PENALTIES}
        for _, meta in test_rounds.iterrows():
            target_round = int(meta["round_index"])
            prior_round = target_round - 1
            target_date = str(meta["target_date"])
            if prior_round < 1:
                continue
            # Carry forward each player's most recent observed CR/role/team from any earlier round.
            # If the player did not play in r-1, their last known price remains the safe lagged proxy.
            candidates = latest_prior_candidates(season_candidates, target_round)
            candidates["target_date"] = target_date
            candidates = candidates.loc[pd.to_numeric(candidates["cr"], errors="coerce").between(4.0, 35.0)].copy()
            if candidates.empty:
                round_rows.append({"season_id": test_season, "round_index": target_round, "target_date": target_date, "status": "no_candidates"})
                continue
            # The optimizer rejects duplicate normalized identities; remove ambiguous candidates rather than silently selecting one.
            dup = candidates["player_key"].eq("") | candidates["player_key"].duplicated(keep=False)
            duplicate_count = int(dup.sum())
            candidates = candidates.loc[~dup].copy()
            if candidates.empty:
                continue

            target_outcomes = season_observed.loc[season_observed["round_index"].eq(target_round)].copy()
            actual_map = dict(zip(target_outcomes["player_key"], target_outcomes["target_pdk_round_total"].astype(float)))
            candidates["team"] = candidates["team_code"].astype(str).str.upper().str.strip()
            # Target matchup is attached from the known NBA schedule, not from current-round fantasy outcomes.
            match_map = team_matchups.loc[team_matchups["season_id"].eq(test_season) & team_matchups["round_index"].eq(target_round)].copy()
            match_map = match_map.rename(columns={"team_code_key": "team"}).drop_duplicates("team")
            map_cols = ["team", "target_opponent"] + matchup_numeric + rest_numeric
            candidates = candidates.merge(match_map[map_cols], on="team", how="left", validate="many_to_one")
            candidates = candidates.loc[candidates["target_opponent"].notna()].copy()
            if len(candidates) < 10:
                round_rows.append({"season_id": test_season, "round_index": target_round, "target_date": target_date, "status": "candidate_pool_too_small", "candidate_count": len(candidates)})
                continue
            # Build pregame predictions for the prior-round market pool.
            candidates["expected_min"] = pd.to_numeric(candidates["prev5_min_mean"], errors="coerce").fillna(pd.to_numeric(candidates["lag1_min_avg"], errors="coerce")).clip(lower=0)
            candidates["p_play"] = 1.0
            candidates["status"] = "Available"
            candidates["expected_plusvalenza"] = 0.0
            candidates["actual_pdk"] = pd.to_numeric(candidates["player_key"].map(actual_map), errors="coerce")
            try:
                candidates["expected_pdk_v2"] = model_v2.predict(candidates[numeric_v2 + categorical])
                candidates["expected_pdk_v6"] = model_v6.predict(candidates[numeric_v6 + categorical])
            except Exception as exc:
                round_rows.append({"season_id": test_season, "round_index": target_round, "target_date": target_date, "status": "prediction_error", "detail": str(exc)})
                continue

            coach_day = coach.loc[coach["season"].eq({"9":"2022-23","13":"2023-24","19":"2024-25"}[test_season]) & coach["game_date"].eq(target_date)].copy()
            if coach_day.empty:
                round_rows.append({"season_id": test_season, "round_index": target_round, "target_date": target_date, "status": "coach_predictions_missing", "candidate_count": len(candidates)})
                continue
            coach_day = coach_day.drop_duplicates("team")
            actual_coach_map = dict(zip(coach_day["team"], pd.to_numeric(coach_day["actual_base_coach_pdk"], errors="coerce")))
            expected_coach_map = dict(zip(coach_day["team"], pd.to_numeric(coach_day["predicted_base_coach_pdk"], errors="coerce")))
            coach_rows = []
            for team, exp in expected_coach_map.items():
                if not np.isfinite(exp) or team not in actual_coach_map:
                    continue
                coach_rows.append({"coach": f"Proxy Coach {team}", "team": team, "coach_cr": 10.0,
                                   "expected_coach_pdk": float(exp), "actual_base_coach_pdk": float(actual_coach_map[team])})
            coaches = pd.DataFrame(coach_rows)
            if coaches.empty:
                continue
            settings = Settings(
                season={"9":"2022-23","13":"2023-24","19":"2024-25"}[test_season],
                season_id=test_season, target_gameweek=target_round, target_dunkest_turn=1,
                budget=95.0, min_cr=4.0, max_cr=35.0, transfer_penalty=0.0,
                max_from_same_nba_team=3, optimizer_objective="expected_value",
                optimizer_time_limit_seconds=1.0, optimizer_relative_gap=0.05,
                use_injuries=False, use_matchup=True, use_coach_model=True,
            )
            players = candidates[["player_name", "team", "role", "cr", "expected_min", "p_play", "status", "expected_plusvalenza"]].copy()
            players["expected_pdk"] = pd.to_numeric(candidates["expected_pdk_v2"], errors="coerce").fillna(train_median).to_numpy(float)
            # Sequentially re-optimize for each transfer penalty, carrying forward
            # that scenario's own previous roster and coach. Only current-round
            # outcomes are used after optimization to score the selected roster.
            for penalty in TRANSFER_PENALTIES:
                state = carry_state[penalty]
                settings.transfer_penalty = float(penalty)
                current_roster, current_coach = state["roster"], state["coach"]
                try:
                    sol = optimize_top_k_lineups(
                        players, coaches[["coach", "team", "coach_cr", "expected_coach_pdk"]],
                        settings, current_roster=current_roster, current_coach=current_coach, k=1
                    )[0]
                    player_actual, coach_actual, gross_actual = score_lineup(
                        sol, dict(zip(candidates["player_key"], candidates["actual_pdk"])), actual_coach_map
                    )
                    transfer_count = int(sol.num_transfers)
                    net_actual = float(gross_actual - transfer_count * OFFICIAL_TRANSFER_PENALTY) if np.isfinite(gross_actual) else np.nan
                    objective_proxy_actual = float(gross_actual - transfer_count * penalty) if np.isfinite(gross_actual) else np.nan
                    selected_names = sol.players["player_name"].astype(str).tolist()
                    selected_team = str(sol.coach).rsplit(" ", 1)[-1]
                    lineup_rows.append({
                        "season_id": test_season, "season": settings.season, "round_index": target_round,
                        "source_week": int(meta["source_week"]), "source_round": int(meta["source_round"]),
                        "target_date": target_date, "strategy": "sequential_matchup_v2", "transfer_penalty": penalty,
                        "candidate_count": int(len(candidates)), "duplicate_candidates_removed": duplicate_count,
                        "candidate_target_row_coverage": float(candidates["player_key"].isin(actual_map).mean()),
                        "selected_players": "; ".join(selected_names), "selected_coach_proxy_team": selected_team,
                        "expected_team_pdk": float(sol.expected_team_pdk), "realized_player_score": player_actual,
                        "realized_coach_base_score": coach_actual, "realized_gross_team_score": gross_actual,
                        "realized_net_team_score": net_actual, "realized_objective_proxy_score": objective_proxy_actual,
                        "num_transfers": transfer_count,
                        "official_transfer_malus": float(transfer_count * OFFICIAL_TRANSFER_PENALTY),
                        "optimization_penalty_cost": float(transfer_count * penalty),
                        "previous_roster": "; ".join(current_roster or []), "previous_coach": current_coach,
                        "budget_used": float(sol.budget_used), "captain": sol.captain, "formation": sol.module,
                        "roster_valid": bool(len(sol.players)==10 and sol.players["player_name"].map(player_key).nunique()==10),
                        "optimizer_status": str(sol.meta.get("solver", {}).get("status", "unknown")),
                    })
                    round_rows.append({
                        "season_id": test_season, "season": settings.season, "round_index": target_round,
                        "target_date": target_date, "transfer_penalty": penalty, "status": "evaluated",
                        "candidate_count": int(len(candidates)), "candidate_target_row_coverage": float(candidates["player_key"].isin(actual_map).mean()),
                        "target_players": int(len(target_outcomes)), "target_players_in_candidate_pool": int(target_outcomes["player_key"].isin(candidates["player_key"]).sum()),
                        "realized_player_score": player_actual, "realized_coach_base_score": coach_actual,
                        "strict_actuals_complete": bool(np.isfinite(gross_actual)),
                        "realized_gross_team_score": gross_actual, "realized_net_team_score": net_actual,
                        "realized_objective_proxy_score": objective_proxy_actual,
                        "num_transfers": transfer_count, "official_transfer_malus": float(transfer_count * OFFICIAL_TRANSFER_PENALTY),
                        "optimization_penalty_cost": float(transfer_count * penalty),
                        "selected_roster": "; ".join(selected_names), "selected_coach_team": selected_team,
                        "expected_team_pdk": float(sol.expected_team_pdk), "roster_valid": bool(len(sol.players)==10),
                        "optimizer_status": str(sol.meta.get("solver", {}).get("status", "unknown")),
                    })
                    state["roster"] = selected_names
                    state["coach"] = str(sol.coach)
                except Exception as exc:
                    round_rows.append({"season_id": test_season, "season": settings.season, "round_index": target_round,
                        "target_date": target_date, "transfer_penalty": penalty, "status": "optimization_failed",
                        "candidate_count": len(candidates), "errors": str(exc)})


    round_df = pd.DataFrame(round_rows)
    lineup_df = pd.DataFrame(lineup_rows)
    metrics = []
    if not round_df.empty:
        evaluated = round_df.loc[round_df["status"].eq("evaluated")].copy()
        if not evaluated.empty:
            score_pivot = evaluated.pivot_table(
                index=["season_id", "season", "round_index"],
                columns="transfer_penalty", values="realized_net_team_score", aggfunc="first"
            )
            required_penalties = set(TRANSFER_PENALTIES)
            strict_round_index = score_pivot.index[
                score_pivot.reindex(columns=TRANSFER_PENALTIES).notna().all(axis=1)
            ]
            strict_keys = set(strict_round_index.tolist())
            evaluated["_strict_pair_key"] = list(zip(evaluated["season_id"], evaluated["season"], evaluated["round_index"]))
            evaluated["strict_paired_round_all_penalties"] = evaluated["_strict_pair_key"].isin(strict_keys)
            paired_evaluated = evaluated.loc[evaluated["strict_paired_round_all_penalties"]].copy()
        else:
            paired_evaluated = evaluated
        for keys, group in paired_evaluated.groupby(["season_id", "season", "transfer_penalty"], dropna=False):
            metrics.append({"season_id": keys[0], "season": keys[1], "transfer_penalty": float(keys[2]),
                "rounds_evaluated": int(group["realized_net_team_score"].notna().sum()),
                "rounds_optimized": int(len(group)),
                "rounds_with_complete_observed_actuals": int(group["realized_net_team_score"].notna().sum()),
                "mean_net_team_score": float(group["realized_net_team_score"].mean()),
                "median_net_team_score": float(group["realized_net_team_score"].median()),
                "mean_gross_team_score": float(group["realized_gross_team_score"].mean()),
                "mean_transfers": float(group["num_transfers"].mean()),
                "median_transfers": float(group["num_transfers"].median()),
                "mean_official_transfer_malus": float(group["official_transfer_malus"].mean()),
                "mean_objective_proxy_score": float(group["realized_objective_proxy_score"].mean()),
                "mean_candidate_coverage": float(group["candidate_target_row_coverage"].mean()),
                "mean_target_players_in_candidate_pool_fraction": float((group["target_players_in_candidate_pool"] / group["target_players"]).replace([np.inf,-np.inf],np.nan).mean()),
                "roster_valid_rate": float(group["roster_valid"].mean())})
        for penalty, group in paired_evaluated.groupby("transfer_penalty", dropna=False):
            metrics.append({"season_id": "POOLED", "season": "2022-23–2024-25", "transfer_penalty": float(penalty),
                "rounds_evaluated": int(group["realized_net_team_score"].notna().sum()),
                "rounds_optimized": int(len(group)),
                "rounds_with_complete_observed_actuals": int(group["realized_net_team_score"].notna().sum()),
                "mean_net_team_score": float(group["realized_net_team_score"].mean()),
                "median_net_team_score": float(group["realized_net_team_score"].median()),
                "mean_gross_team_score": float(group["realized_gross_team_score"].mean()),
                "mean_transfers": float(group["num_transfers"].mean()), "median_transfers": float(group["num_transfers"].median()),
                "mean_official_transfer_malus": float(group["official_transfer_malus"].mean()),
                "mean_objective_proxy_score": float(group["realized_objective_proxy_score"].mean()),
                "mean_candidate_coverage": float(group["candidate_target_row_coverage"].mean()),
                "mean_target_players_in_candidate_pool_fraction": float((group["target_players_in_candidate_pool"] / group["target_players"]).replace([np.inf,-np.inf],np.nan).mean()),
                "roster_valid_rate": float(group["roster_valid"].mean())})
    metrics_df = pd.DataFrame(metrics)
    round_df.to_csv(ROUNDS, index=False)
    lineup_df.to_csv(LINEUPS, index=False)
    metrics_df.to_csv(METRICS, index=False)
    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(INPUT.relative_to(ROOT)), "coach_prediction_source": str(COACH_PREDICTIONS.relative_to(ROOT)),
        "candidate_policy": "For target round r, each candidate's latest archived row strictly before r is carried forward; no current-round labels enter prediction or selection.",
        "feature_policy": "Uses the walk-forward expanded-matchup V2 player model and rule-aware pregame coach prediction. V6 rest features are not part of this transfer-only experiment.",
        "transfer_penalties_tested_in_optimizer": TRANSFER_PENALTIES,
        "official_transfer_penalty_for_scoring": OFFICIAL_TRANSFER_PENALTY,
        "sequential_policy": "For each penalty, re-optimize every round using that scenario's own previous selected ten-player roster and coach. Update the carried roster only after a successful optimization. The first evaluated round has no transfer cost because no proxy roster is known before it.",
        "scoring_policy": "All scenarios are scored under the same official proxy rule: realized raw player PDK with starter/sixth/captain multipliers plus neutral-credit coach base score, less OFFICIAL_TRANSFER_PENALTY=5 times the optimizer-reported transfer count. The scenario penalty changes only the optimization objective, not the scoring rule.",
        "metrics": metrics_df.to_dict("records"),
        "round_status_counts": round_df["status"].value_counts(dropna=False).to_dict() if not round_df.empty else {},
        "lineup_rows": len(lineup_df), "production_changed": False,
        "scoring_policy": "Strict observed-only: no missing selected-player outcome is imputed as zero. Strategy score comparisons are paired on identical rounds with complete observed outcomes for every tested transfer penalty.",
        "paired_strict_rounds": int(len(strict_keys)) if not round_df.empty and "strict_paired_round_all_penalties" in evaluated else 0,
        "limitations": [
            "The carried roster is the previous proxy recommendation, not the user's actual historical roster.",
            "Candidate pool only includes players observed earlier in the archived season; late additions and players absent from prior tables are omitted.",
            "Coach CR is fixed at 10 and coach points are neutral-credit base-score estimates; exact historical price-adjusted coach points are unavailable.",
            "Missing selected-player outcomes remain unknown; paired score metrics include only rounds with complete observed player and coach outcomes for every transfer-penalty scenario.",
            "This experiment compares penalties in the same chronological walk-forward design, but is not an official complete-market backtest. The carried roster is simulated, not the user's actual historical roster."
        ]
    }

    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Sequential Dunkest lineup backtest — strict observed-only transfer-penalty scenarios", "",
        f"Generated (UTC): {audit['generated_at_utc']}", "",
        "## Method", "",
        "For each test season, each transfer-penalty scenario starts with no assumed roster. Missing realized player scores remain unknown and are not imputed as zero. In every subsequent round, the optimizer selects a lineup using only lagged player features and pregame coach forecasts, while using that scenario's transfer penalty coefficient in the selection objective. Only fully observed paired rounds contribute to score comparisons. All scenarios are scored under the same fixed 5-point transfer malus; only after scoring is the lineup carried forward to the next round.", "",
        f"Optimizer penalty coefficients tested: {TRANSFER_PENALTIES}. Every scenario is scored with the same official proxy transfer penalty of {OFFICIAL_TRANSFER_PENALTY} points per transfer.", "",
        "## Results", "", metrics_df.to_string(index=False), "",
        "## Coverage and failures", "", f"- Round status counts: {audit['round_status_counts']}",
        f"- Sequential lineup records: {len(lineup_df):,}", "",
        "## Caveats", ""] + [f"- {x}" for x in audit["limitations"]] + ["",
        "The coefficient in the optimizer is a decision parameter, while the official 5-point malus is fixed for scoring all scenarios. Compare official-net score, gross score and transfer frequency; do not change production without stable differences across seasons and broader market coverage.", "",
        "Production model/configuration remains unchanged.", "", "## Artifacts", "",
        f"- Metrics: `{METRICS.relative_to(ROOT)}`", f"- Per-round results: `{ROUNDS.relative_to(ROOT)}`",
        f"- Sequential lineups: `{LINEUPS.relative_to(ROOT)}`", f"- Audit JSON: `{AUDIT.relative_to(ROOT)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "metrics": metrics_df.to_dict("records"),
        "round_status_counts": audit["round_status_counts"], "lineup_rows": len(lineup_df),
        "outputs": [str(x.relative_to(ROOT)) for x in (METRICS, ROUNDS, LINEUPS, AUDIT, REPORT)]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
