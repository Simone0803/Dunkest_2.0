#!/usr/bin/env python3
"""Sequentially validate a small tail-model blend against the strongest V9 model."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"reports/audit"; STEM="dunkest_tail_hybrid_vs_v9_20261013_v1"
CSV=OUT/f"{STEM}_metrics.csv"; JSON=OUT/f"{STEM}.json"; MD=OUT/f"{STEM}.md"; REPS=5000

def score(y,p):
 y=np.asarray(y,float); p=np.asarray(p,float); m25=y>=25; m30=y>=30
 return {"n":len(y),"mae":float(mean_absolute_error(y,p)),"rmse":float(mean_squared_error(y,p)**.5),"bias_pred_minus_actual":float(np.mean(p-y)),"mae_actual_ge25":float(np.mean(np.abs(p[m25]-y[m25]))),"n_actual_ge25":int(m25.sum()),"mae_actual_ge30":float(np.mean(np.abs(p[m30]-y[m30]))),"n_actual_ge30":int(m30.sum())}

def bootstrap(g,cand,base,mask=None,seed=20261013):
 d=g.copy()
 if mask is not None: d=d.loc[mask].copy()
 d["delta_abs"]=np.abs(d[cand]-d.y)-np.abs(d[base]-d.y)
 clusters=d.groupby(["season","date"],sort=False).delta_abs.agg(["sum","count"]).reset_index()
 groups={s:(x["sum"].to_numpy(float),x["count"].to_numpy(float)) for s,x in clusters.groupby("season",sort=False)}
 rng=np.random.default_rng(seed); vals=np.empty(REPS)
 for i in range(REPS):
  sm=0.; n=0.
  for sums,counts in groups.values():
   ix=rng.integers(0,len(sums),len(sums)); sm+=sums[ix].sum(); n+=counts[ix].sum()
  vals[i]=sm/n
 return {"n":len(d),"date_clusters":int(len(clusters)),"delta_mae_candidate_minus_v9":float(d.delta_abs.mean()),"ci95":[float(np.quantile(vals,.025)),float(np.quantile(vals,.975))],"bootstrap_reps":REPS}

def main():
 if any(p.exists() for p in [CSV,JSON,MD]): raise SystemExit("Refusing to overwrite outputs")
 blend=pd.read_csv(OUT/"dunkest_20261013_conditional_tail_blend_v1_predictions.csv")
 blend["season_id"]=blend.season_id.astype(str); blend["date"]=pd.to_datetime(blend.game_date).dt.strftime("%Y-%m-%d"); blend["dunkest_player_id"]=blend.dunkest_player_id.astype(str)
 train=pd.read_parquet(ROOT/"data/processed/dunkest_pdk_game_training_2020-25_v2.parquet")
 train["season_id"]=train.season_id.astype(str); train["date"]=pd.to_datetime(train.game_date).dt.strftime("%Y-%m-%d"); train["dunkest_player_id"]=train.dunkest_player_id.astype(str)
 blend=blend.merge(train[["season_id","date","dunkest_player_id","dunkest_player_name"]].drop_duplicates(),on=["season_id","date","dunkest_player_id"],how="left",validate="one_to_one").rename(columns={"dunkest_player_name":"player_name"})
 v9=pd.read_csv(OUT/"dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link_predictions.csv")
 v9=v9.loc[v9.feature_family.eq("historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6")].copy()
 v9["season_id"]=v9.season_id.astype(str); v9["date"]=pd.to_datetime(v9.target_date,errors="coerce").dt.strftime("%Y-%m-%d")
 keys=["season_id","date","player_name"]
 d=blend.merge(v9[keys+["actual_pdk_round_total","predicted_pdk_round_total"]],on=keys,how="inner",validate="one_to_one")
 if len(d)!=57662 or (d.target_pdk-d.actual_pdk_round_total).abs().max()!=0: raise SystemExit("Expected 57,662 exact paired labels; linkage mismatch")
 d=d.rename(columns={"actual_pdk_round_total":"y","predicted_pdk_round_total":"v9","blend_mix_weight_0.25":"tail_model"})
 # Pick the hybrid weight on the earliest validation fold only; freeze it for later folds.
 first=d.loc[d.season.eq("2022-23")]
 weights=[.05,.10,.15,.25,.50]
 selection={}
 for w in weights: selection[str(w)]=float(np.mean(np.abs((1-w)*first.v9+w*first.tail_model-first.y)))
 chosen=min(weights,key=lambda w:selection[str(w)])
 d["hybrid"]=(1-chosen)*d.v9+chosen*d.tail_model
 d["actual_ge25"]=d.y.ge(25); d["actual_ge30"]=d.y.ge(30)
 later=d.loc[d.season.isin(["2023-24","2024-25"])].copy()
 rows=[]
 for scope,g in [("2022-23_selection_fold",d.loc[d.season.eq("2022-23")]),("2023-24",d.loc[d.season.eq("2023-24")]),("2024-25",d.loc[d.season.eq("2024-25")]),("pooled_later_folds",later),("all_folds_descriptive",d)]:
  for name in ["v9","hybrid","tail_model"]: rows.append({"scope":scope,"candidate":name,**score(g.y,g[name])})
 metrics=pd.DataFrame(rows); metrics.to_csv(CSV,index=False)
 boots={"overall_later_folds":bootstrap(later,"hybrid","v9",seed=20261013),"actual_ge25_later_folds":bootstrap(later,"hybrid","v9",later.actual_ge25,seed=20261014),"actual_ge30_later_folds":bootstrap(later,"hybrid","v9",later.actual_ge30,seed=20261015)}
 audit={"created_utc":datetime.now(timezone.utc).isoformat(),"paired_rows":len(d),"label_mismatches":0,"join_keys":["season_id","target_date/game_date","player_name"],"strong_baseline":"V9 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6","tail_specialist":"25% conditional-tail mixture + 75% direct HGB; this specialist was discovered in exploratory folds and is not a pristine pre-registered candidate.","hybrid_weight_selection":"Choose tail-specialist weight from 5%, 10%, 15%, 25%, 50% using 2022/23 MAE only; freeze selected weight and evaluate on 2023/24 and 2024/25.","selection_fold_mae":selection,"selected_tail_specialist_weight":chosen,"later_folds":["2023-24","2024-25"],"paired_date_cluster_bootstrap_later_folds":boots,"holdout_2025_26_loaded":False,"prospective_snapshot_loaded":False,"caveat":"The validation folds were previously inspected in exploratory work and the tail specialist was developed on them. This is a sequential robustness check, not a pristine final test. No lineup-level utility is measured here.","production_changed":False}
 JSON.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
 report=["# Tail-specialist hybrid vs V9 — V1","",f"Generated UTC: {audit['created_utc']}","","## Question","","Does a small blend of the conditional-tail specialist add value to the strongest existing walk-forward predictor, V9 (historical form + lagged credit + matchup/rest/schedule), rather than only beating the weaker direct HGB baseline?","","## Protocol","","Join the two prediction sets on season, target date, and player name. Exact pairing is required: 57,662 rows and zero label mismatches. Choose the hybrid weight on 2022/23 only among 5%, 10%, 15%, 25%, and 50%, then freeze it and evaluate 2023/24 and 2024/25. The later folds have been examined previously, and the tail specialist itself was discovered in exploratory work, so this is not a pristine final test.","",f"Selected tail-specialist weight: **{chosen:.0%}**. Selection-fold MAEs: `{selection}`.","","## Results","",metrics.to_string(index=False,float_format=lambda x:f"{x:.5f}"),"","## Paired date-cluster bootstrap on later folds","","Delta MAE = hybrid minus V9; negative favors the hybrid. Resampling is stratified by season and clusters all player rows on a target date.","",json.dumps(boots,indent=2),"","## Decision","","This validates only player-round prediction accuracy. The tail-specialist adds no lagged-credit feature and does not reproduce the V9 feature family; a positive hybrid result is a reason to continue with a dedicated walk-forward lineup replay, not permission to deploy it. No production model, config, weights, optimizer, or prospective snapshot was changed.","","## Artifacts","",f"- Metrics: `{CSV.relative_to(ROOT)}`",f"- Audit: `{JSON.relative_to(ROOT)}`","","No commit or push.",""]
 MD.write_text("\n".join(report),encoding="utf-8")
 print(metrics.to_string(index=False),flush=True); print(json.dumps(audit,indent=2),flush=True); print("REPORT="+str(MD.relative_to(ROOT)),flush=True)
if __name__=="__main__": main()
