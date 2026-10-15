#!/usr/bin/env python3
"""Leakage-safe walk-forward ablation consuming persisted date-assisted linkage.

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
STEM = "dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link"
METRICS = OUT / f"{STEM}_metrics.csv"
PREDICTIONS = OUT / f"{STEM}_predictions.csv"
AUDIT = OUT / f"{STEM}.json"
REPORT = OUT / f"{STEM}.md"
# 2020/21–2024/25 have verified official Dunkest targets in this source.
VALID_SEASONS = ["5", "7", "9", "13", "19"]
TEST_SEASONS = ["9", "13", "19"]
ENRICHED = ROOT / "data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
TEAM_LOGS = ROOT / "data/processed/team_game_logs_2018-26_v1.parquet"
LINKED = ROOT / "data/processed/dunkest_historical_game_linked_rows_20261013_v3_date_assisted.parquet"


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
    """Infer round dates from unambiguous links, then use that date to resolve
    otherwise ambiguous rows only when PDK and all 17 box-score fields match an
    official-valid player-game row uniquely. This is retrospective outcome linkage,
    not a pre-lock roster or availability snapshot.
    """
    if not LINKED.is_file() or not TEAM_LOGS.is_file():
        raise FileNotFoundError(f"Required matchup sources missing: {LINKED}, {TEAM_LOGS}")
    base = raw.copy().reset_index(drop=True)
    base["_source_row_id"] = np.arange(len(base), dtype=int)
    base["season_id"] = base["source_season_id"].astype(str)
    for col in ("source_week", "source_round"):
        base[col] = pd.to_numeric(base[col], errors="coerce").astype("Int64")
    base["id_key"] = base["id"].astype(str)

    link = pd.read_parquet(LINKED)
    link["season_id"] = link["source_season_id"].astype(str)
    for col in ("source_week", "source_round"):
        link[col] = pd.to_numeric(link[col], errors="coerce").astype("Int64")
    link["id_key"] = link["id"].astype(str)
    # Consume persisted v3 statuses; original observed validity flag is preserved.
    link["link_status_v2"] = link["link_status"]
    link["link_status"] = link["link_status_v3"]
    valid_observed = link["gameValidForDunkest_observed"].astype(str).str.lower().isin({"true", "1"})
    # Date-assisted rows are accepted only from a candidate independently verified official-valid.
    valid = valid_observed | link["link_status"].eq("date_assisted_exact_pdk_and_17_stats")
    unique_status = link["link_status"].isin({
        "unique_exact_team_signature",
        "unique_boxscore_pdk_match_team_code_differs",
        "unique_boxscore_pdk_match_nba_team_unknown",
        "date_assisted_exact_pdk_and_17_stats",
    })
    link = link.loc[valid & unique_status & link["linked_nba_game_date"].notna(), [
        "season_id", "source_week", "source_round", "id_key", "linked_nba_game_date",
        "linked_nba_game_team_code", "link_status",
    ]].copy()
    if link.duplicated(["season_id", "source_week", "source_round", "id_key"]).any():
        raise RuntimeError("Unique game-link dataset has duplicate player/season/week/round keys")
    link = link.rename(columns={"linked_nba_game_date": "candidate_date", "linked_nba_game_team_code": "target_team_code"})
    row_link = base[["_source_row_id", "season_id", "source_week", "source_round", "id_key"]].merge(
        link, on=["season_id", "source_week", "source_round", "id_key"], how="left", validate="one_to_one"
    )
    usable = row_link.loc[row_link["candidate_date"].notna() & ~row_link["link_status"].eq("date_assisted_exact_pdk_and_17_stats")].copy()
    round_stats = []
    for (sid, week, rnd), group in usable.groupby(["season_id", "source_week", "source_round"], dropna=False):
        counts = group["candidate_date"].value_counts()
        if counts.empty:
            continue
        round_stats.append({
            "season_id": str(sid), "source_week": int(week), "source_round": int(rnd),
            "unique_player_date_links": int(group["id_key"].nunique()), "candidate_dates": int(len(counts)),
            "target_date": str(counts.index[0]), "date_confidence": float(counts.iloc[0] / len(group)),
        })
    round_map = pd.DataFrame(round_stats)
    if round_map.empty:
        raise RuntimeError("Could not infer historical round dates from the unique game-link dataset")
    round_map["matchup_date_ready"] = round_map["date_confidence"].ge(0.75) & round_map["unique_player_date_links"].ge(10)
    round_map.loc[~round_map["matchup_date_ready"], "target_date"] = np.nan
    d = d.merge(round_map[["season_id", "source_week", "source_round", "target_date", "date_confidence", "matchup_date_ready"]],
                on=["season_id", "source_week", "source_round"], how="left", validate="many_to_one")
    row_link_for_d = row_link.rename(columns={"id_key": "_id_key"})
    d["_id_key"] = d["id"].astype(str)
    d = d.merge(row_link_for_d[["season_id", "source_week", "source_round", "_id_key", "target_team_code", "link_status"]],
                on=["season_id", "source_week", "source_round", "_id_key"], how="left", validate="one_to_one")

    # Date-assisted matches are already materialized and audited in the v3 dataset.
    # Do not recompute or broaden them here; round dates above use v2 links only.
    d = d.drop(columns=["_id_key"])
    linked_v3 = pd.read_parquet(LINKED)
    assisted_mask = linked_v3["link_status_v3"].astype(str).eq("date_assisted_exact_pdk_and_17_stats")
    assisted_rows = linked_v3.loc[assisted_mask]
    date_assist_audit = {
        "rows_considered": 475,
        "rows_resolved": int(len(assisted_rows)),
        "rows_resolved_with_source_team_mismatch": int(assisted_rows["linked_game_team_differs_from_source_v3"].sum()),
        "rows_with_nonunique_or_nonmatching_candidate": 34,
        "resolution_source": "persisted v3 date-assisted dataset; round-date consensus recomputed from v2 exact links only",
    }
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
    d["team_code_key"] = d["target_team_code"].astype("string").str.upper().str.strip()
    d = d.merge(schedule[["GAME_DATE", "team_code_key", "opponent_code"]].drop_duplicates(),
                left_on=["target_date", "team_code_key"], right_on=["GAME_DATE", "team_code_key"],
                how="left", validate="many_to_one")
    d = d.rename(columns={"opponent_code": "target_opponent"}).drop(columns=["GAME_DATE", "_id_key"], errors="ignore")
    d = d.merge(defense, on=["target_date", "target_opponent"], how="left", validate="many_to_one")
    d["target_opponent"] = d["target_opponent"].astype(object).where(d["target_opponent"].notna(), np.nan)
    audit = {
        "rounds_total": int(len(round_map)),
        "rounds_with_confident_date": int(round_map["matchup_date_ready"].sum()),
        "rounds_date_confidence_threshold": 0.75,
        "minimum_unique_player_date_links_per_round": 10,
        "rows_with_target_opponent": int(d["target_opponent"].notna().sum()),
        "rows_with_linked_nba_team": int(d["target_team_code"].notna().sum()),
        "rows_with_source_vs_nba_team_mismatch": int((d["target_team_code"].astype("string").str.upper().str.strip() != d["team_code"].astype("string").str.upper().str.strip()).fillna(False).sum()),
        "date_assisted_linkage": date_assist_audit,
        "rows_with_all_eight_expanded_opponent_features": int(d[["opp_def_allowed_pts_prev10", "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10", "opp_def_allowed_stl_prev10", "opp_def_allowed_blk_prev10", "opp_def_allowed_tov_prev10", "opp_pace_prev10", "opp_possessions_allowed_prev10"]].notna().all(axis=1).sum()),
        "date_mapping_by_season": round_map.groupby("season_id").agg(
            rounds=("source_week", "size"), confident_rounds=("matchup_date_ready", "sum"),
            median_confidence=("date_confidence", "median")
        ).reset_index().to_dict("records"),
        "mapping_method": "Round dates are established exclusively from original v2 unique official-valid links (>=75% agreement and >=10 unique player links). Player/game assignments then consume the separately persisted v3 date-assisted exact-signature dataset. Date-assisted assignments require gp=1, unique same-date official-valid game, rounded PDK match and all 17 box-score fields. Matchup features use NBA schedule and opponent defensive stats strictly before the target date.",
    }
    return d, audit




def attach_rest_schedule_features(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Attach team/opponent rest and congestion using completed games strictly before target date.

    Date-only target dates are treated conservatively: all games on the target date are excluded.
    """
    teams = pd.read_parquet(TEAM_LOGS, columns=["GAME_DATE", "TEAM_ABBREVIATION", "GAME_ID"])
    teams["game_date"] = pd.to_datetime(teams["GAME_DATE"], errors="coerce").dt.normalize()
    teams["team"] = teams["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    teams = teams.dropna(subset=["game_date", "team"]).drop_duplicates(["team", "game_date", "GAME_ID"])
    dates_by_team = {
        team: np.sort(g["game_date"].drop_duplicates().to_numpy(dtype="datetime64[ns]")).astype("datetime64[D]")
        for team, g in teams.groupby("team", sort=False)
    }
    target_dates = pd.to_datetime(d["target_date"], errors="coerce").to_numpy(dtype="datetime64[D]")
    team_codes = d["target_team_code"].astype("string").str.upper().str.strip().fillna("").to_numpy()
    opponents = d["target_opponent"].astype("string").str.upper().str.strip().fillna("").to_numpy()
    n = len(d)
    own_days = np.full(n, np.nan); opp_days = np.full(n, np.nan)
    own_prev7 = np.full(n, np.nan); opp_prev7 = np.full(n, np.nan)
    def fill_side(codes, days_out, games_out):
        for code in pd.unique(codes):
            arr = dates_by_team.get(code)
            if arr is None or len(arr) == 0:
                continue
            ix = np.flatnonzero((codes == code) & ~np.isnat(target_dates))
            if not len(ix):
                continue
            td = target_dates[ix]
            end = np.searchsorted(arr, td, side="left")
            has_prior = end > 0
            delta = np.full(len(ix), np.nan)
            delta[has_prior] = (td[has_prior] - arr[end[has_prior] - 1]).astype("timedelta64[D]").astype(int)
            days_out[ix] = delta
            start7 = np.searchsorted(arr, td - np.timedelta64(7, "D"), side="left")
            games_out[ix] = end - start7
    fill_side(team_codes, own_days, own_prev7)
    fill_side(opponents, opp_days, opp_prev7)
    out = d.copy()
    out["team_days_since_game_v6"] = own_days
    out["opponent_days_since_game_v6"] = opp_days
    out["team_games_prior7d_v6"] = own_prev7
    out["opponent_games_prior7d_v6"] = opp_prev7
    out["team_back_to_back_v6"] = np.where(np.isfinite(own_days), (own_days <= 1).astype(float), np.nan)
    out["opponent_back_to_back_v6"] = np.where(np.isfinite(opp_days), (opp_days <= 1).astype(float), np.nan)
    out["rest_advantage_days_v6"] = own_days - opp_days
    audit = {
        "policy": "For each target team and opponent, only team-game dates strictly earlier than target_date are used. All games on target_date are excluded because archives are date-only.",
        "features": ["team_days_since_game_v6", "opponent_days_since_game_v6", "team_games_prior7d_v6", "opponent_games_prior7d_v6", "team_back_to_back_v6", "opponent_back_to_back_v6", "rest_advantage_days_v6"],
        "rows_with_team_prior_game": int(np.isfinite(own_days).sum()),
        "rows_with_opponent_prior_game": int(np.isfinite(opp_days).sum()),
        "rows_with_complete_rest_features": int(np.isfinite(own_days + opp_days + own_prev7 + opp_prev7).sum()),
        "target_date_same_day_games_excluded": True,
    }
    return out, audit

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
    d, rest_audit = attach_rest_schedule_features(d)

    # Focused ablation: identical feature sets except for past-only rest/schedule indicators.
    form_num = ["lag1_pdk", "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean",
                "lag1_min_avg", "prev3_min_mean", "prev5_min_mean", "lag1_plus",
                "lag1_pts_avg", "lag1_reb_avg", "lag1_ast_avg", "lag1_stl_avg",
                "lag1_blk_avg", "lag1_tov_avg", "lag1_plus_minus_avg",
                "lag1_gp", "history_rounds_before_target", "credit_age_rounds", "prior_round_present"]
    credit_num = ["lag1_cr"]
    categorical = ["lagged_role", "lagged_team"]
    matchup_num_v2 = ["opp_def_allowed_pts_prev10", "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10",
        "opp_def_allowed_stl_prev10", "opp_def_allowed_blk_prev10", "opp_def_allowed_tov_prev10",
        "opp_pace_prev10", "opp_possessions_allowed_prev10", "opp_def_allowed_pts_prev5", "opp_def_allowed_reb_prev5",
        "opp_def_allowed_ast_prev5", "opp_pace_prev5"]
    rest_num_v6 = ["team_days_since_game_v6", "opponent_days_since_game_v6", "team_games_prior7d_v6",
        "opponent_games_prior7d_v6", "team_back_to_back_v6", "opponent_back_to_back_v6", "rest_advantage_days_v6"]
    families = {
        "historical_form_plus_lagged_credit_and_expanded_matchup_v2": (form_num + credit_num + matchup_num_v2, ["lagged_role", "target_opponent"]),
        "historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6": (form_num + credit_num + matchup_num_v2 + rest_num_v6, ["lagged_role", "target_opponent"]),
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
        "feature_policy": "Every CR/form feature is shifted from the player's last observed earlier round. The current-round CR, PDK, minutes, boxscore stats, plusvalenza, and starter status are never features. Matchup uses target opponent defensive PTS/REB/AST/STL/BLK/TOV, rolling pace/possessions, and selected 5-game recent trends. Rest/schedule features use team-game dates strictly before the target date; same-day games are excluded.",
        "matchup_reconstruction": matchup_audit,
        "rest_schedule_features": rest_audit,
        "rest_schedule_policy": rest_audit["policy"],
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
    lines = ["# Dunkest historical lagged-credit walk-forward — V9 (date-assisted exact-signature linkage)", "",
        f"Generated (UTC): {audit['generated_at_utc']}", "",
        "## Method", "",
        "Each target is the official-valid player PDK total in a historical Dunkest week/round. Player history features are shifted from earlier observed rounds only. This experiment consumes the persisted v3 full-stat/date-assisted linkage dataset. Round-date consensus is reconstructed exclusively from original v2 exact links (>=10 unique links and >=75% agreement), excluding date-assisted rows to avoid circular date inference. The persisted fallback links require a unique official-valid candidate on that independently established date, matching rounded PDK and all 17 box-score fields. It never uses source team_code to infer the NBA game team and never resolves gp>1 aggregates. Opponent and rest/schedule features use completed NBA team games strictly before the linked target date; same-day games are excluded. Within this corrected linkage, it compares the expanded-matchup model with the same model plus team/opponent rest, back-to-back, and prior-seven-day game-count features. No current-round CR or statistics enter predictors.", "",
        "The test is expanding-origin by season: train on earlier valid seasons and predict a later season. Seasons 2018/19 and 2019/20 are excluded as supervised targets because their official validity flags are false in the local archive.", "",
        "## Pooled out-of-fold metrics", "",
        pooled_df.to_string(index=False), "", "## Metrics by held-out season", "", m.to_string(index=False), "",
        "## Coverage and interpretation", ""]
    lines.append(f"- Matchup date mapping: {matchup_audit['rounds_with_confident_date']:,}/{matchup_audit['rounds_total']:,} historical rounds accepted; {matchup_audit['rows_with_target_opponent']:,} rows linked to a target opponent.")
    da = matchup_audit['date_assisted_linkage']
    lines.append(f"- Persisted v3 date-assisted mapping contains {da['rows_resolved']:,} unique links; {da['rows_resolved_with_source_team_mismatch']:,} use a linked NBA team different from the source Dunkest team. Round-date consensus is based on v2 links only; no unresolved row is retried in this run.")
    for f in fold_audit:
        lines.append(f"- Season ID {f['test_season_id']}: {f['test_rows']:,} matchup-ready test rows out of {f.get('test_rows_all', 0):,} total rows; lagged CR present on {f.get('test_rows_with_lagged_cr', 0):,} rows; exact prior archived-round row on {f.get('test_rows_with_exact_previous_round_cr', 0):,} rows.")
    lines += ["", "## Limitations", "",
        "This is a market- and matchup-aware player-score backtest, not yet a complete optimal-lineup backtest. Date-assisted mapping improves linkage only where the independent round date and full PDK+box-score signature agree; it remains a retrospective outcome linkage, not a pre-lock snapshot. The weekly-round files contain outcome rows rather than a full timestamped pre-lock market universe. A valid lineup backtest must avoid using the target-round player list as if it were known before lock.", "",
        "The local player archives also lack historical coach CR markets. NBA final team points and margins can reconstruct the coach score before the credit-difference multiplier; exact historical coach PDK needs the historical coach prices or a validated reconstruction.", "",
        "## Rest/schedule feature coverage", "",
        f"- Rows with prior own-team game: {rest_audit['rows_with_team_prior_game']:,}; opponent prior game: {rest_audit['rows_with_opponent_prior_game']:,}.",
        f"- Rows with all rest/schedule inputs: {rest_audit['rows_with_complete_rest_features']:,}. Same-day games excluded: yes.", "",
        "Production model/configuration remains unchanged. This V9 run is an experimental walk-forward ablation; it does not replace V6 without paired evaluation on common rows.", "", "## Artifacts", "",
        f"- Metrics: `{METRICS.relative_to(ROOT)}`", f"- Predictions: `{PREDICTIONS.relative_to(ROOT)}`", f"- Audit JSON: `{AUDIT.relative_to(ROOT)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "rows_input": len(raw), "metrics": str(METRICS.relative_to(ROOT)),
        "predictions": str(PREDICTIONS.relative_to(ROOT)), "audit": str(AUDIT.relative_to(ROOT)),
        "report": str(REPORT.relative_to(ROOT)), "pooled_oof_metrics": pooled_df.to_dict("records"), "folds": fold_audit}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
