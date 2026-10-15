#!/usr/bin/env python3
"""Walk-forward ablation of recent PDK/minutes/stat lags for direct PDK forecasts."""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
import experiment_dunkest_minutes_rate_decomposition_v1 as base
OUT=ROOT/'reports/audit'; STAMP='dunkest_pdk_lag_feature_ablation_20261014_v1'
METRICS=OUT/f'{STAMP}_metrics.csv'; PRED=OUT/f'{STAMP}_predictions.csv'; REPORT=OUT/f'{STAMP}.md'; AUDIT=OUT/f'{STAMP}.json'

def score(y,p):
 y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
 return {'n':len(y),'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5),'bias_pred_minus_actual':float(e.mean())}
def make_model(kind, columns):
 cats=[c for c in ['opponentTeamCode','opponentTeamPosition'] if c in columns]
 nums=[c for c in columns if c not in cats]
 numeric=Pipeline([('imputer',SimpleImputer(strategy='median',add_indicator=True))])
 transformers=[('num',numeric,nums)]
 if cats:
  categorical=Pipeline([('imputer',SimpleImputer(strategy='most_frequent')),('onehot',OneHotEncoder(handle_unknown='ignore',sparse_output=False))])
  transformers.append(('cat',categorical,cats))
 prep=ColumnTransformer(transformers,remainder='drop',sparse_threshold=0)
 if kind=='hgb': estimator=__import__('sklearn.ensemble',fromlist=['HistGradientBoostingRegressor']).HistGradientBoostingRegressor(max_iter=180,learning_rate=.06,max_leaf_nodes=31,l2_regularization=5.0,min_samples_leaf=40,random_state=2026)
 else: estimator=ExtraTreesRegressor(n_estimators=140,min_samples_leaf=12,max_features=.85,n_jobs=-1,random_state=2026)
 return Pipeline([('prep',prep),('model',estimator)])
def main():
 for f in [METRICS,PRED,REPORT,AUDIT]:
  if f.exists(): raise SystemExit(f'Refusing to overwrite existing output: {f}')
 df=pd.read_parquet(ROOT/'data/processed/dunkest_pdk_game_training_2020-26_v3.parquet')
 df['season_id']=df.season_id.astype(str); df=df.loc[df.season_id.isin(base.SEASONS)].copy()
 df['game_date']=pd.to_datetime(df.game_date,errors='coerce'); df['target_pdk']=pd.to_numeric(df.target_pdk,errors='coerce')
 labels=pd.read_parquet(ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet',columns=['nba_GAME_ID','nba_PLAYER_ID','nba_MIN','nba_match_status'])
 labels['nba_GAME_ID']=labels.nba_GAME_ID.astype('string'); labels['nba_PLAYER_ID']=pd.to_numeric(labels.nba_PLAYER_ID,errors='coerce').astype('Int64')
 labels=labels.loc[labels.nba_match_status.eq('matched_player_date_opponent')].copy(); keys=['nba_GAME_ID','nba_PLAYER_ID']
 for _,g in labels.loc[labels.duplicated(keys,keep=False)].groupby(keys,dropna=False):
  if g.nba_MIN.nunique(dropna=False)>1: raise SystemExit('Conflicting duplicate minutes labels')
 labels=labels.drop_duplicates(keys,keep='first')
 df['nba_GAME_ID']=df.nba_GAME_ID.astype('string'); df['nba_PLAYER_ID']=pd.to_numeric(df.nba_PLAYER_ID,errors='coerce').astype('Int64')
 df=df.merge(labels[keys+['nba_MIN']],on=keys,how='left',validate='many_to_one')
 df['target_minutes']=pd.to_numeric(df.nba_MIN,errors='coerce')
 df=df.loc[df.target_minutes.notna() & df.target_pdk.notna() & df.game_date.notna()].copy()
 df=base.make_features(df).replace([np.inf,-np.inf],np.nan)
 # Approximate the certified production adapter feature set using only columns
 # that exist in the archive; all candidates share identical target rows.
 prod={
  'pdk_mean_3':'prev3_pdk_mean','pdk_mean_5':'prev5_pdk_mean','pdk_mean_10':'prev10_pdk_mean',
  'pdk_std_5':'prev5_pdk_std','pdk_season_mean':'prev10_pdk_mean','min_mean_5':'prev5_nba_min_mean',
  'min_mean_10':'prev5_nba_min_mean','pdk_per_min_season':None,'pts_mean_5':'prev5_nba_pts_mean',
  'reb_mean_5':'prev5_nba_reb_mean','ast_mean_5':'prev5_nba_ast_mean','rest_days':'rest_days_from_nba_logs',
  'is_home':None,'is_b2b':None,'player_opp_pdk_per_min':None,'player_opp_games':None,
 }
 # Include the remaining rate features as they are in the production adapter.
 for stat in ['stl','blk','tov','oreb','dreb','fg3m','fga','fta']:
  prod[f'{stat}_per36_5']=None
 for c in ['fg3_pct_5','ft_pct_5','three_point_bonus_mean_5','pdk_category_bonus_mean_5','opp_pts_allowed_mean_5','opp_plus_minus_mean_5','opp_def_rating_mean_5','opp_pace_mean_5','opp_dreb_rate_mean_5']:
  prod[c]=None
 for col,src in prod.items():
  if src is not None:
   df[col]=pd.to_numeric(df[src],errors='coerce')
  elif col=='pdk_per_min_season': df[col]=pd.to_numeric(df.prev5_pdk_mean,errors='coerce')/pd.to_numeric(df.prev5_nba_min_mean,errors='coerce').where(pd.to_numeric(df.prev5_nba_min_mean,errors='coerce').gt(0))
  elif col=='is_home': df[col]=df.opponentTeamPosition.astype(str).str.casefold().eq('visitor').astype(float)
  elif col=='is_b2b': df[col]=pd.to_numeric(df.rest_days_from_nba_logs,errors='coerce').le(1).astype(float)
  elif col=='player_opp_pdk_per_min': df[col]=df.pdk_per_min_season
  elif col=='player_opp_games': df[col]=0.0
  elif col.endswith('_per36_5'):
   stat=col.replace('_per36_5',''); numerator=f'prev5_nba_{stat}_mean'; denom='prev5_nba_min_mean'
   df[col]=36*pd.to_numeric(df[numerator],errors='coerce')/pd.to_numeric(df[denom],errors='coerce').where(pd.to_numeric(df[denom],errors='coerce').gt(0)) if numerator in df else np.nan
  else: df[col]=np.nan
 df['pdk_median_5']=df[[f'lag{i}_pdk' for i in range(1,6)]].apply(pd.to_numeric,errors='coerce').median(axis=1)
 prod_cols=list(prod.keys())+['pdk_median_5']
 # Add only lagged features available in both current feature builder and archive adapter.
 extra_cols=['lag1_pdk','lag2_pdk','lag3_pdk','lag4_pdk','lag5_pdk','pdk_trend_3v10','min_trend_3v5','min_last_vs_prev5',
  'lag1_nba_min','lag2_nba_min','lag3_nba_min','prev3_nba_min_mean','lag1_nba_pts','lag2_nba_pts','lag3_nba_pts',
  'prev3_nba_pts_mean','lag1_nba_reb','lag2_nba_reb','lag3_nba_reb','prev3_nba_reb_mean','lag1_nba_ast','lag2_nba_ast','lag3_nba_ast','prev3_nba_ast_mean',
  'history_games_before_target','nba_history_games_before_target','opponentTeamCode','opponentTeamPosition']
 for c in prod_cols+extra_cols:
  if c not in df: df[c]=np.nan
 folds=[]; pred_rows=[]
 for fold in base.FOLDS:
  tr=df.loc[df.season_id.map(lambda x:int(x)<int(fold))].copy(); te=df.loc[df.season_id.eq(fold)].copy()
  for model_kind in ['hgb','et12']:
   mbase=make_model(model_kind,prod_cols); mbase.fit(tr[prod_cols],tr.target_pdk.to_numpy(float)); pb=np.asarray(mbase.predict(te[prod_cols]),float)
   mext=make_model(model_kind,prod_cols+extra_cols); mext.fit(tr[prod_cols+extra_cols],tr.target_pdk.to_numpy(float)); pe=np.asarray(mext.predict(te[prod_cols+extra_cols]),float)
   for label,pred,cols in [('adapter_features',pb,prod_cols),('expanded_lags',pe,prod_cols+extra_cols)]:
    y=te.target_pdk.to_numpy(float); met={'fold_season_id':fold,'fold_season':base.SEASONS[fold],'model':model_kind,'feature_set':label,'feature_count':len(cols),**score(y,pred)}
    for threshold in [25,30]:
     mask=y>=threshold; met[f'mae_actual_ge{threshold}']=float(np.mean(np.abs(pred[mask]-y[mask]))) if mask.any() else np.nan; met[f'n_actual_ge{threshold}']=int(mask.sum())
    low=pd.to_numeric(te.history_games_before_target,errors='coerce').fillna(0).to_numpy()<5
    met['mae_history_lt5']=float(np.mean(np.abs(pred[low]-y[low]))) if low.any() else np.nan; met['n_history_lt5']=int(low.sum())
    folds.append(met)
    p=te[['season_id','game_date','gameId','dunkest_player_id','history_games_before_target','target_minutes','target_pdk']].copy(); p['prediction']=pred; p['model']=model_kind; p['feature_set']=label; pred_rows.append(p)
  print(f'Completed PDK feature fold {base.SEASONS[fold]}',flush=True)
 metrics=pd.DataFrame(folds); predictions=pd.concat(pred_rows,ignore_index=True)
 pooled=[]
 for (model_kind,feature_set),g in predictions.groupby(['model','feature_set'],sort=False):
  y=g.target_pdk.to_numpy(float); p=g.prediction.to_numpy(float); low=pd.to_numeric(g.history_games_before_target,errors='coerce').fillna(0).to_numpy()<5
  row={'model':model_kind,'feature_set':feature_set,'feature_count':len(prod_cols)+(len(extra_cols) if feature_set=='expanded_lags' else 0),**score(y,p)}
  for t in [25,30]:
   mask=y>=t; row[f'mae_actual_ge{t}']=float(np.mean(np.abs(p[mask]-y[mask]))) if mask.any() else np.nan; row[f'n_actual_ge{t}']=int(mask.sum())
  row['mae_history_lt5']=float(np.mean(np.abs(p[low]-y[low]))) if low.any() else np.nan; row['n_history_lt5']=int(low.sum()); pooled.append(row)
 pooled=pd.DataFrame(pooled).sort_values(['model','feature_set'])
 metrics.to_csv(METRICS,index=False); predictions.to_csv(PRED,index=False)
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'training_source':'dunkest_pdk_game_training_2020-26_v3.parquet filtered to 2020/21–2024/25','minutes_label_source':'dunkest_nba_player_games_enriched_2018-25_v1.parquet','rows':len(df),'folds':{f:base.SEASONS[f] for f in base.FOLDS},'holdout_2025_26_loaded':False,'prospective_2026_27_loaded':False,'feature_sets':{'adapter_features':prod_cols,'expanded_lags':prod_cols+extra_cols},'pooled_metrics':pooled.to_dict('records'),'fold_metrics':metrics.to_dict('records'),'production_changed':False}
 AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
 report=['# PDK recent-lag feature ablation — V1','',f"Generated UTC: {audit['created_utc']}",'','## Method','','Compare identical expanding-origin folds (2022/23, 2023/24, 2024/25) and identical player-game rows using the same estimator but two feature sets: a reconstruction of the production multi-season adapter, and that set plus explicit lag-1…5 PDK, recent NBA minutes/stat lags, short-vs-long trends, history counts and opponent categories. Target-game PDK and minutes are labels only. The 2025/26 holdout and prospective 2026/27 bundle were not loaded.','','## Pooled metrics','',pooled.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Fold metrics','',metrics.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Decision','','Promote expanded lags only if the improvement is consistent across seasons and does not worsen high-score or low-history cohorts. This experiment does not change production features or weights.','','No commit or push.','']
 REPORT.write_text('\n'.join(report),encoding='utf-8')
 print('\nPOOLED RESULTS\n'+pooled.to_string(index=False),flush=True); print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
if __name__=='__main__': main()
