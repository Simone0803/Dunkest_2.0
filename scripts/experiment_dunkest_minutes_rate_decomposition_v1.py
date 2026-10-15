#!/usr/bin/env python3
"""Leakage-controlled experiment: direct PDK vs expected minutes x PDK/minute.

Uses only verified historical target seasons through 2024/25. Target-game NBA
minutes are joined from the archived Dunkest/NBA crosswalk strictly as labels;
no target-game statistics enter predictors. This is research-only and does not
modify production models, configuration, weights, or prospective snapshots.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[1]
TRAIN_PATH = ROOT / "data/processed/dunkest_pdk_game_training_2020-25_v2.parquet"
LABEL_PATH = ROOT / "data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
OUT = ROOT / "reports/audit"
STAMP = "20261013_minutes_rate_decomposition_v1"
METRICS = OUT / f"dunkest_{STAMP}_metrics.csv"
PREDICTIONS = OUT / f"dunkest_{STAMP}_predictions.csv"
REPORT = OUT / f"dunkest_{STAMP}.md"
AUDIT = OUT / f"dunkest_{STAMP}.json"
SEASONS = {"5":"2020-21", "7":"2021-22", "9":"2022-23", "13":"2023-24", "19":"2024-25"}
FOLDS = ["9", "13", "19"]

BASE_NUM = [
    "history_games_before_target", "nba_history_games_before_target", "rest_days_from_nba_logs",
    "lag1_pdk", "lag2_pdk", "lag3_pdk", "lag4_pdk", "lag5_pdk",
    "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean", "prev5_pdk_std",
]
STATS = ["nba_min","nba_pts","nba_reb","nba_ast","nba_stl","nba_blk","nba_tov","nba_fg3m","nba_fga","nba_ftm","nba_oreb","nba_dreb","nba_plus_minus"]
for stat in STATS:
    BASE_NUM += [f"lag1_{stat}", f"lag2_{stat}", f"lag3_{stat}", f"prev3_{stat}_mean", f"prev5_{stat}_mean"]
CAT = ["opponentTeamCode", "opponentTeamPosition"]


def model(kind: str) -> Pipeline:
    nums = list(BASE_NUM) + [
        "pdk_trend_3v10", "min_trend_3v5", "min_last_vs_prev5",
        "lag1_pdk_per_min", "prev3_pdk_per_min", "prev5_pdk_per_min",
        "lag1_pts_per_min", "prev3_pts_per_min", "prev5_pts_per_min",
        "lag1_reb_per_min", "prev3_reb_per_min", "prev5_reb_per_min",
        "lag1_ast_per_min", "prev3_ast_per_min", "prev5_ast_per_min",
        "lag1_usage_proxy", "prev3_usage_proxy", "prev5_usage_proxy",
    ]
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True))])
    categorical = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))])
    prep = ColumnTransformer([("num", numeric, nums), ("cat", categorical, CAT)], remainder="drop", sparse_threshold=0)
    if kind == "et12":
        estimator = ExtraTreesRegressor(n_estimators=140, min_samples_leaf=12, max_features=0.85, n_jobs=-1, random_state=2026)
    elif kind == "et20":
        estimator = ExtraTreesRegressor(n_estimators=140, min_samples_leaf=20, max_features=0.85, n_jobs=-1, random_state=2026)
    elif kind == "hgb":
        estimator = HistGradientBoostingRegressor(max_iter=180, learning_rate=0.06, max_leaf_nodes=31, l2_regularization=5.0, min_samples_leaf=40, random_state=2026)
    elif kind == "rf12":
        estimator = RandomForestRegressor(n_estimators=140, max_depth=14, min_samples_leaf=12, max_features=0.85, n_jobs=-1, random_state=2026)
    else:
        raise ValueError(kind)
    return Pipeline([("prep", prep), ("model", estimator)])


def metrics(y, pred):
    y = np.asarray(y, dtype=float); pred = np.asarray(pred, dtype=float)
    return {"n": int(len(y)), "mae": float(mean_absolute_error(y, pred)), "rmse": float(mean_squared_error(y, pred)**0.5), "bias_pred_minus_actual": float(np.mean(pred-y))}


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    for col in BASE_NUM + CAT:
        if col not in x:
            x[col] = np.nan
    x["pdk_trend_3v10"] = x["prev3_pdk_mean"] - x["prev10_pdk_mean"]
    x["min_trend_3v5"] = x["prev3_nba_min_mean"] - x["prev5_nba_min_mean"]
    x["min_last_vs_prev5"] = x["lag1_nba_min"] - x["prev5_nba_min_mean"]
    # Shrunk, past-only per-minute features. Rolling sums/means are not current-game stats.
    for stat in ["pdk", "pts", "reb", "ast"]:
        for lag in [1]:
            if stat == "pdk":
                numerator = x[f"lag{lag}_pdk"]
                denominator = x[f"lag{lag}_nba_min"]
            else:
                numerator = x[f"lag{lag}_nba_{stat}"]
                denominator = x[f"lag{lag}_nba_min"]
            x[f"lag1_{stat}_per_min"] = pd.to_numeric(numerator, errors="coerce") / pd.to_numeric(denominator, errors="coerce").where(pd.to_numeric(denominator, errors="coerce").gt(0))
        for window in [3, 5]:
            if stat == "pdk":
                numerator = x[f"prev{window}_pdk_mean"]
            else:
                numerator = x[f"prev{window}_nba_{stat}_mean"]
            denominator = x[f"prev{window}_nba_min_mean"]
            x[f"prev{window}_{stat}_per_min"] = pd.to_numeric(numerator, errors="coerce") / pd.to_numeric(denominator, errors="coerce").where(pd.to_numeric(denominator, errors="coerce").gt(0))
    # FGA + FTA + TOV is a deliberately named usage proxy, not official usage rate.
    x["lag1_usage_proxy"] = (x["lag1_nba_fga"] + x["lag1_nba_ftm"] + x["lag1_nba_tov"]) / x["lag1_nba_min"].where(x["lag1_nba_min"].gt(0))
    x["prev3_usage_proxy"] = (x["prev3_nba_fga_mean"] + x["prev3_nba_ftm_mean"] + x["prev3_nba_tov_mean"]) / x["prev3_nba_min_mean"].where(x["prev3_nba_min_mean"].gt(0))
    x["prev5_usage_proxy"] = (x["prev5_nba_fga_mean"] + x["prev5_nba_ftm_mean"] + x["prev5_nba_tov_mean"]) / x["prev5_nba_min_mean"].where(x["prev5_nba_min_mean"].gt(0))
    return x


def cluster_bootstrap_delta(y, a, b, dates, reps=1200, seed=20261013):
    """CI for MAE(b)-MAE(a), resampling whole target dates."""
    frame = pd.DataFrame({"y":y,"a":a,"b":b,"date":pd.Series(dates).astype(str)})
    frame = frame.dropna(subset=["y","a","b","date"])
    groups = [g for _,g in frame.groupby("date", sort=False)]
    if len(groups) < 10: return {"clusters":len(groups),"delta_mae_b_minus_a":float(np.mean(np.abs(frame.b-frame.y)-np.abs(frame.a-frame.y))),"ci95":[None,None]}
    rng=np.random.default_rng(seed); deltas=np.empty(reps)
    for i in range(reps):
        picks=rng.integers(0,len(groups),len(groups)); sample=pd.concat([groups[j] for j in picks],ignore_index=True)
        deltas[i]=np.mean(np.abs(sample.b-sample.y)-np.abs(sample.a-sample.y))
    return {"clusters":len(groups),"delta_mae_b_minus_a":float(np.mean(np.abs(frame.b-frame.y)-np.abs(frame.a-frame.y))),"ci95":[float(np.quantile(deltas,.025)),float(np.quantile(deltas,.975))]}


def main():
    for p in [METRICS,PREDICTIONS,REPORT,AUDIT]:
        if p.exists(): raise SystemExit(f"Refusing to overwrite existing output: {p}")
    OUT.mkdir(parents=True,exist_ok=True)
    # The input is strictly through 2024/25; no 2025/26 source is opened.
    df=pd.read_parquet(TRAIN_PATH)
    df["season_id"]=df.season_id.astype(str)
    df=df.loc[df.season_id.isin(SEASONS)].copy()
    df["game_date"]=pd.to_datetime(df.game_date,errors="coerce")
    df["target_pdk"]=pd.to_numeric(df.target_pdk,errors="coerce")
    labels=pd.read_parquet(LABEL_PATH,columns=["nba_GAME_ID","nba_PLAYER_ID","nba_MIN","nba_PTS","nba_REB","nba_AST","nba_STL","nba_BLK","nba_TOV","nba_FGA","nba_FTM","gameValidForDunkest","nba_match_status"])
    labels["nba_GAME_ID"]=labels.nba_GAME_ID.astype("string")
    labels["nba_PLAYER_ID"]=pd.to_numeric(labels.nba_PLAYER_ID,errors="coerce").astype("Int64")
    labels=labels.loc[labels.nba_match_status.eq("matched_player_date_opponent")].copy()
    # Resolve the few duplicate crosswalk keys only if all target labels agree exactly.
    key=["nba_GAME_ID","nba_PLAYER_ID"]
    stat_cols=["nba_MIN","nba_PTS","nba_REB","nba_AST","nba_STL","nba_BLK","nba_TOV","nba_FGA","nba_FTM"]
    dup=labels.loc[labels.duplicated(key,keep=False)].copy()
    duplicate_conflicts=0
    if not dup.empty:
        for _,g in dup.groupby(key,dropna=False):
            if any(g[c].nunique(dropna=False)>1 for c in stat_cols): duplicate_conflicts+=1
    if duplicate_conflicts:
        raise SystemExit(f"Crosswalk has {duplicate_conflicts} duplicate NBA game/player keys with conflicting target stats; refusing ambiguous minutes labels")
    labels=labels.drop_duplicates(key,keep="first")
    df["nba_GAME_ID"]=df.nba_GAME_ID.astype("string")
    df["nba_PLAYER_ID"]=pd.to_numeric(df.nba_PLAYER_ID,errors="coerce").astype("Int64")
    df=df.merge(labels[key+stat_cols],on=key,how="left",validate="many_to_one",suffixes=("","_label"))
    df["target_minutes"]=pd.to_numeric(df.nba_MIN,errors="coerce")
    # Identity integrity: historical PDK lags must equal prior target labels.
    ordered=df.sort_values(["dunkest_player_id","game_date","gameId"],kind="stable")
    prev=ordered.groupby("dunkest_player_id",sort=False).target_pdk.shift(1)
    lag=pd.to_numeric(ordered.lag1_pdk,errors="coerce")
    valid=prev.notna()&lag.notna(); lag_mismatch=int(((prev[valid]-lag[valid]).abs()>1e-9).sum())
    if lag_mismatch: raise SystemExit(f"Lag-1 PDK integrity failure: {lag_mismatch} mismatches")
    if df.duplicated(["season_id","dunkest_player_id","gameId"]).any(): raise SystemExit("Duplicate training target key")
    # Positive target minutes are needed for a meaningful per-minute label. Keep all
    # valid matched rows in the direct forecast; decomp metrics use the same rows.
    matched=df.target_minutes.notna() & df.target_minutes.ge(0)
    df=df.loc[matched].copy()
    df=make_features(df)
    ycol="target_pdk"
    feature_cols=BASE_NUM+["pdk_trend_3v10","min_trend_3v5","min_last_vs_prev5","lag1_pdk_per_min","prev3_pdk_per_min","prev5_pdk_per_min","lag1_pts_per_min","prev3_pts_per_min","prev5_pts_per_min","lag1_reb_per_min","prev3_reb_per_min","prev5_reb_per_min","lag1_ast_per_min","prev3_ast_per_min","prev5_ast_per_min","lag1_usage_proxy","prev3_usage_proxy","prev5_usage_proxy"]+CAT
    rows=[]; pred_rows=[]; audits=[]
    for fold in FOLDS:
        train=df.loc[df.season_id.astype(str).map(lambda s:int(s)<int(fold))].copy()
        test=df.loc[df.season_id.astype(str).eq(fold)].copy()
        if train.empty or test.empty: raise SystemExit(f"Empty fold {SEASONS[fold]}")
        Xtr=train[feature_cols]; Xte=test[feature_cols]
        ytr=train[ycol].to_numpy(float); y=test[ycol].to_numpy(float)
        # Direct forecast: two tree settings plus a robust previous-5 baseline.
        direct_preds={"baseline_prev5":pd.to_numeric(test.prev5_pdk_mean,errors="coerce").fillna(float(np.median(ytr))).to_numpy(float)}
        for kind in ["et12","hgb"]:
            m=model(kind); m.fit(Xtr,ytr); direct_preds[f"direct_{kind}"]=np.asarray(m.predict(Xte),float)
        # Component candidates use the same past-only X. Minutes target and rate target
        # are current-game labels only; no current-game stats are predictors.
        min_train=train.target_minutes.notna().to_numpy(); min_test=test.target_minutes.notna().to_numpy()
        minute_models={}; minute_preds={}
        for kind in ["et12","hgb"]:
            mm=model(kind); mm.fit(Xtr.loc[min_train],train.loc[min_train,"target_minutes"].to_numpy(float))
            minute_models[kind]=mm; minute_preds[kind]=np.clip(mm.predict(Xte),0,48)
        rate_train=train.target_minutes.gt(0).to_numpy()
        rate_target=(train.loc[rate_train,"target_pdk"].to_numpy(float)/train.loc[rate_train,"target_minutes"].to_numpy(float))
        rate_models={}; rate_preds={}
        for kind in ["et12","hgb"]:
            rm=model(kind); rm.fit(Xtr.loc[rate_train],rate_target)
            rate_models[kind]=rm; rate_preds[kind]=np.clip(rm.predict(Xte),-0.75,2.5)
        candidate_preds=dict(direct_preds)
        for mk in ["et12","hgb"]:
            for rk in ["et12","hgb"]:
                candidate_preds[f"minutes_{mk}_x_rate_{rk}"]=minute_preds[mk]*rate_preds[rk]
        # Product-of-conditional-means can be biased; include a calibrated only-on-train
        # scalar shrinkage coefficient chosen on earlier-season fitted residuals is not
        # used here, so this comparison stays simple and interpretable.
        fold_date=test.game_date.dt.strftime("%Y-%m-%d").to_numpy()
        for name,pred in candidate_preds.items():
            row={"fold_season_id":fold,"fold_season":SEASONS[fold],"candidate":name,**metrics(y,pred)}
            rows.append(row)
            frame=pd.DataFrame({"season_id":fold,"season":SEASONS[fold],"game_date":fold_date,"dunkest_player_id":test.dunkest_player_id.astype(str).to_numpy(),"gameId":test.gameId.astype(str).to_numpy(),"target_pdk":y,"target_minutes":test.target_minutes.to_numpy(float),"history_games_before_target":test.history_games_before_target.to_numpy(float),"prediction":pred,"candidate":name})
            frame["actual_ge25"]=frame.target_pdk.ge(25); frame["actual_ge30"]=frame.target_pdk.ge(30)
            pred_rows.append(frame)
            print(f"{SEASONS[fold]} {name}: MAE={row['mae']:.5f}; RMSE={row['rmse']:.5f}",flush=True)
        # Minute metrics for component model, independent of PDK.
        y_min=test.target_minutes.to_numpy(float)
        for kind,pred in minute_preds.items():
            audits.append({"fold_season_id":fold,"fold_season":SEASONS[fold],"target":"minutes","candidate":kind,**metrics(y_min,pred)})
        audits.append({"fold_season_id":fold,"fold_season":SEASONS[fold],"target":"rate_pdk_per_min","candidate":"historical_train_rate_mean","n":int(rate_train.sum()),"mae":float(mean_absolute_error(rate_target,np.repeat(np.mean(rate_target),len(rate_target)))) if len(rate_target) else None,"rmse":float(mean_squared_error(rate_target,np.repeat(np.mean(rate_target),len(rate_target)))**.5) if len(rate_target) else None,"bias_pred_minus_actual":0.0})
    detail=pd.DataFrame(rows); preds=pd.concat(pred_rows,ignore_index=True)
    summary=detail.groupby("candidate",as_index=False).apply(lambda g:pd.Series({"weighted_mae":np.average(g.mae,weights=g.n),"weighted_rmse":np.sqrt(np.average(np.square(g.rmse),weights=g.n)),"weighted_bias":np.average(g.bias_pred_minus_actual,weights=g.n),"folds":g.fold_season_id.nunique()}),include_groups=False).reset_index(drop=True).sort_values(["weighted_mae","weighted_rmse"])
    pooled=[]
    for cand,g in preds.groupby("candidate",sort=False):
        pooled.append({"candidate":cand,**metrics(g.target_pdk,g.prediction),"mae_actual_ge25":float(np.mean(np.abs(g.loc[g.actual_ge25,"target_pdk"]-g.loc[g.actual_ge25,"prediction"]))) if g.actual_ge25.any() else None,"n_actual_ge25":int(g.actual_ge25.sum()),"mae_actual_ge30":float(np.mean(np.abs(g.loc[g.actual_ge30,"target_pdk"]-g.loc[g.actual_ge30,"prediction"]))) if g.actual_ge30.any() else None,"n_actual_ge30":int(g.actual_ge30.sum()),"mae_low_history_lt5":float(np.mean(np.abs(g.loc[g.history_games_before_target.lt(5),"target_pdk"]-g.loc[g.history_games_before_target.lt(5),"prediction"]))) if g.history_games_before_target.lt(5).any() else None,"n_low_history_lt5":int(g.history_games_before_target.lt(5).sum())})
    pooled=pd.DataFrame(pooled).sort_values(["mae","rmse"])
    # Paired, target-date cluster bootstrap for best decomposition vs best direct candidate.
    best_decomp=pooled[pooled.candidate.str.startswith("minutes_")].iloc[0].candidate
    best_direct=pooled[pooled.candidate.str.startswith("direct_")].iloc[0].candidate
    boot={}
    for fold in FOLDS:
        sub=preds.loc[preds.season_id.eq(fold)]
        a=sub.loc[sub.candidate.eq(best_direct)].sort_values(["game_date","gameId","dunkest_player_id"])
        b=sub.loc[sub.candidate.eq(best_decomp)].sort_values(["game_date","gameId","dunkest_player_id"])
        if not a[["game_date","gameId","dunkest_player_id"]].reset_index(drop=True).equals(b[["game_date","gameId","dunkest_player_id"]].reset_index(drop=True)):
            raise SystemExit("Prediction pairing mismatch")
        boot[SEASONS[fold]]=cluster_bootstrap_delta(a.target_pdk.to_numpy(),a.prediction.to_numpy(),b.prediction.to_numpy(),a.game_date.to_numpy(),seed=20261013+int(fold))
    detail.to_csv(METRICS,index=False); preds.to_csv(PREDICTIONS,index=False)
    audit={"created_utc":datetime.now(timezone.utc).isoformat(),"training_dataset":str(TRAIN_PATH.relative_to(ROOT)),"target_label_source":str(LABEL_PATH.relative_to(ROOT)),"seasons_loaded":SEASONS,"validation_folds":{f:SEASONS[f] for f in FOLDS},"2025_26_loaded":False,"prospective_snapshot_loaded":False,"training_rows_after_target_minutes_link":int(len(df)),"target_minutes_nonnull_rate":float(df.target_minutes.notna().mean()),"target_minutes_zero_rate":float(df.target_minutes.eq(0).mean()),"label_join_duplicate_keys":int(len(dup)),"label_join_duplicate_conflicts":duplicate_conflicts,"lag1_pdk_mismatches":lag_mismatch,"candidates":summary.to_dict("records"),"pooled_subgroups":pooled.to_dict("records"),"best_direct":best_direct,"best_decomposition":best_decomp,"paired_date_cluster_bootstrap_delta_mae_decomposition_minus_direct":boot,"component_minute_metrics":audits,"feature_policy":"Only past-game PDK and box-score lags/rolling summaries plus opponent/home-away. Current-game minutes and box-score columns are labels only.","rookie_policy":"No fabricated zero/negative labels from absent target rows; low-history is analyzed as a subgroup, not a learned NBA appearance probability.","production_changed":False,"holdout_note":"Only 2020/21–2024/25 training source and 2020–2025 crosswalk were opened. 2025/26 holdout and frozen 2026/27 GW1 snapshot were not loaded."}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    report=["# Minutes × rate decomposition — V1","",f"Generated UTC: {audit['created_utc']}","","## Design","","Compare direct player-game Dunkest PDK forecasts with a two-stage forecast: expected minutes × expected PDK per minute. Target-game NBA minutes/statistics are labels only and never predictors. Candidate models are fitted in expanding-origin folds (2022/23, 2023/24, 2024/25), with all earlier eligible seasons used for training. The 2025/26 holdout and frozen 2026/27 GW1 prediction bundle are not loaded.","","## Data integrity","",f"- Rows after target-minute linkage: {len(df):,}",f"- Target minutes non-null: {df.target_minutes.notna().mean():.3%}",f"- Lag-1 PDK mismatches: {lag_mismatch}",f"- Duplicate crosswalk keys: {len(dup)}; conflicting duplicate labels: {duplicate_conflicts}","- Only the 2020/21–2024/25 training parquet and 2018–2025 enriched historical crosswalk were read.","","## Pooled candidate results","",pooled.to_string(index=False,float_format=lambda z:f"{z:.5f}"),"","## Fold metrics","",detail.sort_values(["candidate","fold_season_id"]).to_string(index=False,float_format=lambda z:f"{z:.5f}"),"","## Paired date-cluster bootstrap","", "Delta is decomposition MAE minus direct-model MAE; negative favors decomposition.","",json.dumps(boot,indent=2),"","## Minute component accuracy","",pd.DataFrame(audits).to_string(index=False,float_format=lambda z:f"{z:.5f}"),"","## Decision rule","","This is a research experiment, not a production change. A candidate should not be promoted if it only improves pooled player-game MAE while harming high-score or low-history segments, or if date-cluster intervals are inconclusive. Lineup-level gains still require a valid historical player pool and matched coach/credit/transfer rules; this experiment does not claim lineup improvement.","","## Artifacts","",f"- Metrics: `{METRICS.relative_to(ROOT)}`",f"- Predictions: `{PREDICTIONS.relative_to(ROOT)}`",f"- Audit JSON: `{AUDIT.relative_to(ROOT)}`","","No production source/config/model/weights or prospective snapshot was changed. No commit or push was performed.",""]
    REPORT.write_text("\n".join(report),encoding="utf-8")
    print("\nPOOLED RESULTS\n"+pooled.to_string(index=False),flush=True)
    print("\nBOOTSTRAP\n"+json.dumps(boot,indent=2),flush=True)
    print("REPORT="+str(REPORT.relative_to(ROOT)),flush=True)

if __name__=="__main__": main()
