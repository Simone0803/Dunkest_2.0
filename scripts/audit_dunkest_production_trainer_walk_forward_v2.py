#!/usr/bin/env python3
"""Evaluate the exact production multi-season trainer on held-out seasons."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.config import Settings
from dunkest.models.multiseason_training import adapt_certified_training_rows, DEFAULT_DATASET
from dunkest.models.predictor import train_models, _ensemble_predict
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'; STAMP='dunkest_production_trainer_walk_forward_20261015_v2'
METRICS=OUT/f'{STAMP}_metrics.csv'; PRED=OUT/f'{STAMP}_predictions.csv'; REPORT=OUT/f'{STAMP}.md'; AUDIT=OUT/f'{STAMP}.json'
FOLDS=[('9','2022-23'),('13','2023-24'),('19','2024-25')]
def score(y,p):
 y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
 return {'n':len(y),'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5),'bias_pred_minus_actual':float(e.mean())}
def main():
 for f in (METRICS,PRED,REPORT,AUDIT):
  if f.exists(): raise SystemExit(f'Refusing to overwrite existing output: {f}')
 settings=Settings.from_yaml(); source=pd.read_parquet(settings.data_path/DEFAULT_DATASET); all_rows=adapt_certified_training_rows(source)
 rows=[]; pred_rows=[]; model_meta=[]
 for fold,season in FOLDS:
  tr=all_rows.loc[all_rows.season_id.astype(str).map(lambda x:int(x)<int(fold))].copy()
  te=all_rows.loc[all_rows.season_id.astype(str).eq(fold)].copy()
  if tr.empty or te.empty: raise SystemExit(f'Empty train/test for {season}')
  models,_=train_models(settings,tr,target_column='target_pdk_official',sample_weight=tr['_training_sample_weight'])
  prediction=_ensemble_predict(models,te)
  y=te.target_pdk_official.to_numpy(float)
  frame=te[['season_id','GAME_DATE','GAME_ID','PLAYER_ID','PLAYER_NAME','target_pdk_official','prev10_pdk_mean','history_games_before_target']].copy()
  frame=frame.rename(columns={'GAME_DATE':'game_date','GAME_ID':'game_id','PLAYER_ID':'player_id','PLAYER_NAME':'player_name','target_pdk_official':'target_pdk','prev10_pdk_mean':'baseline_prev10'})
  frame['prediction_production_ensemble']=prediction
  frame['fold_season']=season
  pred_rows.append(frame)
  for candidate,pred in [('production_ensemble',prediction),('baseline_prev10',pd.to_numeric(frame.baseline_prev10,errors='coerce').fillna(float(np.median(tr.target_pdk_official))).to_numpy(float))]:
   metric={'fold_season_id':fold,'fold_season':season,'candidate':candidate,**score(y,pred)}
   for threshold in (25,30):
    mask=y>=threshold; metric[f'mae_actual_ge{threshold}']=float(np.mean(np.abs(pred[mask]-y[mask]))) if mask.any() else np.nan; metric[f'n_actual_ge{threshold}']=int(mask.sum())
   low=pd.to_numeric(frame.history_games_before_target,errors='coerce').fillna(0).to_numpy()<5
   metric['mae_history_lt5']=float(np.mean(np.abs(pred[low]-y[low]))) if low.any() else np.nan; metric['n_history_lt5']=int(low.sum())
   rows.append(metric)
  model_meta.append({'season':season,'train_rows':len(tr),'test_rows':len(te),'feature_count':len(models.get('_feature_cols',[])),'features':models.get('_feature_cols',[]),'weights':models.get('_weights',{}),'ridge_alpha':getattr(models.get('ridge'),'alpha',None),'residual_std':models.get('_residual_std'),'team_change_bias_correction_pdk':models.get('_team_change_bias_correction_pdk',0.0),'team_change_bias_correction_oof_rows':models.get('_team_change_bias_correction_oof_rows',0),'team_change_bias_correction_raw_residual_mean':models.get('_team_change_bias_correction_raw_residual_mean',0.0),'team_change_bias_correction_fold_diagnostics':models.get('_team_change_bias_correction_fold_diagnostics',[])})
  print(f"Completed exact production trainer fold {season}: train={len(tr):,}, test={len(te):,}, features={len(models.get('_feature_cols',[]))}, weights={models.get('_weights',{})}",flush=True)
 metrics=pd.DataFrame(rows); predictions=pd.concat(pred_rows,ignore_index=True)
 pooled=[]
 for candidate in metrics.candidate.unique():
  g=metrics.loc[metrics.candidate.eq(candidate)]
  pooled.append({'candidate':candidate,'n':int(g.n.sum()),'mae':float(np.average(g.mae,weights=g.n)),'rmse':float(np.sqrt(np.average(g.rmse**2,weights=g.n))),'bias_pred_minus_actual':float(np.average(g.bias_pred_minus_actual,weights=g.n)),'mae_actual_ge25':float(np.average(g.mae_actual_ge25,weights=g.n)),'mae_actual_ge30':float(np.average(g.mae_actual_ge30,weights=g.n)),'mae_history_lt5':float(np.average(g.mae_history_lt5,weights=g.n))})
 pooled=pd.DataFrame(pooled)
 metrics.to_csv(METRICS,index=False); predictions.to_csv(PRED,index=False)
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'source_dataset':str((settings.data_path/DEFAULT_DATASET).relative_to(ROOT)),'target':'certified official Dunkest PDK','folds':{f:s for f,s in FOLDS},'training_rows':len(all_rows),'holdout_2025_26_loaded':False,'prospective_2026_27_loaded':False,'same_production_trainer':True,'model_metadata':model_meta,'metrics':metrics.to_dict('records'),'pooled_metrics':pooled.to_dict('records'),'production_code_changed_by_this_audit':False,'team_change_bias_correction_active':True}
 AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
 report=['# Exact production trainer — player-level walk-forward V2','',f"Generated UTC: {audit['created_utc']}",'','## Method','','The exact `train_multiseason_models` adapter and production `train_models` trainer are refit separately before each held-out season (2022/23, 2023/24, 2024/25). Only earlier certified Dunkest official-PDK rows enter training; the model learns its ensemble weights and calibration using the training block’s own past-only folds. Evaluation uses the held-out season. The 2025/26 holdout and frozen 2026/27 bundle are not loaded.','','## Pooled results','',pooled.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Fold results','',metrics.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Fold-specific model metadata','',json.dumps(model_meta,indent=2),'','## Interpretation','','This audit measures the exact production trainer with the expanded feature schema. The previous lag ablation used fixed ExtraTrees/HistGradientBoosting candidates; those results were research evidence for feature enrichment, not a substitute for this production-trainer test. Do not use these player-level results as evidence of realized lineup superiority.','','No commit or push.','']
 REPORT.write_text('\n'.join(report),encoding='utf-8')
 print('\nPOOLED RESULTS\n'+pooled.to_string(index=False),flush=True); print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
if __name__=='__main__': main()
