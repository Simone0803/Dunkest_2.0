#!/usr/bin/env python3
"""Past-only score-band bias calibration on production ensemble OOF predictions.

Calibrator is learned from earlier-season OOF forecasts only, with shrinkage to the
pooled residual median. The 2025/26 season is excluded; no production files change.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT=Path(__file__).resolve().parents[1]
PRED=ROOT/'reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261014_v1_predictions.csv'
OUT=ROOT/'reports/audit'
STEM='dunkest_score_band_bias_calibration_20261014_v1'
FILES=[OUT/f'{STEM}.json',OUT/f'{STEM}.md',OUT/f'{STEM}_metrics.csv',OUT/f'{STEM}_predictions.csv',OUT/f'{STEM}_cohorts.csv']
BINS=[-np.inf,5,10,15,20,25,np.inf]
LABELS=['<5','5-10','10-15','15-20','20-25','25+']

def metric(y,p):
 y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
 return {'n':len(y),'mae':float(np.mean(np.abs(e))),'rmse':float(np.sqrt(np.mean(e**2))),'bias_pred_minus_actual':float(e.mean())}

def main():
 if any(p.exists() for p in FILES): raise SystemExit('Refusing to overwrite versioned calibration outputs')
 df=pd.read_csv(PRED)
 df['game_date']=pd.to_datetime(df.game_date,errors='coerce')
 for c in ['actual_pdk','predicted_pdk','history_games']:
  df[c]=pd.to_numeric(df[c],errors='coerce')
 df=df.dropna(subset=['test_season','method','game_date','actual_pdk','predicted_pdk']).copy()
 # Use only the actual production ensemble configuration; exclude final/previous holdout.
 df=df.loc[df.method.eq('all_prior_seasons') & df.test_season.isin(['2022-23','2023-24','2024-25'])].copy()
 if df.empty: raise SystemExit('No eligible production-ensemble OOF predictions')
 df['residual']=df.predicted_pdk-df.actual_pdk
 df['pred_band']=pd.cut(df.predicted_pdk,bins=BINS,labels=LABELS,right=False)
 allpred=[]; metricrows=[]; cohortrows=[]; fold_info=[]
 for season in ['2023-24','2024-25']:
  train=df.loc[df.test_season.lt(season)].copy(); test=df.loc[df.test_season.eq(season)].copy()
  if train.empty or test.empty: raise SystemExit(f'Missing strict prior calibration/test fold {season}')
  global_med=float(train.residual.median())
  # Small bins are shrunk to the pooled correction; no target-season labels enter.
  corrections={}; counts={}
  for band in LABELS:
   g=train.loc[train.pred_band.astype(str).eq(band),'residual']
   n=len(g); counts[band]=n
   alpha=n/(n+1000.0)
   corrections[band]=float(alpha*g.median()+(1-alpha)*global_med) if n else global_med
  t=test.copy()
  t['calibration_season']=season
  t['global_median_correction']=global_med
  t['band_correction']=t.pred_band.astype(str).map(corrections).astype(float)
  t['calibrated_pdk']=t.predicted_pdk-t.band_correction
  t['raw_error']=t.predicted_pdk-t.actual_pdk
  t['calibrated_error']=t.calibrated_pdk-t.actual_pdk
  # Keep correction from generating physically implausible negative score forecasts.
  t['calibrated_pdk']=t.calibrated_pdk.clip(lower=0)
  for method,col in [('raw','predicted_pdk'),('pooled_median_offset','predicted_pdk'),('score_band_shrinkage','calibrated_pdk')]:
   p=t[col].to_numpy(float).copy()
   if method=='pooled_median_offset': p=np.maximum(0,p-global_med)
   for cohort,mask in [('all',np.ones(len(t),dtype=bool)),('actual_ge_25',t.actual_pdk.ge(25).to_numpy()),('actual_ge_30',t.actual_pdk.ge(30).to_numpy()),('predicted_ge_20',t.predicted_pdk.ge(20).to_numpy()),('low_history_le_5',t.history_games.le(5).fillna(False).to_numpy()),('history_gt_5',t.history_games.gt(5).fillna(False).to_numpy())]:
    if mask.sum(): metricrows.append({'test_season':season,'method':method,'cohort':cohort,**metric(t.actual_pdk.to_numpy()[mask],p[mask])})
  for band,g in t.groupby('pred_band',observed=True):
   for method,col in [('raw','predicted_pdk'),('score_band_shrinkage','calibrated_pdk')]:
    cohortrows.append({'test_season':season,'predicted_band':str(band),'method':method,'mean_predicted':float(g[col].mean()),'mean_actual':float(g.actual_pdk.mean()),'bias':float((g[col]-g.actual_pdk).mean()),'n':len(g)})
  # Date-cluster paired bootstrap for MAE delta, deterministic seed per fold.
  wide=t[['game_date','actual_pdk','predicted_pdk','calibrated_pdk']].copy()
  wide['day']=wide.game_date.dt.strftime('%Y-%m-%d')
  days=wide.day.unique(); rng=np.random.default_rng(20261014+int(season[:4]))
  deltas=[]
  grouped={d:wide.loc[wide.day.eq(d)] for d in days}
  for _ in range(2000):
   sample=rng.choice(days,size=len(days),replace=True)
   yy=np.concatenate([grouped[d].actual_pdk.to_numpy(float) for d in sample])
   pr=np.concatenate([grouped[d].predicted_pdk.to_numpy(float) for d in sample])
   pc=np.concatenate([grouped[d].calibrated_pdk.to_numpy(float) for d in sample])
   deltas.append(np.mean(np.abs(pc-yy))-np.mean(np.abs(pr-yy)))
  fold_info.append({'test_season':season,'calibration_seasons':sorted(train.test_season.unique()),'n_calibration':len(train),'n_test':len(test),'global_median_residual':global_med,'band_residual_medians':corrections,'band_calibration_counts':counts,'date_clusters':len(days),'paired_bootstrap_delta_mae_calibrated_minus_raw':float(np.mean(np.abs(t.calibrated_pdk-t.actual_pdk))-np.mean(np.abs(t.predicted_pdk-t.actual_pdk))),'paired_bootstrap_ci95_delta_mae':[float(np.quantile(deltas,.025)),float(np.quantile(deltas,.975))]})
  allpred.append(t)
 metrics=pd.DataFrame(metricrows); cohorts=pd.DataFrame(cohortrows); predictions=pd.concat(allpred,ignore_index=True)
 metrics.to_csv(FILES[2],index=False); predictions.to_csv(FILES[3],index=False); cohorts.to_csv(FILES[4],index=False)
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'source':str(PRED.relative_to(ROOT)),'test_seasons':['2023-24','2024-25'],'calibration':'strictly earlier OOF seasons; predicted score bands; residual median shrinkage alpha=n/(n+1000); corrections subtracted from prediction','bootstrap':'paired resampling by game date, 2000 replicates, deterministic seed','holdout_policy':'2025/26 excluded; 2026/27 frozen GW1 untouched','production_changed':False,'folds':fold_info,'metrics':metricrows,'prediction_bands':cohortrows,'decision_rule':'Promote only if paired OOS MAE delta CI is below zero in both folds and high-score cohorts improve without material ordinary-score regressions; otherwise keep research-only.'}
 FILES[0].write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 lines=['# Past-only score-band residual calibration audit','',f"Generated UTC: {audit['created_utc']}",'','## Protocol','','- Uses production-ensemble out-of-fold predictions only.','- Calibrators for each test season use strictly earlier seasons.','- Correction is residual median by predicted-score band, shrunk toward global median by n/(n+1000).','- Paired date-cluster bootstrap, 2,000 resamples, compares calibrated and raw MAE.','- This is an offline experiment only; no production model, weights, configuration, or frozen GW1 artifact changed.','','## Fold decisions','','| Test season | Calibration seasons | N | Raw MAE | Calibrated MAE | Delta MAE | 95% paired CI | Decision |','|---|---|---:|---:|---:|---:|---|---|']
 for f in fold_info:
  raw=next(x for x in metricrows if x['test_season']==f['test_season'] and x['method']=='raw' and x['cohort']=='all')
  cal=next(x for x in metricrows if x['test_season']==f['test_season'] and x['method']=='score_band_shrinkage' and x['cohort']=='all')
  lo,hi=f['paired_bootstrap_ci95_delta_mae']; decision='candidate' if hi<0 else 'do not promote'
  lines.append(f"| {f['test_season']} | {';'.join(f['calibration_seasons'])} | {f['n_test']} | {raw['mae']:.4f} | {cal['mae']:.4f} | {cal['mae']-raw['mae']:+.4f} | [{lo:+.4f}, {hi:+.4f}] | {decision} |")
 lines += ['','## Cohort metrics','','| Test season | Method | Cohort | N | MAE | RMSE | Bias |','|---|---|---|---:|---:|---:|---:|']
 for r in metricrows: lines.append(f"| {r['test_season']} | {r['method']} | {r['cohort']} | {r['n']} | {r['mae']:.4f} | {r['rmse']:.4f} | {r['bias_pred_minus_actual']:.4f} |")
 lines += ['','## Predicted-score bands','','| Test season | Band | Method | N | Mean prediction | Mean actual | Bias |','|---|---|---|---:|---:|---:|---:|']
 for r in cohortrows: lines.append(f"| {r['test_season']} | {r['predicted_band']} | {r['method']} | {r['n']} | {r['mean_predicted']:.3f} | {r['mean_actual']:.3f} | {r['bias']:+.3f} |")
 lines += ['','## Interpretation','','A calibration method is not promoted based on pooled MAE alone. It must improve paired date-cluster MAE in both folds and avoid material regressions in the high-score cohort. Conditional-on-actual high-score metrics are diagnostic only because actual score is unknown at inference. The predicted-score-band analysis is the actionable counterpart.','', '## Artifacts','',f'- Metrics: `{FILES[2].relative_to(ROOT)}`',f'- Calibrated predictions: `{FILES[3].relative_to(ROOT)}`',f'- Predicted-band diagnostics: `{FILES[4].relative_to(ROOT)}`',f'- Audit JSON: `{FILES[0].relative_to(ROOT)}`','']
 FILES[1].write_text('\n'.join(lines),encoding='utf-8')
 print('FOLDS')
 for f in fold_info: print(json.dumps(f,ensure_ascii=False))
 print('\nMETRICS\n'+metrics.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
 print('\nREPORT='+str(FILES[1]))
if __name__=='__main__': main()
