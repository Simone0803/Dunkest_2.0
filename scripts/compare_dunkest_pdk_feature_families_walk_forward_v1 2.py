#!/usr/bin/env python3
"""Walk-forward feature-family comparison for verified official Dunkest PDK targets.

This is a standalone experiment. It never changes production models, configs, or datasets.
Selection folds: 2022/23-2024/25. 2025/26 is reported only as a secondary historical fold.
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
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
OUT=ROOT/"reports/audit"
STAMP="20261013_v1"
PRED=OUT/f"dunkest_pdk_feature_families_predictions_{STAMP}.csv"
METRICS=OUT/f"dunkest_pdk_feature_families_metrics_{STAMP}.csv"
COHORTS=OUT/f"dunkest_pdk_feature_families_cohorts_{STAMP}.csv"
AUDIT=OUT/f"dunkest_pdk_feature_families_audit_{STAMP}.json"
REPORT=OUT/f"dunkest_pdk_feature_families_{STAMP}.md"
LABELS={"5":"2020-21","7":"2021-22","9":"2022-23","13":"2023-24","19":"2024-25","25":"2025-26"}
TUNE=["9","13","19"]
HOLDOUT="25"
PDK=["history_games_before_target","lag1_pdk","lag2_pdk","lag3_pdk","lag4_pdk","lag5_pdk",
     "prev3_pdk_mean","prev5_pdk_mean","prev10_pdk_mean","prev5_pdk_std"]
NBA=["nba_history_games_before_target","rest_days_from_nba_logs"]
for a in ["nba_min","nba_pts","nba_reb","nba_ast","nba_stl","nba_blk","nba_tov","nba_fg3m","nba_fga","nba_ftm","nba_oreb","nba_dreb","nba_plus_minus"]:
    NBA += [f"lag1_{a}",f"lag2_{a}",f"lag3_{a}",f"prev3_{a}_mean",f"prev5_{a}_mean"]
OPP=["opponentTeamCode","opponentTeamPosition"]
FAMILIES={
 "pdk_history_plus_opponent": PDK+OPP,
 "nba_history_plus_opponent": NBA+OPP,
 "combined_full": PDK+NBA+OPP,
 "combined_without_opponent": PDK+NBA,
}
MIN_HISTORY= "history_games_before_target"

def make_model(features):
    numeric=[c for c in features if c not in OPP]
    categorical=[c for c in features if c in OPP]
    parts=[("numeric",Pipeline([("imputer",SimpleImputer(strategy="median",add_indicator=True)),("scale",StandardScaler())]),numeric)]
    if categorical:
        parts.append(("categorical",Pipeline([("imputer",SimpleImputer(strategy="most_frequent")),("onehot",OneHotEncoder(handle_unknown="ignore"))]),categorical))
    return Pipeline([("preprocess",ColumnTransformer(parts)),("model",ExtraTreesRegressor(
        n_estimators=240,max_depth=None,min_samples_leaf=10,max_features=0.8,n_jobs=-1,random_state=42
    ))])

def score(y,p):
    y=np.asarray(y,dtype=float); p=np.asarray(p,dtype=float); e=p-y
    return {"n":int(len(y)),"mae":float(mean_absolute_error(y,p)),
            "rmse":float(np.sqrt(mean_squared_error(y,p))),"bias_pred_minus_actual":float(e.mean()),
            "r2":float(r2_score(y,p)) if len(y)>1 else None,
            "p90_absolute_error":float(np.quantile(np.abs(e),.90))}

def main():
    outputs=[PRED,METRICS,COHORTS,AUDIT,REPORT]
    if any(p.exists() for p in outputs): raise SystemExit("Refusing to overwrite versioned outputs.")
    if not DATA.exists(): raise SystemExit(f"Missing dataset: {DATA}")
    df=pd.read_parquet(DATA).copy()
    required={"season_id","season_label","game_date","gameId","dunkest_player_id","target_pdk",MIN_HISTORY,*PDK,*NBA,*OPP}
    if not required.issubset(df.columns): raise SystemExit(f"Missing columns: {sorted(required-set(df.columns))}")
    df["season_id"]=df.season_id.astype(str)
    df["game_date"]=pd.to_datetime(df.game_date,errors="coerce")
    df["target_pdk"]=pd.to_numeric(df.target_pdk,errors="coerce")
    df[MIN_HISTORY]=pd.to_numeric(df[MIN_HISTORY],errors="coerce")
    if df[["season_id","game_date","gameId","dunkest_player_id","target_pdk"]].isna().any().any(): raise SystemExit("Missing target/key.")
    if df.duplicated(["season_id","dunkest_player_id","gameId"]).any(): raise SystemExit("Duplicate player-game keys.")
    if df[["season_id","dunkest_player_id","game_date"]].duplicated().any(): raise SystemExit("Duplicate player/date rows.")
    for name,cols in FAMILIES.items():
        missing=sorted(set(cols)-set(df.columns))
        if missing: raise SystemExit(f"{name} missing features: {missing}")
    if "prior_nba_history_game_date" in df:
        prior=pd.to_datetime(df.prior_nba_history_game_date,errors="coerce")
        if int((prior.notna() & prior.ge(df.game_date)).sum()): raise SystemExit("Current/future NBA history found.")
    # Lag integrity across every season is a hard gate.
    ordered=df.sort_values(["game_date","season_id","dunkest_player_id","gameId"],kind="stable").reset_index(drop=True)
    expected=ordered.groupby("dunkest_player_id",sort=False).target_pdk.shift(1)
    stored=pd.to_numeric(ordered.lag1_pdk,errors="coerce")
    both=expected.notna() & stored.notna()
    mismatch=int(((expected[both]-stored[both]).abs()>1e-9).sum())
    miss_mismatch=int((expected.isna()!=stored.isna()).sum())
    if mismatch or miss_mismatch: raise SystemExit(f"lag1 integrity failed: values={mismatch}, missing={miss_mismatch}")
    if df.season_id.isin(["1","3"]).any(): raise SystemExit("Invalid legacy seasons included as supervised targets.")

    metrics=[]; predictions=[]; cohort_rows=[]; fold_audit=[]
    # Candidate/feature definitions are frozen before looking at the 2025/26 results.
    folds=TUNE+[HOLDOUT]
    for test_season in folds:
        earlier=[s for s in LABELS if int(s)<int(test_season)]
        train=df[df.season_id.isin(earlier)].copy()
        test=df[df.season_id.eq(test_season)].copy()
        if train.empty or test.empty: raise SystemExit(f"Missing train/test fold for {test_season}")
        y_train=train.target_pdk.astype(float)
        y_test=test.target_pdk.astype(float).to_numpy()
        baseline=pd.to_numeric(test.prev10_pdk_mean,errors="coerce").fillna(float(y_train.median())).to_numpy()
        split="validation" if test_season in TUNE else "secondary_historical_2025_26"
        base_score=score(y_test,baseline)
        metrics.append({"split":split,"test_season":LABELS[test_season],"feature_family":"baseline_prev10_mean","n_features":1,
                        "train_rows":len(train),"test_rows":len(test),**base_score})
        base_pred=pd.DataFrame({"split":split,"test_season":LABELS[test_season],"season_id":test.season_id.to_numpy(),
          "game_date":test.game_date.dt.strftime("%Y-%m-%d").to_numpy(),"gameId":test.gameId.astype(str).to_numpy(),
          "dunkest_player_id":test.dunkest_player_id.astype(str).to_numpy(),"target_pdk":y_test,
          "history_games_before_target":test[MIN_HISTORY].to_numpy(),"feature_family":"baseline_prev10_mean","prediction":baseline})
        predictions.append(base_pred)
        fold_best=None
        for family,features in FAMILIES.items():
            model=make_model(features)
            model.fit(train[features],y_train)
            pred=model.predict(test[features])
            row={"split":split,"test_season":LABELS[test_season],"feature_family":family,"n_features":len(features),
                 "train_rows":len(train),"test_rows":len(test),**score(y_test,pred)}
            metrics.append(row)
            part=pd.DataFrame({"split":split,"test_season":LABELS[test_season],"season_id":test.season_id.to_numpy(),
              "game_date":test.game_date.dt.strftime("%Y-%m-%d").to_numpy(),"gameId":test.gameId.astype(str).to_numpy(),
              "dunkest_player_id":test.dunkest_player_id.astype(str).to_numpy(),"target_pdk":y_test,
              "history_games_before_target":test[MIN_HISTORY].to_numpy(),"feature_family":family,"prediction":pred})
            predictions.append(part)
            if split=="validation" and (fold_best is None or row["mae"]<fold_best["mae"]): fold_best=row
            # Cohort metrics, based only on history available before this game's target.
            h=test[MIN_HISTORY]
            masks={
              "new_or_no_prior_pdk_history":h.fillna(0).le(0),
              "low_history_1_to_3_games":h.between(1,3),
              "limited_history_4_to_10_games":h.between(4,10),
              "established_history_over_10_games":h.gt(10),
            }
            for cohort,mask in masks.items():
                ix=np.asarray(mask.fillna(False),dtype=bool)
                if ix.sum():
                    cohort_rows.append({"split":split,"test_season":LABELS[test_season],"feature_family":family,
                      "cohort":cohort,**score(y_test[ix],pred[ix])})
        # baseline cohort metrics for direct reference
        h=test[MIN_HISTORY]
        for cohort,mask in {
          "new_or_no_prior_pdk_history":h.fillna(0).le(0),
          "low_history_1_to_3_games":h.between(1,3),
          "limited_history_4_to_10_games":h.between(4,10),
          "established_history_over_10_games":h.gt(10),
        }.items():
            ix=np.asarray(mask.fillna(False),dtype=bool)
            if ix.sum(): cohort_rows.append({"split":split,"test_season":LABELS[test_season],"feature_family":"baseline_prev10_mean","cohort":cohort,**score(y_test[ix],baseline[ix])})
        fold_audit.append({"test_season":LABELS[test_season],"split":split,"train_seasons":[LABELS[s] for s in earlier],
          "train_rows":len(train),"test_rows":len(test),"best_validation_family":fold_best["feature_family"] if fold_best else None,
          "best_validation_mae":fold_best["mae"] if fold_best else None})
        print(f"Completed {LABELS[test_season]}: train={len(train):,} test={len(test):,}; best validation candidate={fold_best['feature_family'] if fold_best else 'not selected'}",flush=True)
    met=pd.DataFrame(metrics); pred_df=pd.concat(predictions,ignore_index=True); coh=pd.DataFrame(cohort_rows)
    # Selection only across validation seasons, row-weighted by number of held-out observations.
    validation=met[(met.split=="validation") & (met.feature_family!="baseline_prev10_mean")]
    summary=validation.groupby("feature_family").apply(lambda g:pd.Series({
      "weighted_mae":np.average(g.mae,weights=g.n),
      "weighted_rmse":np.sqrt(np.average(np.square(g.rmse),weights=g.n)),
      "weighted_bias":np.average(g.bias_pred_minus_actual,weights=g.n),
      "validation_rows":int(g.n.sum()),"folds":int(g.test_season.nunique())}),include_groups=False).reset_index()
    summary=summary.sort_values(["weighted_mae","weighted_rmse"]).reset_index(drop=True)
    # Output files are new, unique versioned experiment artifacts.
    met.to_csv(METRICS,index=False); pred_df.to_csv(PRED,index=False); coh.to_csv(COHORTS,index=False)
    audit={"created_utc":datetime.now(timezone.utc).isoformat(),"dataset":str(DATA.relative_to(ROOT)),
      "target":"target_pdk: verified official PDK labels with gameValidForDunkest=True and verified NBA match",
      "validation_seasons":[LABELS[s] for s in TUNE],"secondary_historical_fold":LABELS[HOLDOUT],
      "selection_rule":"Select feature family using row-weighted MAE over 2022/23, 2023/24, 2024/25; weighted RMSE is tie-breaker. 2025/26 excluded from selection.",
      "chosen_family":str(summary.iloc[0].feature_family),"validation_summary":summary.to_dict(orient="records"),
      "fold_audit":fold_audit,"feature_families":FAMILIES,"pdk_lag_mismatches":mismatch,
      "pdk_lag_missingness_mismatches":miss_mismatch,"current_or_future_nba_history_rows":0,
      "duplicate_player_game_keys":0,"duplicate_player_dates":0,
      "cohort_definition":"History cohort is based on count of previous valid Dunkest PDK games, not a verified NBA draft-year rookie flag. This is a low-history robustness diagnostic, not a definitive rookie cohort.",
      "limitations":[
       "The 2025/26 fold has been inspected by earlier project experiments; it is a secondary historical comparison, not a globally untouched holdout.",
       "Player-game metrics do not validate full lineup scores, coach points, credit budget, availability or transfer malus.",
       "The training target and PDK history lags are official-valid PDK observations in this dataset. This experiment compares feature families, not the historical proxy-trained target mode.",
       "No production code, model artifact, configuration, dataset, or frozen run was changed."
      ],
      "outputs":{k:str(v.relative_to(ROOT)) for k,v in {"predictions":PRED,"metrics":METRICS,"cohorts":COHORTS,"report":REPORT,"audit":AUDIT}.items()}}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# Dunkest PDK feature-family comparison — 2026-10-13","",f"Generated UTC: {audit['created_utc']}","","## Protocol",
      "","- Expanding-origin training: all earlier eligible seasons only.",
      "- Feature selection uses 2022/23, 2023/24 and 2024/25 only.",
      "- 2025/26 is shown as a secondary historical fold, not used for selection; it is not a globally untouched holdout.",
      "- Target labels are verified official PDK rows; 2018/19 and 2019/20 remain feature-history-only seasons.",
      "- All candidates use the same Extra Trees estimator settings; only feature families change.",
      "- Baseline: mean PDK over the previous 10 valid games, falling back to training-target median.",
      "- No production model or configuration was changed.","",
      "## Validation summary","",
      summary.to_string(index=False),"",
      f"Selected family by validation MAE: **{audit['chosen_family']}**.","",
      "## Per-fold metrics","",met.to_string(index=False),"",
      "## Low-history cohort comparison","",
      "Cohorts use prior valid Dunkest PDK game count. They approximate cold-start difficulty but are not the same as an official NBA rookie label.","",
      coh[coh.split.eq("validation")].groupby(["feature_family","cohort"],as_index=False).apply(
        lambda g: pd.Series({"n":int(g.n.sum()),"weighted_mae":np.average(g.mae,weights=g.n),
         "weighted_rmse":np.sqrt(np.average(np.square(g.rmse),weights=g.n)),
         "weighted_bias":np.average(g.bias_pred_minus_actual,weights=g.n)}),include_groups=False
      ).reset_index(drop=True).to_string(index=False),"",
      "## Interpretation guardrails","",
      "- Feature-family selection is based only on 2022/23–2024/25 chronological folds.",
      "- The 2025/26 rows are reported after the candidate definitions were fixed, but previous project work has already inspected that season.",
      "- A lower player-level MAE does not establish a better optimized fantasy lineup. That requires authentic frozen pre-match player/coach market, credits, injury/availability and fixture-linked actual scores.",
      "- The low-history cohort is not an NBA rookie label. The separate rookie audit remains the evidence for draft-year-matched rookies.",
      "- Proxy-trained vs official-target comparisons already exist in proxy_vs_official_target_comparison_2025-26_v2.md; they are mixed and do not justify changing production target mode by themselves.","",
      "## Artifacts",""]+[f"- {k}: {v.relative_to(ROOT)}" for k,v in {"Predictions":PRED,"Metrics":METRICS,"Cohorts":COHORTS,"Audit JSON":AUDIT}.items()]
    REPORT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\nVALIDATION SUMMARY\n",summary.to_string(index=False))
    print("\nSECONDARY 2025/26 COMPARISON\n",met[met.split.eq("secondary_historical_2025_26")].sort_values("mae").to_string(index=False))
    print("\nCOHORT SUMMARY\n",coh[coh.split.eq("validation")].groupby(["feature_family","cohort"],as_index=False).agg(n=("n","sum"),mae=("mae","mean")).to_string(index=False))
    print("\nREPORT",REPORT); print("METRICS",METRICS); print("COHORTS",COHORTS); print("AUDIT",AUDIT)
if __name__=="__main__": main()
