#!/usr/bin/env python3
"""Restricted-universe lineup experiment with shrunk player-vs-opponent history.

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
STEM = "dunkest_historical_lineups_h2h_20261013_v6"
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
h2h_spec = importlib.util.spec_from_file_location(
    "historical_h2h_feature_model",
    ROOT / "scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v4.py",
)
if h2h_spec is None or h2h_spec.loader is None:
    raise RuntimeError("Could not load leakage-safe H2H feature builder.")
h2h_module = importlib.util.module_from_spec(h2h_spec)
h2h_spec.loader.exec_module(h2h_module)
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


def build_candidate_h2h(candidates: pd.DataFrame, target_date: str, histories: dict) -> pd.DataFrame:
    """Add target-opponent history using only official-valid PDK games before target date."""
    out = candidates.copy()
    date = np.datetime64(pd.Timestamp(target_date).to_datetime64(), "ns")
    means = np.full(len(out), np.nan); lasts = np.full(len(out), np.nan)
    counts = np.zeros(len(out), dtype=float); minutes_means = np.full(len(out), np.nan)
    minutes_lasts = np.full(len(out), np.nan); game_counts = np.zeros(len(out), dtype=float)
    for i, (_, row) in enumerate(out.iterrows()):
        key = (str(row.get("player_key", "")), str(row.get("target_opponent", "")).upper().strip())
        hist = histories.get(key)
        if hist is None:
            continue
        dates, scores, minutes = hist
        end = int(np.searchsorted(dates, date, side="left"))
        if end <= 0:
            continue
        start = max(0, end - 5)
        ps = scores[start:end]; ms = minutes[start:end]
        good_p = ps[np.isfinite(ps)]; good_m = ms[np.isfinite(ms)]
        counts[i] = len(good_p); game_counts[i] = len(good_m)
        if len(good_p): means[i] = float(good_p.mean()); lasts[i] = float(good_p[-1])
        if len(good_m): minutes_means[i] = float(good_m.mean()); minutes_lasts[i] = float(good_m[-1])
    out["h2h_pdk_mean_prev5"] = means
    out["h2h_pdk_last"] = lasts
    out["h2h_valid_pdk_games_prev5"] = counts
    out["h2h_minutes_mean_prev5"] = minutes_means
    out["h2h_minutes_last"] = minutes_lasts
    out["h2h_games_prev5"] = game_counts
    prior = pd.to_numeric(out["prev5_pdk_mean"], errors="coerce").to_numpy(float)
    shrunk = np.full(len(out), np.nan); has_prior = np.isfinite(prior); has_h2h = counts > 0
    both = has_prior & has_h2h
    shrunk[both] = (means[both] * counts[both] + 3.0 * prior[both]) / (counts[both] + 3.0)
    shrunk[has_prior & ~has_h2h] = prior[has_prior & ~has_h2h]
    shrunk[~has_prior & has_h2h] = means[~has_prior & has_h2h]
    out["h2h_pdk_mean_shrunk_prev5"] = shrunk
    return out


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
    raw = raw.loc[np.isfinite(raw["target_pdk_round_total"])].copy()
    base_features = player_module.build_features(raw)
    feature_rows, matchup_audit = player_module.attach_matchup_features(base_features, raw)
    feature_rows, h2h_audit = h2h_module.attach_player_opponent_history(feature_rows)
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
               "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10",
               "h2h_pdk_mean_shrunk_prev5", "h2h_pdk_last", "h2h_valid_pdk_games_prev5",
               "h2h_minutes_mean_prev5", "h2h_minutes_last", "h2h_games_prev5"]
    categorical = ["lagged_role", "target_opponent"]
    coach = pd.read_csv(COACH_PREDICTIONS)
    coach = coach.loc[coach["method"].eq("model_pregame_team_form")].copy()
    coach["season"] = coach["season"].astype(str)
    coach["game_date"] = pd.to_datetime(coach["game_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    coach["team"] = coach["team"].astype(str).str.upper().str.strip()
    coach["opponent"] = coach["opponent"].astype(str).str.upper().str.strip()

    candidate_rows = candidate_history_features(raw)
    # Historical H2H lookup table; invalid Dunkest PDK labels are excluded, while NBA minutes
    # remain a separate participation feature. Date-only archives exclude all same-day games.
    hsource = pd.read_parquet(h2h_module.ENRICHED)
    hsource["game_date_key"] = pd.to_datetime(hsource["nba_NBA_GAME_DATE_PARSED"], errors="coerce")
    hsource["player_key"] = hsource["dunkest_player_name"].astype(str).str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    hsource["opponent_key"] = hsource["opponentTeamCode"].astype(str).str.upper().str.strip()
    hsource["historical_pdk"] = pd.to_numeric(hsource["pdk"], errors="coerce")
    valid_h2h = hsource["gameValidForDunkest"].astype(str).str.lower().isin({"true", "1"})
    hsource["historical_pdk"] = hsource["historical_pdk"].where(valid_h2h & np.isfinite(hsource["historical_pdk"]))
    hsource["historical_minutes"] = pd.to_numeric(hsource["min"], errors="coerce")
    hsource = hsource.dropna(subset=["game_date_key", "player_key", "opponent_key"]).sort_values("game_date_key")
    h2h_histories = {}
    for key, group in hsource.groupby(["player_key", "opponent_key"], sort=False):
        h2h_histories[key] = (group["game_date_key"].to_numpy(dtype="datetime64[ns]"),
                              group["historical_pdk"].to_numpy(float),
                              group["historical_minutes"].to_numpy(float))

    metrics_rows, round_rows, lineup_rows = [], [], []
    for test_season in TEST_SEASONS:
        train = feature_rows.loc[feature_rows["season_id"].isin(VALID_SEASONS[:VALID_SEASONS.index(test_season)]) & feature_rows["target_opponent"].notna()].copy()
        test_rounds = round_meta.loc[round_meta["season_id"].eq(test_season)].sort_values("round_index")
        if train.empty or test_rounds.empty:
            continue
        model = make_model(numeric, categorical)
        model.fit(train[numeric + categorical], train["target_pdk_round_total"].to_numpy(float))
        numeric_no_h2h = [x for x in numeric if not x.startswith("h2h_")]
        model_no_h2h = make_model(numeric_no_h2h, categorical)
        model_no_h2h.fit(train[numeric_no_h2h + categorical], train["target_pdk_round_total"].to_numpy(float))
        train_median = float(pd.to_numeric(train["target_pdk_round_total"], errors="coerce").median())
        season_candidates = candidate_rows.loc[candidate_rows["season_id"].eq(test_season)].copy()
        season_observed = feature_rows.loc[feature_rows["season_id"].eq(test_season)].copy()
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
            # Team is strictly the latest archived pre-target team; do not infer it from target-round outcomes.
            candidates["team"] = candidates["team_code"].astype(str).str.upper().str.strip()
            # Target matchup is attached from the known NBA schedule, not from current-round fantasy outcomes.
            match_map = team_matchups.loc[team_matchups["season_id"].eq(test_season) & team_matchups["round_index"].eq(target_round)].copy()
            match_map = match_map.rename(columns={"team_code_key": "team"}).drop_duplicates("team")
            candidates = candidates.merge(match_map[["team", "target_opponent", "opp_def_allowed_pts_prev10", "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10"]],
                on="team", how="left", validate="many_to_one")
            candidates = candidates.loc[candidates["target_opponent"].notna()].copy()
            candidates = build_candidate_h2h(candidates, target_date, h2h_histories)
            if len(candidates) < 10:
                round_rows.append({"season_id": test_season, "round_index": target_round, "target_date": target_date, "status": "candidate_pool_too_small", "candidate_count": len(candidates)})
                continue
            # Build pregame predictions for the prior-round market pool.
            candidates["expected_min"] = pd.to_numeric(candidates["prev5_min_mean"], errors="coerce").fillna(pd.to_numeric(candidates["lag1_min_avg"], errors="coerce")).clip(lower=0)
            candidates["p_play"] = 1.0
            candidates["status"] = "Available"
            candidates["expected_plusvalenza"] = 0.0
            candidates["actual_pdk"] = candidates["player_key"].map(actual_map).fillna(0.0).astype(float)
            try:
                candidates["expected_pdk_model"] = model_no_h2h.predict(candidates[numeric_no_h2h + categorical])
                candidates["expected_pdk_h2h"] = model.predict(candidates[numeric + categorical])
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
            for strategy, score_col in (("model", "expected_pdk_model"), ("model_h2h", "expected_pdk_h2h"), ("previous5_baseline", "expected_pdk_baseline")):
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
                        "candidate_target_row_coverage": float(candidates["player_key"].isin(actual_map).mean()),
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
            if all(k in selected_results for k in ("model", "model_h2h", "previous5_baseline")):
                model_result = selected_results["model"]
                h2h_result = selected_results["model_h2h"]
                baseline_result = selected_results["previous5_baseline"]
                round_rows.append({
                    "season_id": test_season, "season": settings.season, "round_index": target_round,
                    "source_week": int(meta["source_week"]), "source_round": int(meta["source_round"]),
                    "target_date": target_date, "status": "evaluated", "candidate_count": int(len(candidates)),
                    "candidate_target_row_coverage": float(candidates["player_key"].isin(actual_map).mean()),
                    "target_players": int(len(target_outcomes)), "target_players_in_candidate_pool": int(target_outcomes["player_key"].isin(candidates["player_key"]).sum()),
                    "model_realized_team_score": model_result["team_actual"],
                    "h2h_realized_team_score": h2h_result["team_actual"],
                    "baseline_realized_team_score": baseline_result["team_actual"],
                    "model_minus_baseline": model_result["team_actual"] - baseline_result["team_actual"],
                    "h2h_minus_model": h2h_result["team_actual"] - model_result["team_actual"],
                    "h2h_minus_baseline": h2h_result["team_actual"] - baseline_result["team_actual"],
                    "h2h_roster": "; ".join(h2h_result["solution"].players["player_name"].astype(str).tolist()),
                    "h2h_coach_team": str(h2h_result["solution"].coach).rsplit(" ", 1)[-1],
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
            h2h_diff = pd.to_numeric(group["h2h_minus_model"], errors="coerce")
            metrics.append({"season_id": sid, "season": group["season"].iloc[0], "rounds_evaluated": len(group),
                "mean_model_realized_team_score": float(group["model_realized_team_score"].mean()),
                "mean_baseline_realized_team_score": float(group["baseline_realized_team_score"].mean()),
                "mean_delta_model_minus_baseline": float(diff.mean()),
                "mean_h2h_minus_model": float(h2h_diff.mean()),
                "median_h2h_minus_model": float(h2h_diff.median()),
                "h2h_win_rate_vs_model": float((h2h_diff > 0).mean()),
                "median_delta_model_minus_baseline": float(diff.median()),
                "model_win_rate_vs_baseline": float((diff > 0).mean()),
                "mean_candidate_count": float(group["candidate_count"].mean()),
                "mean_candidate_target_row_coverage": float(group["candidate_target_row_coverage"].mean()),
                "mean_target_players_covered": float((group["target_players_in_candidate_pool"] / group["target_players"]).replace([np.inf,-np.inf],np.nan).mean())})
        if not evaluated.empty:
            diff = pd.to_numeric(evaluated["model_minus_baseline"], errors="coerce")
            h2h_diff = pd.to_numeric(evaluated["h2h_minus_model"], errors="coerce")
            metrics.append({"season_id": "POOLED", "season": "2022-23–2024-25", "rounds_evaluated": len(evaluated),
                "mean_model_realized_team_score": float(evaluated["model_realized_team_score"].mean()),
                "mean_baseline_realized_team_score": float(evaluated["baseline_realized_team_score"].mean()),
                "mean_delta_model_minus_baseline": float(diff.mean()),
                "mean_h2h_minus_model": float(h2h_diff.mean()),
                "median_h2h_minus_model": float(h2h_diff.median()),
                "h2h_win_rate_vs_model": float((h2h_diff > 0).mean()),
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
        "supersedes_diagnostic_versions": {"v1": "identity-key mismatch made outcome join coverage invalid", "v2": "candidate pool restricted to immediately previous round and missed most target participants", "v4": "deterministic every-third-round sample; V5 evaluates all high-confidence rounds"},
        "input": str(INPUT.relative_to(ROOT)), "coach_prediction_source": str(COACH_PREDICTIONS.relative_to(ROOT)),
        "candidate_policy": "For target round r, each candidate's latest observed row strictly before r is carried forward. CR, role and team are therefore lagged; when a player has no row in r-1, the last observed CR is carried forward because no intervening appearance was recorded. Current target-round PDK is used only as realized outcome. This expands coverage beyond players who appeared in r-1 but still excludes players who have never appeared in the archived season.",
        "target_date_mapping": matchup_audit,
        "h2h_feature_audit": h2h_audit,
        "h2h_candidate_features": ["h2h_pdk_mean_shrunk_prev5", "h2h_pdk_last", "h2h_valid_pdk_games_prev5", "h2h_minutes_mean_prev5", "h2h_minutes_last", "h2h_games_prev5"],
        "h2h_policy": "Only player-vs-target-opponent games strictly before target calendar date; same-day games excluded. PDK history only from official-valid labels. Candidate team and price come only from pre-target archive rows; target-round outcomes are used solely for realized scoring.",
        "coach_policy": "Historical coach CR is missing; use fixed coach_cr=10 for every team, and reconstruct neutral-credit base score from final NBA results. Coach budget and price-difference multipliers are therefore proxies, not historical market truth.",
        "optimizer": {"budget": 95.0, "fixed_coach_cr": 10.0, "player_budget_after_coach": 85.0,
                      "formation": "4G/4F/2C roster; 5 starters, sixth man, 4 bench; one captain; max 3 per NBA team including coach",
                      "transfer_malus": 0.0, "reason": "Historical carry-over roster and exact transfer/coach prices are not archived; this evaluates fresh independent round lineups."},
        "fold_policy": "Train separate player score models with and without H2H features on earlier valid seasons only; test seasons 2022-23, 2023-24 and 2024-25. No test-season labels are used to fit its model. All high-confidence mapped rounds with a prior historical candidate pool are evaluated; CBC uses a 1-second time limit and 5% relative gap.",
        "metrics": metrics_df.to_dict("records"),
        "round_status_counts": round_df["status"].value_counts(dropna=False).to_dict() if not round_df.empty else {},
        "lineup_rows": len(lineup_df), "production_changed": False,
        "limitations": [
            "This is a restricted-universe lineup experiment, not a complete historical Dunkest market backtest. The candidate universe contains only players observed in the prior archived round; late additions and players absent from that round may be missing.",
            "The historical round archives are outcomes, not timestamped complete pre-lock roster snapshots. Candidate coverage is reported; results must not be generalized to the full market without complete roster archives.",
            "Missing target-round player rows are scored as zero only within this restricted experiment; this assumes absence from the official-valid round table means no fantasy points for that player in the round.",
            "Historical coach prices and exact credit-difference multipliers are unavailable; coach CR is fixed at 10 and neutral-credit base scores are used.",
            "No transfer malus is applied because historical carry-over rosters and coach prices are unavailable."
        ]
    }
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Dunkest historical lineup experiment with lagged market — V1", "",
        f"Generated (UTC): {audit['generated_at_utc']}", "",
        "V6 compares three optimizer strategies on the same restricted pre-target candidate pool: a model without H2H, a model with shrunk player-vs-opponent history, and the previous-five-round PDK baseline.", "",
        "## Method", "",
        "For target round r, the candidate pool carries forward each player's most recent archived row strictly before r. CR, role and player form are therefore lagged; if a player did not appear in r−1, their last observed price is carried forward. The current round's player score is used only as the realized outcome. A walk-forward player model is trained on earlier seasons only and compared with a previous-five-round mean baseline.", "",
        "The optimizer uses the repository's roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model.", "",
        "## Results", "", metrics_df.to_string(index=False), "",
        "## Coverage", "",
        f"- Round outcomes: {audit['round_status_counts']}",
        f"- Optimized lineup records: {len(lineup_df):,}", "",
        "## Critical caveats", "",
        "This is a restricted candidate-pool experiment. Historical round tables do not contain a complete pre-lock roster snapshot, so players with no earlier observed row in the season are not candidates. The result cannot be called a complete historical market optimum.", "",
        "Coach prices are also missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is set to zero because historical carried rosters are not archived. These choices isolate the value of the player prediction model, but do not validate historical transfer strategy or exact coach-price selection.", "",
        "The 2025/26 game-level H2H holdout motivates this experiment but does not tune this test. Production model/configuration remains unchanged.", "",
        "## Artifacts", "", f"- Round metrics: `{METRICS.relative_to(ROOT)}`", f"- Per-round outcomes: `{ROUNDS.relative_to(ROOT)}`", f"- Selected lineups: `{LINEUPS.relative_to(ROOT)}`", f"- Audit JSON: `{AUDIT.relative_to(ROOT)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "metrics": metrics_df.to_dict("records"),
        "round_status_counts": audit["round_status_counts"], "lineup_rows": len(lineup_df),
        "outputs": [str(x.relative_to(ROOT)) for x in (METRICS, ROUNDS, LINEUPS, AUDIT, REPORT)]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
