#!/usr/bin/env python3
"""Sequential validation: choose blend weight on 2022/23 only, freeze for later folds."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"reports/audit"; STEM="dunkest_blend_sequential_weight_validation_20261013_v1"
CSV=OUT/f"{STEM}.csv"; JSON=OUT/f"{STEM}.json"; MD=OUT/f"{STEM}.md"; REPS=5000

def summarize(g,p):
 y=g.target_pdk.to_numpy(float); q=g[p].to_numpy(float); a25=y>=25; a30=y>=30
 return {"n":len(g),"mae":float(mean_absolute_error(y,q)),"rmse":float(mean_squared_error(y,q)**.5),"bias":float(np.mean(q-y)),"mae_actual_ge25":float(np.mean(np.abs(q[a25]-y[a25]))),"n_actual_ge25":int(a25.sum()),"mae_actual_ge30":float(np.mean(np.abs(q[a30]-y[a30]))),"n_actual_ge30":int(a30.sum())}

def bootstrap(g, candidate, baseline, mask=None, seed=20261013):
 d=g.copy()
 if mask is not None: d=d.loc[mask].copy()
 d["delta"]=np.abs(d[candidate]-d.target_pdk)-np.abs(d[baseline]-d.target_pdk)
 cl=d.groupby(["season","game_date"],sort=False).delta.agg(["sum","count"]).reset_index()
 groups={s:(z["sum"].to_numpy(float),z["count"].to_numpy(float)) for s,z in cl.groupby("season",sort=False)}
 rng=np.random.default_rng(seed); vals=np.empty(REPS)
 for i in range(REPS):
  total=0.; n=0.
  for sums,counts in groups.values():
   ix=rng.integers(0,len(sums),len(sums)); total+=sums[ix].sum(); n+=counts[ix].sum()
  vals[i]=total/n
 return {"n":len(d),"clusters":int(len(cl)),"delta_mae_candidate_minus_direct":float(d.delta.mean()),"ci95":[float(np.quantile(vals,.025)),float(np.quantile(vals,.975))],"reps":REPS}

def main():
 if any(p.exists() for p in [CSV,JSON,MD]): raise SystemExit("Refusing to overwrite outputs")
 d=pd.read_csv(OUT/"dunkest_20261013_conditional_tail_blend_v1_predictions.csv")
 # Select weight on the earliest validation fold only; then freeze it for later folds.
 first=d.loc[d.season.eq("2022-23")]
 weights=[.25,.5,.75]
 scores={w:float(np.mean(np.abs(first[f"blend_mix_weight_{w:.2f}"]-first.target_pdk))) for w in weights}
 selected=min(scores,key=scores.get)
 later=d.loc[d.season.isin(["2023-24","2024-25"])].copy()
 candidate=f"blend_mix_weight_{selected:.2f}"
 rows=[]
 for fold,g in d.groupby("season",sort=True):
  for name in ["direct_hgb",candidate]: rows.append({"scope":fold,"candidate":name,**summarize(g,name)})
 for name in ["direct_hgb",candidate]: rows.append({"scope":"pooled_later_folds_2023-24_2024-25","candidate":name,**summarize(later,name)})
 metrics=pd.DataFrame(rows); metrics.to_csv(CSV,index=False)
 later["actual_ge25"]=later.target_pdk.ge(25); later["actual_ge30"]=later.target_pdk.ge(30)
 boots={"overall":bootstrap(later,candidate,"direct_hgb",seed=20261013),"actual_ge25":bootstrap(later,candidate,"direct_hgb",later.actual_ge25,seed=20261014),"actual_ge30":bootstrap(later,candidate,"direct_hgb",later.actual_ge30,seed=20261015)}
 audit={"created_utc":datetime.now(timezone.utc).isoformat(),"source":"dunkest_20261013_conditional_tail_blend_v1_predictions.csv","selection_rule":"Choose among fixed weights 0.25, 0.50, 0.75 using 2022/23 MAE only; freeze the selected weight and evaluate on 2023/24 and 2024/25 without re-selection.","selection_mae_2022_23":{str(k):v for k,v in scores.items()},"selected_weight":selected,"later_folds":["2023-24","2024-25"],"later_fold_metrics":metrics.loc[metrics.scope.eq("pooled_later_folds_2023-24_2024-25")].to_dict("records"),"paired_date_cluster_bootstrap_later_folds":boots,"holdout_2025_26_loaded":False,"prospective_snapshot_loaded":False,"caveat":"Later folds were previously inspected during exploratory work; this sequential rule removes same-fold weight selection but is not a pristine untouched final test set.","production_changed":False}
 JSON.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
 report=["# Sequential blend-weight validation — V1","",f"Generated UTC: {audit['created_utc']}","","## Protocol","","Choose the blend weight among 25%, 50%, and 75% mixture on 2022/23 MAE only, freeze it, and evaluate the exact rule on 2023/24 and 2024/25. No 2025/26 holdout or 2026/27 prospective snapshot is loaded. The later folds have been inspected in prior exploratory work, so this is stronger temporal validation but not a pristine final test.","",f"Selected weight: **{selected:.0%} mixture**. Selection-fold MAE: `{scores}`.","","## Results","",metrics.to_string(index=False,float_format=lambda x:f"{x:.5f}"),"","## Paired date-cluster bootstrap on later folds","","Delta MAE = frozen blend minus direct HGB; negative favors the blend.","",json.dumps(boots,indent=2),"","## Decision","","This validates or rejects the weight-selection rule, not lineup-level utility. Do not promote until the complete historical lineup replay demonstrates an improvement under the same candidate pool, credits, coaches, and transfer rules.","","No production change, no commit/push.",""]
 MD.write_text("\n".join(report),encoding="utf-8")
 print(metrics.to_string(index=False),flush=True); print(json.dumps(audit,indent=2),flush=True); print("REPORT="+str(MD.relative_to(ROOT)),flush=True)
if __name__=="__main__": main()
