#!/usr/bin/env python3
"""Targeted walk-forward hyperparameter comparison for the production PDK trainer.
Uses only certified official labels from seasons preceding each fold. Never loads 2025/26 or 2026/27.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.config import Settings
import dunkest.models.predictor as predictor
from dunkest.models.multiseason_training import adapt_certified_training_rows, DEFAULT_DATASET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/audit'
STAMP='dunkest_production_hyperparams_walk_forward_20261016_v2'
METRICS=OUT/f'{STAMP}_metrics.csv'; REPORT=OUT/f'{STAMP}.md'; AUDIT=OUT/f'{STAMP}.json'
FOLDS=[('9','2022-23'),('13','2023-24'),('19','2024-25')]
CONFIGS={
 'gbr_regularized': {'rf_n':200,'rf_depth':6,'rf_leaf':1,'gbr_n':180,'gbr_lr':0.04,'gbr_depth':2,'gbr_leaf':5,'gbr_subsample':0.85},
}

def score(y,p):
 y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
 out={'n':int(len(y)),'mae':float(mean_absolute_error(y,p)),'rmse':float(np.sqrt(mean_squared_error(y,p))),'bias_pred_minus_actual':float(e.mean())}
 for threshold in (25,30):
  mask=y>=threshold
  out[f'mae_actual_ge{threshold}']=float(np.mean(np.abs(e[mask]))) if mask.any() else float('nan')
  out[f'n_actual_ge{threshold}']=int(mask.sum())
 return out

def main():
 for f in (METRICS,REPORT,AUDIT):
  if f.exists(): raise SystemExit(f'Refusing to overwrite {f}')
 settings=Settings.from_yaml()
 source=pd.read_parquet(settings.data_path/DEFAULT_DATASET)
 rows=adapt_certified_training_rows(source)
 original=predictor._model_zoo
 records=[]; metadata=[]
 try:
  for candidate,cfg in CONFIGS.items():
   def model_zoo(s, c=cfg):
    return {
      'ridge': Ridge(alpha=3.0,random_state=s.random_state),
      'rf': RandomForestRegressor(n_estimators=c['rf_n'],max_depth=c['rf_depth'],min_samples_leaf=c['rf_leaf'],random_state=s.random_state,n_jobs=2,max_features=1.0),
      'gbr': GradientBoostingRegressor(n_estimators=c['gbr_n'],learning_rate=c['gbr_lr'],max_depth=c['gbr_depth'],min_samples_leaf=c['gbr_leaf'],subsample=c['gbr_subsample'],random_state=s.random_state),
    }
   predictor._model_zoo=model_zoo
   for fold,season in FOLDS:
    train=rows.loc[rows.season_id.astype(str).map(lambda x:int(x)<int(fold))].copy()
    test=rows.loc[rows.season_id.astype(str).eq(fold)].copy()
    models,_=predictor.train_models(settings,train,target_column='target_pdk_official',sample_weight=train['_training_sample_weight'])
    p=predictor._ensemble_predict(models,test)
    y=test.target_pdk_official.to_numpy(float)
    metrics=score(y,p)
    baseline=pd.to_numeric(test['prev10_pdk_mean'],errors='coerce').fillna(float(np.median(train.target_pdk_official))).to_numpy(float)
    baseline_metrics=score(y,baseline)
    records.append({'candidate':candidate,'fold_season':season,**metrics,'baseline_mae':baseline_metrics['mae'],'baseline_rmse':baseline_metrics['rmse'],'rf_n':cfg['rf_n'],'rf_depth':cfg['rf_depth'],'rf_leaf':cfg['rf_leaf'],'gbr_n':cfg['gbr_n'],'gbr_lr':cfg['gbr_lr'],'gbr_depth':cfg['gbr_depth'],'gbr_leaf':cfg['gbr_leaf'],'gbr_subsample':cfg['gbr_subsample']})
    print(f"{candidate} {season}: MAE={metrics['mae']:.5f}, RMSE={metrics['rmse']:.5f}, bias={metrics['bias_pred_minus_actual']:.4f}, high25={metrics['mae_actual_ge25']:.4f}, high30={metrics['mae_actual_ge30']:.4f}",flush=True)
    metadata.append({'candidate':candidate,'fold_season':season,'train_rows':len(train),'test_rows':len(test),'feature_count':len(models.get('_feature_cols',[])),'weights':models.get('_weights',{}),'ridge_alpha':getattr(models.get('ridge'),'alpha',None),'config':cfg})
 finally:
  predictor._model_zoo=original
 metrics=pd.DataFrame(records)
 summary=metrics.groupby('candidate').apply(lambda g:pd.Series({'n':int(g.n.sum()),'weighted_mae':float(np.average(g.mae,weights=g.n)),'weighted_rmse':float(np.sqrt(np.average(g.rmse**2,weights=g.n))),'weighted_bias':float(np.average(g.bias_pred_minus_actual,weights=g.n)),'mae_actual_ge25':float(np.average(g.mae_actual_ge25,weights=g['n_actual_ge25'])),'mae_actual_ge30':float(np.average(g.mae_actual_ge30,weights=g['n_actual_ge30'])),'folds':g.fold_season.nunique()}),include_groups=False).reset_index().sort_values(['weighted_mae','weighted_rmse'])
 metrics.to_csv(METRICS,index=False)
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'dataset':str((settings.data_path/DEFAULT_DATASET).relative_to(ROOT)),'target':'certified official Dunkest PDK','folds':{f:s for f,s in FOLDS},'holdout_2025_26_used':False,'prospective_2026_27_used':False,'configs':CONFIGS,'fold_metadata':metadata,'fold_metrics':records,'summary':summary.to_dict('records'),'selection_rule':'Rank by pooled row-weighted MAE, then pooled RMSE; inspect bias and high-score cohorts before promotion.','production_changed':False}
 AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
 report=['# Production PDK hyperparameter walk-forward — V1','',f"Generated UTC: {audit['created_utc']}",'','## Protocol','','Exact production feature adapter and target; each fold trains only on earlier certified official Dunkest PDK rows. Validation seasons: 2022/23, 2023/24, 2024/25. 2025/26 is excluded from training/evaluation folds; prospective 2026/27 outcomes are not used. The model zoo is varied only in Random Forest and Gradient Boosting settings; Ridge regularization and ensemble weights remain past-only learned by the production trainer. Forest jobs capped at 2 to avoid overloading the season-opener process.','','## Pooled summary','',summary.to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Per-fold results','',metrics.to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Interpretation','','No candidate is promoted automatically. A candidate should be promoted only if it improves pooled MAE/RMSE without materially worsening bias, extreme-score error, or a specific season. This is player-game validation, not lineup-level proof.','','Production code was not changed by this experiment.','']
 REPORT.write_text('\n'.join(report),encoding='utf-8')
 print('\nSUMMARY\n'+summary.to_string(index=False),flush=True)
 print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
if __name__=='__main__': main()
