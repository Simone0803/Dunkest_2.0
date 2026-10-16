#!/usr/bin/env python3
"""Evaluate shrunk affine/residual-on-score calibrators using past OOS folds only."""
from pathlib import Path
from datetime import datetime,timezone
import json,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/audit';SRC=OUT/'dunkest_production_ensemble_expanding_oos_20261014_v1_predictions.csv';TAG='dunkest_affine_score_calibration_walk_forward_20261016_v1';CSV=OUT/f'{TAG}_metrics.csv';MD=OUT/f'{TAG}.md';JS=OUT/f'{TAG}.json';SEASONS=['2022-23','2023-24','2024-25']
def metrics(y,p):
 e=np.asarray(p)-np.asarray(y);y=np.asarray(y);p=np.asarray(p);o={'n':len(y),'mae':float(abs(e).mean()),'rmse':float(np.sqrt((e*e).mean())),'bias':float(e.mean())}
 for t in (25,30):
  m=y>=t;o[f'mae_actual_ge{t}']=float(abs(e[m]).mean()) if m.any() else np.nan;o[f'n_actual_ge{t}']=int(m.sum())
 for t in (20,25,30):
  m=p>=t;o[f'mae_pred_ge{t}']=float(abs(e[m]).mean()) if m.any() else np.nan;o[f'bias_pred_ge{t}']=float(e[m].mean()) if m.any() else np.nan;o[f'n_pred_ge{t}']=int(m.sum())
 return o
def main():
 for x in (CSV,MD,JS):
  if x.exists():raise SystemExit(f'Refusing to overwrite {x}')
 d=pd.read_csv(SRC);d['test_season']=d.test_season.astype(str);d=d[d.test_season.isin(['2021-22']+SEASONS)].copy();rows=[];details=[]
 for season in SEASONS:
  cal=d[d.test_season<season];test=d[d.test_season==season]
  if cal.empty or test.empty:raise SystemExit('Missing fold '+season)
  x=cal.prediction.to_numpy(float);r=(cal.actual_pdk-cal.prediction).to_numpy(float);xm=float(x.mean());xs=float(x.std()) or 1.;z=(x-xm)/xs
  # OLS residual-on-score fit from previous OOS seasons only.
  design=np.column_stack([np.ones(len(z)),z]);coef=np.linalg.lstsq(design,r,rcond=None)[0];intercept=float(coef[0]);slope=float(coef[1]/xs)
  tp=test.prediction.to_numpy(float);y=test.actual_pdk.to_numpy(float);raw=tp.copy()
  configs=[('none',0.,0.,np.inf),('global_bias',0.,1.,np.inf)]
  for shrink in (.25,.5,.75,1.):
   for clip in (1.,2.,3.,np.inf):
    configs.append(('affine',shrink,clip,np.inf))
    for gate in (20.,25.):configs.append(('affine_gated',shrink,clip,gate))
  for mode,scale,clip,gate in configs:
   pred=raw.copy()
   if mode=='global_bias':pred+=scale*float(r.mean())
   elif mode.startswith('affine'):
    corr=scale*(intercept+slope*(tp-xm));corr=np.clip(corr,-clip,clip)
    if mode=='affine_gated':corr=np.where(tp>=gate,corr,0.)
    pred+=corr
   m=metrics(y,pred);rows.append({'season':season,'method':mode,'correction_scale':scale,'correction_clip':clip,'gate_prediction':gate,'calibration_seasons':';'.join(sorted(cal.test_season.unique())),'calibration_rows':len(cal),'intercept':intercept,'slope_per_score':slope,**m})
  details.append({'season':season,'calibration_seasons':sorted(cal.test_season.unique()),'intercept':intercept,'slope_per_score':slope,'mean_prediction':xm,'calibration_rows':len(cal)})
 out=pd.DataFrame(rows);out.to_csv(CSV,index=False);po=[]
 for keys,g in out.groupby(['method','correction_scale','correction_clip','gate_prediction']):
  if len(g)!=len(SEASONS):continue
  po.append({'method':keys[0],'scale':keys[1],'clip':keys[2],'gate':keys[3],'n':int(g.n.sum()),'mae':float(np.average(g.mae,weights=g.n)),'rmse':float(np.sqrt(np.average(g.rmse**2,weights=g.n))),'bias':float(np.average(g.bias,weights=g.n)),'mae_actual_ge25':float(np.average(g.mae_actual_ge25,weights=g.n_actual_ge25)),'mae_actual_ge30':float(np.average(g.mae_actual_ge30,weights=g.n_actual_ge30)),'mae_pred_ge25':float(np.average(g.mae_pred_ge25,weights=g.n_pred_ge25)),'bias_pred_ge25':float(np.average(g.bias_pred_ge25,weights=g.n_pred_ge25))})
 pool=pd.DataFrame(po).sort_values(['mae','rmse']);baseline=pool[pool.method=='none'].iloc[0];safe=pool[(pool.method!='none')&(pool.mae<=baseline.mae)&(pool.rmse<=baseline.rmse)&(pool.mae_actual_ge25<=baseline.mae_actual_ge25)&(pool.mae_actual_ge30<=baseline.mae_actual_ge30)]
 payload={'created_utc':datetime.now(timezone.utc).isoformat(),'source':str(SRC.relative_to(ROOT)),'evaluation_seasons':SEASONS,'method':'Fit residual = actual - prediction as affine function of score on earlier seasons\' OOS predictions; shrink and clip correction; optional score gate.','fold_fits':details,'pooled':pool.to_dict('records'),'holdout_2025_26_used':False,'prospective_2026_27_used':False,'production_changed':False};JS.write_text(json.dumps(payload,indent=2,ensure_ascii=False,default=str)+'\n')
 MD.write_text('\n'.join(['# Affine score calibration walk-forward','','Generated UTC: '+payload['created_utc'],'','## Protocol','','Only prior-season out-of-sample predictions fit the affine residual correction. Candidate corrections are shrunk and clipped; some apply only above a raw predicted-score gate. 2025/26 and 2026/27 are excluded.','','## Pooled results','',pool.head(30).to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Candidates meeting all pooled non-regression constraints','',safe.head(20).to_string(index=False,float_format=lambda x:f'{x:.5f}') if len(safe) else 'None.','','## Per-fold results','',out.to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Fold calibration coefficients','',json.dumps(details,indent=2),'','Production unchanged. A candidate is not promotable based on pooled results alone; fold stability and tail-cohort errors remain mandatory.',''])+'\n')
 print('POOLED TOP\n'+pool.head(20).to_string(index=False,float_format=lambda x:f'{x:.5f}'),flush=True);print('SAFE',len(safe),flush=True);print('REPORT='+str(MD.relative_to(ROOT)),flush=True)
if __name__=='__main__':main()
