#!/usr/bin/env python3
"""Tune PDK model candidates on 2022/23-2024/25; reserve 2025/26 for final comparison."""
from datetime import datetime, timezone
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
OUT = ROOT / "data/processed"
REPORTS = ROOT / "reports/audit"
STAMP = "20261012_v1"
PRED_PATH = OUT / f"dunkest_pdk_model_tuning_walk_forward_{STAMP}.csv"
METRICS_PATH = OUT / f"dunkest_pdk_model_tuning_metrics_{STAMP}.csv"
AUDIT_PATH = OUT / f"dunkest_pdk_model_tuning_audit_{STAMP}.json"
MODEL_PATH = OUT / f"dunkest_pdk_historical_tuned_train_2020-25_test_2025-26_{STAMP}.joblib"
META_PATH = OUT / f"dunkest_pdk_historical_tuned_train_2020-25_test_2025-26_{STAMP}.json"
REPORT_PATH = REPORTS / f"dunkest_pdk_model_tuning_{STAMP}.md"
NUM = ["history_games_before_target", "nba_history_games_before_target", "rest_days_from_nba_logs",
       "lag1_pdk", "lag2_pdk", "lag3_pdk", "lag4_pdk", "lag5_pdk",
       "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean", "prev5_pdk_std"]
for a in ["nba_min","nba_pts","nba_reb","nba_ast","nba_stl","nba_blk","nba_tov","nba_fg3m",
          "nba_fga","nba_ftm","nba_oreb","nba_dreb","nba_plus_minus"]:
    NUM += [f"lag1_{a}", f"lag2_{a}", f"lag3_{a}", f"prev3_{a}_mean", f"prev5_{a}_mean"]
CAT = ["opponentTeamCode", "opponentTeamPosition"]
FEATURES = NUM + CAT
TARGET = "target_pdk"
LABELS = {"5":"2020-21","7":"2021-22","9":"2022-23","13":"2023-24","19":"2024-25","25":"2025-26"}
TUNE = ["9","13","19"]
TRAIN = ["5","7","9","13","19"]

def build(kind):
    num = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                    ("scale", StandardScaler())])
    cat = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")),
                    ("onehot", OneHotEncoder(handle_unknown="ignore"))])
    pre = ColumnTransformer([("numeric", num, NUM), ("categorical", cat, CAT)])
    if kind == "rf_baseline":
        est = RandomForestRegressor(n_estimators=160, max_depth=9, min_samples_leaf=5, max_features=.8, n_jobs=-1, random_state=42)
    elif kind == "rf_deeper":
        est = RandomForestRegressor(n_estimators=220, max_depth=12, min_samples_leaf=5, max_features=.8, n_jobs=-1, random_state=42)
    elif kind == "rf_regularized":
        est = RandomForestRegressor(n_estimators=220, max_depth=14, min_samples_leaf=10, max_features=.8, n_jobs=-1, random_state=42)
    elif kind == "extra_trees_regularized":
        est = ExtraTreesRegressor(n_estimators=240, max_depth=14, min_samples_leaf=8, max_features=.8, n_jobs=-1, random_state=42)
    elif kind == "extra_trees_deep":
        est = ExtraTreesRegressor(n_estimators=240, max_depth=None, min_samples_leaf=10, max_features=.8, n_jobs=-1, random_state=42)
    elif kind == "ridge":
        est = Ridge(alpha=3.0)
    else:
        raise ValueError(kind)
    return Pipeline([("preprocess", pre), ("model", est)])

def score(y, p):
    return {"n": int(len(y)), "mae": float(mean_absolute_error(y,p)),
            "rmse": float(np.sqrt(mean_squared_error(y,p))),
            "bias_pred_minus_actual": float(np.mean(p-y)), "r2": float(r2_score(y,p))}

