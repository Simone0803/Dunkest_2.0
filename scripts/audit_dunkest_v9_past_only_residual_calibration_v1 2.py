#!/usr/bin/env python3
"""Evaluate past-only affine residual calibration on saved V9 OOF predictions."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link_predictions.csv'
OUT=ROOT/'reports/audit'
MODEL='historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6'
BOOT=3000; SEED=20261013

def metrics(y,p):
 e=np.asarray(p)-np.asarray(y)
 return {'mae':float(np.mean(np.abs(e))),'rmse':float(np.sqrt(np.mean(e*e))),'bias_pred_minus_actual':float(e.mean())}
def ci_delta(g, pred_col, raw_col, reps, rng):
 z=g.copy(); z['_cluster']=z.season_id.astype(str)+':'+z.round_index.astype(str)
 z['_delta']=(z[pred_col]-z.actual_pdk_round_total).abs()-(z[raw_col]-z.actual_pdk_round_total).abs()
 obs=float(z['_delta'].mean()); byseason={}
 for s,sg in z.groupby('season_id'):
  byseason[s]=[v['_delta'].to_numpy(float) for _,v in sg.groupby('_cluster')]
 draws=np.empty(reps)
 for i in range(reps):
  tot=0.; n=0
  for clusters in byseason.values():
   if not clusters: continue
   for j in rng.integers(0,len(clusters),size=len(clusters)):
    vals=clusters[j]; tot+=float(vals.sum()); n+=len(vals)
  draws[i]=tot/n
 lo,hi=np.quantile(draws,[.025,.975])
 return obs,float(lo),float(hi),int(z['_cluster'].nunique())
def main():
 if not SRC.exists(): raise SystemExit(f'Missing {SRC}')
 d=pd.read_csv(SRC)
 d=d[d.feature_family.eq(MODEL)].copy()
 for c in ['actual_pdk_round_total','predicted_pdk_round_total']:
  d[c]=pd.to_numeric(d[c],errors='coerce')
 d=d.dropna(subset=['actual_pdk_round_total','predicted_pdk_round_total','season_id','season','round_index'])
 seasons=sorted(d.season.unique())
 out=[]; coeff=[]; predictions=[]; rng=np.random.default_rng(SEED)
 # At least one complete prior held-out season is required before calibration.
 for i,season in enumerate(seasons):
  if i<1: continue
  train=d[d.season.isin(seasons[:i])].copy(); test=d[d.season.eq(season)].copy()
  if len(train)<1000 or test.empty: continue
  xtr=train[['predicted_pdk_round_total']].to_numpy(); ytr=train.actual_pdk_round_total.to_numpy()
  cal=LinearRegression().fit(xtr,ytr)
  test['raw_prediction']=test.predicted_pdk_round_total
  test['affine_calibrated_prediction']=cal.predict(test[['predicted_pdk_round_total']].to_numpy())
  # Also test past-only intercept correction as a lower-variance alternative.
  offset=float((train.actual_pdk_round_total-train.predicted_pdk_round_total).mean())
  test['mean_bias_corrected_prediction']=test.raw_prediction+offset
  for name,col in [('raw','raw_prediction'),('past_only_affine','affine_calibrated_prediction'),('past_only_mean_bias','mean_bias_corrected_prediction')]:
   m=metrics(test.actual_pdk_round_total,test[col]); out.append({'test_season':season,'method':name,'n':len(test),**m})
  for method,col in [('past_only_affine','affine_calibrated_prediction'),('past_only_mean_bias','mean_bias_corrected_prediction')]:
   delta,lo,hi,nc=ci_delta(test,col,'raw_prediction',BOOT,rng)
   out[-1 if method=='past_only_mean_bias' else -2].update({'delta_mae_vs_raw':delta,'ci95_low_delta':lo,'ci95_high_delta':hi,'round_clusters':nc})
  coeff.append({'test_season':season,'calibration_train_seasons':';'.join(seasons[:i]),'n_train_oof':len(train),'n_test':len(test),'affine_intercept':float(cal.intercept_),'affine_slope':float(cal.coef_[0]),'mean_residual_offset':offset,'raw_train_mae':metrics(ytr,xtr[:,0])['mae'],'calibrated_train_mae':metrics(ytr,cal.predict(xtr))['mae']})
  keep=['season_id','season','round_index','source_week','source_round','player_name','actual_pdk_round_total','raw_prediction','affine_calibrated_prediction','mean_bias_corrected_prediction']
  predictions.append(test[keep])
 result=pd.DataFrame(out); co=pd.DataFrame(coeff); pred=pd.concat(predictions,ignore_index=True) if predictions else pd.DataFrame()
 tag='20261013_v1'; paths={'metrics':OUT/f'dunkest_v9_past_only_calibration_{tag}_metrics.csv','coefficients':OUT/f'dunkest_v9_past_only_calibration_{tag}_coefficients.csv','predictions':OUT/f'dunkest_v9_past_only_calibration_{tag}_predictions.csv','json':OUT/f'dunkest_v9_past_only_calibration_{tag}.json','report':OUT/f'dunkest_v9_past_only_calibration_{tag}.md'}
 result.to_csv(paths['metrics'],index=False); co.to_csv(paths['coefficients'],index=False); pred.to_csv(paths['predictions'],index=False)
 payload={'created_utc':datetime.now(timezone.utc).isoformat(),'source_predictions':str(SRC.relative_to(ROOT)),'model_family':MODEL,'protocol':'for each target season, calibrator is fitted only on earlier seasons\' expanding-origin OOF predictions and labels; evaluate on next untouched season','calibration_methods':['OLS affine mapping actual ~ raw prediction','mean residual offset estimated on earlier seasons'],'bootstrap_replicates':BOOT,'bootstrap_seed':SEED,'prospective_holdout_read':False,'production_changed':False,'metrics':result.to_dict(orient='records'),'coefficients':co.to_dict(orient='records'),'limitations':['Only 2023/24 and 2024/25 can be evaluated because calibration needs at least one prior OOF season.','The experiment evaluates game-level score calibration, not lineup-level utility or coach/transfer scoring.','Two test seasons are not sufficient for production promotion; all results are exploratory.','No 2025/26 final holdout or frozen 2026/27 GW1 predictions were read or changed.']}
 paths['json'].write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 def md(df):
  if df.empty:return '(no rows)'
  z=df.round(4); cols=list(z.columns); rows=[[str(v) for v in row] for row in z.itertuples(index=False,name=None)]; widths=[max(len(str(cols[i])),*(len(row[i]) for row in rows)) for i in range(len(cols))]; return '\n'.join(['| '+' | '.join(str(cols[i]).ljust(widths[i]) for i in range(len(cols)))+' |','| '+' | '.join('-'*widths[i] for i in range(len(cols)))+' |']+['| '+' | '.join(row[i].ljust(widths[i]) for i in range(len(cols)))+' |' for row in rows])
 report=['# V9 past-only residual calibration audit','',f"Created UTC: {payload['created_utc']}",'','## Protocol','','For each held-out season, the affine calibrator and mean-residual offset are fitted only on earlier seasons’ saved OOF predictions and labels. The calibration is then evaluated on the next season. The first OOF season is used only as calibration training data; no 2025/26 or prospective 2026/27 holdout is read.','', '## Metrics','',md(result),'','`delta_mae_vs_raw` is calibrated MAE minus raw MAE; negative favors calibration. Confidence intervals resample round clusters within each held-out season.','', '## Fitted coefficients','',md(co),'','## Limitations','',*[f'- {v}' for v in payload['limitations']],'','## Artifacts','',*[f'- `{v.relative_to(ROOT)}`' for v in paths.values()],'']
 paths['report'].write_text('\n'.join(report),encoding='utf-8')
 print('REPORT',paths['report']); print(result.to_string(index=False)); print('\nCOEFFICIENTS'); print(co.to_string(index=False))
if __name__=='__main__': main()
