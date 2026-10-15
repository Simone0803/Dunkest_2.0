#!/usr/bin/env python3
"""Leakage-safe walk-forward test with expanded matchup and shrunk player-vs-opponent history.

Uses historical player-week/round outcome tables. Current-round CR and statistics
are never used as features: all numeric history and CR inputs are shifted from
strictly earlier rounds. Official-valid target seasons only are included.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet"
OUT = ROOT / "reports/audit"
STEM = "dunkest_lagged_credit_matchup_walk_forward_20261013_v5_role_interactions"
METRICS = OUT / f"{STEM}_metrics.csv"
PREDICTIONS = OUT / f"{STEM}_predictions.csv"
AUDIT = OUT / f"{STEM}.json"
REPORT = OUT / f"{STEM}.md"
# 2020/21–2024/25 have verified official Dunkest targets in this source.
VALID_SEASONS = ["5", "7", "9", "13", "19"]
TEST_SEASONS = ["9", "13", "19"]
ENRICHED = ROOT / "data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
TEAM_LOGS = ROOT / "data/processed/team_game_logs_2018-26_v1.parquet"


def metric_row(y: np.ndarray, p: np.ndarray, season: str, family: str, n: int) -> dict:
    err = p - y
    return {
        "test_season_id": season,
        "test_season": {"9": "2022-23", "13": "2023-24", "19": "2024-25"}.get(season, season),
        "feature_family": family,
        "n": int(n),
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(mean_squared_error(y, p) ** 0.5),
        "bias_pred_minus_actual": float(np.mean(err)),
    }


def build_features(raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.copy()
    d["season_id"] = d["source_season_id"].astype(str)
    d["player_name"] = d["player_name"].astype(str).str.strip()
    d["player_key"] = d["player_name"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    d["source_week"] = pd.to_numeric(d["source_week"], errors="coerce")
    d["source_round"] = pd.to_numeric(d["source_round"], errors="coerce")
    d["round_key"] = d["source_week"].astype("Int64").astype(str) + ":" + d["source_round"].astype("Int64").astype(str)
    round_order = d[["season_id", "source_week", "source_round"]].drop_duplicates().sort_values(
        ["season_id", "source_week", "source_round"]
    )
    round_order["round_index"] = round_order.groupby("season_id").cumcount() + 1
    d = d.merge(round_order, on=["season_id", "source_week", "source_round"], how="left", validate="many_to_one")
    d = d.sort_values(["season_id", "player_key", "round_index"]).reset_index(drop=True)

    numeric_history = {
        "cr": "lag1_cr",
        "target_pdk_round_total": "lag1_pdk",
        "min_avg": "lag1_min_avg",
        "min_tot": "lag1_min_tot",
        "plus": "lag1_plus",
        "gp": "lag1_gp",
        "pts_avg": "lag1_pts_avg",
        "reb_avg": "lag1_reb_avg",
        "ast_avg": "lag1_ast_avg",
        "stl_avg": "lag1_stl_avg",
        "blk_avg": "lag1_blk_avg",
        "tov_avg": "lag1_tov_avg",
        "plus_minus_avg": "lag1_plus_minus_avg",
    }
    for source, dest in numeric_history.items():
        values = pd.to_numeric(d[source], errors="coerce")
        d[dest] = values.groupby([d["season_id"], d["player_key"]]).shift(1)

    for window in (3, 5, 10):
        d[f"prev{window}_pdk_mean"] = d.groupby(["season_id", "player_key"])["lag1_pdk"].transform(
            lambda s: s.shift(0).rolling(window, min_periods=1).mean()
        )
        d[f"prev{window}_min_mean"] = d.groupby(["season_id", "player_key"])["lag1_min_avg"].transform(
            lambda s: s.shift(0).rolling(window, min_periods=1).mean()
        )
    # Explicit recency/gap features; the last known CR is always from an earlier round.
    d["last_seen_round_index"] = d["round_index"] - d.groupby(["season_id", "player_key"])["round_index"].shift(1)
    d["credit_age_rounds"] = d["last_seen_round_index"]
    d["prior_round_present"] = d["last_seen_round_index"].eq(1).astype(int)
    d["history_rounds_before_target"] = d.groupby(["season_id", "player_key"]).cumcount()
    # All category values come from the player's most recent earlier observed round.
    for source, dest in (("role", "lagged_role"), ("team_code", "lagged_team")):
        d[dest] = d.groupby(["season_id", "player_key"])[source].shift(1).astype(object)
        d[dest] = d[dest].where(pd.notna(d[dest]), np.nan)
    d["season_round_index"] = d["round_index"]
    return d


def attach_matchup_features(d: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Infer high-confidence target-round dates from official player/game linkage,
    then attach opponent and opponent-defense form using NBA logs strictly before
    the target date. The PDK score is used only to link outcome rows to fixtures,
    never as a predictor.
    """
    if not ENRICHED.is_file() or not TEAM_LOGS.is_file():
        raise FileNotFoundError(f"Required matchup sources missing: {ENRICHED}, {TEAM_LOGS}")
    base = raw.copy().reset_index(drop=True)
    base["_source_row_id"] = np.arange(len(base), dtype=int)
    base["season_id"] = base["source_season_id"].astype(str)
    base["player_key"] = base["player_name"].astype(str).str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    base["team_code_key"] = base["team_code"].astype(str).str.upper().str.strip()
    base["pdk_key"] = pd.to_numeric(base["target_pdk_round_total"], errors="coerce").round(2)

    official = pd.read_parquet(ENRICHED)
    official = official.loc[official["gameValidForDunkest"].astype(str).str.lower().isin({"true", "1"})].copy()
    official["season_id"] = official["season_id"].astype(str)
    official["player_key"] = official["dunkest_player_name"].astype(str).str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    official["team_code_key"] = official["nba_TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    official["pdk_key"] = pd.to_numeric(official["pdk"], errors="coerce").round(2)
    official["candidate_date"] = pd.to_datetime(official["gameDate"], errors="coerce").dt.strftime("%Y-%m-%d")
    official = official.dropna(subset=["candidate_date"])
    candidates = base[[
        "_source_row_id", "season_id", "player_key", "team_code_key", "pdk_key",
        "source_week", "source_round",
    ]].merge(
        official[["season_id", "player_key", "team_code_key", "pdk_key", "candidate_date"]].drop_duplicates(),
        on=["season_id", "player_key", "team_code_key", "pdk_key"], how="left",
    )
    date_counts = candidates.groupby("_source_row_id")["candidate_date"].nunique(dropna=True)
    candidates["candidate_date_count"] = candidates["_source_row_id"].map(date_counts)
    unique_link = candidates.loc[candidates["candidate_date_count"].eq(1) & candidates["candidate_date"].notna()].drop_duplicates(
        ["_source_row_id", "candidate_date"]
    )
    unique_link["season_id"] = unique_link["season_id"].astype(str)
    round_stats = []
    for (sid, week, rnd), group in unique_link.groupby(["season_id", "source_week", "source_round"], dropna=False):
        counts = group["candidate_date"].value_counts()
        if counts.empty:
            continue
        round_stats.append({
            "season_id": str(sid), "source_week": int(week), "source_round": int(rnd),
            "unique_player_date_links": int(len(group)), "candidate_dates": int(len(counts)),
            "target_date": str(counts.index[0]), "date_confidence": float(counts.iloc[0] / len(group)),
        })
    round_map = pd.DataFrame(round_stats)
    if round_map.empty:
        raise RuntimeError("Could not infer any historical round dates from official-valid player-game links.")
    round_map["matchup_date_ready"] = round_map["date_confidence"].ge(0.75) & round_map["unique_player_date_links"].ge(10)
    round_map.loc[~round_map["matchup_date_ready"], "target_date"] = np.nan
    d = d.merge(round_map[["season_id", "source_week", "source_round", "target_date", "date_confidence", "matchup_date_ready"]],
                on=["season_id", "source_week", "source_round"], how="left", validate="many_to_one")

    teams = pd.read_parquet(TEAM_LOGS).copy()
    teams["GAME_DATE"] = pd.to_datetime(teams["GAME_DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    teams["GAME_ID"] = teams["GAME_ID"].astype(str)
    teams["TEAM_ABBREVIATION"] = teams["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    teams["PTS"] = pd.to_numeric(teams["PTS"], errors="coerce")
    for c in ("REB", "AST", "STL", "BLK", "TOV", "FGA", "FTA", "OREB"):
        teams[c] = pd.to_numeric(teams[c], errors="coerce")
    game_groups = teams.groupby("GAME_ID", sort=False)
    team_pairs = []
    for game_id, g in game_groups:
        g = g.drop_duplicates("TEAM_ABBREVIATION")
        if len(g) != 2:
            continue
        a, b = g.iloc[0], g.iloc[1]
        for own, opp in ((a, b), (b, a)):
            team_pairs.append({
                "GAME_ID": str(game_id), "GAME_DATE": str(own["GAME_DATE"]),
                "team_code_key": str(own["TEAM_ABBREVIATION"]),
                "opponent_code": str(opp["TEAM_ABBREVIATION"]),
                "team_pts": own["PTS"], "team_reb": own["REB"], "team_ast": own["AST"],
                "allowed_pts": opp["PTS"], "allowed_reb": opp["REB"], "allowed_ast": opp["AST"],
                "allowed_stl": opp["STL"], "allowed_blk": opp["BLK"], "allowed_tov": opp["TOV"],
                "team_possessions": own["FGA"] + 0.44 * own["FTA"] - own["OREB"] + own["TOV"],
                "opponent_possessions": opp["FGA"] + 0.44 * opp["FTA"] - opp["OREB"] + opp["TOV"],
            })
    schedule = pd.DataFrame(team_pairs)
    schedule = schedule.dropna(subset=["GAME_DATE", "team_code_key", "opponent_code"])
    schedule = schedule.sort_values(["team_code_key", "GAME_DATE", "GAME_ID"])
    # Each row describes the opponent's defensive output in that completed game.
    defense = schedule[["GAME_ID", "GAME_DATE", "team_code_key", "allowed_pts", "allowed_reb", "allowed_ast",
                        "allowed_stl", "allowed_blk", "allowed_tov", "team_possessions", "opponent_possessions"]].copy()
    defense = defense.sort_values(["team_code_key", "GAME_DATE", "GAME_ID"])
    # Every rolling feature is shifted before rolling; target-game box scores cannot enter.
    rolling_sources = (
        ("allowed_pts", "opp_def_allowed_pts_prev10"),
        ("allowed_reb", "opp_def_allowed_reb_prev10"),
        ("allowed_ast", "opp_def_allowed_ast_prev10"),
        ("allowed_stl", "opp_def_allowed_stl_prev10"),
        ("allowed_blk", "opp_def_allowed_blk_prev10"),
        ("allowed_tov", "opp_def_allowed_tov_prev10"),
        ("team_possessions", "opp_pace_prev10"),
        ("opponent_possessions", "opp_possessions_allowed_prev10"),
    )
    for source, dest in rolling_sources:
        defense[dest] = defense.groupby("team_code_key")[source].transform(
            lambda x: x.shift(1).rolling(10, min_periods=3).mean()
        )
    # Shorter 5-game windows let recent defensive changes compete against the 10-game trend.
    for source, dest in (("allowed_pts", "opp_def_allowed_pts_prev5"),
                         ("allowed_reb", "opp_def_allowed_reb_prev5"),
                         ("allowed_ast", "opp_def_allowed_ast_prev5"),
                         ("team_possessions", "opp_pace_prev5")):
        defense[dest] = defense.groupby("team_code_key")[source].transform(
            lambda x: x.shift(1).rolling(5, min_periods=3).mean()
        )
    defense = defense[["GAME_DATE", "team_code_key"] + [dest for _, dest in rolling_sources] +
                      ["opp_def_allowed_pts_prev5", "opp_def_allowed_reb_prev5", "opp_def_allowed_ast_prev5", "opp_pace_prev5"]].rename(
        columns={"GAME_DATE": "target_date", "team_code_key": "target_opponent"}
    )
    d["team_code_key"] = d["team_code"].astype(str).str.upper().str.strip()
    d = d.merge(schedule[["GAME_DATE", "team_code_key", "opponent_code"]].drop_duplicates(),
                left_on=["target_date", "team_code_key"], right_on=["GAME_DATE", "team_code_key"],
                how="left", validate="many_to_one")
    d = d.rename(columns={"opponent_code": "target_opponent"}).drop(columns=["GAME_DATE"], errors="ignore")
    d = d.merge(defense, on=["target_date", "target_opponent"], how="left", validate="many_to_one")
    d["target_opponent"] = d["target_opponent"].astype(object).where(d["target_opponent"].notna(), np.nan)
    audit = {
        "rounds_total": int(len(round_map)),
        "rounds_with_confident_date": int(round_map["matchup_date_ready"].sum()),
        "rounds_date_confidence_threshold": 0.75,
        "minimum_unique_player_date_links_per_round": 10,
        "rows_with_target_opponent": int(d["target_opponent"].notna().sum()),
        "rows_with_all_eight_expanded_opponent_features": int(d[["opp_def_allowed_pts_prev10", "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10", "opp_def_allowed_stl_prev10", "opp_def_allowed_blk_prev10", "opp_def_allowed_tov_prev10", "opp_pace_prev10", "opp_possessions_allowed_prev10"]].notna().all(axis=1).sum()),
        "date_mapping_by_season": round_map.groupby("season_id").agg(
            rounds=("source_week", "size"), confident_rounds=("matchup_date_ready", "sum"),
            median_confidence=("date_confidence", "median")
        ).reset_index().to_dict("records"),
        "mapping_method": "Official-valid Dunkest PDK and player/team identity are used only to link historical outcome rows to candidate NBA dates. A round date is accepted only if >=75% of unique player-date links agree and >=10 unique links exist. Matchup features use NBA schedule and opponent defensive stats strictly before that date.",
    }
    return d, audit



def attach_player_opponent_history(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Attach only player-vs-opponent games strictly before the target calendar date.

    Dunkest PDK labels are included only where the source marks them official-valid.
    NBA minutes are available as a separate role/participation signal. A same-day
    game is excluded because date-only archives cannot establish pre-tip ordering.
    """
    source = pd.read_parquet(ENRICHED)
    source["game_date_key"] = pd.to_datetime(source["nba_NBA_GAME_DATE_PARSED"], errors="coerce")
    source["player_key"] = source["dunkest_player_name"].astype(str).str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    source["opponent_key"] = source["opponentTeamCode"].astype(str).str.upper().str.strip()
    source["historical_pdk"] = pd.to_numeric(source["pdk"], errors="coerce")
    valid = source["gameValidForDunkest"].astype(str).str.lower().isin({"true", "1"})
    source["historical_pdk"] = source["historical_pdk"].where(valid & np.isfinite(source["historical_pdk"]))
    source["historical_minutes"] = pd.to_numeric(source["min"], errors="coerce")
    source = source.dropna(subset=["game_date_key", "player_key", "opponent_key"])
    source = source.sort_values("game_date_key")
    # Group into sorted arrays so lookup work is O(log n) per player-round, not a large Cartesian join.
    histories = {}
    for key, g in source.groupby(["player_key", "opponent_key"], sort=False):
        histories[key] = (g["game_date_key"].to_numpy(dtype="datetime64[ns]"),
                          g["historical_pdk"].to_numpy(float),
                          g["historical_minutes"].to_numpy(float))
    dates = pd.to_datetime(d["target_date"], errors="coerce")
    pkeys = d["player_key"].astype(str).to_numpy()
    opps = d["target_opponent"].astype(str).str.upper().to_numpy()
    target_dates = dates.to_numpy(dtype="datetime64[ns]")
    n = len(d)
    pdk_mean = np.full(n, np.nan); min_mean = np.full(n, np.nan)
    count = np.zeros(n, dtype=float); pdk_count = np.zeros(n, dtype=float)
    pdk_recent = np.full(n, np.nan); min_recent = np.full(n, np.nan)
    for i, (pk, opp, date) in enumerate(zip(pkeys, opps, target_dates)):
        if np.isnat(date):
            continue
        hist = histories.get((pk, opp))
        if hist is None:
            continue
        hd, hp, hm = hist
        end = int(np.searchsorted(hd, date, side="left"))
        if end <= 0:
            continue
        start = max(0, end - 5)
        past_pdk = hp[start:end]; past_min = hm[start:end]
        good_pdk = past_pdk[np.isfinite(past_pdk)]
        good_min = past_min[np.isfinite(past_min)]
        count[i] = len(past_min[np.isfinite(past_min)])
        pdk_count[i] = len(good_pdk)
        if len(good_pdk):
            pdk_mean[i] = float(np.mean(good_pdk))
            pdk_recent[i] = float(good_pdk[-1])
        if len(good_min):
            min_mean[i] = float(np.mean(good_min))
            min_recent[i] = float(good_min[-1])
    out = d.copy()
    out["h2h_pdk_mean_prev5"] = pdk_mean
    out["h2h_minutes_mean_prev5"] = min_mean
    out["h2h_pdk_last"] = pdk_recent
    out["h2h_minutes_last"] = min_recent
    out["h2h_games_prev5"] = count
    out["h2h_valid_pdk_games_prev5"] = pdk_count
    # Empirical-Bayes-style shrinkage: 3 pseudo-observations from the player's
    # general recent PDK form keep 1-2 head-to-head games from dominating.
    prior_form = pd.to_numeric(out["prev5_pdk_mean"], errors="coerce").to_numpy(float)
    h2h_sum = np.nan_to_num(pdk_mean, nan=0.0) * pdk_count
    shrunk = np.full(n, np.nan)
    both = np.isfinite(prior_form) & (pdk_count > 0)
    shrunk[both] = (h2h_sum[both] + 3.0 * prior_form[both]) / (pdk_count[both] + 3.0)
    only_h2h = (~np.isfinite(prior_form)) & (pdk_count > 0)
    shrunk[only_h2h] = h2h_sum[only_h2h] / pdk_count[only_h2h]
    only_prior = np.isfinite(prior_form) & (pdk_count == 0)
    shrunk[only_prior] = prior_form[only_prior]
    out["h2h_pdk_mean_shrunk_prev5"] = shrunk
    audit = {"source_rows": int(len(source)), "player_opponent_history_keys": int(len(histories)),
             "rows_with_prior_h2h_game": int((count > 0).sum()),
             "rows_with_prior_official_valid_h2h_pdk": int((pdk_count > 0).sum()),
             "feature_policy": "Player-vs-opponent history uses only games strictly before the target calendar date. Same-day games are excluded. PDK features require official-valid labels; NBA minutes are treated separately.",
             "features": ["h2h_pdk_mean_prev5", "h2h_pdk_mean_shrunk_prev5", "h2h_minutes_mean_prev5", "h2h_pdk_last", "h2h_minutes_last", "h2h_games_prev5", "h2h_valid_pdk_games_prev5"]}
    return out, audit


def make_model(numeric: list[str], categorical: list[str]) -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True))]), numeric),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")),
                              ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ],
        remainder="drop",
    )
    return Pipeline([("preprocess", pre), ("model", ExtraTreesRegressor(
        n_estimators=180, min_samples_leaf=8, max_features=0.85,
        random_state=42, n_jobs=-1,
    ))])


def main() -> int:
    for p in (METRICS, PREDICTIONS, AUDIT, REPORT):
        if p.exists():
            raise SystemExit(f"Refusing to overwrite versioned artifact: {p}")
    if not INPUT.is_file():
        raise FileNotFoundError(INPUT)
    raw = pd.read_parquet(INPUT)
    raw["source_season_id"] = raw["source_season_id"].astype(str)
    raw = raw.loc[raw["source_season_id"].isin(VALID_SEASONS)].copy()
    raw["target_pdk_round_total"] = pd.to_numeric(raw["target_pdk_round_total"], errors="coerce")
    raw = raw.loc[np.isfinite(raw["target_pdk_round_total"])].copy()
    d = build_features(raw)
    d, matchup_audit = attach_matchup_features(d, raw)
    d, h2h_audit = attach_player_opponent_history(d)

    # Role-conditioned matchup effects: interactions are formed only with the
    # lagged Dunkest role, never the target-round role. These let the same
    # opponent defensive profile affect guards, forwards and centers differently.
    interaction_sources = {
        "opp_def_allowed_pts_prev10": "pts",
        "opp_def_allowed_reb_prev10": "reb",
        "opp_def_allowed_ast_prev10": "ast",
        "opp_pace_prev10": "pace",
    }
    role_interaction_features = []
    for role in ("G", "F", "C"):
        role_mask = d["lagged_role"].astype(str).eq(role).astype(float)
        for source, short in interaction_sources.items():
            name = f"role_{role}_x_opp_{short}_prev10"
            d[name] = pd.to_numeric(d[source], errors="coerce") * role_mask
            role_interaction_features.append(name)

    # These feature groups are deliberately nested to measure the incremental
    # value of lagged CR, not to select a production change automatically.
    form_num = ["lag1_pdk", "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean",
                "lag1_min_avg", "prev3_min_mean", "prev5_min_mean", "lag1_plus",
                "lag1_pts_avg", "lag1_reb_avg", "lag1_ast_avg", "lag1_stl_avg",
                "lag1_blk_avg", "lag1_tov_avg", "lag1_plus_minus_avg",
                "lag1_gp", "history_rounds_before_target", "credit_age_rounds", "prior_round_present"]
    credit_num = ["lag1_cr"]
    categorical = ["lagged_role", "lagged_team"]
    matchup_num_v1 = ["opp_def_allowed_pts_prev10", "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10"]
    matchup_num_v2 = matchup_num_v1 + ["opp_def_allowed_stl_prev10", "opp_def_allowed_blk_prev10", "opp_def_allowed_tov_prev10",
        "opp_pace_prev10", "opp_possessions_allowed_prev10", "opp_def_allowed_pts_prev5", "opp_def_allowed_reb_prev5",
        "opp_def_allowed_ast_prev5", "opp_pace_prev5"]
    h2h_num_v3 = ["h2h_pdk_mean_prev5", "h2h_minutes_mean_prev5", "h2h_pdk_last", "h2h_minutes_last",
               "h2h_games_prev5", "h2h_valid_pdk_games_prev5"]
    h2h_num_v4 = ["h2h_pdk_mean_shrunk_prev5", "h2h_minutes_mean_prev5", "h2h_pdk_last", "h2h_minutes_last",
               "h2h_games_prev5", "h2h_valid_pdk_games_prev5"]
    families = {
        "historical_form_only": (form_num, []),
        "historical_form_plus_lagged_credit": (form_num + credit_num, ["lagged_role"]),
        "historical_form_plus_lagged_credit_and_matchup_v1": (form_num + credit_num + matchup_num_v1, ["lagged_role", "target_opponent"]),
        "historical_form_plus_lagged_credit_and_expanded_matchup_v2": (form_num + credit_num + matchup_num_v2, ["lagged_role", "target_opponent"]),
        "historical_form_plus_lagged_credit_expanded_matchup_and_h2h_v3": (form_num + credit_num + matchup_num_v2 + h2h_num_v3, ["lagged_role", "target_opponent"]),
        "historical_form_plus_lagged_credit_expanded_matchup_and_shrunk_h2h_v4": (form_num + credit_num + matchup_num_v2 + h2h_num_v4, ["lagged_role", "target_opponent"]),
        "historical_form_plus_lagged_credit_expanded_matchup_role_interactions_v5": (form_num + credit_num + matchup_num_v2 + role_interaction_features, ["lagged_role", "target_opponent"]),
    }
    metrics = []
    predictions = []
    fold_audit = []
    for test_season in TEST_SEASONS:
        train_all = d.loc[d["season_id"].isin(VALID_SEASONS[:VALID_SEASONS.index(test_season)])].copy()
        test_all = d.loc[d["season_id"].eq(test_season)].copy()
        train = train_all.loc[train_all["target_opponent"].notna()].copy()
        test = test_all.loc[test_all["target_opponent"].notna()].copy()
        if train.empty or test.empty:
            fold_audit.append({"test_season_id": test_season, "status": "skipped_empty_fold", "train_rows": len(train), "test_rows": len(test)})
            continue
        y_train = train["target_pdk_round_total"].to_numpy(float)
        y_test = test["target_pdk_round_total"].to_numpy(float)
        # Simple lagged baselines: they are based only on previous-round scores.
        for name, pred in (
            ("baseline_last_round", pd.to_numeric(test["lag1_pdk"], errors="coerce")),
            ("baseline_previous5_mean", pd.to_numeric(test["prev5_pdk_mean"], errors="coerce")),
            ("baseline_train_median", pd.Series(np.full(len(test), float(np.median(y_train))), index=test.index)),
        ):
            valid = pred.notna().to_numpy() & np.isfinite(pred.to_numpy(float))
            if valid.any():
                metrics.append(metric_row(y_test[valid], pred.to_numpy(float)[valid], test_season, name, int(valid.sum())))
                for ix in np.flatnonzero(valid):
                    row = test.iloc[ix]
                    predictions.append({"season_id": test_season, "season": row.get("source_season_label", test_season),
                        "round_index": int(row["round_index"]), "source_week": int(row["source_week"]),
                        "source_round": int(row["source_round"]), "player_name": row["player_name"],
                        "actual_pdk_round_total": float(y_test[ix]), "predicted_pdk_round_total": float(pred.iloc[ix]),
                        "feature_family": name, "lagged_cr": row.get("lag1_cr"), "lag1_pdk": row.get("lag1_pdk"),
                        "target_date": row.get("target_date"), "target_opponent": row.get("target_opponent"),
                        "opponent_def_allowed_pts_prev10": row.get("opp_def_allowed_pts_prev10"),
                        "opponent_def_allowed_reb_prev10": row.get("opp_def_allowed_reb_prev10"),
                        "opponent_def_allowed_ast_prev10": row.get("opp_def_allowed_ast_prev10"),
                        "opponent_def_allowed_stl_prev10": row.get("opp_def_allowed_stl_prev10"),
                        "opponent_def_allowed_blk_prev10": row.get("opp_def_allowed_blk_prev10"),
                        "opponent_def_allowed_tov_prev10": row.get("opp_def_allowed_tov_prev10"),
                        "opponent_pace_prev10": row.get("opp_pace_prev10"),
                        "opponent_possessions_allowed_prev10": row.get("opp_possessions_allowed_prev10")})
        for family, (numeric, cats) in families.items():
            model = make_model(numeric, cats)
            model.fit(train[numeric + cats], y_train)
            pred = model.predict(test[numeric + cats])
            metrics.append(metric_row(y_test, pred, test_season, family, len(test)))
            for ix, p in enumerate(pred):
                row = test.iloc[ix]
                predictions.append({"season_id": test_season, "season": row.get("source_season_label", test_season),
                    "round_index": int(row["round_index"]), "source_week": int(row["source_week"]),
                    "source_round": int(row["source_round"]), "player_name": row["player_name"],
                    "actual_pdk_round_total": float(y_test[ix]), "predicted_pdk_round_total": float(p),
                    "feature_family": family, "lagged_cr": row.get("lag1_cr"), "lag1_pdk": row.get("lag1_pdk"),
                    "target_date": row.get("target_date"), "target_opponent": row.get("target_opponent"),
                    "opponent_def_allowed_pts_prev10": row.get("opp_def_allowed_pts_prev10"),
                        "opponent_def_allowed_reb_prev10": row.get("opp_def_allowed_reb_prev10"),
                        "opponent_def_allowed_ast_prev10": row.get("opp_def_allowed_ast_prev10"),
                        "opponent_def_allowed_stl_prev10": row.get("opp_def_allowed_stl_prev10"),
                        "opponent_def_allowed_blk_prev10": row.get("opp_def_allowed_blk_prev10"),
                        "opponent_def_allowed_tov_prev10": row.get("opp_def_allowed_tov_prev10"),
                        "opponent_pace_prev10": row.get("opp_pace_prev10"),
                        "opponent_possessions_allowed_prev10": row.get("opp_possessions_allowed_prev10")})
        fold_audit.append({
            "test_season_id": test_season, "status": "evaluated", "train_rows": len(train), "test_rows": len(test),
            "train_rows_all": len(train_all), "test_rows_all": len(test_all),
            "train_seasons": sorted(train["season_id"].unique().tolist()),
            "test_rounds": int(test[["source_week", "source_round"]].drop_duplicates().shape[0]),
            "test_rows_with_target_opponent": int(test["target_opponent"].notna().sum()),
            "test_rows_with_lagged_cr": int(test["lag1_cr"].notna().sum()),
            "test_rows_with_exact_previous_round_cr": int(test["prior_round_present"].eq(1).sum()),
            "test_rows_with_lagged_pdk": int(test["lag1_pdk"].notna().sum()),
        })
    m = pd.DataFrame(metrics)
    p = pd.DataFrame(predictions)
    m.to_csv(METRICS, index=False)
    p.to_csv(PREDICTIONS, index=False)
    summary = m.groupby("feature_family").agg(n_rows=("n", "sum"), folds=("test_season_id", "nunique"),
        mean_fold_mae=("mae", "mean"), mean_fold_rmse=("rmse", "mean"), mean_fold_bias=("bias_pred_minus_actual", "mean")).reset_index()
    # Pooled out-of-fold metrics weighted by actual prediction rows; no training predictions included.
    pooled = []
    for family, g in p.groupby("feature_family"):
        err = g["predicted_pdk_round_total"].astype(float) - g["actual_pdk_round_total"].astype(float)
        pooled.append({"feature_family": family, "n": len(g), "pooled_mae": float(err.abs().mean()),
                       "pooled_rmse": float(np.sqrt(np.mean(err ** 2))), "pooled_bias": float(err.mean())})
    pooled_df = pd.DataFrame(pooled)
    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "input": str(INPUT.relative_to(ROOT)),
        "target_definition": "Official-valid Dunkest PDK total from each archived player-week/round row.",
        "feature_policy": "Every CR/form feature is shifted from the player's last observed earlier round. The current-round CR, PDK, minutes, boxscore stats, plusvalenza, and starter status are never features. Matchup uses target opponent defensive PTS/REB/AST/STL/BLK/TOV, rolling pace/possessions, and selected 5-game recent trends. Every NBA rolling feature is shifted to exclude the target game. H2H features use only prior calendar-date games against the target opponent; same-day games are excluded and historical PDK is limited to official-valid labels.",
        "matchup_reconstruction": matchup_audit,
        "player_opponent_history": h2h_audit,
        "role_interaction_features": role_interaction_features,
        "role_interaction_policy": "Interaction role comes from the player's most recent earlier observed round (lagged_role); opponent defense and pace features are shifted before the target game.",
        "round_price_semantics": "Historical weekly-round tables are not timestamped market snapshots. Lagged CR is a prior-observed-round proxy, not proof of exact pre-lock credit for every player. Rows also report whether the prior archived round had a player row.",
        "season_policy": {"valid_target_season_ids": VALID_SEASONS, "test_season_ids": TEST_SEASONS,
                          "invalid_official_target_seasons_excluded": ["1", "3"]},
        "folds": fold_audit, "rows_input": len(raw), "rows_with_lagged_cr": int(d["lag1_cr"].notna().sum()),
        "rows_with_exact_previous_round_row": int(d["prior_round_present"].eq(1).sum()),
        "feature_families": {k: {"numeric": v[0], "categorical": v[1]} for k, v in families.items()},
        "fold_metrics": m.to_dict("records"), "pooled_oof_metrics": pooled_df.to_dict("records"),
        "production_changed": False,
        "limitations": [
            "This phase validates round-level player score prediction with lagged historical credits; it does not yet claim a complete historical optimal-lineup result.",
            "Historical player-round archives list observed player rows, not a complete timestamped pre-lock player universe. Full lineup optimization needs a verified candidate universe and historically correct role/budget rules.",
            "Opponent matching is accepted only for rounds with a high-confidence date mapping. Matchup model metrics therefore apply to the subset with a reliable historical fixture link.",
            "Historical coach credit markets are not present in these player archives. Coach outcome components can be reconstructed from final NBA team scores, but exact credit-adjusted coach PDK requires historical coach CRs or a separately validated reconstruction."
        ]
    }
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Dunkest historical lagged-credit walk-forward — V5 (role-conditioned matchup interactions)", "",
        f"Generated (UTC): {audit['generated_at_utc']}", "",
        "## Method", "",
        "Each target is the official-valid player PDK total in a historical Dunkest week/round. Features are built by shifting player CR, PDK, minutes, plusvalenza and box-score summaries from earlier observed rounds only. Matchup features use high-confidence reconstructed round dates and opponent defensive trends and pace strictly before the target date. The V3 challenger adds player-vs-opponent history. V4 adds a shrinkage feature that blends prior official-valid head-to-head PDK with the player's general previous-five-round PDK mean using three pseudo-observations; same-day games are excluded. No current-round CR or statistics enter the predictor.", "",
        "The test is expanding-origin by season: train on earlier valid seasons and predict a later season. Seasons 2018/19 and 2019/20 are excluded as supervised targets because their official validity flags are false in the local archive.", "",
        "## Pooled out-of-fold metrics", "",
        pooled_df.to_string(index=False), "", "## Metrics by held-out season", "", m.to_string(index=False), "",
        "## Coverage and interpretation", ""]
    lines.append(f"- Matchup date mapping: {matchup_audit['rounds_with_confident_date']:,}/{matchup_audit['rounds_total']:,} historical rounds accepted; {matchup_audit['rows_with_target_opponent']:,} rows linked to a target opponent.")
    for f in fold_audit:
        lines.append(f"- Season ID {f['test_season_id']}: {f['test_rows']:,} matchup-ready test rows out of {f.get('test_rows_all', 0):,} total rows; lagged CR present on {f.get('test_rows_with_lagged_cr', 0):,} rows; exact prior archived-round row on {f.get('test_rows_with_exact_previous_round_cr', 0):,} rows.")
    lines += ["", "## Limitations", "",
        "This is a market- and matchup-aware player-score backtest, not yet a complete optimal-lineup backtest. The weekly-round files contain outcome rows rather than a full timestamped pre-lock market universe. A valid lineup backtest must avoid using the target-round player list as if it were known before lock.", "",
        "The local player archives also lack historical coach CR markets. NBA final team points and margins can reconstruct the coach score before the credit-difference multiplier; exact historical coach PDK needs the historical coach prices or a validated reconstruction.", "",
        "## Player-vs-opponent history coverage", "",
        f"- Historical source rows: {h2h_audit['source_rows']:,}; player-opponent history keys: {h2h_audit['player_opponent_history_keys']:,}.",
        f"- Target rows with prior head-to-head game: {h2h_audit['rows_with_prior_h2h_game']:,}; with official-valid prior PDK: {h2h_audit['rows_with_prior_official_valid_h2h_pdk']:,}.", "",
        "Production model/configuration remains unchanged.", "", "## Artifacts", "",
        f"- Metrics: `{METRICS.relative_to(ROOT)}`", f"- Predictions: `{PREDICTIONS.relative_to(ROOT)}`", f"- Audit JSON: `{AUDIT.relative_to(ROOT)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "rows_input": len(raw), "metrics": str(METRICS.relative_to(ROOT)),
        "predictions": str(PREDICTIONS.relative_to(ROOT)), "audit": str(AUDIT.relative_to(ROOT)),
        "report": str(REPORT.relative_to(ROOT)), "pooled_oof_metrics": pooled_df.to_dict("records"), "folds": fold_audit}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
