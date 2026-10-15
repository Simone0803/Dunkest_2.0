#!/usr/bin/env python3
"""Sensitivity of past-only score-band residual correction strength."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'
PRED=OUT/'dunkest_multiseason_production_ensemble_walk_forward_20261014_v1_predictions.csv'
STEM='dunkest_score_band_calibration_strength_20261014_v1'
FILES=[OUT/f'{STEM}.json',OUT/f'{STEM}.md',OUT/f'{STEM}_metrics.csv']
BINS=[-np.inf,5,10,15,20,25,np.inf]; LABELS=['<5','5-10','10-15','15-20','20-25','25+']
def score(g,p):
 y=g.actual_pdk.to_numpy(float); e=np.asarray(p,float)-y
 return {'n':len(g),'mae':float(np.mean(abs(e))),'rmse':float(np.sqrt(np.mean(e**2))),'bias':float(e.mean())}
def main():
 if any(x.exists() for x in FILES): raise SystemExit('Refusing overwrite')
 d=pd.read_csv(PRED); d=d.loc[d.method.eq('all_prior_seasons') & d.test_season.isin(['2022-23','2023-24','2024-25'])].copy()
 for c in ['predicted_pdk','actual_pdk','history_games']: d[c]=pd.to_numeric(d[c],errors='coerce')
 d=d.dropna(subset=['predicted_pdk','actual_pdk']); d['band']=pd.cut(d.predicted_pdk,BINS,labels=LABELS,right=False); rows=[]; fold=[]
 for season in ['2023-24','2024-25']:
  cal=d.loc[d.test_season.lt(season)].copy(); t=d.loc[d.test_season.eq(season)].copy()
  med=float(cal.eval('predicted_pdk-actual_pdk').median()); cal['resid']=cal.predicted_pdk-cal.actual_pdk
  corr={}
  for band in LABELS:
   g=cal.loc[cal.band.astype(str).eq(band),'resid']; n=len(g); a=n/(n+1000.0)
   corr[band]=float(a*g.median()+(1-a)*med) if n else med
  t['corr']=t.band.astype(str).map(corr).astype(float)
  for strength in [0,.25,.5,.75,1.0]:
   p=np.maximum(0,t.predicted_pdk.to_numpy(float)-strength*t['corr'].to_numpy(float))
   for cohort,mask in [('all',np.ones(len(t),bool)),('actual_ge_25',t.actual_pdk.ge(25).to_numpy()),('actual_ge_30',t.actual_pdk.ge(30).to_numpy()),('predicted_ge_20',t.predicted_pdk.ge(20).to_numpy()),('low_history_le_5',t.history_games.le(5).fillna(False).to_numpy())]:
    if mask.sum(): rows.append({'season':season,'strength':strength,'cohort':cohort,**score(t.loc[mask],p[mask])})
  fold.append({'season':season,'calibration_seasons':sorted(cal.test_season.unique()),'n_cal':len(cal),'n_test':len(t),'global_median_residual':med,'band_corrections':corr})
 m=pd.DataFrame(rows); m.to_csv(FILES[2],index=False)
 payload={'created_utc':datetime.now(timezone.utc).isoformat(),'source':str(PRED.relative_to(ROOT)),'folds':fold,'strengths':[0,.25,.5,.75,1.0],'policy':'strictly past-season residuals; no target-season fit; 2025/26 and 2026/27 GW1 excluded','production_changed':False,'metrics':rows}
 FILES[0].write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
 lines=['# Score-band calibration strength sensitivity','',f"Generated UTC: {payload['created_utc']}",'','Corrections are trained on prior-season production-ensemble OOF residuals only. Strength 0 is raw; strength 1 applies the full shrunk score-band median residual correction. No production settings changed.','','## All-row metrics','','| Season | Strength | N | MAE | RMSE | Bias |','|---|---:|---:|---:|---:|---:|']
 for r in rows:
  if r['cohort']=='all': lines.append(f"| {r['season']} | {r['strength']:.2f} | {r['n']} | {r['mae']:.4f} | {r['rmse']:.4f} | {r['bias']:+.4f} |")
 lines += ['','## Cohort metrics','','| Season | Strength | Cohort | N | MAE | RMSE | Bias |','|---|---:|---|---:|---:|---:|---:|']
 for r in rows: lines.append(f"| {r['season']} | {r['strength']:.2f} | {r['cohort']} | {r['n']} | {r['mae']:.4f} | {r['rmse']:.4f} | {r['bias']:+.4f} |")
 lines += ['','## Decision rule','','A candidate is not promoted unless it improves both MAE and RMSE in both folds and does not materially regress actual-high-score or low-history cohorts. These folds are validation evidence; 2025/26 was examined in previous experiments and is not a pristine final holdout.','']
 FILES[1].write_text('\n'.join(lines))
 print(m.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
 print('REPORT',FILES[1])
if __name__=='__main__': main()
