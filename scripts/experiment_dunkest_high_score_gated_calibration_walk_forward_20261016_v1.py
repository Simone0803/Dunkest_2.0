#!/usr/bin/env python3
"""Past-only high-score gated additive calibration on certified OOS predictions."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'; SRC=OUT/'dunkest_production_ensemble_expanding_oos_20261014_v1_predictions.csv'; STAMP='dunkest_high_score_gated_calibration_walk_forward_20261016_v1'; CSV=OUT/f'{STAMP}_metrics.csv'; JSON=OUT/f'{STAMP}.json'; MD=OUT/f'{STAMP}.md'
SEASONS=['2022-23','2023-24','2024-25']; BINS=[-np.inf,5,10,15,20,25,30,np.inf]; LABELS=['<5','5-10','10-15','15-20','20-25','25-30','30+']
def metrics(y,p):
 y=np.asarray(y,float);p=np.asarray(p,float);e=p-y;o={'n':len(y),'mae':float(np.mean(abs(e))),'rmse':float(np.sqrt(np.mean(e*e))),'bias':float(e.mean())}
 for t in (25,30):
  m=y>=t;o[f'mae_actual_ge{t}']=float(np.mean(abs(e[m]))) if m.any() else np.nan;o[f'n_actual_ge{t}']=int(m.sum())
 for t in (20,25,30):
  m=p>=t;o[f'mae_pred_ge{t}']=float(np.mean(abs(e[m]))) if m.any() else np.nan;o[f'bias_pred_ge{t}']=float(e[m].mean()) if m.any() else np.nan;o[f'n_pred_ge{t}']=int(m.sum())
 return o
def main():
 for p in (CSV,JSON,MD):
  if p.exists():raise SystemExit(f'Refusing overwrite {p}')
 d=pd.read_csv(SRC);d['test_season']=d.test_season.astype(str);d=d[d.test_season.isin(['2021-22']+SEASONS)].copy();rows=[];details=[]
 for season in SEASONS:
  tr=d[d.test_season<season];te=d[d.test_season==season]
  if tr.empty or te.empty:raise SystemExit(f'Missing fold {season}')
  pcal=tr.prediction.to_numpy(float); r=(tr.actual_pdk-tr.prediction).to_numpy(float); cats=pd.cut(pcal,bins=BINS,labels=LABELS,right=False).astype(str); global_r=float(r.mean())
  band={}
  for lab in LABELS:
   rr=r[np.asarray(cats==lab)];band[lab]={'n':int(len(rr)),'mean':float(rr.mean()) if len(rr) else global_r}
  raw=te.prediction.to_numpy(float); y=te.actual_pdk.to_numpy(float)
  configs=[('none',100,0.,np.inf)]
  for gate in (20.,25.,30.):
   for shrink in (100.,250.,500.,1000.):
    for scale in (.25,.5,.75,1.): configs.append(('gated_band',shrink,scale,gate))
   for scale in (.25,.5,.75,1.): configs.append(('gated_global',0.,scale,gate))
  for mode,shrink,scale,gate in configs:
   pred=raw.copy()
   if mode=='gated_band':
    tc=pd.cut(raw,bins=BINS,labels=LABELS,right=False).astype(str)
    for i,lab in enumerate(tc):
     if raw[i]>=gate:
      b=band.get(lab,{'n':0,'mean':global_r}); corr=(b['n']*b['mean']+shrink*global_r)/(b['n']+shrink) if b['n']+shrink else global_r; pred[i]+=scale*corr
   elif mode=='gated_global': pred[raw>=gate]+=scale*global_r
   m=metrics(y,pred); rows.append({'season':season,'method':mode,'shrinkage_rows':shrink,'correction_scale':scale,'gate_prediction':gate,'calibration_seasons':';'.join(sorted(tr.test_season.unique())),'calibration_rows':len(tr),**m})
  details.append({'season':season,'global_actual_minus_prediction':global_r,'band_residuals':band})
 out=pd.DataFrame(rows);out.to_csv(CSV,index=False);pool=[]
 for (mode,sh,scale,gate),g in out.groupby(['method','shrinkage_rows','correction_scale','gate_prediction']):
  if len(g)!=len(SEASONS):continue
  pool.append({'method':mode,'shrinkage_rows':sh,'correction_scale':scale,'gate_prediction':gate,'n':int(g.n.sum()),'mae':float(np.average(g.mae,weights=g.n)),'rmse':float(np.sqrt(np.average(g.rmse**2,weights=g.n))),'bias':float(np.average(g.bias,weights=g.n)),'mae_actual_ge25':float(np.average(g.mae_actual_ge25,weights=g.n_actual_ge25)),'mae_actual_ge30':float(np.average(g.mae_actual_ge30,weights=g.n_actual_ge30)),'mae_pred_ge25':float(np.average(g.mae_pred_ge25,weights=g.n_pred_ge25)),'bias_pred_ge25':float(np.average(g.bias_pred_ge25,weights=g.n_pred_ge25))})
 pooled=pd.DataFrame(pool).sort_values(['mae','rmse']);payload={'created_utc':datetime.now(timezone.utc).isoformat(),'source':str(SRC.relative_to(ROOT)),'evaluation_seasons':SEASONS,'calibration':'Only earlier OOS seasons; actual-minus-prediction residual correction; score band and gate depend only on forecast; 2025/26 and 2026/27 excluded.','band_residuals_by_fold':details,'pooled':pooled.to_dict('records'),'production_changed':False,'holdout_2025_26_used':False,'prospective_2026_27_used':False};JSON.write_text(json.dumps(payload,indent=2,ensure_ascii=False,default=str)+'\n')
 baseline=pooled[(pooled.method=='none')].iloc[0].to_dict();safe=pooled[(pooled.method!='none')&(pooled.mae<=baseline['mae'])&(pooled.rmse<=baseline['rmse'])&(pooled.mae_actual_ge25<=baseline['mae_actual_ge25'])&(pooled.mae_actual_ge30<=baseline['mae_actual_ge30'])]
 report=['# High-score gated residual calibration walk-forward','','Generated UTC: '+payload['created_utc'],'','## Protocol','','Each fold calibrates on prior seasons’ OOS predictions only. Correction is added only when raw prediction crosses the gate; band residual estimates are shrunk toward the past-only global residual. 2025/26 holdout and 2026/27 prospective test excluded.','','## Best pooled candidates','',pooled.head(25).to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Candidates meeting all pooled non-regression constraints','',safe.head(20).to_string(index=False,float_format=lambda x:f'{x:.5f}') if len(safe) else 'None. No candidate simultaneously improves/maintains MAE, RMSE, actual >=25 and actual >=30 cohorts versus no correction.','','## Per-fold metrics','',out.to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Decision','','No production changes. Any candidate must also show stable fold-level effects; pooled aggregates alone are insufficient for promotion.',''];MD.write_text('\n'.join(report)+'\n');print('POOLED TOP\n'+pooled.head(20).to_string(index=False,float_format=lambda x:f'{x:.5f}'),flush=True);print('SAFE CANDIDATES',len(safe),flush=True);print('REPORT='+str(MD.relative_to(ROOT)),flush=True)
if __name__=='__main__':main()
