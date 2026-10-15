#!/usr/bin/env python3
"""Evaluate fixed blends of direct HGB and calibrated-prevalence tail mixture."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"reports/audit"; STAMP="20261013_conditional_tail_blend_v1"
CSV=OUT/f"dunkest_{STAMP}_metrics.csv"; PRED=OUT/f"dunkest_{STAMP}_predictions.csv"; JSON=OUT/f"dunkest_{STAMP}.json"; MD=OUT/f"dunkest_{STAMP}.md"; REPS=3000

def metrics(g,pcol):
    y=g.target_pdk.to_numpy(float); p=g[pcol].to_numpy(float)
    high25=g.target_pdk.ge(25).to_numpy(); high30=g.target_pdk.ge(30).to_numpy()
    return {"n":len(g),"mae":float(mean_absolute_error(y,p)),"rmse":float(mean_squared_error(y,p)**.5),"bias_pred_minus_actual":float(np.mean(p-y)),"mae_actual_ge25":float(np.mean(np.abs(p[high25]-y[high25]))),"n_ge25":int(high25.sum()),"mae_actual_ge30":float(np.mean(np.abs(p[high30]-y[high30]))),"n_ge30":int(high30.sum())}

def bootstrap(frame, pcol, baseline, mask=None, seed=20261013):
    d=frame.copy()
    if mask is not None: d=d.loc[mask].copy()
    d["delta"]=np.abs(d[pcol]-d.target_pdk)-np.abs(d[baseline]-d.target_pdk)
    cl=d.groupby(["season","game_date"],sort=False).delta.agg(["sum","count"]).reset_index()
    groups={s:(g["sum"].to_numpy(float),g["count"].to_numpy(float)) for s,g in cl.groupby("season",sort=False)}
    rng=np.random.default_rng(seed); values=np.empty(REPS)
    for i in range(REPS):
        total=0.; n=0.
        for sums,counts in groups.values():
            idx=rng.integers(0,len(sums),len(sums)); total+=sums[idx].sum(); n+=counts[idx].sum()
        values[i]=total/n
    return {"n":len(d),"delta_mae_candidate_minus_baseline":float(d.delta.mean()),"ci95":[float(np.quantile(values,.025)),float(np.quantile(values,.975))],"clusters":int(len(cl)),"reps":REPS}

def main():
    if any(p.exists() for p in [CSV,PRED,JSON,MD]): raise SystemExit("Refusing to overwrite existing outputs")
    direct=pd.read_csv(OUT/"dunkest_20261013_minutes_rate_decomposition_v1_predictions.csv")
    mix=pd.read_csv(OUT/"dunkest_20261013_conditional_tail_model_v2_predictions.csv")
    direct=direct.loc[direct.candidate.eq("direct_hgb")].copy(); mix=mix.loc[mix.candidate.eq("mixture_threshold_25")].copy()
    keys=["season_id","season","game_date","dunkest_player_id","gameId"]
    d=mix[keys+["target_pdk","prediction"]].merge(direct[keys+["target_pdk","prediction"]],on=keys,how="inner",validate="one_to_one",suffixes=("_mix","_hgb"))
    if len(d)!=len(mix) or not np.allclose(d.target_pdk_mix,d.target_pdk_hgb,atol=1e-12): raise SystemExit("Prediction pairing/label mismatch")
    out=pd.DataFrame({"season_id":d.season_id,"season":d.season,"game_date":d.game_date,"dunkest_player_id":d.dunkest_player_id,"gameId":d.gameId,"target_pdk":d.target_pdk_mix,"direct_hgb":d.prediction_hgb,"mixture25":d.prediction_mix})
    rows=[]
    for w in [0.25,0.5,0.75]:
        col=f"blend_mix_weight_{w:.2f}"; out[col]=(1-w)*out.direct_hgb+w*out.mixture25
        rows.append({"candidate":col,"mixture_weight":w,**metrics(out,col)})
    rows.append({"candidate":"direct_hgb","mixture_weight":0.0,**metrics(out,"direct_hgb")})
    rows.append({"candidate":"mixture25","mixture_weight":1.0,**metrics(out,"mixture25")})
    detail=pd.DataFrame(rows).sort_values(["mae","rmse"]); detail.to_csv(CSV,index=False); out.to_csv(PRED,index=False)
    boot={}
    for w in [0.25,0.5,0.75]:
        col=f"blend_mix_weight_{w:.2f}"
        boot[col]={"vs_direct_hgb_overall":bootstrap(out,col,"direct_hgb",seed=20261013+int(w*100)),"vs_direct_hgb_actual_ge25":bootstrap(out,col,"direct_hgb",out.target_pdk.ge(25),seed=20261113+int(w*100)),"vs_direct_hgb_actual_ge30":bootstrap(out,col,"direct_hgb",out.target_pdk.ge(30),seed=20261213+int(w*100))}
    audit={"created_utc":datetime.now(timezone.utc).isoformat(),"source_predictions":["dunkest_20261013_minutes_rate_decomposition_v1_predictions.csv","dunkest_20261013_conditional_tail_model_v2_predictions.csv"],"folds":["2022-23","2023-24","2024-25"],"holdout_2025_26_loaded":False,"prospective_snapshot_loaded":False,"definition":"blend=(1-w)*direct HGB + w*threshold-25 mixture; weights are research candidates on validation folds, not production weights.","metrics":detail.to_dict("records"),"bootstrap":boot,"production_changed":False}
    JSON.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    report=["# Conditional tail blend — V1","",f"Generated UTC: {audit['created_utc']}","","The blend is `(1-w) × direct HistGradientBoosting + w × threshold-25 mixture`. All predictions share identical labels and expanding-origin folds. This is a validation-only ensemble experiment, not production tuning on the 2025/26 holdout.","","## Pooled metrics","",detail.to_string(index=False,float_format=lambda x:f"{x:.5f}"),"","## Paired date-cluster bootstrap vs direct HGB","","Delta MAE is blend minus direct HGB; negative favors the blend.","",json.dumps(boot,indent=2),"","## Decision","","A blend is not promoted solely on a small aggregate MAE change. It must preserve or improve high-score tails, improve RMSE/calibration, and then pass a complete lineup-level historical replay. No production source/config/weights/snapshot was changed; no commit or push.","","## Artifacts","",f"- Metrics: `{CSV.relative_to(ROOT)}`",f"- Predictions: `{PRED.relative_to(ROOT)}`",f"- Audit: `{JSON.relative_to(ROOT)}`","\n"]
    MD.write_text("\n".join(report),encoding="utf-8")
    print(detail.to_string(index=False),flush=True); print(json.dumps(boot,indent=2),flush=True); print("REPORT="+str(MD.relative_to(ROOT)),flush=True)
if __name__=="__main__": main()