def main():
    outputs = [PRED_PATH,METRICS_PATH,AUDIT_PATH,MODEL_PATH,META_PATH,REPORT_PATH]
    if any(p.exists() for p in outputs): raise SystemExit("Refusing to overwrite versioned outputs.")
    df = pd.read_parquet(DATA).copy()
    df["season_id"] = df["season_id"].astype(str)
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")
    if df[TARGET].isna().any() or df[["season_id","game_date","dunkest_player_id","gameId"]].isna().any().any():
        raise SystemExit("Missing target or key.")
    if df.duplicated(["season_id","dunkest_player_id","gameId"]).any(): raise SystemExit("Duplicate player-game keys.")
    if set(FEATURES)-set(df.columns): raise SystemExit(f"Missing features: {sorted(set(FEATURES)-set(df.columns))}")
    if df["season_id"].isin(["1","3"]).any(): raise SystemExit("Legacy seasons cannot enter supervised targets.")
    df = df.sort_values(["game_date","season_id","dunkest_player_id","gameId"],kind="stable").reset_index(drop=True)
    expected = df.groupby("dunkest_player_id",sort=False)[TARGET].shift(1)
    lag = pd.to_numeric(df["lag1_pdk"],errors="coerce")
    valid = expected.notna() & lag.notna()
    mismatch = int(((expected[valid]-lag[valid]).abs()>1e-9).sum())
    miss = int((expected.isna()!=lag.isna()).sum())
    if mismatch or miss: raise SystemExit(f"PDK lag integrity failed: {mismatch}/{miss}")
    if "prior_nba_history_game_date" in df:
        d = pd.to_datetime(df["prior_nba_history_game_date"],errors="coerce")
        if int((d.notna() & d.ge(df["game_date"])).sum()): raise SystemExit("Current/future NBA history detected.")
    candidates = ["rf_baseline","rf_deeper","rf_regularized","extra_trees_regularized","extra_trees_deep","ridge"]
    records, preds = [], []
    for season in TUNE:
        earlier = [s for s in TRAIN if int(s)<int(season)]
        tr, te = df[df.season_id.isin(earlier)], df[df.season_id.eq(season)]
        y, yt = tr[TARGET].astype(float), te[TARGET].astype(float).to_numpy()
        baseline = pd.to_numeric(te["prev10_pdk_mean"],errors="coerce").fillna(float(y.median())).to_numpy()
        records.append({"model":"baseline_prev10_mean","fold_season_id":season,"fold_season":LABELS[season],"train_rows":len(tr),**score(yt,baseline)})
        for kind in candidates:
            model=build(kind); model.fit(tr[FEATURES],y); p=model.predict(te[FEATURES])
            records.append({"model":kind,"fold_season_id":season,"fold_season":LABELS[season],"train_rows":len(tr),**score(yt,p)})
            preds.append(pd.DataFrame({"season":LABELS[season],"season_id":season,
                "game_date":te["game_date"].dt.strftime("%Y-%m-%d").to_numpy(),
                "dunkest_player_id":te["dunkest_player_id"].astype(str).to_numpy(),
                "gameId":te["gameId"].astype(str).to_numpy(),"target_pdk":yt,"model":kind,"prediction":p}))
            print(f"{LABELS[season]} {kind}: MAE={mean_absolute_error(yt,p):.5f}",flush=True)
    metrics=pd.DataFrame(records)
    summ=metrics[metrics.model.isin(candidates)].groupby("model").apply(
        lambda g: pd.Series({"validation_mae_weighted":np.average(g.mae,weights=g.n),
                             "validation_rmse_weighted":np.sqrt(np.average(g.rmse**2,weights=g.n)),
                             "validation_bias_weighted":np.average(g.bias_pred_minus_actual,weights=g.n),
                             "folds":g.fold_season_id.nunique()}),include_groups=False).reset_index()
    chosen=str(summ.sort_values(["validation_mae_weighted","validation_rmse_weighted"]).iloc[0].model)
    pd.concat(preds,ignore_index=True).to_csv(PRED_PATH,index=False); metrics.to_csv(METRICS_PATH,index=False)
    tr=df[df.season_id.isin(TRAIN)]; te=df[df.season_id.eq("25")]
    if set(tr.season_id.unique())!=set(TRAIN) or te.empty: raise SystemExit("Unexpected final train/test seasons.")
    final=build(chosen); final.fit(tr[FEATURES],tr[TARGET].astype(float)); yt=te[TARGET].astype(float).to_numpy()
    p=final.predict(te[FEATURES]); baseline=pd.to_numeric(te["prev10_pdk_mean"],errors="coerce").fillna(float(tr[TARGET].median())).to_numpy()
    final_scores={"selected_model":score(yt,p),"baseline_prev10_mean":score(yt,baseline)}
    joblib.dump(final,MODEL_PATH,compress=3)
    audit={"created_utc":datetime.now(timezone.utc).isoformat(),"dataset":str(DATA),"target":TARGET,
        "features":FEATURES,"train_seasons":{s:LABELS[s] for s in TRAIN},
        "validation_seasons":{s:LABELS[s] for s in TUNE},"test_season":{"25":LABELS["25"]},
        "train_rows":len(tr),"test_rows":len(te),"selected_model":chosen,
        "selection_rule":"Lowest row-weighted MAE across expanding validation seasons 2022/23-2024/25; RMSE breaks ties.",
        "validation_summary":summ.sort_values("validation_mae_weighted").to_dict(orient="records"),
        "fold_metrics":records,"final_test_metrics":final_scores,
        "temporal_checks":{"lag1_value_mismatches":mismatch,"lag1_missingness_mismatches":miss,"current_or_future_nba_history_rows":0},
        "label_policy":"Official verified valid PDK labels only from 2020/21-2025/26. 2018/19 and 2019/20 are excluded as supervised targets because archived validity flags are all false; NBA boxscores from these seasons remain usable as prior features.",
        "production_status":"Standalone candidate; not integrated into production.",
        "holdout_caveat":"2025/26 was not used to select hyperparameters in this run, but earlier project experiments have inspected it; it is not globally untouched across the project."}
    AUDIT_PATH.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    META_PATH.write_text(json.dumps({"model_artifact":str(MODEL_PATH),"model_type":chosen,"training_rows":len(tr),
        "training_seasons":[LABELS[s] for s in TRAIN],"features":FEATURES,"final_test_metrics":final_scores},indent=2,ensure_ascii=False),encoding="utf-8")
    REPORTS.mkdir(parents=True,exist_ok=True)
    report="# Dunkest PDK model tuning — "+STAMP+"\n\n"
    report+="Validation selection used 2022/23–2024/25 only; 2025/26 was excluded from tuning.\n\n"
    report+="## Validation summary\n\n"+summ.sort_values("validation_mae_weighted").to_markdown(index=False,floatfmt=".5f")+"\n\n"
    report+=f"Selected candidate: **{chosen}**.\n\n## 2025/26 historical holdout\n\n"
    report+=pd.DataFrame([{"model":"selected "+chosen,**final_scores["selected_model"]},{"model":"previous-10 mean",**final_scores["baseline_prev10_mean"]}]).to_markdown(index=False,floatfmt=".5f")+"\n\n"
    report+="## Limitations\n\nThe model is player-game level, not a lineup optimizer. The 2025/26 season has been inspected by prior experiments, so this is not globally unseen. Production was not changed.\n"
    REPORT_PATH.write_text(report,encoding="utf-8")
    print("\nVALIDATION SUMMARY\n",summ.sort_values("validation_mae_weighted").to_string(index=False))
    print("\nSELECTED",chosen,"\nHOLDOUT",json.dumps(final_scores,indent=2))
    print("REPORT",REPORT_PATH)

if __name__=="__main__": main()
