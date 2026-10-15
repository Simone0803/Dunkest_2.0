#!/usr/bin/env python3
"""Nested walk-forward experiment for a production-ensemble / high-score-tail blend.

The blend weight is selected only on a later-in-time validation slice inside each
outer training block. Outer held-out seasons are never used to select the weight.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from dunkest.config import Settings
from dunkest.models.multiseason_training import adapt_certified_training_rows, DEFAULT_DATASET
from dunkest.models.predictor import train_models, _ensemble_predict
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'; STAMP='dunkest_production_tail_blend_nested_20261014_v1'
METRICS=OUT/f'{STAMP}_metrics.csv'; PRED=OUT/f'{STAMP}_predictions.csv'; REPORT=OUT/f'{STAMP}.md'; AUDIT=OUT/f'{STAMP}.json'
FOLDS=[('9','2022-23'),('13','2023-24'),('19','2024-25')]; BLEND_WEIGHTS=[0.0,0.25,0.5,0.75,1.0]
def score(y,p):
 y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
 return {'n':len(y),'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5),'bias_pred_minus_actual':float(e.mean())}
def _fit_tail(train, valid, cols):
 cols=[c for c in cols if c in train and pd.to_numeric(train[c],errors='coerce').notna().any()]
 xtr=train[cols].apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan)
 xva=valid[cols].apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan)
 med=xtr.median().fillna(0.0); xtr=xtr.fillna(med).fillna(0.0); xva=xva.fillna(med).fillna(0.0)
 y=pd.to_numeric(train.target_pdk_official,errors='coerce').to_numpy(float); high=y>=25.0; low=~high
 if high.sum()<100 or low.sum()<100: raise RuntimeError('Insufficient class rows for conditional tail model')
 clf=HistGradientBoostingClassifier(max_iter=160,learning_rate=.06,max_leaf_nodes=31,l2_regularization=5.0,min_samples_leaf=40,random_state=2026)
 hi=HistGradientBoostingRegressor(max_iter=180,learning_rate=.06,max_leaf_nodes=31,l2_regularization=5.0,min_samples_leaf=40,random_state=2026)
 lo=HistGradientBoostingRegressor(max_iter=180,learning_rate=.06,max_leaf_nodes=31,l2_regularization=5.0,min_samples_leaf=40,random_state=2026)
 clf.fit(xtr,high.astype(int)); hi.fit(xtr.loc[high],y[high]); lo.fit(xtr.loc[low],y[low])
 probability=np.asarray(clf.predict_proba(xva)[:,1],float).clip(0.0,1.0)
 high_mean=np.asarray(hi.predict(xva),float); low_mean=np.asarray(lo.predict(xva),float)
 return probability*high_mean+(1.0-probability)*low_mean, {'tail_train_rows':len(train),'tail_high_rows':int(high.sum()),'tail_low_rows':int(low.sum()),'tail_feature_count':len(cols)}
def _fit_direct(settings,train,valid):
 model,_=train_models(settings,train,target_column='target_pdk_official',sample_weight=train['_training_sample_weight'])
 return _ensemble_predict(model,valid),model

def main():
 for f in (METRICS,PRED,REPORT,AUDIT):
  if f.exists(): raise SystemExit(f'Refusing to overwrite existing output: {f}')
 settings=Settings.from_yaml(); source=pd.read_parquet(settings.data_path/DEFAULT_DATASET); all_rows=adapt_certified_training_rows(source)
 metric_rows=[]; pred_rows=[]; fold_audit=[]
 for fold,season in FOLDS:
  outer_train=all_rows.loc[all_rows.season_id.astype(str).map(lambda x:int(x)<int(fold))].copy()
  outer_test=all_rows.loc[all_rows.season_id.astype(str).eq(fold)].copy()
  dates=np.sort(pd.to_datetime(outer_train.GAME_DATE,errors='coerce').dropna().unique())
  if len(dates)<20: raise RuntimeError(f'Insufficient unique train dates for nested fold {season}')
  cutoff=dates[int(len(dates)*0.80)]
  inner_train=outer_train.loc[pd.to_datetime(outer_train.GAME_DATE).lt(cutoff)].copy()
  inner_valid=outer_train.loc[pd.to_datetime(outer_train.GAME_DATE).ge(cutoff)].copy()
  if len(inner_train)<10000 or len(inner_valid)<1000: raise RuntimeError(f'Insufficient inner split for {season}')
  direct_inner,_=_fit_direct(settings,inner_train,inner_valid)
  tail_inner,tail_inner_meta=_fit_tail(inner_train,inner_valid,models_cols := [c for c in inner_train.columns if c in __import__('dunkest.models.predictor',fromlist=['FEATURE_COLS']).FEATURE_COLS])
  y_inner=inner_valid.target_pdk_official.to_numpy(float)
  blend_scores=[]
  for w in BLEND_WEIGHTS:
   pred=(1.0-w)*direct_inner+w*tail_inner
   blend_scores.append({'tail_weight':w,'mae':float(mean_absolute_error(y_inner,pred)),'rmse':float(mean_squared_error(y_inner,pred)**.5)})
  chosen=min(blend_scores,key=lambda r:(r['mae'],r['tail_weight']))['tail_weight']
  direct_outer,model_outer=_fit_direct(settings,outer_train,outer_test)
  tail_outer,tail_outer_meta=_fit_tail(outer_train,outer_test,[c for c in outer_train.columns if c in __import__('dunkest.models.predictor',fromlist=['FEATURE_COLS']).FEATURE_COLS])
  y=outer_test.target_pdk_official.to_numpy(float); blended=(1.0-chosen)*direct_outer+chosen*tail_outer
  frame=outer_test[['season_id','GAME_DATE','GAME_ID','PLAYER_ID','PLAYER_NAME','target_pdk_official','prev10_pdk_mean','history_games_before_target']].copy()
  frame=frame.rename(columns={'GAME_DATE':'game_date','GAME_ID':'game_id','PLAYER_ID':'player_id','PLAYER_NAME':'player_name','target_pdk_official':'target_pdk','prev10_pdk_mean':'baseline_prev10'})
  frame['prediction_production_ensemble']=direct_outer; frame['prediction_tail_mixture25']=tail_outer; frame['prediction_nested_blend']=blended; frame['selected_tail_weight']=chosen; frame['fold_season']=season; pred_rows.append(frame)
  candidates={'production_ensemble':direct_outer,'tail_mixture25':tail_outer,'nested_blend':blended,'baseline_prev10':pd.to_numeric(frame.baseline_prev10,errors='coerce').fillna(float(np.median(outer_train.target_pdk_official))).to_numpy(float)}
  for name,pred in candidates.items():
   m={'fold_season_id':fold,'fold_season':season,'candidate':name,'selected_tail_weight':chosen if name=='nested_blend' else np.nan,**score(y,pred)}
   for threshold in (25,30):
    mask=y>=threshold; m[f'mae_actual_ge{threshold}']=float(np.mean(np.abs(pred[mask]-y[mask]))) if mask.any() else np.nan; m[f'n_actual_ge{threshold}']=int(mask.sum())
   low=pd.to_numeric(frame.history_games_before_target,errors='coerce').fillna(0).to_numpy()<5
   m['mae_history_lt5']=float(np.mean(np.abs(pred[low]-y[low]))) if low.any() else np.nan; m['n_history_lt5']=int(low.sum()); metric_rows.append(m)
  fold_audit.append({'season':season,'outer_train_rows':len(outer_train),'outer_test_rows':len(outer_test),'inner_train_rows':len(inner_train),'inner_valid_rows':len(inner_valid),'inner_cutoff_utc':pd.Timestamp(cutoff).isoformat(),'inner_blend_scores':blend_scores,'selected_tail_weight':chosen,'direct_model_weights':model_outer.get('_weights',{}),'production_feature_count':len(model_outer.get('_feature_cols',[])),'inner_tail':tail_inner_meta,'outer_tail':tail_outer_meta})
  print(f"Completed nested tail blend fold {season}: selected tail weight={chosen:.2f}; inner scores={blend_scores}",flush=True)
 metrics=pd.DataFrame(metric_rows); predictions=pd.concat(pred_rows,ignore_index=True)
 pooled=[]
 for name,g in metrics.groupby('candidate',sort=False):
  pooled.append({'candidate':name,'n':int(g.n.sum()),'mae':float(np.average(g.mae,weights=g.n)),'rmse':float(np.sqrt(np.average(g.rmse**2,weights=g.n))),'bias_pred_minus_actual':float(np.average(g.bias_pred_minus_actual,weights=g.n)),'mae_actual_ge25':float(np.average(g.mae_actual_ge25,weights=g.n)),'mae_actual_ge30':float(np.average(g.mae_actual_ge30,weights=g.n)),'mae_history_lt5':float(np.average(g.mae_history_lt5,weights=g.n))})
 pooled=pd.DataFrame(pooled)
 metrics.to_csv(METRICS,index=False); predictions.to_csv(PRED,index=False)
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'source_dataset':str((settings.data_path/DEFAULT_DATASET).relative_to(ROOT)),'target':'certified official Dunkest PDK','outer_folds':{f:s for f,s in FOLDS},'inner_weight_candidates':BLEND_WEIGHTS,'inner_validation_fraction':0.20,'holdout_2025_26_loaded':False,'prospective_2026_27_loaded':False,'fold_audit':fold_audit,'pooled_metrics':pooled.to_dict('records'),'production_changed':False}
 AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
 report=['# Nested production / conditional-tail blend — V1','',f"Generated UTC: {audit['created_utc']}",'','## Method','','For each held-out season, the direct production ensemble and a conditional PDK≥25 mixture are fit only on earlier seasons. The blend weight is selected from {0, .25, .5, .75, 1} using a later-in-time 20% validation slice inside the training block; the outer test season is not used for blend selection. The 2025/26 holdout and frozen 2026/27 prospective bundle are excluded.','','## Pooled outer-fold metrics','',pooled.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Outer-fold metrics','',metrics.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Inner selection audit','',json.dumps(fold_audit,indent=2),'','## Decision','','The nested blend is only eligible for production if it improves player-level overall MAE/RMSE and does not worsen high-score or low-history cohorts across all outer folds. This is player-game forecasting evidence only, not realized lineup validation. No production blend weight is changed by this experiment.','','No commit or push.','']
 REPORT.write_text('\n'.join(report),encoding='utf-8')
 print('\nPOOLED RESULTS\n'+pooled.to_string(index=False),flush=True); print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
if __name__=='__main__': main()
