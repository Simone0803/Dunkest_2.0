#!/usr/bin/env python3
"""Past-only residual correction experiment for historical Dunkest PDK predictions."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link_predictions.csv'
OUT=ROOT/'reports/audit'
STAMP='20261013_past_only_residual_correction_v1'
METRICS=OUT/f'dunkest_{STAMP}_metrics.csv'
PRED=OUT/f'dunkest_{STAMP}_predictions.csv'
REPORT=OUT/f'dunkest_{STAMP}.md'
AUDIT=OUT/f'dunkest_{STAMP}.json'
FAMILY='historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6'
FEATURES=['predicted_pdk_round_total','lagged_cr','lag1_pdk','opponent_def_allowed_pts_prev10','opponent_def_allowed_reb_prev10','opponent_def_allowed_ast_prev10','opponent_def_allowed_stl_prev10','opponent_def_allowed_blk_prev10','opponent_def_allowed_tov_prev10','opponent_pace_prev10','opponent_possessions_allowed_prev10','round_index']
SEASONS=['2022-23','2023-24','2024-25']

def metric(y,p):
 return {'n':int(len(y)),'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5),'bias_pred_minus_actual':float(np.mean(p-y))}

def main():
 for p in [METRICS,PRED,REPORT,AUDIT]:
  if p.exists(): raise SystemExit(f'Refusing to overwrite {p}')
 d=pd.read_csv(SOURCE)
 d=d.loc[d.feature_family.eq(FAMILY)&d.season.isin(SEASONS)].copy()
 d['target_date']=pd.to_datetime(d.target_date,errors='coerce')
 for c in FEATURES+['actual_pdk_round_total','predicted_pdk_round_total','round_index']:
  d[c]=pd.to_numeric(d[c],errors='coerce')
 d=d.dropna(subset=['season','target_date','actual_pdk_round_total','predicted_pdk_round_total']).copy()
 d['residual_actual_minus_pred']=d.actual_pdk_round_total-d.predicted_pdk_round_total
 if d.duplicated(['season','player_name','round_index']).any(): raise SystemExit('Duplicate player-round key')
 candidates={
  'ridge_residual':lambda:make_pipeline(SimpleImputer(strategy='median',add_indicator=True),Ridge(alpha=100.0)),
  'hgb_residual':lambda:make_pipeline(SimpleImputer(strategy='median',add_indicator=True),HistGradientBoostingRegressor(max_iter=160,learning_rate=.04,max_leaf_nodes=15,min_samples_leaf=120,l2_regularization=15.0,random_state=2026)),
  'et_residual':lambda:make_pipeline(SimpleImputer(strategy='median',add_indicator=True),ExtraTreesRegressor(n_estimators=160,min_samples_leaf=120,max_features=.9,n_jobs=-1,random_state=2026)),
 }
 rows=[]; preds=[]
 for season in ['2023-24','2024-25']:
  tr=d.loc[d.season.lt(season)].copy(); te=d.loc[d.season.eq(season)].copy()
  for name, factory in candidates.items():
   model=factory(); model.fit(tr[FEATURES],tr.residual_actual_minus_pred)
   correction=model.predict(te[FEATURES])
   pp=te[['season','season_id','round_index','source_week','source_round','player_name','target_date','actual_pdk_round_total','predicted_pdk_round_total','lagged_cr','lag1_pdk']].copy()
   pp['method']=name; pp['correction']=correction; pp['corrected_prediction']=(pp.predicted_pdk_round_total+correction).clip(lower=0)
   for segment,mask in [('all',np.ones(len(pp),dtype=bool)),('actual_ge_25',pp.actual_pdk_round_total.to_numpy()>=25),('predicted_ge_25',pp.predicted_pdk_round_total.to_numpy()>=25),('actual_ge_30',pp.actual_pdk_round_total.to_numpy()>=30)]:
    sub=pp.loc[mask]
    if len(sub):
     for version,values in [('raw',sub.predicted_pdk_round_total.to_numpy()),('corrected',sub.corrected_prediction.to_numpy())]:
      rows.append({'season':season,'method':name,'segment':segment,'prediction_version':version,**metric(sub.actual_pdk_round_total.to_numpy(),values)})
   preds.append(pp)
   print(f'{season} {name}: raw MAE={mean_absolute_error(te.actual_pdk_round_total,te.predicted_pdk_round_total):.4f}; corrected MAE={mean_absolute_error(te.actual_pdk_round_total,pp.corrected_prediction):.4f}',flush=True)
 pred=pd.concat(preds,ignore_index=True); met=pd.DataFrame(rows)
 rng=np.random.default_rng(20261013); boots=[]
 for (season,method),g in pred.groupby(['season','method'],sort=True):
  cluster=g.assign(raw_abs=(g.actual_pdk_round_total-g.predicted_pdk_round_total).abs(),corr_abs=(g.actual_pdk_round_total-g.corrected_prediction).abs()).groupby('target_date',sort=False).agg(n=('actual_pdk_round_total','size'),raw=('raw_abs','sum'),corr=('corr_abs','sum')).reset_index(drop=True)
  arr=cluster[['n','raw','corr']].to_numpy(float)
  chosen=rng.integers(0,len(arr),size=(5000,len(arr)))
  sampled=arr[chosen].sum(axis=1)
  ds=(sampled[:,2]-sampled[:,1])/sampled[:,0]
  boots.append({'season':season,'method':method,'n':len(g),'date_clusters':len(cluster),'raw_mae':float(mean_absolute_error(g.actual_pdk_round_total,g.predicted_pdk_round_total)),'corrected_mae':float(mean_absolute_error(g.actual_pdk_round_total,g.corrected_prediction)),'delta_mae_corrected_minus_raw':float(mean_absolute_error(g.actual_pdk_round_total,g.corrected_prediction)-mean_absolute_error(g.actual_pdk_round_total,g.predicted_pdk_round_total)),'ci95_low':float(np.quantile(ds,.025)),'ci95_high':float(np.quantile(ds,.975))})
 met.to_csv(METRICS,index=False); pred.to_csv(PRED,index=False)
 aud={'source':str(SOURCE.relative_to(ROOT)),'feature_family':FAMILY,'seasons_loaded':SEASONS,'validation_seasons':['2023-24','2024-25'],'target_season_2025_26_loaded':False,'methods':list(candidates),'features':FEATURES,'past_only':True,'production_changed':False,'metrics':boots,'note':'Correction is fit on saved prior-season OOF residuals. Exploratory second-stage correction, not independent model selection; no production promotion without repeatable improvement and lineup-level validation.'}
 AUDIT.write_text(json.dumps(aud,indent=2)+'\n')
 lines=['# Past-only residual correction experiment — V1','','## Design','',
 'A second-stage residual learner is fitted only on earlier-season saved OOF predictions. Validation is expanding-origin: 2023/24 is corrected using 2022/23 residuals; 2024/25 is corrected using 2022/23 and 2023/24 residuals. Only the V6 rest/schedule predictor family is used. 2025/26 and the prospective 2026/27 run are excluded.','','## Overall results','',pd.DataFrame(boots).to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Segment metrics','',met.to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Decision','','No production change is made. A correction is only a candidate if the direction is stable across both seasons, the date-cluster interval supports an improvement, and the gain also holds for high-scoring players without materially damaging ordinary-score players. These folds are exploratory and do not replace the reserved final holdout.','','## Artifacts','',f'- Predictions: {PRED.relative_to(ROOT)}',f'- Metrics: {METRICS.relative_to(ROOT)}',f'- Audit: {AUDIT.relative_to(ROOT)}','']
 REPORT.write_text('\n'.join(lines)+'\n')
 print('\nSUMMARY\n'+pd.DataFrame(boots).to_string(index=False),flush=True)
 print(f'REPORT={REPORT.relative_to(ROOT)}',flush=True)
if __name__=='__main__': raise SystemExit(main())
