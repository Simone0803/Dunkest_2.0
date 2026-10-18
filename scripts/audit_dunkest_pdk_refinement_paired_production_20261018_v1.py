#!/usr/bin/env python3
"""Paired temporal check of the top refinement MLP against production OOS predictions."""
from __future__ import annotations
import importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.config import Settings
from dunkest.models.predictor import FEATURE_COLS
from dunkest.models.multiseason_training import adapt_certified_training_rows, DEFAULT_DATASET
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("refinement", ROOT/"scripts/grid_search_dunkest_pdk_refinement_20261018_v1.py")
ref=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(ref)
OUT=ROOT/"reports/audit/dunkest_pdk_refinement_paired_production_20261018_v1"
FOLDS=["2022-23","2023-24","2024-25"]
CFG={"hidden":(128,64),"dropout":0.05,"weight_decay":0.0001,"lr":0.001}
SEED=20261016
def fit_predict(Xtr,ytr,wtr,dates,Xte,fold_index):
    ud=np.sort(pd.to_datetime(dates,errors="coerce").dropna().unique())
    cut=ud[max(1,int(len(ud)*.85))] if len(ud)>5 else ud[-1]
    a=pd.to_datetime(dates,errors="coerce")<cut; b=~a
    if int(a.sum())<1000 or int(b.sum())<100:
        a=pd.Series(np.arange(len(Xtr))<int(len(Xtr)*.85),index=np.arange(len(Xtr))); b=~a
        a=a.to_numpy(); b=b.to_numpy()
    else: a=a.to_numpy(); b=b.to_numpy()
    _,epochs,val_loss=ref.fit_torch(CFG,Xtr[a],ytr[a],wtr[a],Xtr[b],ytr[b],SEED+fold_index)
    import torch
    torch.manual_seed(SEED+fold_index); np.random.seed(SEED+fold_index); torch.set_num_threads(4)
    mean=Xtr.mean(axis=0); sd=np.where(Xtr.std(axis=0)<1e-8,1.,Xtr.std(axis=0))
    xt=torch.tensor((Xtr-mean)/sd,dtype=torch.float32)
    ym=float(ytr.mean()); ys=float(ytr.std()) or 1.
    yt=torch.tensor((ytr-ym)/ys,dtype=torch.float32); wt=torch.tensor(wtr,dtype=torch.float32)
    model=ref.DropoutMLP(Xtr.shape[1],tuple(CFG["hidden"]),CFG["dropout"])
    opt=torch.optim.AdamW(model.parameters(),lr=CFG["lr"],weight_decay=CFG["weight_decay"])
    for _ in range(max(8,epochs)):
        model.train()
        for ix in torch.randperm(len(xt)).split(ref.BATCH_SIZE):
            opt.zero_grad(set_to_none=True); pr=model(xt[ix]); loss=(((pr-yt[ix])**2)*wt[ix]).mean()
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),5.); opt.step()
    model.eval()
    with torch.no_grad(): pred=model(torch.tensor((Xte-mean)/sd,dtype=torch.float32)).numpy()*ys+ym
    return pred,epochs,val_loss
