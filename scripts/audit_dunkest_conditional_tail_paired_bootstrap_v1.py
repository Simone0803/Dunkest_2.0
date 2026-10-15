#!/usr/bin/env python3
"""Paired date-cluster bootstrap for conditional high-score model vs direct models."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"reports/audit"; STAMP="20261013_conditional_tail_paired_bootstrap_v1"
JSON=OUT/f"dunkest_{STAMP}.json"; CSV=OUT/f"dunkest_{STAMP}.csv"; MD=OUT/f"dunkest_{STAMP}.md"; REPS=3000

def boot_delta(frame, mask=None, seed=20261013):
    d=frame.copy()
    if mask is not None: d=d.loc[mask].copy()
    if d.empty: return {"n":0,"delta_mae_mixture_minus_direct":None,"ci95":None}
    d["delta_abs_error"]=np.abs(d.pred_b-d.target_pdk)-np.abs(d.pred_a-d.target_pdk)
    cluster=d.groupby(["season","game_date"],sort=False).delta_abs_error.agg(["sum","count"]).reset_index()
    by_season={s:(g["sum"].to_numpy(float),g["count"].to_numpy(float)) for s,g in cluster.groupby("season",sort=False)}
    rng=np.random.default_rng(seed); boot=np.empty(REPS)
    for i in range(REPS):
        total_sum=0.0; total_n=0.0
        for sums,counts in by_season.values():
            picks=rng.integers(0,len(sums),len(sums))
            total_sum+=float(sums[picks].sum()); total_n+=float(counts[picks].sum())
        boot[i]=total_sum/total_n
    return {"n":int(len(d)),"season_date_clusters":int(len(cluster)),"delta_mae_mixture_minus_direct":float(d.delta_abs_error.mean()),"ci95":[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))],"bootstrap_reps":REPS}

def main():
    if any(p.exists() for p in [JSON,CSV,MD]): raise SystemExit("Refusing to overwrite existing audit outputs")
    mixture=pd.read_csv(OUT/"dunkest_20261013_conditional_tail_model_v2_predictions.csv")
    direct=pd.read_csv(OUT/"dunkest_20261013_minutes_rate_decomposition_v1_predictions.csv")
    mixture=mixture.loc[mixture.candidate.eq("mixture_threshold_25")].copy()
    direct=direct.loc[direct.candidate.isin(["direct_et12","direct_hgb"])].copy()
    keys=["season_id","season","game_date","dunkest_player_id","gameId"]
    results={}; rows=[]
    for cand in ["direct_et12","direct_hgb"]:
        a=direct.loc[direct.candidate.eq(cand),keys+["target_pdk","prediction"]].copy(); a["season_id"]=a.season_id.astype(str)
        b=mixture[keys+["target_pdk","prediction"]].copy(); b["season_id"]=b.season_id.astype(str)
        d=b.merge(a,on=keys,how="inner",validate="one_to_one",suffixes=("_mix","_direct"))
        if len(d)!=len(b) or not np.allclose(d.target_pdk_mix,d.target_pdk_direct,atol=1e-12): raise SystemExit(f"Prediction pairing/label mismatch for {cand}")
        frame=pd.DataFrame({"season_id":d.season_id,"season":d.season,"game_date":d.game_date,"target_pdk":d.target_pdk_mix,"pred_a":d.prediction_direct,"pred_b":d.prediction_mix})
        frame["actual_ge25"]=frame.target_pdk.ge(25); frame["actual_ge30"]=frame.target_pdk.ge(30)
        comparisons={}
        for i,(label,mask) in enumerate([("overall",None),("actual_pdk_ge25",frame.actual_ge25),("actual_pdk_ge30",frame.actual_ge30)]):
            res=boot_delta(frame,mask=mask,seed=20261013+i+(0 if cand=="direct_et12" else 100))
            comparisons[label]=res; rows.append({"direct_model":cand,"segment":label,**res})
        results[f"mixture_threshold_25_vs_{cand}"]=comparisons
    out=pd.DataFrame(rows); out.to_csv(CSV,index=False)
    audit={"created_utc":datetime.now(timezone.utc).isoformat(),"mixture_predictions":"dunkest_20261013_conditional_tail_model_v2_predictions.csv","direct_predictions":"dunkest_20261013_minutes_rate_decomposition_v1_predictions.csv","holdout_2025_26_loaded":False,"prospective_snapshot_loaded":False,"definition":"delta MAE = mixture threshold-25 minus direct model; negative favors mixture. Resampling is stratified by season and clusters all player rows on a target date.","results":results}
    JSON.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    report=["# Conditional tail model paired bootstrap — V1","",f"Generated UTC: {audit['created_utc']}","","Delta MAE is mixture-threshold-25 minus the direct model; negative favors the mixture. Bootstrap resamples complete target dates within each season (3,000 repetitions). This is a paired comparison of identical player-game labels and folds.","",out.to_string(index=False,float_format=lambda x:f"{x:.5f}"),"","## Interpretation","","The mixture is only a candidate if overall MAE and high-score subgroup results improve without material degradation elsewhere. This bootstrap does not use 2025/26 or frozen prospective 2026/27 data and does not justify production promotion on its own.","","No production code/config/weights changed; no commit or push.",""]
    MD.write_text("\n".join(report),encoding="utf-8")
    print(out.to_string(index=False),flush=True); print("REPORT="+str(MD.relative_to(ROOT)),flush=True)
if __name__=="__main__": main()
