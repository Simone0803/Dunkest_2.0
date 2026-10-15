#!/usr/bin/env python3
"""Walk-forward test of individual-player expected-minutes forecasts.

Only certified 2020/21–2024/25 Dunkest target rows and historical NBA logs are
loaded. Target-game NBA minutes are labels only. No 2025/26 holdout, prospective
2026/27 prediction bundle, or realized lineup score is used.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import experiment_dunkest_minutes_rate_decomposition_v1 as base
OUT=ROOT/"reports/audit"; STAMP="dunkest_minutes_forecast_walk_forward_20261014_v1"
METRICS=OUT/f"{STAMP}_metrics.csv"; PRED=OUT/f"{STAMP}_predictions.csv"; REPORT=OUT/f"{STAMP}.md"; AUDIT=OUT/f"{STAMP}.json"


def score(y,p):
    y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
    return {"n":int(len(y)),"mae":float(mean_absolute_error(y,p)),"rmse":float(mean_squared_error(y,p)**.5),"bias_pred_minus_actual":float(e.mean()),"within_5_min":float(np.mean(np.abs(e)<=5.0))}


def main():
    for path in (METRICS,PRED,REPORT,AUDIT):
        if path.exists(): raise SystemExit(f"Refusing to overwrite existing output: {path}")
    df=pd.read_parquet(ROOT/"data/processed/dunkest_pdk_game_training_2020-26_v3.parquet")
    df["season_id"]=df.season_id.astype(str); df=df.loc[df.season_id.isin(base.SEASONS)].copy()
    df["game_date"]=pd.to_datetime(df.game_date,errors="coerce",utc=True).dt.tz_convert(None)
    labels=pd.read_parquet(ROOT/"data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet",columns=["nba_GAME_ID","nba_PLAYER_ID","nba_MIN","nba_match_status"])
    labels["nba_GAME_ID"]=labels.nba_GAME_ID.astype("string"); labels["nba_PLAYER_ID"]=pd.to_numeric(labels.nba_PLAYER_ID,errors="coerce").astype("Int64")
    labels=labels.loc[labels.nba_match_status.eq("matched_player_date_opponent")].copy()
    keys=["nba_GAME_ID","nba_PLAYER_ID"]
    duplicates=labels.loc[labels.duplicated(keys,keep=False)]
    if not duplicates.empty:
        for _,g in duplicates.groupby(keys,dropna=False):
            if g.nba_MIN.nunique(dropna=False)>1: raise SystemExit("Conflicting duplicate target-minute labels")
    labels=labels.drop_duplicates(keys,keep="first")
    df["nba_GAME_ID"]=df.nba_GAME_ID.astype("string"); df["nba_PLAYER_ID"]=pd.to_numeric(df.nba_PLAYER_ID,errors="coerce").astype("Int64")
    df=df.merge(labels[keys+["nba_MIN"]],on=keys,how="left",validate="many_to_one")
    df["target_minutes"]=pd.to_numeric(df.nba_MIN,errors="coerce")
    df=df.loc[df.target_minutes.notna() & df.game_date.notna()].copy()
    # Reuse strictly lagged features from the existing leakage-audited player model experiment.
    df=base.make_features(df)
    features=base.BASE_NUM+["pdk_trend_3v10","min_trend_3v5","min_last_vs_prev5","lag1_pdk_per_min","prev3_pdk_per_min","prev5_pdk_per_min","lag1_pts_per_min","prev3_pts_per_min","prev5_pts_per_min","lag1_reb_per_min","prev3_reb_per_min","prev5_reb_per_min","lag1_ast_per_min","prev3_ast_per_min","prev5_ast_per_min","lag1_usage_proxy","prev3_usage_proxy","prev5_usage_proxy"]+base.CAT
    df=df.replace([np.inf,-np.inf],np.nan)
    rows=[]; preds=[]; fold_audits=[]
    for fold in base.FOLDS:
        tr=df.loc[df.season_id.map(lambda s:int(s)<int(fold))].copy(); te=df.loc[df.season_id.eq(fold)].copy()
        if tr.empty or te.empty: raise SystemExit(f"Empty fold {base.SEASONS[fold]}")
        ytr=tr.target_minutes.to_numpy(float); y=te.target_minutes.to_numpy(float)
        candidates={
            "baseline_prev5":pd.to_numeric(te.prev5_nba_min_mean,errors="coerce"),
            "baseline_prev3":pd.to_numeric(te.prev3_nba_min_mean,errors="coerce"),
            "baseline_blend_3_5":0.65*pd.to_numeric(te.prev3_nba_min_mean,errors="coerce")+0.35*pd.to_numeric(te.prev5_nba_min_mean,errors="coerce"),
            "baseline_last_game":pd.to_numeric(te.lag1_nba_min,errors="coerce"),
        }
        for kind in ("et12","et20","hgb","rf12"):
            m=base.model(kind); m.fit(tr[features],ytr); candidates[f"model_{kind}"]=pd.Series(np.clip(m.predict(te[features]),0,48),index=te.index)
        for name,raw in candidates.items():
            pred=pd.to_numeric(raw,errors="coerce")
            valid=pred.notna() & np.isfinite(pred.to_numpy(float))
            if not valid.any(): continue
            actual=y[valid.to_numpy()]; forecast=pred.loc[valid].to_numpy(float)
            metric={"fold_season_id":fold,"fold_season":base.SEASONS[fold],"candidate":name,**score(actual,forecast)}
            low=te.loc[valid,"history_games_before_target"].lt(5).to_numpy()
            high_minutes=actual.ge(25) if isinstance(actual,pd.Series) else actual>=25
            metric["mae_actual_minutes_ge25"]=float(np.mean(np.abs(forecast[high_minutes]-actual[high_minutes]))) if np.any(high_minutes) else np.nan
            metric["n_actual_minutes_ge25"]=int(np.sum(high_minutes))
            metric["mae_history_lt5"]=float(np.mean(np.abs(forecast[low]-actual[low]))) if np.any(low) else np.nan
            metric["n_history_lt5"]=int(np.sum(low))
            metric["mae_zero_minutes"]=float(np.mean(np.abs(forecast[actual==0]-actual[actual==0]))) if np.any(actual==0) else np.nan
            metric["n_zero_minutes"]=int(np.sum(actual==0))
            rows.append(metric)
            use=valid.to_numpy()
            p=te.loc[valid,["season_id","game_date","gameId","dunkest_player_id","history_games_before_target"]].copy()
            p["target_minutes"]=y[use]; p["prediction_minutes"]=forecast; p["candidate"]=name
            preds.append(p)
        print(f"Completed minutes fold {base.SEASONS[fold]}: train={len(tr):,}, test={len(te):,}",flush=True)
    detail=pd.DataFrame(rows); predictions=pd.concat(preds,ignore_index=True)
    pooled=[]
    for name,g in predictions.groupby("candidate",sort=False):
        y=g.target_minutes.to_numpy(float); p=g.prediction_minutes.to_numpy(float); h=g.history_games_before_target.lt(5).to_numpy(); hi=y>=25; zero=y==0
        pooled.append({"candidate":name,**score(y,p),"mae_actual_minutes_ge25":float(np.mean(np.abs(p[hi]-y[hi]))) if hi.any() else np.nan,"n_actual_minutes_ge25":int(hi.sum()),"mae_history_lt5":float(np.mean(np.abs(p[h]-y[h]))) if h.any() else np.nan,"n_history_lt5":int(h.sum()),"mae_zero_minutes":float(np.mean(np.abs(p[zero]-y[zero]))) if zero.any() else np.nan,"n_zero_minutes":int(zero.sum())})
    pooled=pd.DataFrame(pooled).sort_values(["mae","rmse"])
    detail.to_csv(METRICS,index=False); predictions.to_csv(PRED,index=False)
    audit={"created_utc":datetime.now(timezone.utc).isoformat(),"source":"data/processed/dunkest_pdk_game_training_2020-26_v3.parquet","minutes_label_source":"data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet","seasons_loaded":base.SEASONS,"folds":{f:base.SEASONS[f] for f in base.FOLDS},"rows_with_linked_minutes":int(len(df)),"minutes_label_coverage":float(df.target_minutes.notna().mean()),"duplicate_target_minute_keys":int(len(duplicates)),"holdout_2025_26_loaded":False,"prospective_2026_27_loaded":False,"features":"Past-only PDK and NBA box-score lags/rolling summaries plus opponent identity; target-game minutes are labels only.","pooled_metrics":pooled.to_dict("records"),"production_changed":False}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    report=["# Player expected-minutes walk-forward — V1","",f"Generated UTC: {audit['created_utc']}","","## Objective","","Measure whether a learned expected-minutes forecast improves on recent-minute baselines before considering any production integration. Target-game NBA minutes are labels only; predictors are past-only. Folds are expanding-origin seasons 2022/23, 2023/24 and 2024/25. The 2025/26 holdout and frozen 2026/27 prospective bundle are excluded.","","## Data integrity","",f"- Rows with linked target minutes: {len(df):,}",f"- Target-minute label coverage after the join: {df.target_minutes.notna().mean():.3%}",f"- Conflicting duplicate target-minute keys: {int(len(duplicates))}","- Candidate models: ExtraTrees leaf 12/20, HistGradientBoosting, Random Forest; baselines use previous 1/3/5 games.","","## Pooled metrics","",pooled.to_string(index=False,float_format=lambda z:f"{z:.4f}"),"","## Fold metrics","",detail.to_string(index=False,float_format=lambda z:f"{z:.4f}"),"","## Decision","","A learned minute forecast is eligible for a production shadow component only if it improves pooled and per-season MAE against the strongest recent-minute baseline, does not materially worsen zero-minute and low-history cohorts, and has stable bias. A lower minutes MAE alone does not certify higher PDK accuracy; downstream score predictions need a separate paired player-game test before changing their blend.","","No production code/config/weights were changed by this experiment. No commit or push.",""]
    REPORT.write_text("\n".join(report),encoding="utf-8")
    print("\nPOOLED RESULTS\n"+pooled.to_string(index=False),flush=True)
    print("\nFOLD RESULTS\n"+detail.to_string(index=False),flush=True)
    print("REPORT="+str(REPORT.relative_to(ROOT)),flush=True)

if __name__=="__main__": main()
