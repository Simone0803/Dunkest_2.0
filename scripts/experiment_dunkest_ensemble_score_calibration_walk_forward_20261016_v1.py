#!/usr/bin/env python3
"""Evaluate past-only residual calibration of certified OOS PDK forecasts.

Uses saved expanding-origin predictions, with 2025/26 excluded completely.
For each evaluation season, every calibrator is fit only on earlier OOS seasons.
This is an audit/experiment; production code is never changed.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'
SOURCE=OUT/'dunkest_production_ensemble_expanding_oos_20261014_v1_predictions.csv'
STAMP='dunkest_ensemble_score_calibration_walk_forward_20261016_v1'
METRICS=OUT/f'{STAMP}_metrics.csv'; REPORT=OUT/f'{STAMP}.md'; AUDIT=OUT/f'{STAMP}.json'
EVAL_SEASONS=['2022-23','2023-24','2024-25']
BINS=[-np.inf,5,10,15,20,25,30,np.inf]
LABELS=['<5','5-10','10-15','15-20','20-25','25-30','30+']

def score(y,p,h):
 y=np.asarray(y,float); p=np.asarray(p,float); e=p-y; o={'n':len(y),'mae':float(np.mean(np.abs(e))),'rmse':float(np.sqrt(np.mean(e*e))),'bias_pred_minus_actual':float(np.mean(e))}
 for t in (25,30):
  m=y>=t; o[f'mae_actual_ge{t}']=float(np.mean(np.abs(e[m]))) if m.any() else np.nan; o[f'n_actual_ge{t}']=int(m.sum())
 for lo,hi,label in [(20,np.inf,'predicted_ge20'),(25,np.inf,'predicted_ge25'),(30,np.inf,'predicted_ge30')]:
  m=(p>=lo)&(p<hi); o[f'mae_{label}']=float(np.mean(np.abs(e[m]))) if m.any() else np.nan; o[f'bias_{label}']=float(np.mean(e[m])) if m.any() else np.nan; o[f'n_{label}']=int(m.sum())
 return o

def fit_calibration(cal, mode, shrink):
 # residual is actual - raw prediction; fit exclusively on prior OOS seasons.
 p=cal.prediction.to_numpy(float); r=(cal.actual_pdk-cal.prediction).to_numpy(float)
 global_mean=float(np.mean(r)); global_median=float(np.median(r))
 if mode=='none': return {'global':0.,'bands':{}}
 if mode=='global_mean': return {'global':global_mean*shrink,'bands':{}}
 if mode=='global_median': return {'global':global_median*shrink,'bands':{}}
 bands={}; cats=pd.cut(p,bins=BINS,labels=LABELS,right=False)
 for lab in LABELS:
  vals=r[np.asarray(cats.astype(str)==lab)]
  # Empirical band mean shrunk toward global mean; sparse bins fall back smoothly.
  bands[lab]=float((len(vals)*np.mean(vals)+shrink*global_mean)/(len(vals)+shrink)) if len(vals) else global_mean
 return {'global':global_mean,'bands':bands}

def apply_calibration(test, mode, params):
 p=test.prediction.to_numpy(float)
 if mode=='band_mean':
  cats=pd.cut(p,bins=BINS,labels=LABELS,right=False).astype(str)
  return p+np.array([params['bands'].get(c,params['global']) for c in cats])
 return p+params['global']

def main():
 for f in (METRICS,REPORT,AUDIT):
  if f.exists(): raise SystemExit(f'Refusing to overwrite {f}')
 if not SOURCE.exists(): raise SystemExit(f'Missing OOS predictions: {SOURCE}')
 df=pd.read_csv(SOURCE)
 required={'test_season','actual_pdk','prediction','history_games_before_target'}
 if not required.issubset(df.columns): raise SystemExit(f'Missing columns: {required-set(df.columns)}')
 df['test_season']=df.test_season.astype(str)
 # Hard exclusion: final 2025/26 holdout is never loaded into calibration/evaluation frames.
 df=df.loc[df.test_season.isin(['2021-22','2022-23','2023-24','2024-25'])].copy()
 if df.empty: raise SystemExit('No eligible pre-holdout OOS predictions.')
 records=[]; fold_details=[]
 for season in EVAL_SEASONS:
  test=df.loc[df.test_season.eq(season)].copy()
  cal=df.loc[df.test_season.lt(season)].copy()
  if test.empty or cal.empty: raise SystemExit(f'Missing prior calibration/test rows for {season}')
  h=pd.to_numeric(test.history_games_before_target,errors='coerce').fillna(0).to_numpy(float)
  configs=[('none',0),('global_mean',0.25),('global_mean',0.5),('global_mean',0.75),('global_mean',1.0),('global_median',0.5),('global_median',1.0)]
  for sh in (100,250,500,1000): configs.append(('band_mean',sh))
  for mode,sh in configs:
   params=fit_calibration(cal,mode,sh if mode=='band_mean' else sh)
   pred=apply_calibration(test,mode,params)
   met=score(test.actual_pdk.to_numpy(float),pred,h)
   records.append({'test_season':season,'method':mode,'shrinkage_rows':sh,'calibration_seasons':';'.join(sorted(cal.test_season.unique())),'calibration_rows':len(cal),**met})
   if mode=='band_mean': fold_details.append({'test_season':season,'shrinkage_rows':sh,'global_correction':params['global'],'band_corrections':params['bands']})
 metrics=pd.DataFrame(records); metrics.to_csv(METRICS,index=False)
 pooled=[]
 for method,sh in metrics[['method','shrinkage_rows']].drop_duplicates().itertuples(index=False,name=None):
  g=metrics[(metrics.method==method)&(metrics.shrinkage_rows==sh)]
  if len(g)!=len(EVAL_SEASONS): continue
  pooled.append({'method':method,'shrinkage_rows':sh,'n':int(g.n.sum()),'mae':float(np.average(g.mae,weights=g.n)),'rmse':float(np.sqrt(np.average(g.rmse**2,weights=g.n))),'bias':float(np.average(g.bias_pred_minus_actual,weights=g.n)),'mae_actual_ge25':float(np.average(g.mae_actual_ge25,weights=g.n_actual_ge25)),'mae_actual_ge30':float(np.average(g.mae_actual_ge30,weights=g.n_actual_ge30)),'mae_predicted_ge25':float(np.average(g.mae_predicted_ge25,weights=g.n_predicted_ge25)),'bias_predicted_ge25':float(np.average(g.bias_predicted_ge25,weights=g.n_predicted_ge25))})
 pool=pd.DataFrame(pooled).sort_values(['mae','rmse'])
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'source':str(SOURCE.relative_to(ROOT)),'evaluation_seasons':EVAL_SEASONS,'calibration_protocol':'For each evaluation season, fit additive residual correction on strictly earlier seasons\' out-of-sample predictions only. Final 2025/26 holdout and 2026/27 prospective test excluded.','residual_definition':'actual minus prediction; correction is added to raw prediction.','score_bins':LABELS,'fold_band_corrections':fold_details,'pooled_metrics':pool.to_dict('records'),'production_changed':False,'holdout_2025_26_used':False,'prospective_2026_27_used':False}
 AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
 report=['# Walk-forward score-band ensemble calibration','','Generated UTC: '+audit['created_utc'],'','## Protocol','','- Evaluated 2022/23–2024/25 only, each season calibrated from earlier OOS seasons.','- Correction methods: no correction, shrunk global mean/median residual, and score-band residual means shrunk toward the global mean.','- Score bands are based only on raw predicted score, never on the evaluation target.','- 2025/26 final holdout and 2026/27 prospective test are excluded.','- Diagnostic only; production code is unchanged.','','## Pooled results','',pool.to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Per-season results','',metrics.to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Interpretation','','Prefer only a correction that improves pooled MAE/RMSE, reduces bias, and remains stable across all three seasons without worsening actual-score >=25 or >=30 cohorts. This evaluates a core historical OOS forecast and does not establish full lineup-level gains.','']
 REPORT.write_text('\n'.join(report),encoding='utf-8')
 print('POOLED RESULTS\n'+pool.to_string(index=False,float_format=lambda x:f'{x:.5f}'),flush=True)
 print('PER SEASON\n'+metrics.to_string(index=False,float_format=lambda x:f'{x:.5f}'),flush=True)
 print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
if __name__=='__main__': main()
