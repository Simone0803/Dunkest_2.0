#!/usr/bin/env python3
"""Nested temporal test of subgroup-gated expected minutes and downstream PDK scaling."""
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.metrics import mean_absolute_error,mean_squared_error
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import experiment_dunkest_minutes_rate_decomposition_v1 as base
OUT=ROOT/'reports/audit';STAMP='dunkest_minutes_hybrid_nested_20261014_v1'
MET=OUT/f'{STAMP}_metrics.csv';PRED=OUT/f'{STAMP}_predictions.csv';REPORT=OUT/f'{STAMP}.md';AUDIT=OUT/f'{STAMP}.json'
WEIGHTS=[0.,.25,.5,.75,1.]
def score(y,p):
 y=np.asarray(y,float);p=np.asarray(p,float);e=p-y
 return {'n':len(y),'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5),'bias_pred_minus_actual':float(e.mean())}
def predict_minutes(train,valid,cols):
 model=base.model('hgb'); medians=train[cols].apply(pd.to_numeric,errors='coerce').median().fillna(0.)
 Xtr=train[cols].apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan).fillna(medians).fillna(0.)
 Xva=valid[cols].apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan).fillna(medians).fillna(0.)
 model.fit(Xtr,train.target_minutes.to_numpy(float));return np.clip(model.predict(Xva),0,48)
def baseline(frame):return pd.to_numeric(frame.prev5_nba_min_mean,errors='coerce').to_numpy(float)
def mix(b,m,w):return np.where(np.isfinite(b),(1-w)*b+w*m,m)
def select_weight(y,b,m,mask):
 valid=mask & np.isfinite(y)&np.isfinite(b)&np.isfinite(m)
 if int(valid.sum())<100:return 1.0,{'fallback':'insufficient_inner_rows','n':int(valid.sum())}
 scores=[]
 for w in WEIGHTS:scores.append({'model_weight':w,'mae':float(mean_absolute_error(y[valid],mix(b[valid],m[valid],w))),'rmse':float(mean_squared_error(y[valid],mix(b[valid],m[valid],w))**.5),'n':int(valid.sum())})
 best=min(scores,key=lambda r:(r['mae'],r['model_weight']))
 return float(best['model_weight']),{'n':int(valid.sum()),'scores':scores}
