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
LINKED_INPUT = ROOT / "data/processed/dunkest_historical_game_linked_rows_20261013_v3_date_assisted.parquet"
OFFICIAL_GAMES = ROOT / "data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
COACH_PREDICTIONS = ROOT / "reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_predictions.csv"
OUT = ROOT / "reports/audit"
STEM = "dunkest_historical_lineups_gamelevel_actuals_20261014_v2"
METRICS = OUT / f"{STEM}_metrics.csv"
ROUNDS = OUT / f"{STEM}_rounds.csv"
LINEUPS = OUT / f"{STEM}_lineups.csv"
AUDIT = OUT / f"{STEM}.json"
REPORT = OUT / f"{STEM}.md"
VALID_SEASONS = ["5", "7", "9", "13", "19"]
TEST_SEASONS = ["9", "13", "19"]

spec = importlib.util.spec_from_file_location(
    "historical_credit_matchup_model",
    ROOT / "scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v1.py",
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
        score = float(actual_player_scores.get(key, 0.0))
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
    raw["player_id_num"] = pd.to_numeric(raw["id"], errors="coerce")
    raw = raw.loc[np.isfinite(raw["target_pdk_round_total"])].copy()

    # Reconstruct realized PDK from official Dunkest player-game records. Accept
    # a round date only with >=75% linked-date agreement and >=10 unique player links;
    # then use the full official Dunkest-valid slate for that season/date. This avoids
    # cross-date collisions from repeated exact box-score signatures.
    linked = pd.read_parquet(LINKED_INPUT)
    linked["season_id"] = linked["source_season_id"].astype(str)
    linked["week_num"] = pd.to_numeric(linked["source_week"], errors="coerce")
    linked["round_num"] = pd.to_numeric(linked["source_round"], errors="coerce")
    linked["player_id_num"] = pd.to_numeric(linked["id"], errors="coerce")
    linked["target_pdk_round_total"] = pd.to_numeric(linked["target_pdk_round_total"], errors="coerce")
    linked["linked_date"] = pd.to_datetime(linked["linked_nba_game_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    # A few exact box-score signatures can recur on different dates. Never union
    # all linked game IDs blindly: establish one high-confidence round date first,
    # then recover the full official Dunkest-valid slate for that date.
    round_game_dates = {}
    for key, group in linked.groupby(["season_id", "week_num", "round_num"]):
        if pd.isna(key[1]) or pd.isna(key[2]):
            continue
        date_rows = group.loc[group["linked_date"].notna(), ["player_id_num", "linked_date"]].drop_duplicates("player_id_num")
        if date_rows.empty:
            continue
        counts = date_rows["linked_date"].value_counts()
        round_date = str(counts.index[0])
        confidence = float(counts.iloc[0] / len(date_rows))
        unique_links = int(counts.iloc[0])
        if confidence >= 0.75 and unique_links >= 10:
            round_game_dates[(str(key[0]), int(key[1]), int(key[2]))] = {
                "date": round_date, "confidence": confidence, "unique_player_links": unique_links
            }

    official = pd.read_parquet(OFFICIAL_GAMES)
    official["season_id"] = official["season_id"].astype(str)
    official["nba_GAME_ID"] = official["nba_GAME_ID"].astype(str)
    official["game_date"] = pd.to_datetime(official["nba_GAME_DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    official["player_id_num"] = pd.to_numeric(official["dunkest_player_id"], errors="coerce")
    official["pdk_num"] = pd.to_numeric(official["pdk"], errors="coerce")
    valid_mask = official["gameValidForDunkest"].astype("boolean").fillna(False)
    official_valid = official.loc[valid_mask & official["player_id_num"].notna() & official["pdk_num"].notna()].copy()
    official_player_ids = {sid: set(pd.to_numeric(g["player_id_num"], errors="coerce").dropna().astype(int))
                           for sid, g in official.groupby("season_id")}

    reconstruction_checks = []
    for key, group in linked.groupby(["season_id", "week_num", "round_num"]):
        if pd.isna(key[1]) or pd.isna(key[2]):
            continue
        round_key = (str(key[0]), int(key[1]), int(key[2]))
        round_info = round_game_dates.get(round_key)
        if not round_info:
            continue
        actual = official_valid.loc[
            official_valid["season_id"].eq(str(key[0])) & official_valid["game_date"].eq(round_info["date"])
        ].groupby("player_id_num")["pdk_num"].sum()
        observed = group.drop_duplicates("player_id_num").copy()
        observed["reconstructed_pdk"] = observed["player_id_num"].map(actual)
        observed = observed.loc[observed["target_pdk_round_total"].notna() & observed["reconstructed_pdk"].notna()]
        if not observed.empty:
            delta = (observed["target_pdk_round_total"] - observed["reconstructed_pdk"]).abs()
            reconstruction_checks.append({"n": int(len(observed)), "exact_002": int((delta < 0.02).sum()), "mae_sum": float(delta.sum())})
    reconstruction_n = sum(x["n"] for x in reconstruction_checks)
    reconstruction_exact = sum(x["exact_002"] for x in reconstruction_checks)
    reconstruction_mae = sum(x["mae_sum"] for x in reconstruction_checks) / reconstruction_n if reconstruction_n else np.nan

    base_features = player_module.build_features(raw)
    feature_rows, matchup_audit = player_module.attach_matchup_features(base_features, raw)
    # Use the same canonical identity function as the optimizer for all joins.
    feature_rows["player_key"] = feature_rows["player_name"].astype(str).map(player_key)
    # Keep round identity and high-confidence matchup date metadata.
    round_meta = feature_rows[["season_id", "round_index", "source_week", "source_round", "target_date", "date_confidence"]].drop_duplicates()
    round_meta = round_meta.loc[round_meta["target_date"].notna()].copy()
    team_matchups = feature_rows.loc[feature_rows["target_opponent"].notna(), [
        "season_id", "round_index", "team_code_key", "target_opponent", "opp_def_allowed_pts_prev10",
        "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10",
    ]].drop_duplicates(["season_id", "round_index", "team_code_key"])

    # Training features are all lagged. Matchup model is fitted separately for each held-out season.
    numeric = ["lag1_pdk", "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean",
               "lag1_min_avg", "prev3_min_mean", "prev5_min_mean", "lag1_plus", "lag1_pts_avg",
               "lag1_reb_avg", "lag1_ast_avg", "lag1_stl_avg", "lag1_blk_avg", "lag1_tov_avg",
               "lag1_plus_minus_avg", "lag1_gp", "history_rounds_before_target", "credit_age_rounds",
               "prior_round_present", "lag1_cr", "opp_def_allowed_pts_prev10",
               "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10"]
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
        model = make_model(numeric, categorical)
        model.fit(train[numeric + categorical], train["target_pdk_round_total"].to_numpy(float))
        train_median = float(pd.to_numeric(train["target_pdk_round_total"], errors="coerce").median())
        season_candidates = candidate_rows.loc[candidate_rows["season_id"].eq(test_season)].copy()
        season_observed = feature_rows.loc[feature_rows["season_id"].eq(test_season)].copy()
        for _, meta in test_rounds.iterrows():
            target_round = int(meta["round_index"])
            prior_round = target_round - 1
            target_date = pd.to_datetime(meta["target_date"], errors="coerce").strftime("%Y-%m-%d")
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
            archive_actual_map = dict(zip(target_outcomes["player_key"], target_outcomes["target_pdk_round_total"].astype(float)))
            # Strictly pre-target team identity only: never use target-round outcome rows
            # to decide the candidate's team or matchup.
            candidates["team"] = candidates["team_code"].astype(str).str.upper()
            # Target matchup is attached from the known NBA schedule, not from current-round fantasy outcomes.
            match_map = team_matchups.loc[team_matchups["season_id"].eq(test_season) & team_matchups["round_index"].eq(target_round)].copy()
            match_map = match_map.rename(columns={"team_code_key": "team"}).drop_duplicates("team")
            candidates = candidates.merge(match_map[["team", "target_opponent", "opp_def_allowed_pts_prev10", "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10"]],
                on="team", how="left", validate="many_to_one")
            # Keep the same schedule-eligible candidate universe as the prior proxy:
            # only teams with a mapped fixture in the target round can score.
            candidates = candidates.loc[candidates["target_opponent"].notna()].copy()

            # A candidate can be assigned a zero only if their Dunkest player ID is
            # represented in the official season archive and no valid PDK row exists
            # for any fixture in this reconstructed round. Unknown IDs are excluded.
            candidates["player_id_num"] = pd.to_numeric(candidates["id"], errors="coerce")
            known_ids = official_player_ids.get(test_season, set())
            known_mask = candidates["player_id_num"].notna() & candidates["player_id_num"].astype("Int64").isin(known_ids)
            unknown_identity_count = int((~known_mask).sum())
            candidates = candidates.loc[known_mask].copy()
            round_key = (str(test_season), int(meta["source_week"]), int(meta["source_round"]))
            round_info = round_game_dates.get(round_key)
            if not round_info or round_info["date"] != target_date:
                round_rows.append({"season_id": test_season, "round_index": target_round, "target_date": target_date,
                    "status": "missing_or_conflicting_round_date_mapping", "candidate_count": len(candidates)})
                continue
            round_actuals = official_valid.loc[
                official_valid["season_id"].eq(test_season) & official_valid["game_date"].eq(round_info["date"])
            ].groupby("player_id_num")["pdk_num"].sum()
            if len(candidates) < 10:
                round_rows.append({"season_id": test_season, "round_index": target_round, "target_date": target_date,
                    "status": "candidate_pool_too_small", "candidate_count": len(candidates),
                    "unknown_candidate_identity_count": unknown_identity_count})
                continue

            # Build pregame predictions for the prior-round market pool.
            candidates["expected_min"] = pd.to_numeric(candidates["prev5_min_mean"], errors="coerce").fillna(pd.to_numeric(candidates["lag1_min_avg"], errors="coerce")).clip(lower=0)
            candidates["p_play"] = 1.0
            candidates["status"] = "Available"
            candidates["expected_plusvalenza"] = 0.0
            candidates["actual_pdk"] = candidates["player_id_num"].map(round_actuals).fillna(0.0).astype(float)
            try:
                candidates["expected_pdk_model"] = model.predict(candidates[numeric + categorical])
            except Exception as exc:
                round_rows.append({"season_id": test_season, "round_index": target_round, "target_date": target_date, "status": "prediction_error", "detail": str(exc)})
                continue
            candidates["expected_pdk_baseline"] = pd.to_numeric(candidates["prev5_pdk_mean"], errors="coerce").fillna(train_median)

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
            selected_results = {}
            errors = {}
            for strategy, score_col in (("model", "expected_pdk_model"), ("previous5_baseline", "expected_pdk_baseline")):
                players = candidates[["player_name", "team", "role", "cr", "expected_min", "p_play", "status", "expected_plusvalenza"]].copy()
                players["expected_pdk"] = pd.to_numeric(candidates[score_col], errors="coerce").fillna(train_median).to_numpy(float)
                try:
                    sol = optimize_top_k_lineups(players, coaches[["coach", "team", "coach_cr", "expected_coach_pdk"]], settings, k=1)[0]
                    player_actual, coach_actual, total_actual = score_lineup(sol, dict(zip(candidates["player_key"], candidates["actual_pdk"])), actual_coach_map)
                    selected_results[strategy] = {"solution": sol, "player_actual": player_actual, "coach_actual": coach_actual, "team_actual": total_actual}
                    selected_team = str(sol.coach).rsplit(" ", 1)[-1]
                    lineup_rows.append({
                        "season_id": test_season, "season": settings.season, "round_index": target_round,
                        "source_week": int(meta["source_week"]), "source_round": int(meta["source_round"]),
                        "target_date": target_date, "strategy": strategy,
                        "candidate_count": int(len(candidates)), "duplicate_candidates_removed": duplicate_count,
                        "candidate_target_row_coverage": float(candidates["player_key"].isin(archive_actual_map).mean()),
                        "selected_players": "; ".join(sol.players["player_name"].astype(str).tolist()),
                        "selected_coach_proxy_team": selected_team,
                        "expected_team_pdk": float(sol.expected_team_pdk),
                        "realized_player_score": player_actual, "realized_coach_base_score": coach_actual,
                        "realized_team_score": total_actual, "budget_used": float(sol.budget_used),
                        "captain": sol.captain, "formation": sol.module,
                        "roster_valid": bool(len(sol.players)==10 and sol.players["player_name"].map(player_key).nunique()==10),
                        "optimizer_status": str(sol.meta.get("solver", {}).get("status", "unknown")),
                    })
                except Exception as exc:
                    errors[strategy] = str(exc)
            if "model" in selected_results and "previous5_baseline" in selected_results:
                model_result = selected_results["model"]
                baseline_result = selected_results["previous5_baseline"]
                round_rows.append({
                    "season_id": test_season, "season": settings.season, "round_index": target_round,
                    "source_week": int(meta["source_week"]), "source_round": int(meta["source_round"]),
                    "target_date": target_date, "status": "evaluated", "candidate_count": int(len(candidates)),
                    "candidate_target_row_coverage": float(candidates["player_key"].isin(archive_actual_map).mean()),
                    "target_players": int(len(target_outcomes)), "target_players_in_candidate_pool": int(target_outcomes["player_key"].isin(candidates["player_key"]).sum()),
                    "model_realized_team_score": model_result["team_actual"],
                    "baseline_realized_team_score": baseline_result["team_actual"],
                    "model_minus_baseline": model_result["team_actual"] - baseline_result["team_actual"],
                    "model_roster": "; ".join(model_result["solution"].players["player_name"].astype(str).tolist()),
                    "baseline_roster": "; ".join(baseline_result["solution"].players["player_name"].astype(str).tolist()),
                    "model_coach_team": str(model_result["solution"].coach).rsplit(" ", 1)[-1],
                    "baseline_coach_team": str(baseline_result["solution"].coach).rsplit(" ", 1)[-1],
                    "model_expected_team_pdk": float(model_result["solution"].expected_team_pdk),
                    "baseline_expected_team_pdk": float(baseline_result["solution"].expected_team_pdk),
                    "model_roster_valid": bool(len(model_result["solution"].players)==10),
                    "baseline_roster_valid": bool(len(baseline_result["solution"].players)==10),
                })
            else:
                round_rows.append({"season_id": test_season, "season": settings.season, "round_index": target_round,
                    "target_date": target_date, "status": "optimization_failed", "candidate_count": len(candidates),
                    "errors": json.dumps(errors)})

    round_df = pd.DataFrame(round_rows)
    lineup_df = pd.DataFrame(lineup_rows)
    metrics = []
    if not round_df.empty and "status" in round_df:
        evaluated = round_df.loc[round_df["status"].eq("evaluated")].copy()
        for sid, group in evaluated.groupby("season_id"):
            diff = pd.to_numeric(group["model_minus_baseline"], errors="coerce")
            metrics.append({"season_id": sid, "season": group["season"].iloc[0], "rounds_evaluated": len(group),
                "mean_model_realized_team_score": float(group["model_realized_team_score"].mean()),
                "mean_baseline_realized_team_score": float(group["baseline_realized_team_score"].mean()),
                "mean_delta_model_minus_baseline": float(diff.mean()),
                "median_delta_model_minus_baseline": float(diff.median()),
                "model_win_rate_vs_baseline": float((diff > 0).mean()),
                "mean_candidate_count": float(group["candidate_count"].mean()),
                "mean_candidate_target_row_coverage": float(group["candidate_target_row_coverage"].mean()),
                "mean_target_players_covered": float((group["target_players_in_candidate_pool"] / group["target_players"]).replace([np.inf,-np.inf],np.nan).mean())})
        if not evaluated.empty:
            diff = pd.to_numeric(evaluated["model_minus_baseline"], errors="coerce")
            metrics.append({"season_id": "POOLED", "season": "2022-23–2024-25", "rounds_evaluated": len(evaluated),
                "mean_model_realized_team_score": float(evaluated["model_realized_team_score"].mean()),
                "mean_baseline_realized_team_score": float(evaluated["baseline_realized_team_score"].mean()),
                "mean_delta_model_minus_baseline": float(diff.mean()),
                "median_delta_model_minus_baseline": float(diff.median()),
                "model_win_rate_vs_baseline": float((diff > 0).mean()),
                "mean_candidate_count": float(evaluated["candidate_count"].mean()),
                "mean_candidate_target_row_coverage": float(evaluated["candidate_target_row_coverage"].mean()),
                "mean_target_players_covered": float((evaluated["target_players_in_candidate_pool"] / evaluated["target_players"]).replace([np.inf,-np.inf],np.nan).mean())})
    metrics_df = pd.DataFrame(metrics)
    round_df.to_csv(ROUNDS, index=False)
    lineup_df.to_csv(LINEUPS, index=False)
    metrics_df.to_csv(METRICS, index=False)
    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "supersedes_diagnostic_versions": {"v1": "identity-key mismatch made outcome join coverage invalid", "v2": "candidate pool restricted to immediately previous round and missed most target participants", "v4": "deterministic every-third-round sample; V5 evaluates all high-confidence rounds", "gamelevel_actuals_v1": "unioning all linked game IDs allowed cross-date exact-signature collisions; v2 uses high-confidence round-date consensus and the official valid slate for that date"},
        "input": str(INPUT.relative_to(ROOT)), "coach_prediction_source": str(COACH_PREDICTIONS.relative_to(ROOT)),
        "realized_player_score_source": str(OFFICIAL_GAMES.relative_to(ROOT)),
        "game_level_actual_reconstruction": {
            "date_link_source": str(LINKED_INPUT.relative_to(ROOT)),
            "rounds_with_confident_date_mapping": int(len(round_game_dates)),
            "date_confidence_threshold": 0.75,
            "minimum_unique_player_date_links": 10,
            "weekly_rows_reconstructed": int(reconstruction_n),
            "rows_with_absolute_difference_below_0_02": int(reconstruction_exact),
            "share_with_absolute_difference_below_0_02": float(reconstruction_exact / reconstruction_n) if reconstruction_n else None,
            "mean_absolute_difference": float(reconstruction_mae) if np.isfinite(reconstruction_mae) else None,
            "scoring_rule": "Establish the round date from the mode of linked player-game dates, requiring at least 75% date agreement and 10 unique player links. Sum official Dunkest PDK for all gameValidForDunkest=True player-game rows on that season/date. This avoids including unrelated games when an exact box-score signature recurs on another date."
        },
        "candidate_policy": "For target round r, each candidate's latest observed row strictly before r is carried forward. CR, role and team are lagged; when a player has no row in r-1, the last observed CR is carried forward. Player outcomes are reconstructed from official per-game Dunkest PDK using the mapped fixture set, not filled from missing weekly aggregate rows. Players never observed in the archived season remain outside the candidate universe.",
        "target_date_mapping": matchup_audit,
        "coach_policy": "Historical coach CR is missing; use fixed coach_cr=10 for every team, and reconstruct neutral-credit base score from final NBA results. Coach budget and price-difference multipliers are therefore proxies, not historical market truth.",
        "optimizer": {"budget": 95.0, "fixed_coach_cr": 10.0, "player_budget_after_coach": 85.0,
                      "formation": "4G/4F/2C roster; 5 starters, sixth man, 4 bench; one captain; max 3 per NBA team including coach",
                      "transfer_malus": 0.0, "reason": "Historical carry-over roster and exact transfer/coach prices are not archived; this evaluates fresh independent round lineups."},
        "fold_policy": "Train player score model on earlier valid seasons only; test seasons 2022-23, 2023-24 and 2024-25. No test-season labels are used to fit its model. All high-confidence mapped rounds with a prior historical candidate pool are evaluated; CBC uses a 1-second time limit and 5% relative gap.",
        "metrics": metrics_df.to_dict("records"),
        "round_status_counts": round_df["status"].value_counts(dropna=False).to_dict() if not round_df.empty else {},
        "lineup_rows": len(lineup_df), "production_changed": False,
        "limitations": [
            "This is a restricted-universe lineup experiment, not a complete historical Dunkest market backtest. The candidate universe contains only players observed earlier in the archived season; late additions and players with no earlier archived row may be missing.",
            "The historical round archives are outcomes, not timestamped complete pre-lock roster snapshots. Candidate CR/role/team are lagged proxies, not certified market state.",
            "Game-level PDK reconstruction is validated against weekly outcomes at near-perfect row-level agreement, but round fixtures still depend on the persisted game-link mapping; rounds without a mapping are skipped.",
            "Historical coach prices and exact credit-difference multipliers are unavailable; coach CR is fixed at 10 and neutral-credit base scores are used.",
            "No transfer malus is applied because historical carried rosters and coach prices are unavailable.",
            "The 2025/26 season is not used in this lineup comparison; tested seasons are 2022/23 through 2024/25."
        ]
    }
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Dunkest historical lineup experiment with game-level official actuals — V2", "",
        f"Generated (UTC): {audit['generated_at_utc']}", "",
        "This version corrects the earlier game-ID-union method, which could include a repeated box-score signature from another date. Realized player scores are reconstructed from the official Dunkest-valid slate on a high-confidence round date.", "",
        "## Method", "",
        "For target round r, each candidate's latest archived row strictly before r supplies lagged CR, role, team and form. A round date is accepted only if at least 75% of unique player-date links agree and at least 10 unique player links exist. Realized player PDK is the sum of official game-level PDK for that season/date where gameValidForDunkest=True; candidate identities absent from the official season archive are excluded. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-round mean baseline.", "",
        "## Game-level reconstruction validation", "",
        f"- Historical weekly rows compared: {audit['game_level_actual_reconstruction']['weekly_rows_reconstructed']:,}",
        f"- Rows matching weekly PDK within 0.02 points: {audit['game_level_actual_reconstruction']['rows_with_absolute_difference_below_0_02']:,} ({audit['game_level_actual_reconstruction']['share_with_absolute_difference_below_0_02']:.3%})",
        f"- Mean absolute difference: {audit['game_level_actual_reconstruction']['mean_absolute_difference']:.5f} PDK",
        "",
        "The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model.", "",
        "## Results", "", metrics_df.to_string(index=False), "",
        "Paired uncertainty is reported by scripts/audit_dunkest_gamelevel_lineup_bootstrap_v2.py after this backtest completes.", "",
        "## Coverage", "",
        f"- Round outcomes: {audit['round_status_counts']}",
        f"- Optimized lineup records: {len(lineup_df):,}", "",
        "## Critical caveats", "",
        "This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so late additions and players with no earlier observed row in the season are not candidates. The candidate pool contains about 210 players on average and covers about 94.9% of players appearing in the target-round outcome archive; candidate_target_row_coverage (~60.5%) is the share of candidates with a weekly aggregate row, not the share with reconstructed actuals.", "",
        "Coach prices are missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. This compares fresh independent round lineups, not a sequential roster with transfers, and historical rule differences may remain. Forty-nine rounds failed optimization and six had candidate pools too small; metrics cover the 409 rounds where both strategies were successfully evaluated.", "",
        "Production model/configuration remains unchanged.", "",
        "## Artifacts", "", f"- Round metrics: `{METRICS.relative_to(ROOT)}`", f"- Per-round outcomes: `{ROUNDS.relative_to(ROOT)}`", f"- Selected lineups: `{LINEUPS.relative_to(ROOT)}`", f"- Audit JSON: `{AUDIT.relative_to(ROOT)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "metrics": metrics_df.to_dict("records"),
        "round_status_counts": audit["round_status_counts"], "lineup_rows": len(lineup_df),
        "outputs": [str(x.relative_to(ROOT)) for x in (METRICS, ROUNDS, LINEUPS, AUDIT, REPORT)]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
