#!/usr/bin/env python3
"""One-shot final holdout evaluation of the preselected production+Torch MLP candidate.
No hyperparameter selection or model changes are based on this holdout.
"""
from __future__ import annotations
import importlib.util, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.config import Settings
import dunkest.models.predictor as predictor
from dunkest.models.multiseason_training import adapt_certified_training_rows, DEFAULT_DATASET
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'; STAMP='dunkest_production_torch_mlp_holdout_2025_26_once_20261016_v1'
CSV=OUT/f'{STAMP}_metrics.csv'; REPORT=OUT/f'{STAMP}.md'; AUDIT=OUT/f'{STAMP}.json'
for p in (CSV,REPORT,AUDIT):
 if p.exists(): raise SystemExit(f'Refusing to repeat or overwrite one-shot holdout evaluation: {p}')
spec=importlib.util.spec_from_file_location('ensemble_torch_mlp_exp',ROOT/'scripts/experiment_dunkest_production_ensemble_with_torch_mlp_walk_forward_20261016_v1.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); TorchMLPRegressor=module.TorchMLPRegressor
settings=Settings.from_yaml(); source=pd.read_parquet(settings.data_path/DEFAULT_DATASET)
mp=settings.data_path/'processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'; labels=None
if mp.exists(): labels=pd.read_parquet(mp,columns=['nba_GAME_ID','nba_PLAYER_ID','nba_MIN','nba_match_status'])
all_rows=adapt_certified_training_rows(source,include_2025_26=True,minutes_labels=labels)
train=all_rows.loc[all_rows.season_label.astype(str)<'2025-26'].copy(); test=all_rows.loc[all_rows.season_label.astype(str).eq('2025-26')].copy()
if train.empty or test.empty: raise RuntimeError(f'Bad holdout split: train={len(train)}, test={len(test)}')
y=pd.to_numeric(test.target_pdk_official,errors='coerce').to_numpy(float); history=pd.to_numeric(test.history_games_before_target,errors='coerce').fillna(0).to_numpy(float)
def score(name,p):
 p=np.asarray(p,float); e=p-y; out={'model':name,'n':int(len(y)),'mae':float(mean_absolute_error(y,p)),'rmse':float(np.sqrt(mean_squared_error(y,p))),'bias_pred_minus_actual':float(e.mean())}
 for t in (25,30):
  m=y>=t; out[f'mae_actual_ge{t}']=float(np.abs(e[m]).mean()) if m.any() else float('nan'); out[f'n_actual_ge{t}']=int(m.sum())
 m=history<5; out['mae_history_lt5']=float(np.abs(e[m]).mean()) if m.any() else float('nan'); out['n_history_lt5']=int(m.sum()); return out
original=predictor._model_zoo; results=[]
try:
 print(f'FINAL HOLDOUT 2025-26: training rows={len(train):,}, holdout rows={len(test):,}; no hyperparameter tuning.',flush=True)
 predictor._model_zoo=original
 models,_=predictor.train_models(settings,train,target_column='target_pdk_official',sample_weight=train['_training_sample_weight'])
 p0=predictor._ensemble_predict(models,test); results.append(score('current_production_ensemble',p0)); print('CURRENT',results[-1],flush=True)
 def candidate_zoo(s):
  from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
  from sklearn.linear_model import Ridge
  return {'ridge':Ridge(alpha=3.,random_state=s.random_state),'rf':RandomForestRegressor(n_estimators=200,max_depth=6,random_state=s.random_state,n_jobs=3),'gbr':GradientBoostingRegressor(random_state=s.random_state),'torch_mlp':TorchMLPRegressor(hidden=(128,64),dropout=0.0,weight_decay=0.001,lr=0.001,random_state=s.random_state)}
 predictor._model_zoo=candidate_zoo
 models,_=predictor.train_models(settings,train,target_column='target_pdk_official',sample_weight=train['_training_sample_weight'])
 p1=predictor._ensemble_predict(models,test); results.append(score('production_ensemble_plus_torch_mlp',p1)); print('CANDIDATE',results[-1],flush=True)
finally: predictor._model_zoo=original
out=pd.DataFrame(results); out.to_csv(CSV,index=False)
a=out.set_index('model'); b=a.loc['current_production_ensemble']; c=a.loc['production_ensemble_plus_torch_mlp']
# Predeclared final rule: candidate must improve MAE and RMSE and must not worsen either high-score cohort.
passed=bool(c.mae < b.mae and c.rmse < b.rmse and c.mae_actual_ge25 <= b.mae_actual_ge25 and c.mae_actual_ge30 <= b.mae_actual_ge30)
audit={'created_utc':datetime.now(timezone.utc).isoformat(),'train_seasons':'2020-21 through 2024-25','holdout_season':'2025-26','train_rows':len(train),'holdout_rows':len(test),'holdout_used_for_tuning':False,'prospective_2026_27_used':False,'candidate_selected_before_holdout':True,'decision_rule':'Promote only if MAE and RMSE both improve and MAE for realized scores >=25 and >=30 does not worsen.','metrics':results,'passes_predeclared_rule':passed,'production_code_changed':False}
AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
REPORT.write_text('\n'.join(['# One-shot 2025/26 holdout validation: production ensemble vs production + Torch MLP','','Generated UTC: '+audit['created_utc'],'','## Protocol','','The 51-configuration search and 3-fold development comparison selected the small Torch MLP before this final test. The 2025/26 season was used exactly once here, only as a final evaluation; it was not used for tuning. The prospective 2026/27 GW1 remains untouched.','','## Results','',out.to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Decision',f"\nPredeclared rule passed: **{passed}**. No model code was modified by this evaluation.",'']) ,encoding='utf-8')
print('\nFINAL_DECISION',json.dumps({'passes_predeclared_rule':passed,'metrics':results},indent=2),flush=True); print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
