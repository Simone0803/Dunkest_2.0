#!/usr/bin/env python3
"""Train-only two-part tail model: P(high PDK) x conditional high/low scores.

Research-only. The conditional mixture estimates E[PDK|features] through a
classifier and separate high/low regressors. Expanding-origin seasons end in
2024/25; 2025/26 and prospective 2026/27 predictions are not loaded.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, mean_absolute_error, mean_squared_error, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import experiment_dunkest_minutes_rate_decomposition_v1 as base
OUT=ROOT/"reports/audit"; STAMP="20261013_conditional_tail_model_v2"
METRICS=OUT/f"dunkest_{STAMP}_metrics.csv"; PRED=OUT/f"dunkest_{STAMP}_predictions.csv"; REPORT=OUT/f"dunkest_{STAMP}.md"; AUDIT=OUT/f"dunkest_{STAMP}.json"
NUM=base.BASE_NUM+["pdk_trend_3v10","min_trend_3v5","min_last_vs_prev5","lag1_pdk_per_min","prev3_pdk_per_min","prev5_pdk_per_min","lag1_pts_per_min","prev3_pts_per_min","prev5_pts_per_min","lag1_reb_per_min","prev3_reb_per_min","prev5_reb_per_min","lag1_ast_per_min","prev3_ast_per_min","prev5_ast_per_min","lag1_usage_proxy","prev3_usage_proxy","prev5_usage_proxy"]
CAT=base.CAT

def prep_model(classifier=False):
    num=Pipeline([("imputer",SimpleImputer(strategy="median",add_indicator=True))])
    cat=Pipeline([("imputer",SimpleImputer(strategy="most_frequent")),("onehot",OneHotEncoder(handle_unknown="ignore",sparse_output=False))])
    pre=ColumnTransformer([("num",num,NUM),("cat",cat,CAT)],remainder="drop",sparse_threshold=0)
    if classifier:
        est=HistGradientBoostingClassifier(max_iter=160,learning_rate=.06,max_leaf_nodes=31,l2_regularization=5.0,min_samples_leaf=40,random_state=2026)
    else:
        est=HistGradientBoostingRegressor(max_iter=180,learning_rate=.06,max_leaf_nodes=31,l2_regularization=5.0,min_samples_leaf=40,random_state=2026)
    return Pipeline([("prep",pre),("model",est)])

def score(y,p):
    y=np.asarray(y,float); p=np.asarray(p,float)
    return {"n":len(y),"mae":float(mean_absolute_error(y,p)),"rmse":float(mean_squared_error(y,p)**.5),"bias_pred_minus_actual":float(np.mean(p-y))}

def main():
    for p in [METRICS,PRED,REPORT,AUDIT]:
        if p.exists(): raise SystemExit(f"Refusing to overwrite existing output: {p}")
    df=pd.read_parquet(base.TRAIN_PATH if hasattr(base,"TRAIN_PATH") else ROOT/"data/processed/dunkest_pdk_game_training_2020-25_v2.parquet")
    df["season_id"]=df.season_id.astype(str); df=df.loc[df.season_id.isin(base.SEASONS)].copy()
    df["game_date"]=pd.to_datetime(df.game_date,errors="coerce"); df["target_pdk"]=pd.to_numeric(df.target_pdk,errors="coerce")
    labels=pd.read_parquet(ROOT/"data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet",columns=["nba_GAME_ID","nba_PLAYER_ID","nba_MIN","nba_match_status"])
    labels["nba_GAME_ID"]=labels.nba_GAME_ID.astype("string"); labels["nba_PLAYER_ID"]=pd.to_numeric(labels.nba_PLAYER_ID,errors="coerce").astype("Int64")
    labels=labels.loc[labels.nba_match_status.eq("matched_player_date_opponent")].drop_duplicates(["nba_GAME_ID","nba_PLAYER_ID"])
    df["nba_GAME_ID"]=df.nba_GAME_ID.astype("string"); df["nba_PLAYER_ID"]=pd.to_numeric(df.nba_PLAYER_ID,errors="coerce").astype("Int64")
    df=df.merge(labels[["nba_GAME_ID","nba_PLAYER_ID","nba_MIN"]],on=["nba_GAME_ID","nba_PLAYER_ID"],how="left",validate="many_to_one")
    df=df.loc[pd.to_numeric(df.nba_MIN,errors="coerce").notna()].copy()
    df=base.make_features(df)
    pred_source=pd.read_csv(OUT/"dunkest_20261013_minutes_rate_decomposition_v1_predictions.csv")
    direct=pred_source.loc[pred_source.candidate.isin(["direct_et12","direct_hgb"])].copy()
    direct["season_id"]=direct.season_id.astype(str)
    feature_cols=NUM+CAT
    rows=[]; allpred=[]; calibration=[]
    for fold in ["9","13","19"]:
        tr=df.loc[df.season_id.map(lambda s:int(s)<int(fold))].copy(); te=df.loc[df.season_id.eq(fold)].copy()
        Xtr=tr[feature_cols]; Xte=te[feature_cols]; ytr=tr.target_pdk.to_numpy(float); y=te.target_pdk.to_numpy(float)
        for threshold in [25.0,30.0]:
            binary=(ytr>=threshold).astype(int)
            if len(np.unique(binary))<2: continue
            clf=prep_model(True)
            # Preserve the natural event prevalence so probabilities can estimate the
            # mixture expectation. Calibration is still audited before any promotion.
            clf.fit(Xtr,binary)
            prob=np.asarray(clf.predict_proba(Xte)[:,1],float).clip(0,1)
            hi=ytr>=threshold; lo=~hi
            high=prep_model(False); low=prep_model(False)
            high.fit(Xtr.loc[hi],ytr[hi]); low.fit(Xtr.loc[lo],ytr[lo])
            yh=np.asarray(high.predict(Xte),float); yl=np.asarray(low.predict(Xte),float)
            mixture=prob*yh+(1-prob)*yl
            name=f"mixture_threshold_{int(threshold)}"
            met={"fold_season_id":fold,"fold_season":base.SEASONS[fold],"candidate":name,**score(y,mixture)}
            met["mae_actual_ge25"]=float(np.mean(np.abs(y[y>=25]-mixture[y>=25]))) if np.any(y>=25) else None
            met["n_actual_ge25"]=int(np.sum(y>=25)); met["mae_actual_ge30"]=float(np.mean(np.abs(y[y>=30]-mixture[y>=30]))) if np.any(y>=30) else None; met["n_actual_ge30"]=int(np.sum(y>=30))
            rows.append(met)
            fold_dates=te.game_date.dt.strftime("%Y-%m-%d").to_numpy()
            allpred.append(pd.DataFrame({"season_id":fold,"season":base.SEASONS[fold],"game_date":fold_dates,"dunkest_player_id":te.dunkest_player_id.astype(str).to_numpy(),"gameId":te.gameId.astype(str).to_numpy(),"target_pdk":y,"prediction":mixture,"p_high":prob,"conditional_high_mean":yh,"conditional_low_mean":yl,"candidate":name,"threshold":threshold}))
            calibration.append({"fold_season_id":fold,"fold_season":base.SEASONS[fold],"threshold":threshold,"prevalence":float(np.mean(y>=threshold)),"mean_predicted_probability":float(np.mean(prob)),"brier":float(brier_score_loss((y>=threshold).astype(int),prob)),"roc_auc":float(roc_auc_score((y>=threshold).astype(int),prob)) if len(np.unique(y>=threshold))>1 else None,"observed_high_count":int(np.sum(y>=threshold))})
            print(f"{base.SEASONS[fold]} threshold>={threshold:g}: MAE={met['mae']:.5f}, RMSE={met['rmse']:.5f}, tail25={met['mae_actual_ge25']:.5f}",flush=True)
    preds=pd.concat(allpred,ignore_index=True); metrics=pd.DataFrame(rows)
    combined=[]
    for cand,g in preds.groupby("candidate"):
        combined.append({"candidate":cand,**score(g.target_pdk,g.prediction),"mae_actual_ge25":float(np.mean(np.abs(g.loc[g.target_pdk.ge(25),"target_pdk"]-g.loc[g.target_pdk.ge(25),"prediction"]))),"n_actual_ge25":int(g.target_pdk.ge(25).sum()),"mae_actual_ge30":float(np.mean(np.abs(g.loc[g.target_pdk.ge(30),"target_pdk"]-g.loc[g.target_pdk.ge(30),"prediction"]))),"n_actual_ge30":int(g.target_pdk.ge(30).sum())})
    pooled=pd.DataFrame(combined)
    direct_rows=[]
    for cand,g in direct.groupby("candidate"):
        direct_rows.append({"candidate":cand,**score(g.target_pdk,g.prediction),"mae_actual_ge25":float(np.mean(np.abs(g.loc[g.target_pdk.ge(25),"target_pdk"]-g.loc[g.target_pdk.ge(25),"prediction"]))),"n_actual_ge25":int(g.target_pdk.ge(25).sum()),"mae_actual_ge30":float(np.mean(np.abs(g.loc[g.target_pdk.ge(30),"target_pdk"]-g.loc[g.target_pdk.ge(30),"prediction"]))),"n_actual_ge30":int(g.target_pdk.ge(30).sum())})
    pooled=pd.concat([pooled,pd.DataFrame(direct_rows)],ignore_index=True).sort_values(["mae","rmse"])
    metrics.to_csv(METRICS,index=False); preds.to_csv(PRED,index=False)
    audit={"created_utc":datetime.now(timezone.utc).isoformat(),"training_source":"dunkest_pdk_game_training_2020-25_v2.parquet","target_minutes_link_source":"dunkest_nba_player_games_enriched_2018-25_v1.parquet","seasons_loaded":base.SEASONS,"validation_folds":{"9":"2022-23","13":"2023-24","19":"2024-25"},"holdout_2025_26_loaded":False,"prospective_snapshot_loaded":False,"method":"Expanding-origin high-score classifier and conditional high/low regressors; E[PDK|x] approximated as p_high*mu_high+(1-p_high)*mu_low. Classifier is unweighted; probabilities are not assumed calibrated unless diagnostics support that.","calibration":calibration,"pooled_metrics":pooled.to_dict("records"),"production_changed":False}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    report=["# Conditional high-score tail model — V2","",f"Generated UTC: {audit['created_utc']}","","## Method","","For each expanding-origin fold, fit a classifier for PDK >=25 or >=30 and two conditional regressors, then combine their means with the predicted tail probability. Current-game statistics are target labels only. The classifier is unweighted to preserve the natural event prevalence; probability calibration is explicitly audited and is a promotion gate. Only verified training data through 2024/25 is loaded.","","## Pooled model comparison","",pooled.to_string(index=False,float_format=lambda x:f"{x:.5f}"),"","## Fold metrics","",metrics.to_string(index=False,float_format=lambda x:f"{x:.5f}"),"","## Tail-probability calibration","",pd.DataFrame(calibration).to_string(index=False,float_format=lambda x:f"{x:.5f}"),"","## Decision","","Do not promote unless overall error, tail-segment error, and probability calibration jointly improve across seasons. The unweighted classifier probability is not automatically calibrated; calibration metrics are a promotion gate. No production source, model, configuration, weights, 2025/26 holdout, or frozen prospective snapshot is changed or loaded.","","## Artifacts","",f"- Metrics: `{METRICS.relative_to(ROOT)}`",f"- Predictions: `{PRED.relative_to(ROOT)}`",f"- Audit: `{AUDIT.relative_to(ROOT)}`","","No commit or push.",""]
    REPORT.write_text("\n".join(report),encoding="utf-8")
    print("\nPOOLED\n"+pooled.to_string(index=False),flush=True)
    print("\nCALIBRATION\n"+pd.DataFrame(calibration).to_string(index=False),flush=True)
    print("REPORT="+str(REPORT.relative_to(ROOT)),flush=True)

if __name__=="__main__": main()
