#!/usr/bin/env python3
"""Nested walk-forward test of a rotation-aware PDK expert gated to team changes."""
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.metrics import mean_absolute_error,mean_squared_error
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import experiment_dunkest_minutes_rate_decomposition_v1 as base
import experiment_dunkest_pdk_lag_features_v2 as lagbase
OUT=ROOT/'reports/audit';STAMP='dunkest_team_change_specialist_nested_20261014_v2';MET=OUT/f'{STAMP}_metrics.csv';PRED=OUT/f'{STAMP}_predictions.csv';REPORT=OUT/f'{STAMP}.md';AUDIT=OUT/f'{STAMP}.json'
WEIGHTS=[0.,.25,.5,.75,1.]
def score(y,p):
 y=np.asarray(y,float);p=np.asarray(p,float);e=p-y
 return {'n':len(y),'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5),'bias_pred_minus_actual':float(e.mean())}
def fit_predict(tr,te,cols):
 m=lagbase.make_model('hgb',cols);m.fit(tr[cols],tr.target_pdk.to_numpy(float));return np.asarray(m.predict(te[cols]),float)
def main():
 for f in (MET,PRED,REPORT,AUDIT):
  if f.exists():raise SystemExit(f'Refusing to overwrite existing output: {f}')
 df=pd.read_parquet(ROOT/'data/processed/dunkest_pdk_game_training_2020-26_v3.parquet');df['season_id']=df.season_id.astype(str);df=df.loc[df.season_id.isin(base.SEASONS)].copy();df['game_date']=pd.to_datetime(df.game_date,errors='coerce')
 labels=pd.read_parquet(ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet',columns=['nba_GAME_ID','nba_PLAYER_ID','nba_MIN','nba_match_status']);labels['nba_GAME_ID']=labels.nba_GAME_ID.astype('string');labels['nba_PLAYER_ID']=pd.to_numeric(labels.nba_PLAYER_ID,errors='coerce').astype('Int64');labels=labels.loc[labels.nba_match_status.eq('matched_player_date_opponent')].copy();keys=['nba_GAME_ID','nba_PLAYER_ID']
 dup=labels.loc[labels.duplicated(keys,keep=False)]
 if not dup.empty:
  for _,g in dup.groupby(keys,dropna=False):
   if g.nba_MIN.nunique(dropna=False)>1:raise SystemExit('Conflicting target-minute labels')
 labels=labels.drop_duplicates(keys,keep='first');df['nba_GAME_ID']=df.nba_GAME_ID.astype('string');df['nba_PLAYER_ID']=pd.to_numeric(df.nba_PLAYER_ID,errors='coerce').astype('Int64');df=df.merge(labels[keys+['nba_MIN']],on=keys,how='left',validate='many_to_one');df['target_minutes']=pd.to_numeric(df.nba_MIN,errors='coerce')
 df=df.loc[df.target_minutes.notna()&df.target_pdk.notna()&df.game_date.notna()].copy();df=base.make_features(df).replace([np.inf,-np.inf],np.nan)
 df=df.sort_values(['nba_PLAYER_ID','game_date','gameId'],kind='stable').copy();team=df.nba_TEAM_ABBREVIATION.astype('string').str.upper().str.strip();prev=team.groupby(df.nba_PLAYER_ID,dropna=False).shift(1);df['team_history_known']=prev.notna().astype(float);df['team_changed_from_previous_game']=(prev.notna()&team.notna()&prev.ne(team)).astype(float);segment=df.team_changed_from_previous_game.groupby(df.nba_PLAYER_ID,dropna=False).cumsum();df['team_games_since_change']=df.groupby([df.nba_PLAYER_ID,segment],dropna=False).cumcount().astype(float);prior_min=pd.to_numeric(df.target_minutes,errors='coerce').groupby(df.nba_PLAYER_ID,dropna=False).shift(1);df['min_std_5']=prior_min.groupby(df.nba_PLAYER_ID,dropna=False).transform(lambda s:s.rolling(5,min_periods=2).std(ddof=0));df['min_zero_rate_5']=prior_min.eq(0).astype(float).groupby(df.nba_PLAYER_ID,dropna=False).transform(lambda s:s.rolling(5,min_periods=1).mean());df['abs_min_last_vs_prev5']=pd.to_numeric(df.min_last_vs_prev5,errors='coerce').abs()
 basecols=base.BASE_NUM+['pdk_trend_3v10','min_trend_3v5','min_last_vs_prev5','lag1_pdk_per_min','prev3_pdk_per_min','prev5_pdk_per_min','lag1_pts_per_min','prev3_pts_per_min','prev5_pts_per_min','lag1_reb_per_min','prev3_reb_per_min','prev5_reb_per_min','lag1_ast_per_min','prev3_ast_per_min','prev5_ast_per_min','lag1_usage_proxy','prev3_usage_proxy','prev5_usage_proxy']+base.CAT
 rot=['team_changed_from_previous_game','team_history_known','team_games_since_change','min_std_5','min_zero_rate_5','abs_min_last_vs_prev5']
 for c in basecols+rot:
  if c not in df:df[c]=np.nan
 rotcols=basecols+rot
 foldrows=[];predrows=[];aud=[]
 # Rookie-season cohort is only a descriptive label; model selection/gating uses
 # as-of observable team-change flags, never future-derived rookie tags.
 debut=(df.loc[df.prior_nba_history_game_date.isna()&df.nba_PLAYER_ID.notna()].sort_values(['game_date','gameId']).drop_duplicates('nba_PLAYER_ID').set_index('nba_PLAYER_ID').season_id) if 'prior_nba_history_game_date' in df else pd.Series(dtype=object)
 df['rookie_season']=df.apply(lambda r:pd.notna(r.nba_PLAYER_ID) and debut.get(r.nba_PLAYER_ID)==r.season_id,axis=1)
 for fold in base.FOLDS:
  outer_train=df.loc[df.season_id.map(lambda s:int(s)<int(fold))].copy();outer_test=df.loc[df.season_id.eq(fold)].copy();dates=np.sort(outer_train.game_date.dropna().unique());cut=dates[max(1,int(len(dates)*.8))];inner_train=outer_train.loc[outer_train.game_date.lt(cut)];inner_valid=outer_train.loc[outer_train.game_date.ge(cut)]
  inner_base=fit_predict(inner_train,inner_valid,basecols);inner_rot=fit_predict(inner_train,inner_valid,rotcols);mask=pd.to_numeric(inner_valid.team_changed_from_previous_game,errors='coerce').fillna(0).eq(1).to_numpy();y=inner_valid.target_pdk.to_numpy(float);valid=mask&np.isfinite(y)&np.isfinite(inner_base)&np.isfinite(inner_rot)
  weight_scores=[]
  for w in WEIGHTS:
   if valid.sum():weight_scores.append({'rotation_weight':w,'n_team_change':int(valid.sum()),'mae':float(mean_absolute_error(y[valid],((1-w)*inner_base+w*inner_rot)[valid])),'rmse':float(mean_squared_error(y[valid],((1-w)*inner_base+w*inner_rot)[valid])**.5)})
  chosen=min(weight_scores,key=lambda x:(x['mae'],x['rotation_weight']))['rotation_weight'] if valid.sum()>=40 else 0.0
  outer_base=fit_predict(outer_train,outer_test,basecols);outer_rot=fit_predict(outer_train,outer_test,rotcols);is_change=pd.to_numeric(outer_test.team_changed_from_previous_game,errors='coerce').fillna(0).eq(1).to_numpy();gate=outer_base.copy();gate[is_change]=(1-chosen)*outer_base[is_change]+chosen*outer_rot[is_change]
  fr=outer_test[['season_id','game_date','gameId','dunkest_player_id','nba_PLAYER_ID','target_pdk','history_games_before_target','nba_history_games_before_target','team_changed_from_previous_game','rookie_season']].copy();fr['prediction_expanded_hgb']=outer_base;fr['prediction_rotation_hgb']=outer_rot;fr['prediction_nested_team_change_gate']=gate;fr['selected_rotation_weight']=chosen;fr['fold_season']=base.SEASONS[fold];predrows.append(fr)
  cohorts={'all':np.ones(len(fr),bool),'team_change':is_change,'rookie_season':fr.rookie_season.to_numpy(bool),'low_history_nonrookie':(pd.to_numeric(fr.history_games_before_target,errors='coerce').fillna(0).lt(5)&~fr.rookie_season).to_numpy(),'stable_veteran':(pd.to_numeric(fr.nba_history_games_before_target,errors='coerce').fillna(0).ge(100)&~is_change&~fr.rookie_season.to_numpy(bool)).to_numpy()}
  for name,p in [('expanded_hgb',outer_base),('rotation_hgb',outer_rot),('nested_team_change_gate',gate)]:
   for cohort,cmask in cohorts.items():
    ok=cmask&np.isfinite(fr.target_pdk.to_numpy(float));
    if ok.any():foldrows.append({'fold_season_id':fold,'fold_season':base.SEASONS[fold],'candidate':name,'cohort':cohort,**score(fr.target_pdk.to_numpy(float)[ok],p[ok])})
  aud.append({'season':base.SEASONS[fold],'outer_train_rows':len(outer_train),'outer_test_rows':len(outer_test),'inner_train_rows':len(inner_train),'inner_valid_rows':len(inner_valid),'inner_cutoff':pd.Timestamp(cut).isoformat(),'inner_team_change_rows':int(valid.sum()),'inner_scores':weight_scores,'selected_rotation_weight':chosen,'outer_team_change_rows':int(is_change.sum())});print(f"Completed team-change specialist {base.SEASONS[fold]}: rotation weight={chosen:.2f}, inner rows={int(valid.sum())}",flush=True)
 preds=pd.concat(predrows,ignore_index=True);metrics=pd.DataFrame(foldrows);pooled=[]
 for (cand,cohort),g in metrics.groupby(['candidate','cohort'],sort=False):pooled.append({'candidate':cand,'cohort':cohort,'n':int(g.n.sum()),'mae':float(np.average(g.mae,weights=g.n)),'rmse':float(np.sqrt(np.average(g.rmse**2,weights=g.n))),'bias_pred_minus_actual':float(np.average(g.bias_pred_minus_actual,weights=g.n))})
 pooled=pd.DataFrame(pooled);preds.to_csv(PRED,index=False);metrics.to_csv(MET,index=False);audit={'created_utc':datetime.now(timezone.utc).isoformat(),'source':'dunkest_pdk_game_training_2020-26_v3 filtered to 2020/21–2024/25; enriched crosswalk for minutes labels','outer_folds':{f:base.SEASONS[f] for f in base.FOLDS},'inner_validation_fraction':.20,'rotation_weight_candidates':WEIGHTS,'gating_policy':'apply rotation-aware model blend only when current target team differs from previous observed team; weight selected only on inner time-ordered validation team-change rows','holdout_2025_26_loaded':False,'prospective_2026_27_loaded':False,'fold_selection':aud,'pooled_metrics':pooled.to_dict('records'),'fold_metrics':metrics.to_dict('records'),'production_changed':False};AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
 report=['# Nested team-change specialist — V1','',f"Generated UTC: {audit['created_utc']}",'','## Method','','An expanded-lag HGB model is compared with a rotation-aware HGB model. For each outer held-out season, the blend weight is chosen only on a later-in-time validation slice within the training block and only among player-games with an as-of observed team change. The rotation model is used only for the team-change subgroup; all other rows keep the expanded-lag forecast. Rookie labels are descriptive only. No 2025/26 holdout or 2026/27 prospective bundle is loaded.','','## Pooled metrics by cohort','',pooled.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Fold metrics','',metrics.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Fold-specific selection','',json.dumps(aud,indent=2),'','## Decision','','Promote only if the nested gate improves team-change MAE without a material total MAE/RMSE penalty and the direction is stable in every outer season. Team-change labels are derived from the prior observed team in the linked archive, not an independently verified transaction feed. This is player-level PDK validation only. No production changes or commits/pushes.',''];REPORT.write_text('\n'.join(report),encoding='utf-8');print('\nPOOLED RESULTS\n'+pooled.to_string(index=False),flush=True);print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
if __name__=='__main__':main()