def main():
    settings=Settings.from_yaml()
    source=pd.read_parquet(settings.data_path/DEFAULT_DATASET)
    minute_path=settings.data_path/"processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
    mins=pd.read_parquet(minute_path,columns=["nba_GAME_ID","nba_PLAYER_ID","nba_MIN","nba_match_status"]) if minute_path.exists() else None
    rows=adapt_certified_training_rows(source,minutes_labels=mins)
    if rows.season_label.astype(str).eq("2025-26").any(): raise RuntimeError("Holdout leakage")
    cols=[c for c in FEATURE_COLS if c in rows and pd.to_numeric(rows[c],errors="coerce").replace([np.inf,-np.inf],np.nan).notna().any()]
    frames=[]
    for fi,fold in enumerate(FOLDS):
        tr=rows.loc[rows.season_label.astype(str)<fold].copy(); te=rows.loc[rows.season_label.astype(str).eq(fold)].copy()
        med=pd.DataFrame({c:pd.to_numeric(tr[c],errors="coerce") for c in cols}).replace([np.inf,-np.inf],np.nan).median().fillna(0.)
        Xtr=pd.DataFrame({c:pd.to_numeric(tr[c],errors="coerce") for c in cols}).replace([np.inf,-np.inf],np.nan).fillna(med).fillna(0.).to_numpy(np.float32)
        Xte=pd.DataFrame({c:pd.to_numeric(te[c],errors="coerce") for c in cols}).replace([np.inf,-np.inf],np.nan).fillna(med).fillna(0.).to_numpy(np.float32)
        y=pd.to_numeric(tr.target_pdk_official,errors="coerce").to_numpy(float)
        w=pd.to_numeric(tr["_training_sample_weight"],errors="coerce").fillna(1.).to_numpy(float)
        pred,epochs,val=fit_predict(Xtr,y,w,tr.GAME_DATE,Xte,fi)
        frames.append(pd.DataFrame({"test_season":fold,"game_date":pd.to_datetime(te.GAME_DATE).dt.strftime("%Y-%m-%d"),
            "player_id":te.PLAYER_ID.astype(str).to_numpy(),"game_id":te.GAME_ID.astype(str).to_numpy(),
            "actual_pdk":pd.to_numeric(te.target_pdk_official,errors="coerce").to_numpy(float),"mlp_pred":pred,
            "history_games":pd.to_numeric(te.history_games_before_target,errors="coerce").fillna(0).to_numpy(float)}))
        print(f"{fold}: rows={len(te)} epochs={epochs} val_mse={val:.6f} MAE={np.mean(np.abs(pred-frames[-1].actual_pdk)):.5f}",flush=True)
    cand=pd.concat(frames,ignore_index=True)
    prod=pd.read_csv(ROOT/"reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v2_predictions.csv",dtype={"player_id":"string","game_id":"string"})
    prod=prod.loc[prod.method.eq("all_prior_seasons_low_history_weighted")].copy()
    for c in ["player_id","game_id"]: prod[c]=prod[c].astype(str); cand[c]=cand[c].astype(str)
    merged=cand.merge(prod[["test_season","game_date","player_id","game_id","predicted_pdk"]],on=["test_season","game_date","player_id","game_id"],how="inner",validate="one_to_one")
    if len(merged)!=len(cand): raise RuntimeError(f"Unmatched production rows: candidate={len(cand)}, paired={len(merged)}")
    merged["err_mlp"]=merged.mlp_pred-merged.actual_pdk; merged["err_prod"]=merged.predicted_pdk-merged.actual_pdk
    merged["abs_mlp"]=merged.err_mlp.abs(); merged["abs_prod"]=merged.err_prod.abs()
    merged["delta_abs"]=merged.abs_mlp-merged.abs_prod
    merged["sq_mlp"]=merged.err_mlp**2; merged["sq_prod"]=merged.err_prod**2
    rng=np.random.default_rng(20261018); boot=[]
    clusters={}
    for fold,g in merged.groupby("test_season"):
        by_date=g.groupby("game_date").delta_abs.agg(["sum","count"])
        clusters[fold]=(by_date["sum"].to_numpy(float),by_date["count"].to_numpy(float))
    for _ in range(10000):
        season_deltas=[]
        for sums,counts in clusters.values():
            ix=rng.integers(0,len(sums),size=len(sums))
            season_deltas.append(sums[ix].sum()/counts[ix].sum())
        boot.append(np.mean(season_deltas))
    rows_out=[]
    for fold,g in merged.groupby("test_season"):
        rows_out.append({"season":fold,"n":len(g),"production_mae":g.abs_prod.mean(),"mlp_mae":g.abs_mlp.mean(),"delta_mae_mlp_minus_production":g.delta_abs.mean(),"production_rmse":np.sqrt(g.sq_prod.mean()),"mlp_rmse":np.sqrt(g.sq_mlp.mean()),"production_bias":g.err_prod.mean(),"mlp_bias":g.err_mlp.mean(),"mae_actual_ge25_mlp":g.loc[g.actual_pdk.ge(25),"abs_mlp"].mean(),"mae_actual_ge25_prod":g.loc[g.actual_pdk.ge(25),"abs_prod"].mean(),"mae_actual_ge30_mlp":g.loc[g.actual_pdk.ge(30),"abs_mlp"].mean(),"mae_actual_ge30_prod":g.loc[g.actual_pdk.ge(30),"abs_prod"].mean()})
    summary=pd.DataFrame(rows_out)
    macro_delta=float(summary.delta_mae_mlp_minus_production.mean())
    report={"created_utc":pd.Timestamp.now(tz="UTC").isoformat(),"candidate":"torch_dropout_mlp hidden=(128,64), dropout=0.05, weight_decay=0.0001, lr=0.001",
      "n_paired":len(merged),"folds":summary.to_dict("records"),"macro_equal_season_delta_mae_mlp_minus_production":macro_delta,
      "date_cluster_bootstrap_95pct_interval":np.quantile(boot,[.025,.975]).tolist(),"bootstrap_replicates":10000,"seed":20261018,
      "holdout_2025_26_used":False,"prospective_2026_27_used":False,"production_changed":False,
      "interpretation":"Paired model-selection evidence only; no lineup-level validation. A lower MAE alone does not override RMSE, tails, cohort stability, or the prospective freeze."}
    OUT.with_suffix(".json").write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    OUT.with_suffix(".csv").write_text(merged.to_csv(index=False),encoding="utf-8")
    lines=["# Paired refinement MLP vs current production ensemble","",f"Generated UTC: {report['created_utc']}","",f"Paired predictions: {len(merged):,}; folds: 2022/23–2024/25; no 2025/26 or 2026/27 outcomes used.","","## Per-season comparison","",summary.to_string(index=False,float_format=lambda x:f"{x:.5f}"),"",f"Equal-season macro ΔMAE (MLP − production): {macro_delta:.5f}.","",f"95% game-date-cluster bootstrap interval: [{report['date_cluster_bootstrap_95pct_interval'][0]:.5f}, {report['date_cluster_bootstrap_95pct_interval'][1]:.5f}].","", "Negative ΔMAE favors the MLP. Promotion requires consistent RMSE/tail behavior and lineup-level evidence; production is unchanged.",""]
    OUT.with_suffix(".md").write_text("\n".join(lines),encoding="utf-8")
    print(summary.to_string(index=False)); print("macro_delta",macro_delta,"CI",report["date_cluster_bootstrap_95pct_interval"],"report",OUT.with_suffix(".md"),flush=True)
if __name__=="__main__": main()
