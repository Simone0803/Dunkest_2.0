#!/usr/bin/env python3
"""Full-slate historical lineup reconstruction using prior-round CR and linked NBA team identity.

V7 fixes a critical slate-coverage bug in V3: V3 inferred target opponents only
from teams represented in the sparse historical player archive, leaving just 2-3
teams on many dates. V7 rebuilds the full NBA slate from the season/date schedule
and assigns candidates to their most recently observed linked NBA team. Prices,
roles and player features remain strictly lagged. This remains a historical proxy.
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
TEAM_LOGS = ROOT / "data/processed/team_game_logs_2018-26_v1.parquet"
COACH_PREDICTIONS = ROOT / "reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_predictions.csv"
OUT = ROOT / "reports/audit"
STEM = "dunkest_historical_lineups_gamelevel_actuals_20261014_v7"
METRICS = OUT / f"{STEM}_metrics.csv"
PROXY_METRICS = OUT / f"{STEM}_proxy_metrics.csv"
PLAYER_FORECASTS = OUT / f"{STEM}_player_forecasts.csv"
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


def build_leakage_safe_training_rows(
    feature_rows: pd.DataFrame,
    candidate_rows: pd.DataFrame,
    team_matchups: pd.DataFrame,
    allowed_seasons: list[str],
) -> pd.DataFrame:
    """Build target-round rows from strictly prior player observations.

    The target label comes from the target round, but every player predictor is
    copied from that player's latest archived row before the target round. Target
    matchup/defence context is joined by the lagged team and target-round schedule.
    """
    output = []
    targets_all = feature_rows.loc[feature_rows["season_id"].astype(str).isin(allowed_seasons)].copy()
    for (season_id, target_round), targets in targets_all.groupby(["season_id", "round_index"], sort=True):
        target_round = int(target_round)
        if target_round < 2:
            continue
        season_candidates = candidate_rows.loc[candidate_rows["season_id"].astype(str).eq(str(season_id))]
        prior = latest_prior_candidates(season_candidates, target_round)
        if prior.empty:
            continue
        prior["team"] = prior["team_code"].astype(str).str.upper().str.strip()
        match_map = team_matchups.loc[
            team_matchups["season_id"].astype(str).eq(str(season_id))
            & pd.to_numeric(team_matchups["round_index"], errors="coerce").eq(target_round),
            ["team_code_key", "target_opponent", "opp_def_allowed_pts_prev10",
             "opp_def_allowed_reb_prev10", "opp_def_allowed_ast_prev10"],
        ].drop_duplicates("team_code_key").rename(columns={"team_code_key": "team"})
        if match_map.empty:
            continue
        match_map["team"] = match_map["team"].astype(str).str.upper().str.strip()
        prior = prior.merge(match_map, on="team", how="left", validate="many_to_one")
        prior = prior.loc[prior["target_opponent"].notna()].copy()
        if prior.empty:
            continue
        labels = targets[["player_key", "target_pdk_round_total", "target_date", "source_week", "source_round"]].drop_duplicates("player_key")
        labels = labels.rename(columns={
            "target_pdk_round_total": "training_target",
            "target_date": "target_date_target",
            "source_week": "source_week_target",
            "source_round": "source_round_target",
        })
        train = prior.merge(labels, on="player_key", how="inner", validate="many_to_one")
        if train.empty:
            continue
        train["target_pdk_round_total"] = pd.to_numeric(train["training_target"], errors="coerce")
        train["target_date"] = train["target_date_target"]
        train["source_week"] = train["source_week_target"]
        train["source_round"] = train["source_round_target"]
        train["round_index"] = target_round
        train["target_round_index"] = target_round
        train = train.loc[np.isfinite(train["target_pdk_round_total"])].copy()
        if not train.empty:
            output.append(train)
    return pd.concat(output, ignore_index=True) if output else pd.DataFrame()


def score_lineup(solution, actual_player_scores: dict[str, float], actual_coach_scores: dict[str, float]) -> tuple[float, float, float]:
    player_score = 0.0
    for _, player in solution.players.iterrows():
        key = player_key(player["player_name"])
        score_raw = actual_player_scores.get(key, np.nan)
        if score_raw is None or not np.isfinite(pd.to_numeric(score_raw, errors="coerce")):
            return np.nan, np.nan, np.nan
        score = float(score_raw)
        slot = str(player.get("slot", "Bench"))
        player_score += score * player_contribution_multiplier(
            slot in {"Starter", "Captain"}, slot == "Sixth Man", slot == "Captain"
        )
    coach_team = str(solution.meta.get("selected_coach_team", ""))
    # Some optimizer versions store a display label in selected_coach_team
    # (e.g. "Proxy Coach ATL") rather than the normalized team key. Only trust
    # the metadata when it actually resolves in the realized-score map.
    if coach_team not in actual_coach_scores:
        coach_name = str(solution.coach)
        fallback_team = coach_name.rsplit(" ", 1)[-1]
        if fallback_team in actual_coach_scores:
            coach_team = fallback_team
    coach_raw = actual_coach_scores.get(coach_team, np.nan)
    coach_score = float(coach_raw) if coach_raw is not None and np.isfinite(pd.to_numeric(coach_raw, errors="coerce")) else np.nan
    return player_score, coach_score, player_score + coach_score if np.isfinite(coach_score) else np.nan


def build_full_slate_matchups(round_meta: pd.DataFrame, season_labels: dict[str, str]) -> pd.DataFrame:
    """Build all team/opponent rows for each target date from the NBA schedule.

    Opponent defensive features are rolling, strictly past-only team-game stats.
    Unlike V3, the map does not depend on which teams happened to appear in the
    sparse Dunkest weekly outcome table.
    """
    logs = pd.read_parquet(TEAM_LOGS).copy()
    logs["GAME_DATE"] = pd.to_datetime(logs["GAME_DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    logs["GAME_ID"] = logs["GAME_ID"].astype(str)
    logs["TEAM_ABBREVIATION"] = logs["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    logs["SEASON"] = logs["SEASON"].astype(str)
    for col in ("PTS", "REB", "AST"):
        logs[col] = pd.to_numeric(logs[col], errors="coerce")
    pairs=[]
    for (season, game_id), g in logs.groupby(["SEASON", "GAME_ID"], sort=False):
        g = g.drop_duplicates("TEAM_ABBREVIATION")
        if len(g) != 2:
            continue
        a,b=g.iloc[0],g.iloc[1]
        for own,opp in ((a,b),(b,a)):
            pairs.append({"season":str(season),"GAME_DATE":str(own["GAME_DATE"]),"GAME_ID":str(game_id),
                "team_code_key":str(own["TEAM_ABBREVIATION"]),"target_opponent":str(opp["TEAM_ABBREVIATION"]),
                "allowed_pts":float(opp["PTS"]),"allowed_reb":float(opp["REB"]),"allowed_ast":float(opp["AST"])})
    schedule=pd.DataFrame(pairs).dropna(subset=["GAME_DATE","team_code_key","target_opponent"])
    schedule=schedule.sort_values(["season","team_code_key","GAME_DATE","GAME_ID"],kind="stable")
    defense=schedule[["season","GAME_DATE","GAME_ID","team_code_key","allowed_pts","allowed_reb","allowed_ast"]].copy()
    for source,dest in (("allowed_pts","opp_def_allowed_pts_prev10"),("allowed_reb","opp_def_allowed_reb_prev10"),("allowed_ast","opp_def_allowed_ast_prev10")):
        defense[dest]=defense.groupby(["season","team_code_key"])[source].transform(lambda x:x.shift(1).rolling(10,min_periods=3).mean())
    defense=defense.rename(columns={"team_code_key":"target_opponent","GAME_DATE":"target_date"})
    outputs=[]
    for _,meta in round_meta.drop_duplicates(["season_id","round_index"]).iterrows():
        sid=str(meta["season_id"]); season=season_labels.get(sid); date=pd.to_datetime(meta["target_date"],errors="coerce").strftime("%Y-%m-%d")
        slate=schedule.loc[schedule["season"].eq(season)&schedule["GAME_DATE"].eq(date),["team_code_key","target_opponent"]].drop_duplicates()
        if slate.empty: continue
        slate=slate.copy(); slate["season_id"]=sid; slate["round_index"]=int(meta["round_index"]); slate["target_date"]=date
        slate=slate.merge(defense.loc[defense["season"].eq(season)&defense["target_date"].eq(date),["target_date","target_opponent","opp_def_allowed_pts_prev10","opp_def_allowed_reb_prev10","opp_def_allowed_ast_prev10"]],on=["target_date","target_opponent"],how="left",validate="many_to_one")
        outputs.append(slate)
    if not outputs: return pd.DataFrame(columns=["season_id","round_index","team_code_key","target_opponent","opp_def_allowed_pts_prev10","opp_def_allowed_reb_prev10","opp_def_allowed_ast_prev10"])
    return pd.concat(outputs,ignore_index=True)



def history_bin(values: pd.Series) -> pd.Series:
    n = pd.to_numeric(values, errors="coerce").fillna(0)
    return pd.Series(np.select([n <= 5, n <= 10], ["low_history_0_5", "mid_history_6_10"], default="established_11_plus"), index=values.index)


def build_zero_inclusive_training_rows(candidate_rows: pd.DataFrame, candidate_rows_for_pool: pd.DataFrame,
                                       full_slate_matchups: pd.DataFrame, round_meta: pd.DataFrame,
                                       allowed_seasons: list[str]) -> pd.DataFrame:
    """Build lagged player-round training rows; absent target rows are a labeled zero proxy.

    This explicitly models the missing-row/zero-score scenario. It is not treated as
    observed truth: it is a separate candidate-universe proxy whose assumptions are
    recorded in the audit report.
    """
    outputs=[]
    outcomes=candidate_rows[["season_id","round_index","player_key","target_pdk_round_total"]].copy()
    outcomes["target_pdk_round_total"]=pd.to_numeric(outcomes["target_pdk_round_total"],errors="coerce")
    outcomes=outcomes.dropna(subset=["target_pdk_round_total"]).drop_duplicates(["season_id","round_index","player_key"],keep="last")
    metas=round_meta.drop_duplicates(["season_id","round_index"])
    for sid in allowed_seasons:
        season_pool=candidate_rows_for_pool.loc[candidate_rows_for_pool["season_id"].astype(str).eq(str(sid))]
        season_meta=metas.loc[metas["season_id"].astype(str).eq(str(sid))].sort_values("round_index")
        if season_pool.empty: continue
        for _,meta in season_meta.iterrows():
            target_round=int(meta["round_index"])
            if target_round < 2: continue
            prior=latest_prior_candidates(season_pool,target_round)
            if prior.empty: continue
            prior["team"] = prior["team_code"].astype(str).str.upper().str.strip()
            match_map=full_slate_matchups.loc[
                full_slate_matchups["season_id"].astype(str).eq(str(sid))
                & pd.to_numeric(full_slate_matchups["round_index"],errors="coerce").eq(target_round),
                ["team_code_key","target_opponent","opp_def_allowed_pts_prev10","opp_def_allowed_reb_prev10","opp_def_allowed_ast_prev10"]
            ].drop_duplicates("team_code_key").rename(columns={"team_code_key":"team"})
            if match_map.empty: continue
            match_map["team"]=match_map["team"].astype(str).str.upper().str.strip()
            prior=prior.merge(match_map,on="team",how="inner",validate="many_to_one")
            if prior.empty: continue
            labels=outcomes.loc[outcomes["season_id"].astype(str).eq(str(sid)) & outcomes["round_index"].eq(target_round),["player_key","target_pdk_round_total"]].rename(columns={"target_pdk_round_total":"target_label_proxy"})
            prior=prior.merge(labels,on="player_key",how="left",validate="many_to_one")
            prior["target_pdk_round_total"]=pd.to_numeric(prior["target_label_proxy"],errors="coerce").fillna(0.0)
            prior=prior.drop(columns=["target_label_proxy"])
            prior["target_date"]=meta.get("target_date")
            prior["source_week"]=meta.get("source_week")
            prior["source_round"]=meta.get("source_round")
            prior["round_index"]=target_round
            prior["target_round_index"]=target_round
            prior["outcome_observed_in_round_archive"]=prior["player_key"].isin(set(labels["player_key"]))
            outputs.append(prior)
    return pd.concat(outputs,ignore_index=True) if outputs else pd.DataFrame()


def build_oos_calibration_residuals(training_rows: pd.DataFrame, train_seasons: list[str],
                                    numeric: list[str], categorical: list[str]) -> pd.DataFrame:
    """Generate expanding-season OOS residuals only; never in-sample residuals."""
    records=[]
    for cal_season in train_seasons:
        earlier=[sid for sid in VALID_SEASONS if VALID_SEASONS.index(sid)<VALID_SEASONS.index(cal_season)]
        if not earlier: continue
        fit=training_rows.loc[training_rows["season_id"].astype(str).isin(earlier)].copy()
        val=training_rows.loc[training_rows["season_id"].astype(str).eq(str(cal_season))].copy()
        if fit.empty or val.empty: continue
        model=make_model(numeric,categorical)
        model.fit(fit[numeric+categorical],pd.to_numeric(fit["target_pdk_round_total"],errors="coerce").to_numpy(float))
        val["raw_model_pred"]=model.predict(val[numeric+categorical])
        val["raw_baseline_pred"]=pd.to_numeric(val["prev5_pdk_mean"],errors="coerce")
        val["actual_proxy"]=pd.to_numeric(val["target_pdk_round_total"],errors="coerce")
        val["role_group"]=val["lagged_role"].astype(str).fillna("unknown")
        val["history_group"]=history_bin(val["history_rounds_before_target"])
        val["model_residual"]=val["actual_proxy"]-val["raw_model_pred"]
        val["baseline_residual"]=val["actual_proxy"]-val["raw_baseline_pred"]
        records.append(val[["season_id","round_index","role_group","history_group","model_residual","baseline_residual"]])
    return pd.concat(records,ignore_index=True) if records else pd.DataFrame(columns=["season_id","round_index","role_group","history_group","model_residual","baseline_residual"])


def apply_groupwise_calibration(frame: pd.DataFrame, pred_col: str, residuals: pd.DataFrame,
                                residual_col: str, output_col: str, shrinkage: float = 20.0) -> pd.Series:
    """Past-only role/history residual correction, shrunk to the global OOS bias."""
    if residuals.empty:
        return pd.to_numeric(frame[pred_col],errors="coerce")
    r=residuals.loc[pd.to_numeric(residuals[residual_col],errors="coerce").notna()].copy()
    if r.empty: return pd.to_numeric(frame[pred_col],errors="coerce")
    global_bias=float(pd.to_numeric(r[residual_col],errors="coerce").mean())
    stats=r.groupby(["role_group","history_group"])[residual_col].agg(["mean","count"])
    role=frame["lagged_role"].astype(str).fillna("unknown")
    hist=history_bin(frame["history_rounds_before_target"])
    corrections=[]
    for rr,hh in zip(role,hist):
        if (rr,hh) not in stats.index:
            corrections.append(global_bias)
        else:
            group_mean=float(stats.loc[(rr,hh),"mean"]); n=float(stats.loc[(rr,hh),"count"])
            corrections.append((n/(n+shrinkage))*group_mean+(shrinkage/(n+shrinkage))*global_bias)
    return pd.to_numeric(frame[pred_col],errors="coerce").to_numpy(float)+np.asarray(corrections,dtype=float)

def main() -> int:
    for path in (METRICS, PROXY_METRICS, PLAYER_FORECASTS, ROUNDS, LINEUPS, AUDIT, REPORT):
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
    season_labels = raw.groupby("source_season_id")["source_season_label"].agg(lambda x: str(x.dropna().iloc[0])).to_dict()
    full_slate_matchups = build_full_slate_matchups(round_meta, {str(k): str(v) for k,v in season_labels.items()})

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
    candidate_rows_for_pool = candidate_rows.copy()
    # A player's source Dunkest team can be stale or differ from the NBA team that
    # generated the linked boxscore. For candidate eligibility, carry forward the
    # latest pre-target linked NBA team; fall back to source team only if unlinked.
    team_link = linked[["season_id", "week_num", "round_num", "player_id_num", "linked_nba_game_team_code"]].copy()
    team_link = team_link.rename(columns={"week_num":"source_week", "round_num":"source_round", "player_id_num":"player_id_num_pool", "linked_nba_game_team_code":"linked_team_for_pool"})
    team_link["source_week"] = pd.to_numeric(team_link["source_week"], errors="coerce")
    team_link["source_round"] = pd.to_numeric(team_link["source_round"], errors="coerce")
    candidate_rows_for_pool["player_id_num_pool"] = pd.to_numeric(candidate_rows_for_pool["id"], errors="coerce")
    candidate_rows_for_pool = candidate_rows_for_pool.merge(team_link.drop_duplicates(["season_id","source_week","source_round","player_id_num_pool"]), on=["season_id","source_week","source_round","player_id_num_pool"], how="left", validate="many_to_one")
    candidate_rows_for_pool["team_code"] = candidate_rows_for_pool["linked_team_for_pool"].where(candidate_rows_for_pool["linked_team_for_pool"].notna(), candidate_rows_for_pool["team_code"])
    # Critical leakage guard: for every historical target row, train on the latest
    # candidate observation strictly before that row, with matchup context joined
    # from the target-round schedule. Never fit on same-round PDK/minutes/box score.
    training_rows_all = build_zero_inclusive_training_rows(
        candidate_rows, candidate_rows_for_pool, full_slate_matchups, round_meta, VALID_SEASONS
    )

    metrics_rows, round_rows, lineup_rows, player_forecast_rows = [], [], [], []
    training_row_counts = {}
    for test_season in TEST_SEASONS:
        train_seasons = VALID_SEASONS[:VALID_SEASONS.index(test_season)]
        train = training_rows_all.loc[
            training_rows_all["season_id"].astype(str).isin(train_seasons)
            & training_rows_all["target_opponent"].notna()
        ].copy()
        test_rounds = round_meta.loc[round_meta["season_id"].eq(test_season)].sort_values("round_index")
        if train.empty or test_rounds.empty:
            continue
        calibration_residuals = build_oos_calibration_residuals(training_rows_all, train_seasons, numeric, categorical)
        model = make_model(numeric, categorical)
        model.fit(train[numeric + categorical], train["target_pdk_round_total"].to_numpy(float))
        train_median = float(pd.to_numeric(train["target_pdk_round_total"], errors="coerce").median())
        training_row_counts[test_season] = int(len(train))
        season_candidates = candidate_rows_for_pool.loc[candidate_rows_for_pool["season_id"].eq(test_season)].copy()
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

            # Official Dunkest weekly outcome table is the authoritative realized
            # player score for this fantasy round. Do not reconstruct it from one
            # NBA date: date-level links can omit otherwise valid round outcomes.
            target_outcomes = candidate_rows.loc[
                candidate_rows["season_id"].astype(str).eq(test_season)
                & pd.to_numeric(candidate_rows["round_index"], errors="coerce").eq(target_round)
            ].copy()
            target_outcomes["target_pdk_round_total"] = pd.to_numeric(target_outcomes["target_pdk_round_total"], errors="coerce")
            target_outcomes = target_outcomes.loc[np.isfinite(target_outcomes["target_pdk_round_total"])].drop_duplicates("player_key", keep="last")
            archive_actual_map = dict(zip(target_outcomes["player_key"], target_outcomes["target_pdk_round_total"].astype(float)))
            # Strictly pre-target team identity only: never use target-round outcome rows
            # to decide the candidate's team or matchup.
            candidates["team"] = candidates["team_code"].astype(str).str.upper()
            # Target matchup is attached from the known NBA schedule, not from current-round fantasy outcomes.
            match_map = full_slate_matchups.loc[full_slate_matchups["season_id"].astype(str).eq(test_season) & full_slate_matchups["round_index"].eq(target_round)].copy()
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
            candidates["actual_pdk"] = candidates["player_key"].map(archive_actual_map).astype(float)
            # Sensitivity only: candidates with no row in the round archive are set
            # to zero. Strict metrics retain NaN and exclude incomplete lineups.
            candidates["actual_pdk_proxy_zero_missing"] = candidates["actual_pdk"].fillna(0.0).astype(float)
            try:
                candidates["expected_pdk_model"] = model.predict(candidates[numeric + categorical])
            except Exception as exc:
                round_rows.append({"season_id": test_season, "round_index": target_round, "target_date": target_date, "status": "prediction_error", "detail": str(exc)})
                continue
            candidates["expected_pdk_baseline"] = pd.to_numeric(candidates["prev5_pdk_mean"], errors="coerce").fillna(train_median)
            candidates["expected_pdk_model_calibrated"] = apply_groupwise_calibration(
                candidates, "expected_pdk_model", calibration_residuals, "model_residual", "expected_pdk_model_calibrated")
            candidates["expected_pdk_baseline_calibrated"] = apply_groupwise_calibration(
                candidates, "expected_pdk_baseline", calibration_residuals, "baseline_residual", "expected_pdk_baseline_calibrated")
            candidates["actual_pdk_proxy_zero_missing"] = candidates["actual_pdk"].fillna(0.0).astype(float)
            candidates["history_group"] = history_bin(candidates["history_rounds_before_target"])
            for _, forecast_row in candidates.iterrows():
                player_forecast_rows.append({
                    "season_id": test_season, "season": {"9":"2022-23","13":"2023-24","19":"2024-25"}[test_season],
                    "round_index": target_round, "player_key": forecast_row["player_key"],
                    "role": str(forecast_row.get("lagged_role", "unknown")), "history_group": str(forecast_row["history_group"]),
                    "target_outcome_observed": bool(pd.notna(forecast_row["actual_pdk"])),
                    "actual_pdk_proxy_zero_missing": float(forecast_row["actual_pdk_proxy_zero_missing"]),
                    "expected_model_raw": float(forecast_row["expected_pdk_model"]),
                    "expected_model_calibrated": float(forecast_row["expected_pdk_model_calibrated"]),
                    "expected_baseline_raw": float(forecast_row["expected_pdk_baseline"]),
                    "expected_baseline_calibrated": float(forecast_row["expected_pdk_baseline_calibrated"]),
                })

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
            for strategy, score_col in (("model", "expected_pdk_model_calibrated"), ("previous5_baseline", "expected_pdk_baseline_calibrated")):
                players = candidates[["player_name", "team", "role", "cr", "expected_min", "p_play", "status", "expected_plusvalenza"]].copy()
                players["expected_pdk"] = pd.to_numeric(candidates[score_col], errors="coerce").fillna(train_median).to_numpy(float)
                try:
                    sol = optimize_top_k_lineups(players, coaches[["coach", "team", "coach_cr", "expected_coach_pdk"]], settings, k=1)[0]
                    player_actual, coach_actual, total_actual = score_lineup(sol, dict(zip(candidates["player_key"], candidates["actual_pdk"])), actual_coach_map)
                    player_proxy, coach_proxy, total_proxy = score_lineup(sol, dict(zip(candidates["player_key"], candidates["actual_pdk_proxy_zero_missing"])), actual_coach_map)
                    selected_results[strategy] = {"solution": sol, "player_actual": player_actual, "coach_actual": coach_actual, "team_actual": total_actual,
                                                  "player_proxy": player_proxy, "coach_proxy": coach_proxy, "team_proxy": total_proxy}
                    selected_team = str(sol.coach).rsplit(" ", 1)[-1]
                    selected_keys = sol.players["player_name"].astype(str).map(player_key)
                    strict_score_map = dict(zip(candidates["player_key"], candidates["actual_pdk"]))
                    selected_observed_count = sum(1 for key in selected_keys if key in strict_score_map and pd.notna(strict_score_map[key]))
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
                        "realized_team_score": total_actual, "realized_team_score_proxy_zero_missing": total_proxy,
                        "realized_player_score_proxy_zero_missing": player_proxy,
                        "selected_players_with_observed_pdk": int(selected_observed_count),
                        "selected_players_missing_observed_pdk": int(10-selected_observed_count),
                        "budget_used": float(sol.budget_used),
                        "captain": sol.captain, "formation": sol.module,
                        "roster_valid": bool(len(sol.players)==10 and sol.players["player_name"].map(player_key).nunique()==10),
                        "optimizer_status": str(sol.meta.get("solver", {}).get("status", "unknown")),
                    })
                except Exception as exc:
                    errors[strategy] = str(exc)
            if "model" in selected_results and "previous5_baseline" in selected_results:
                model_result = selected_results["model"]
                baseline_result = selected_results["previous5_baseline"]
                actuals_complete = bool(np.isfinite(model_result["team_actual"]) and np.isfinite(baseline_result["team_actual"]))
                proxy_complete = bool(np.isfinite(model_result["team_proxy"]) and np.isfinite(baseline_result["team_proxy"]))
                round_rows.append({
                    "season_id": test_season, "season": settings.season, "round_index": target_round,
                    "source_week": int(meta["source_week"]), "source_round": int(meta["source_round"]),
                    "target_date": target_date, "status": "evaluated" if actuals_complete else "selected_actuals_incomplete", "candidate_count": int(len(candidates)),
                    "candidate_target_row_coverage": float(candidates["player_key"].isin(archive_actual_map).mean()),
                    "target_players": int(len(target_outcomes)), "target_players_in_candidate_pool": int(target_outcomes["player_key"].isin(candidates["player_key"]).sum()),
                    "model_realized_team_score": model_result["team_actual"],
                    "baseline_realized_team_score": baseline_result["team_actual"],
                    "model_minus_baseline": model_result["team_actual"] - baseline_result["team_actual"] if actuals_complete else np.nan,
                    "proxy_status": "evaluated_proxy" if proxy_complete else "proxy_score_incomplete",
                    "model_realized_team_score_proxy_zero_missing": model_result["team_proxy"],
                    "baseline_realized_team_score_proxy_zero_missing": baseline_result["team_proxy"],
                    "proxy_model_minus_baseline": model_result["team_proxy"] - baseline_result["team_proxy"] if proxy_complete else np.nan,
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
    player_forecasts_df = pd.DataFrame(player_forecast_rows)
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
    proxy_metrics = []
    if not round_df.empty and "proxy_status" in round_df:
        proxy_eval = round_df.loc[round_df["proxy_status"].eq("evaluated_proxy")].copy()
        for sid, group in proxy_eval.groupby("season_id"):
            diff = pd.to_numeric(group["proxy_model_minus_baseline"], errors="coerce").dropna()
            if diff.empty: continue
            proxy_metrics.append({"season_id": sid, "season": group["season"].iloc[0], "rounds_evaluated_proxy": int(len(diff)),
                "mean_model_realized_team_score_proxy": float(group["model_realized_team_score_proxy_zero_missing"].mean()),
                "mean_baseline_realized_team_score_proxy": float(group["baseline_realized_team_score_proxy_zero_missing"].mean()),
                "mean_delta_model_minus_baseline_proxy": float(diff.mean()), "median_delta_model_minus_baseline_proxy": float(diff.median()),
                "model_win_rate_vs_baseline_proxy": float((diff > 0).mean()), "mean_candidate_count": float(group["candidate_count"].mean())})
        if not proxy_eval.empty:
            diff = pd.to_numeric(proxy_eval["proxy_model_minus_baseline"], errors="coerce").dropna()
            proxy_metrics.append({"season_id":"POOLED","season":"2022-23–2024-25","rounds_evaluated_proxy":int(len(diff)),
                "mean_model_realized_team_score_proxy":float(proxy_eval["model_realized_team_score_proxy_zero_missing"].mean()),
                "mean_baseline_realized_team_score_proxy":float(proxy_eval["baseline_realized_team_score_proxy_zero_missing"].mean()),
                "mean_delta_model_minus_baseline_proxy":float(diff.mean()),"median_delta_model_minus_baseline_proxy":float(diff.median()),
                "model_win_rate_vs_baseline_proxy":float((diff>0).mean()),"mean_candidate_count":float(proxy_eval["candidate_count"].mean())})
    proxy_metrics_df = pd.DataFrame(proxy_metrics)
    selection_calibration = {}
    if not lineup_df.empty:
        for strategy, group in lineup_df.groupby("strategy"):
            strict = group.loc[pd.to_numeric(group["realized_team_score"], errors="coerce").notna()].copy()
            strict_expected = pd.to_numeric(strict["expected_team_pdk"], errors="coerce").mean()
            strict_realized = pd.to_numeric(strict["realized_team_score"], errors="coerce").mean()
            proxy_expected = pd.to_numeric(group["expected_team_pdk"], errors="coerce").mean()
            proxy_realized = pd.to_numeric(group["realized_team_score_proxy_zero_missing"], errors="coerce").mean()
            selection_calibration[str(strategy)] = {
                "lineup_rows": int(len(group)),
                "strict_complete_lineup_rows": int(len(strict)),
                "mean_expected_team_pdk": float(strict_expected),
                "mean_realized_team_score": float(strict_realized),
                "mean_optimism_gap": float(strict_expected - strict_realized) if len(strict) else None,
                "proxy_mean_expected_team_pdk": float(proxy_expected),
                "proxy_mean_realized_team_score": float(proxy_realized),
                "proxy_mean_optimism_gap": float(proxy_expected - proxy_realized),
            }
    round_df.to_csv(ROUNDS, index=False)
    lineup_df.to_csv(LINEUPS, index=False)
    player_forecasts_df.to_csv(PLAYER_FORECASTS, index=False)
    metrics_df.to_csv(METRICS, index=False)
    proxy_metrics_df.to_csv(PROXY_METRICS, index=False)
    player_calibration_metrics = {}
    if not player_forecasts_df.empty:
        y=pd.to_numeric(player_forecasts_df["actual_pdk_proxy_zero_missing"],errors="coerce").to_numpy(float)
        for label,col in (("model_raw","expected_model_raw"),("model_calibrated","expected_model_calibrated"),("baseline_raw","expected_baseline_raw"),("baseline_calibrated","expected_baseline_calibrated")):
            p=pd.to_numeric(player_forecasts_df[col],errors="coerce").to_numpy(float)
            ok=np.isfinite(y)&np.isfinite(p)
            err=p[ok]-y[ok]
            player_calibration_metrics[label]={"n":int(ok.sum()),"mae":float(np.mean(np.abs(err))),"rmse":float(np.sqrt(np.mean(err**2))),"bias_pred_minus_actual":float(np.mean(err)),"observations_with_zero_proxy":int((y[ok]==0).sum())}
    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "supersedes_diagnostic_versions": {"v1": "identity-key mismatch made outcome join coverage invalid", "v2": "candidate pool restricted to immediately previous round and missed most target participants", "v4": "deterministic every-third-round sample; V5 evaluates all high-confidence rounds", "gamelevel_actuals_v1": "unioning all linked game IDs allowed cross-date exact-signature collisions; v2 uses high-confidence round-date consensus", "gamelevel_actuals_v2": "training used same-round rows whose lag1_pdk/minutes fields included the target label; v3 constructs each training row from the latest strictly pre-target candidate observation"},
        "input": str(INPUT.relative_to(ROOT)), "coach_prediction_source": str(COACH_PREDICTIONS.relative_to(ROOT)),
        "realized_player_score_source": str(INPUT.relative_to(ROOT)),
        "secondary_game_level_validation_source": str(OFFICIAL_GAMES.relative_to(ROOT)),
        "game_level_actual_reconstruction": {
            "date_link_source": str(LINKED_INPUT.relative_to(ROOT)),
            "rounds_with_confident_date_mapping": int(len(round_game_dates)),
            "date_confidence_threshold": 0.75,
            "minimum_unique_player_date_links": 10,
            "weekly_rows_reconstructed": int(reconstruction_n),
            "rows_with_absolute_difference_below_0_02": int(reconstruction_exact),
            "share_with_absolute_difference_below_0_02": float(reconstruction_exact / reconstruction_n) if reconstruction_n else None,
            "mean_absolute_difference": float(reconstruction_mae) if np.isfinite(reconstruction_mae) else None,
            "scoring_rule": "Use target_pdk_round_total from the official historical Dunkest player-week-round archive as the realized player score. The game-level linked PDK reconstruction remains a secondary audit only and is not used to assign the target outcome to a single NBA date."
        },
        "candidate_policy": "For target round r, each candidate's latest observed row strictly before r is carried forward. CR, role and team are lagged; when a player has no row in r-1, the last observed CR is carried forward. Realized score is joined after lineup selection from the official historical Dunkest player-week-round target_pdk_round_total. Missing rows remain unknown in strict metrics and are zeroed only in the separate sensitivity scenario. Players never observed in the archived season remain outside the candidate universe.",
        "target_date_mapping": matchup_audit,
        "coach_policy": "Historical coach CR is missing; use fixed coach_cr=10 for every team, and reconstruct neutral-credit base score from final NBA results. Coach budget and price-difference multipliers are therefore proxies, not historical market truth.",
        "optimizer": {"budget": 95.0, "fixed_coach_cr": 10.0, "player_budget_after_coach": 85.0,
                      "formation": "4G/4F/2C roster; 5 starters, sixth man, 4 bench; one captain; max 3 per NBA team including coach",
                      "transfer_malus": 0.0, "reason": "Historical carry-over roster and exact transfer/coach prices are not archived; this evaluates fresh independent round lineups."},
        "training_feature_policy": "For every training target round, all player predictors come from the latest archived row strictly before that target round. Target-round PDK is joined only as the label after prior features are selected; players with no target-round row are assigned 0 only in this explicit zero-inclusive proxy. Target matchup and opponent-defense context are joined from the target schedule by lagged team. No same-round PDK, minutes, box-score stats, or target-market role/CR are used as predictors.",
        "calibration_policy": "Player forecasts are calibrated using role x history-cohort residual means from expanding-season out-of-sample predictions only. Residuals are shrunk toward the global OOS residual mean with prior strength 20. The calibration fold never uses the held-out test season; 2022/23 uses OOS 2021/22 residuals, 2023/24 uses OOS 2021/22 and 2022/23 residuals, and 2024/25 uses OOS 2021/22 through 2023/24 residuals. Both the model and previous-five baseline are calibrated before optimization.",
        "calibration_residual_policy": "The calibration labels use the zero-inclusive proxy target: missing player-week-round rows are assumed to score 0. The resulting calibration is appropriate only for this explicit reconstructed-candidate scenario; observed-only rows are retained separately.",
        "training_rows_by_test_season": training_row_counts,
        "fold_policy": "Train player score model on leakage-safe rows from earlier valid seasons only; test seasons 2022-23, 2023-24 and 2024-25. No test-season labels are used to fit its model. All high-confidence mapped rounds with a prior historical candidate pool are evaluated; CBC uses a 1-second time limit and 5% relative gap.",
        "metrics_strict_observed_only": metrics_df.to_dict("records"),
        "player_forecast_rows": int(len(player_forecasts_df)),
        "player_forecast_calibration_metrics": player_calibration_metrics,
        "metrics_proxy_zero_missing": proxy_metrics_df.to_dict("records"),
        "proxy_zero_missing_policy": "Only for the proxy scenario, missing valid player-game PDK rows for previously observed candidates assigned to a scheduled team are set to zero. This is an explicit no-appearance assumption, not observed Dunkest actuals; strict observed-only results remain separate.",
        "selection_conditioned_score_calibration": selection_calibration,
        "round_status_counts": round_df["status"].value_counts(dropna=False).to_dict() if not round_df.empty else {},
        "lineup_rows": len(lineup_df), "production_changed": False,
        "limitations": [
            "This is a reconstructed candidate-universe experiment, not a complete historical Dunkest market backtest. The candidate universe contains players observed earlier in the archived season; late additions and players with no earlier archived row may be missing.",
            "The historical round archives are outcomes, not timestamped complete pre-lock roster snapshots. Candidate CR/role/team are lagged proxies, not certified market state.",
            "Game-level PDK reconstruction is a secondary audit. Strategy realized player scores come directly from the official Dunkest player-week-round outcome archive.",
            "Historical coach prices and exact credit-difference multipliers are unavailable; coach CR is fixed at 10 and neutral-credit base scores are used.",
            "No transfer malus is applied because historical carried rosters and coach prices are unavailable.",
            "The 2025/26 season is not used in this lineup comparison; tested seasons are 2022/23 through 2024/25."
        ]
    }
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Dunkest historical lineup experiment with calibrated zero-inclusive lineups — V7", "",
        f"Generated (UTC): {audit['generated_at_utc']}", "",
        "V7 fixes the V3 candidate-slate bug: target teams/opponents are rebuilt from the full NBA schedule for the target season/date, not inferred from sparse teams in the Dunkest outcome table. Candidate team assignment uses the latest strictly pre-target linked NBA team where available. Training remains past-only.", "",
        "## Method", "",
        "For each historical target round, training predictors are built from the player's latest archived row strictly before that target round. Training uses a reconstructed candidate universe: when a prior-observed player is assigned to a team on the target slate but has no player-week-round outcome row, the target is set to 0 in this explicit proxy. Both the model and previous-five baseline are calibrated with role-by-history residuals from expanding-season OOS predictions before optimization. Realized scores are joined only after selection from the official player-week-round archive; absent rows are zero only in the proxy scenario.", "",
        "## Game-level reconstruction validation", "",
        f"- Historical weekly rows compared: {audit['game_level_actual_reconstruction']['weekly_rows_reconstructed']:,}",
        f"- Rows matching weekly PDK within 0.02 points: {audit['game_level_actual_reconstruction']['rows_with_absolute_difference_below_0_02']:,} ({audit['game_level_actual_reconstruction']['share_with_absolute_difference_below_0_02']:.3%})",
        f"- Mean absolute difference: {audit['game_level_actual_reconstruction']['mean_absolute_difference']:.5f} PDK",
        "",
        "The optimizer uses the repository roster rules and a 95 CR budget, reserving 10 CR for a neutral-price coach proxy. Coach base scores are reconstructed from NBA final scores and predicted with a separate chronological model. The historical candidate pool, prices and availability remain proxies; missing player scores remain unknown and exclude a round from strict paired comparisons.", "",
        "## Strict observed-only results", "", (metrics_df.to_string(index=False) if not metrics_df.empty else "No paired rounds with complete observed actuals."), "",
        "## Player forecast calibration (zero-inclusive proxy target)", "",
        (pd.DataFrame([{"forecast":k,**v} for k,v in player_calibration_metrics.items()]).to_string(index=False) if player_calibration_metrics else "No player forecasts."), "",
        "Calibration uses only expanding-season OOS residuals. These metrics use the explicit zero-for-missing target and must be interpreted as proxy calibration, not official observed-only calibration.", "",
        "## Explicit proxy scenario: missing player PDK set to zero", "",
        "This sensitivity scenario assumes a candidate absent from the historical Dunkest player-week-round outcome archive scores 0. It is an explicit proxy for an unobserved outcome, not a certified actual. Interpret its strategy comparison as exploratory only.", "",
        (proxy_metrics_df.to_string(index=False) if not proxy_metrics_df.empty else "No proxy rounds evaluated."), "",
        "## Paired uncertainty", "",
        "- Strict observed-only estimates use only rounds with complete observed player and coach outcomes; proxy estimates are reported separately and must not be interpreted as certified results.",
        "",
        "## Selection-conditioned calibration", "",
        f"- Model: mean expected team score {selection_calibration['model']['mean_expected_team_pdk']:.2f}, realized {selection_calibration['model']['mean_realized_team_score']:.2f} (optimism gap {selection_calibration['model']['mean_optimism_gap']:.3f})",
        f"- Raw previous-five baseline strict: expected {selection_calibration['previous5_baseline']['mean_expected_team_pdk']:.2f}, realized {selection_calibration['previous5_baseline']['mean_realized_team_score']:.2f} (gap {selection_calibration['previous5_baseline']['mean_optimism_gap']:.3f})",
        f"- Model proxy: expected {selection_calibration['model']['proxy_mean_expected_team_pdk']:.2f}, realized {selection_calibration['model']['proxy_mean_realized_team_score']:.2f} (gap {selection_calibration['model']['proxy_mean_optimism_gap']:.3f})",
        f"- Baseline proxy: expected {selection_calibration['previous5_baseline']['proxy_mean_expected_team_pdk']:.2f}, realized {selection_calibration['previous5_baseline']['proxy_mean_realized_team_score']:.2f} (gap {selection_calibration['previous5_baseline']['proxy_mean_optimism_gap']:.3f})",
        "Both strategies are now calibrated with past-only role/history residuals. The comparison remains conditional on the zero-for-missing training/evaluation proxy and incomplete historical market/availability snapshots; it is not a production-superiority claim.", "",
        "## Coverage", "",
        f"- Round outcomes: {audit['round_status_counts']}",
        f"- Optimized lineup records: {len(lineup_df):,}", "",
        "## Critical caveats", "",
        "The candidate universe is reconstructed from prior-season-round observations and the latest linked NBA team available before each target round. Players never observed earlier in the season, late additions, and traded players without a prior linked appearance for the new team may be missing or misassigned. CR and role are lagged proxies, not certified pre-lock market state.", "",
        "Historical availability is not timestamped; p_play=1 is an eligibility proxy, not verified availability. A selected lineup is included in paired realized-score metrics only when all selected player scores and the coach base score are observed. Missing scores are not imputed to zero.", "",
        "Coach prices are missing. All coaches use 10 CR and the neutral-credit score multiplier; transfer malus is zero because historical carried rosters are not archived. This compares fresh independent round lineups, not a sequential roster with transfers. The full slate comes from NBA team-game logs, but this remains a reconstructed proxy rather than a certified historical Dunkest market backtest.", "",
        "Production model/configuration remains unchanged.", "",
        "## Artifacts", "", f"- Strict observed-only metrics: `{METRICS.relative_to(ROOT)}`", f"- Explicit proxy metrics: `{PROXY_METRICS.relative_to(ROOT)}`", f"- Per-round outcomes: `{ROUNDS.relative_to(ROOT)}`", f"- Selected lineups: `{LINEUPS.relative_to(ROOT)}`", f"- Audit JSON: `{AUDIT.relative_to(ROOT)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "metrics": metrics_df.to_dict("records"),
        "round_status_counts": audit["round_status_counts"], "lineup_rows": len(lineup_df),
        "outputs": [str(x.relative_to(ROOT)) for x in (METRICS, PROXY_METRICS, PLAYER_FORECASTS, ROUNDS, LINEUPS, AUDIT, REPORT)]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
