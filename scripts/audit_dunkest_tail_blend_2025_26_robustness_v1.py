#!/usr/bin/env python3
"""Retrospective 2025/26 robustness test of a nested conditional-tail blend.

Tail blend weight is selected only on the latest 20% of the 2020/21–2024/25
training block. The selected weight is then fixed before scoring the 2025/26
matched official-PDK subset. This is not a pristine holdout: that season has been
seen in prior exploratory work. No production files are modified.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'; STEM='dunkest_tail_blend_2025_26_robustness_v1'
FILES=[OUT/f'{STEM}.json',OUT/f'{STEM}.md',OUT/f'{STEM}_metrics.csv',OUT/f'{STEM}_predictions.csv',OUT/f'{STEM}_cohorts.csv']
WEIGHTS=[0.0,0.25,0.5,0.75,1.0]

def score(y,p):
 y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
 r={'n':int(len(y)),'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5),'bias_pred_minus_actual':float(e.mean())}
 for t in (25,30):
  m=y>=t; r[f'n_actual_ge_{t}']=int(m.sum()); r[f'mae_actual_ge_{t}']=float(np.mean(np.abs(e[m]))) if m.any() else None; r[f'bias_actual_ge_{t}']=float(e[m].mean()) if m.any() else None
 return r

def bootstrap_delta(frame,candidate,baseline,mask=None,seed=20261019,reps=5000):
 d=frame if mask is None else frame.loc[mask]
 d=d[['GAME_DATE','target_pdk_official',candidate,baseline]].copy()
 d['delta']=np.abs(d[candidate]-d.target_pdk_official)-np.abs(d[baseline]-d.target_pdk_official)
 g=d.groupby('GAME_DATE',sort=False).delta.agg(['sum','count']); sums=g['sum'].to_numpy(float); counts=g['count'].to_numpy(float)
 rng=np.random.default_rng(seed); draws=np.empty(reps)
 for i in range(reps):
  ix=rng.integers(0,len(sums),len(sums)); draws[i]=sums[ix].sum()/counts[ix].sum()
 return {'delta_mae_candidate_minus_baseline':float(d.delta.mean()),'ci95_low':float(np.quantile(draws,.025)),'ci95_high':float(np.quantile(draws,.975)),'date_clusters':int(len(g)),'bootstrap_replicates':reps}

def main():
 if any(p.exists() for p in FILES): raise SystemExit('Refusing to overwrite audit outputs')
 sys.path.insert(0,str(ROOT/'scripts'))
 import experiment_dunkest_production_tail_blend_nested_v1 as tail
 from dunkest.config import Settings
 from dunkest.models.multiseason_training import adapt_certified_training_rows,DEFAULT_DATASET,TRAIN_SEASONS
 from dunkest.models.predictor import train_models,_ensemble_predict,FEATURE_COLS
 settings=Settings(training_target='target_pdk_official'); source=pd.read_parquet(settings.data_path/DEFAULT_DATASET)
 rows=adapt_certified_training_rows(source,include_2025_26=True)
 train=rows.loc[rows.season_label.astype(str).isin(TRAIN_SEASONS)].copy(); test=rows.loc[rows.season_label.astype(str).eq('2025-26')].copy()
 if len(train)<90000 or len(test)<10000: raise ValueError(f'Unexpected data sizes train={len(train)} test={len(test)}')
 dates=np.sort(pd.to_datetime(train.GAME_DATE).dropna().unique()); cutoff=dates[int(len(dates)*.8)]
 inner_train=train.loc[pd.to_datetime(train.GAME_DATE).lt(cutoff)].copy(); inner_valid=train.loc[pd.to_datetime(train.GAME_DATE).ge(cutoff)].copy()
 direct_inner_model,_=train_models(settings,inner_train,target_column='target_pdk_official',sample_weight=inner_train['_training_sample_weight'])
 direct_inner=_ensemble_predict(direct_inner_model,inner_valid)
 tail_inner,inner_meta=tail._fit_tail(inner_train,inner_valid,[c for c in inner_train.columns if c in FEATURE_COLS])
 y_inner=inner_valid.target_pdk_official.to_numpy(float)
 weight_scores=[]
 for w in WEIGHTS:
  p=(1-w)*direct_inner+w*tail_inner
  weight_scores.append({'tail_weight':w,**score(y_inner,p)})
 selected=min(weight_scores,key=lambda x:(x['mae'],x['tail_weight']))['tail_weight']
 direct_model,_=train_models(settings,train,target_column='target_pdk_official',sample_weight=train['_training_sample_weight'])
 direct=_ensemble_predict(direct_model,test)
 tail_pred,outer_meta=tail._fit_tail(train,test,[c for c in train.columns if c in FEATURE_COLS])
 blended=(1-selected)*direct+selected*tail_pred
 frame=test[['season_label','GAME_DATE','GAME_ID','PLAYER_ID','PLAYER_NAME','target_pdk_official','prev10_pdk_mean','history_games_before_target','nba_history_games_before_target']].copy()
 frame['prediction_production']=direct; frame['prediction_tail']=tail_pred; frame['prediction_nested_blend']=blended
 frame['baseline_prev10']=pd.to_numeric(frame.prev10_pdk_mean,errors='coerce').fillna(float(train.target_pdk_official.median()))
 frame['actual_ge25']=frame.target_pdk_official.ge(25); frame['actual_ge30']=frame.target_pdk_official.ge(30)
 frame['low_history_le5']=pd.to_numeric(frame.history_games_before_target,errors='coerce').fillna(0).le(5)
 frame['prediction_ge25']=frame.prediction_production.ge(25); frame['prediction_ge30']=frame.prediction_production.ge(30)
 candidates={'production':direct,'tail_mixture':tail_pred,'nested_blend':blended,'previous10_baseline':frame.baseline_prev10.to_numpy(float)}
 metrics=[]
 for name,p in candidates.items(): metrics.append({'candidate':name,**score(frame.target_pdk_official,p)})
 cohorts=[]
 masks={'all':pd.Series(True,index=frame.index),'actual_ge25':frame.actual_ge25,'actual_ge30':frame.actual_ge30,'low_history_le5':frame.low_history_le5,'history_gt5':~frame.low_history_le5,'prediction_ge25':frame.prediction_ge25,'prediction_ge30':frame.prediction_ge30}
 for cohort,mask in masks.items():
  for name,col in [('production','prediction_production'),('tail_mixture','prediction_tail'),('nested_blend','prediction_nested_blend'),('previous10_baseline','baseline_prev10')]:
   g=frame.loc[mask];
   if len(g): cohorts.append({'cohort':cohort,'candidate':name,**score(g.target_pdk_official,g[col])})
 cohort_df=pd.DataFrame(cohorts); metric_df=pd.DataFrame(metrics)
 ci_all=bootstrap_delta(frame,'prediction_nested_blend','prediction_production')
 ci_tail=bootstrap_delta(frame,'prediction_nested_blend','prediction_production',frame.actual_ge25,seed=20261020)
 ci_30=bootstrap_delta(frame,'prediction_nested_blend','prediction_production',frame.actual_ge30,seed=20261021)
 frame.to_csv(FILES[3],index=False); metric_df.to_csv(FILES[2],index=False); cohort_df.to_csv(FILES[4],index=False)
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'training_seasons':list(TRAIN_SEASONS),'training_rows':len(train),'test_season':'2025-26','test_rows':len(test),'inner_train_rows':len(inner_train),'inner_valid_rows':len(inner_valid),'inner_cutoff':str(pd.Timestamp(cutoff)),'weight_candidates':WEIGHTS,'selected_tail_weight':selected,'inner_weight_scores':weight_scores,'tail_model_inner':inner_meta,'tail_model_outer':outer_meta,'outer_metrics':metrics,'paired_bootstrap_nested_blend_minus_production':{'all':ci_all,'actual_ge25':ci_tail,'actual_ge30':ci_30},'holdout_status':'retrospective robustness only; 2025/26 has been inspected in prior experiments','prospective_2026_27_loaded':False,'production_changed':False,'lineup_level_claim':False}
 FILES[0].write_text(json.dumps(audit,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
 lines=['# Conditional-tail blend — 2025/26 retrospective robustness audit','',f"Generated UTC: {audit['created_utc']}",'','## Protocol','','Train the direct production ensemble and a two-part conditional-tail model on official PDK labels from 2020/21–2024/25. Choose the tail mixture weight only on the final 20% of dates in that training block, then freeze it and evaluate the 2025/26 matched official-PDK subset. This season was inspected in earlier experiments, so this is a retrospective robustness check, not a pristine final holdout. The 2026/27 prospective bundle is not loaded.','','## Weight selection on earlier data','',f"Selected tail weight: **{selected:.0%}**",'',pd.DataFrame(weight_scores).to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Outer 2025/26 results','',metric_df.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Paired game-date bootstrap','',json.dumps({'all':ci_all,'actual_ge25':ci_tail,'actual_ge30':ci_30},indent=2),'','Negative ΔMAE favors the nested blend. Actual-score cohorts are diagnostic only and cannot be used to choose a player before a game.','','## Cohorts','',cohort_df.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Decision','','Do not promote from this season alone. A positive result is evidence to retain the challenger for further prospective and temporal validation; a negative result is evidence against its robustness. Player-level metrics do not certify realized lineup superiority. No production model/configuration changed.','','## Artifacts','',*[f'- `{p.relative_to(ROOT)}`' for p in FILES],'']
 FILES[1].write_text('\n'.join(lines),encoding='utf-8')
 print('SELECTED_WEIGHT',selected,flush=True); print('INNER_SCORES\n'+pd.DataFrame(weight_scores).to_string(index=False),flush=True); print('OUTER_METRICS\n'+metric_df.to_string(index=False),flush=True); print('BOOTSTRAP',json.dumps(audit['paired_bootstrap_nested_blend_minus_production'],indent=2),flush=True); print('REPORT='+str(FILES[1].relative_to(ROOT)),flush=True)
if __name__=='__main__': main()