def main():
 for f in (MET,PRED,REPORT,AUDIT):
  if f.exists():raise SystemExit(f'Refusing to overwrite existing output: {f}')
 df=pd.read_parquet(ROOT/'data/processed/dunkest_pdk_game_training_2020-26_v3.parquet')
 df['season_id']=df.season_id.astype(str);df=df.loc[df.season_id.isin(base.SEASONS)].copy();df['game_date']=pd.to_datetime(df.game_date,errors='coerce')
 labels=pd.read_parquet(ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet',columns=['nba_GAME_ID','nba_PLAYER_ID','nba_MIN','nba_match_status'])
 labels['nba_GAME_ID']=labels.nba_GAME_ID.astype('string');labels['nba_PLAYER_ID']=pd.to_numeric(labels.nba_PLAYER_ID,errors='coerce').astype('Int64');labels=labels.loc[labels.nba_match_status.eq('matched_player_date_opponent')].copy();keys=['nba_GAME_ID','nba_PLAYER_ID']
 dup=labels.loc[labels.duplicated(keys,keep=False)]
 if not dup.empty:
  for _,g in dup.groupby(keys,dropna=False):
   if g.nba_MIN.nunique(dropna=False)>1:raise SystemExit('Conflicting target-minute labels')
 labels=labels.drop_duplicates(keys,keep='first');df['nba_GAME_ID']=df.nba_GAME_ID.astype('string');df['nba_PLAYER_ID']=pd.to_numeric(df.nba_PLAYER_ID,errors='coerce').astype('Int64')
 df=df.merge(labels[keys+['nba_MIN']],on=keys,how='left',validate='many_to_one');df['target_minutes']=pd.to_numeric(df.nba_MIN,errors='coerce')
 df=df.loc[df.target_minutes.notna() & df.game_date.notna()].copy();df=base.make_features(df).replace([np.inf,-np.inf],np.nan)
 cols=base.BASE_NUM+['pdk_trend_3v10','min_trend_3v5','min_last_vs_prev5','lag1_pdk_per_min','prev3_pdk_per_min','prev5_pdk_per_min','lag1_pts_per_min','prev3_pts_per_min','prev5_pts_per_min','lag1_reb_per_min','prev3_reb_per_min','prev5_reb_per_min','lag1_ast_per_min','prev3_ast_per_min','prev5_ast_per_min','lag1_usage_proxy','prev3_usage_proxy','prev5_usage_proxy']+base.CAT
 rows=[];preds=[];audit=[]
 for fold in base.FOLDS:
  outer_train=df.loc[df.season_id.map(lambda s:int(s)<int(fold))].copy();outer_test=df.loc[df.season_id.eq(fold)].copy()
  dates=np.sort(pd.to_datetime(outer_train.game_date).dropna().unique());cut=dates[max(1,int(len(dates)*.80))]
  inner_train=outer_train.loc[outer_train.game_date.lt(cut)].copy();inner_valid=outer_train.loc[outer_train.game_date.ge(cut)].copy()
  if len(inner_train)<10000 or len(inner_valid)<1000:raise SystemExit(f'Insufficient inner rows for {base.SEASONS[fold]}')
  inner_pred=predict_minutes(inner_train,inner_valid,cols);yb=inner_valid.target_minutes.to_numpy(float);bb=baseline(inner_valid);hist=pd.to_numeric(inner_valid.history_games_before_target,errors='coerce').fillna(0).to_numpy(float)
  weights={};select={}
  for cohort,mask in [('low_history_lt5',hist<5),('history_ge5',hist>=5),('all',np.ones(len(hist),bool))]:weights[cohort],select[cohort]=select_weight(yb,bb,inner_pred,mask)
  outer_pred=predict_minutes(outer_train,outer_test,cols);yt=outer_test.target_minutes.to_numpy(float);bt=baseline(outer_test);ht=pd.to_numeric(outer_test.history_games_before_target,errors='coerce').fillna(0).to_numpy(float)
  gated=np.where(ht<5,mix(bt,outer_pred,weights['low_history_lt5']),mix(bt,outer_pred,weights['history_ge5']))
  pred_frame=outer_test[['season_id','game_date','gameId','dunkest_player_id','history_games_before_target','nba_history_games_before_target','target_pdk','target_minutes','prev5_nba_min_mean','lag1_nba_min','min_trend_3v5','min_last_vs_prev5']].copy()
  pred_frame['prediction_minutes_hgb']=outer_pred;pred_frame['prediction_minutes_prev5']=bt;pred_frame['prediction_minutes_nested_gated']=gated
  pred_frame['selected_weight_low_history']=weights['low_history_lt5'];pred_frame['selected_weight_history_ge5']=weights['history_ge5'];pred_frame['fold_season']=base.SEASONS[fold];preds.append(pred_frame)
  cohorts={'all':np.ones(len(ht),bool),'low_history_lt5':ht<5,'history_ge5':ht>=5,'nba_history_lt5':pd.to_numeric(outer_test.nba_history_games_before_target,errors='coerce').fillna(0).to_numpy(float)<5,'recent_minutes_drop_ge8':(pd.to_numeric(outer_test.lag1_nba_min,errors='coerce')+8 < pd.to_numeric(outer_test.prev5_nba_min_mean,errors='coerce')).fillna(False).to_numpy()}
  candidates={'hgb':outer_pred,'prev5':bt,'nested_gated':gated,'fixed_blend_50':mix(bt,outer_pred,.5),'fixed_blend_75':mix(bt,outer_pred,.75)}
  for name,p in candidates.items():
   for cohort,mask in cohorts.items():
    valid=mask & np.isfinite(yt)&np.isfinite(p)
    if not valid.any():continue
    m={'fold_season_id':fold,'fold_season':base.SEASONS[fold],'candidate':name,'cohort':cohort,**score(yt[valid],p[valid])};rows.append(m)
  audit.append({'season':base.SEASONS[fold],'outer_train_rows':len(outer_train),'outer_test_rows':len(outer_test),'inner_train_rows':len(inner_train),'inner_valid_rows':len(inner_valid),'inner_cutoff':pd.Timestamp(cut).isoformat(),'selected_weights':weights,'inner_selection':select})
  print(f"Completed nested minutes fold {base.SEASONS[fold]}: selected low-history={weights['low_history_lt5']:.2f}, experienced={weights['history_ge5']:.2f}",flush=True)
 detail=pd.DataFrame(rows);pr=pd.concat(preds,ignore_index=True);detail.to_csv(MET,index=False);pr.to_csv(PRED,index=False)
 pooled=[]
 for (name,cohort),g in detail.groupby(['candidate','cohort'],sort=False):pooled.append({'candidate':name,'cohort':cohort,'n':int(g.n.sum()),'mae':float(np.average(g.mae,weights=g.n)),'rmse':float(np.sqrt(np.average(g.rmse**2,weights=g.n))),'bias_pred_minus_actual':float(np.average(g.bias_pred_minus_actual,weights=g.n))})
 pooled=pd.DataFrame(pooled)
 # Downstream test: scale the direct expanded-lag HGB PDK forecast by each minutes
 # candidate relative to previous-5 minutes; this is diagnostic, not an assumed law.
 pdk=pd.read_csv(OUT/'dunkest_pdk_lag_feature_ablation_20261014_v2_predictions.csv');pdk=pdk.loc[pdk.model.eq('hgb')&pdk.feature_set.eq('expanded_lags')].copy();pdk['season_id']=pdk.season_id.astype(str);pdk['gameId']=pdk.gameId.astype(str);pdk['dunkest_player_id']=pdk.dunkest_player_id.astype(str);pr['season_id']=pr.season_id.astype(str);pr['gameId']=pr.gameId.astype(str);pr['dunkest_player_id']=pr.dunkest_player_id.astype(str)
 j=pdk.merge(pr[['season_id','gameId','dunkest_player_id','prev5_nba_min_mean','prediction_minutes_hgb','prediction_minutes_prev5','prediction_minutes_nested_gated']],on=['season_id','gameId','dunkest_player_id'],how='inner',validate='one_to_one',suffixes=('','_minutes'))
 y=j.target_pdk.to_numpy(float);basep=j.prediction.to_numpy(float);prev=pd.to_numeric(j.prev5_nba_min_mean,errors='coerce').to_numpy(float);validprev=np.isfinite(prev)&(prev>0)
 downstream=[]
 for mn,col in [('hgb','prediction_minutes_hgb'),('prev5','prediction_minutes_prev5'),('nested_gated','prediction_minutes_nested_gated')]:
  mpd=pd.to_numeric(j[col],errors='coerce').to_numpy(float);ratio=np.divide(mpd,prev,out=np.ones(len(j)),where=validprev);ratio=np.clip(ratio,.25,1.75)
  for w in [0.,.1,.2,.3,.5,1.]:
   scaled=basep*((1-w)+w*ratio);mask=np.isfinite(y)&np.isfinite(scaled)
   downstream.append({'minute_candidate':mn,'scale_weight':w,**score(y[mask],scaled[mask]),'n_scaled_rows':int((mask&validprev).sum())})
 down=pd.DataFrame(downstream)
 audit_json={'created_utc':datetime.now(timezone.utc).isoformat(),'source_training':'dunkest_pdk_game_training_2020-26_v3.parquet filtered to 2020/21–2024/25','minutes_label_source':'dunkest_nba_player_games_enriched_2018-25_v1.parquet','outer_folds':{f:base.SEASONS[f] for f in base.FOLDS},'inner_validation_fraction':.20,'weight_candidates':WEIGHTS,'holdout_2025_26_loaded':False,'prospective_2026_27_loaded':False,'fold_selection':audit,'pooled_minutes_metrics':pooled.to_dict('records'),'downstream_pdk_scaling_metrics':down.to_dict('records'),'production_changed':False}
 AUDIT.write_text(json.dumps(audit_json,indent=2,ensure_ascii=False),encoding='utf-8')
 report=['# Nested expected-minutes hybrid — V1','',f"Generated UTC: {audit_json['created_utc']}",'','## Method','','For each outer held-out season (2022/23, 2023/24, 2024/25), the HGB minutes model is fitted only on earlier data. Blend weights are selected on a later-in-time 20% validation slice within the outer training block, separately for fewer than five prior Dunkest games and at least five. When the previous-five-minute baseline is missing, the model forecast is used. The 2025/26 holdout and prospective 2026/27 bundle are excluded.','','## Pooled minutes metrics by subgroup','',pooled.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Outer-fold metrics','',detail.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Downstream PDK rescaling experiment','','Diagnostic only: the direct expanded-lag HGB PDK prediction is rescaled toward a minutes-ratio correction (minutes candidate / previous-five-minute mean), with ratio clipped to [0.25, 1.75]. The weight is not tuned on outer holdout; table reports a sensitivity sweep. This is not production integration.','',down.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Decision','','Only integrate a minutes model if the nested gate improves minutes error in each cohort without worsening low-history or rotation-change cohorts, and if a downstream PDK adjustment improves MAE/RMSE consistently across outer seasons. A minutes-only gain is insufficient. No production code, configuration or weights were changed.','','No commit or push.','']
 REPORT.write_text('\n'.join(report),encoding='utf-8');print('\nPOOLED MINUTES\n'+pooled.to_string(index=False),flush=True);print('\nDOWNSTREAM PDK SENSITIVITY\n'+down.to_string(index=False),flush=True);print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
if __name__=='__main__':main()
