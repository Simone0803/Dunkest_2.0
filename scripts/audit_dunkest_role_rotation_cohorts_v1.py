#!/usr/bin/env python3
"""Audit PDK lag-feature gains by rookie, low-history and team-change cohorts.

Uses archived outer-fold predictions only; target PDK/minutes are evaluation labels.
The 2025/26 holdout and 2026/27 prospective bundle are not loaded.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'; STAMP='dunkest_role_rotation_cohort_audit_20261014_v3'
PRED=OUT/'dunkest_pdk_lag_feature_ablation_20261014_v2_predictions.csv'; DATA=ROOT/'data/processed/dunkest_pdk_game_training_2020-26_v3.parquet'
METRICS=OUT/f'{STAMP}_metrics.csv'; FOLDS=OUT/f'{STAMP}_fold_metrics.csv'; REPORT=OUT/f'{STAMP}.md'; AUDIT=OUT/f'{STAMP}.json'
def metrics(y,p):
 y=np.asarray(y,float);p=np.asarray(p,float);e=p-y
 return {'n':len(y),'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5),'bias_pred_minus_actual':float(e.mean())}
def main():
 for f in (METRICS,FOLDS,REPORT,AUDIT):
  if f.exists(): raise SystemExit(f'Refusing to overwrite existing output: {f}')
 pred=pd.read_csv(PRED); pred['season_id']=pred.season_id.astype(str); pred['gameId']=pred.gameId.astype(str); pred['dunkest_player_id']=pred.dunkest_player_id.astype(str); pred['game_date']=pd.to_datetime(pred.game_date,errors='coerce')
 data=pd.read_parquet(DATA,columns=['season_id','game_date','gameId','dunkest_player_id','dunkest_player_name','nba_PLAYER_ID','nba_TEAM_ABBREVIATION','nba_history_games_before_target','history_games_before_target','prior_nba_history_game_date','prior_nba_history_season_id'])
 data['season_id']=data.season_id.astype(str);data['gameId']=data.gameId.astype(str);data['dunkest_player_id']=data.dunkest_player_id.astype(str);data['game_date']=pd.to_datetime(data.game_date,errors='coerce')
 if data.duplicated(['season_id','gameId','dunkest_player_id']).any(): raise SystemExit('Duplicate target keys in training data')
 data=data.sort_values(['nba_PLAYER_ID','game_date','gameId'],kind='stable').copy()
 data['prior_observed_team']=data.groupby('nba_PLAYER_ID',dropna=False)['nba_TEAM_ABBREVIATION'].shift(1)
 data['experienced_team_change']=(data['prior_observed_team'].notna() & data['nba_TEAM_ABBREVIATION'].notna() & data['prior_observed_team'].astype(str).ne(data['nba_TEAM_ABBREVIATION'].astype(str)))
 # True rookie season: the first season in the available linked history in which a
 # player's cumulative NBA-history count is zero on an observed target. Mark all
 # rows of that player-season; do not confuse a Dunkest newcomer with an NBA rookie.
 first_debut=(data.loc[data.prior_nba_history_game_date.isna() & data.nba_PLAYER_ID.notna()].sort_values(['game_date','gameId'],kind='stable').drop_duplicates('nba_PLAYER_ID',keep='first').set_index('nba_PLAYER_ID')['season_id'])
 data['rookie_season']=data.apply(lambda r: bool(pd.notna(r.nba_PLAYER_ID) and first_debut.get(r.nba_PLAYER_ID)==r.season_id),axis=1)
 data['low_history_nonrookie']=(pd.to_numeric(data.history_games_before_target,errors='coerce').fillna(0).lt(5) & ~data.rookie_season)
 keys=['season_id','gameId','dunkest_player_id']
 joined=pred.merge(data[keys+['nba_PLAYER_ID','nba_TEAM_ABBREVIATION','nba_history_games_before_target','history_games_before_target','prior_observed_team','experienced_team_change','rookie_season','low_history_nonrookie']],on=keys,how='left',validate='many_to_one',suffixes=('','_source'))
 if joined.nba_PLAYER_ID.isna().mean()>.01: raise SystemExit('Too many prediction rows failed cohort metadata join')
 joined['cohort_rookie_season']=joined.rookie_season.fillna(False)
 joined['cohort_low_history_nonrookie']=joined.low_history_nonrookie.fillna(False)
 joined['cohort_experienced_team_change']=joined.experienced_team_change.fillna(False)
 joined['cohort_stable_veteran']=(pd.to_numeric(joined.nba_history_games_before_target,errors='coerce').fillna(0).ge(100) & ~joined.cohort_experienced_team_change & ~joined.cohort_rookie_season)
 groups={'all':'__all__','rookie_season':'cohort_rookie_season','low_history_nonrookie':'cohort_low_history_nonrookie','experienced_team_change':'cohort_experienced_team_change','stable_veteran':'cohort_stable_veteran'}
 metrics_rows=[];fold_rows=[]
 for (model,feature_set),g0 in joined.groupby(['model','feature_set'],sort=False):
  for cohort,maskcol in groups.items():
   g=g0 if maskcol=='__all__' else g0.loc[g0[maskcol]]
   if g.empty: continue
   row={'model':model,'feature_set':feature_set,'cohort':cohort,**metrics(g.target_pdk,g.prediction)}
   if cohort!='all': row['unique_players']=int(g.nba_PLAYER_ID.nunique())
   metrics_rows.append(row)
   for season,sg in g.groupby('season_id'):
    fold_rows.append({'model':model,'feature_set':feature_set,'cohort':cohort,'season_id':season,**metrics(sg.target_pdk,sg.prediction),'unique_players':int(sg.nba_PLAYER_ID.nunique())})
 metrics_df=pd.DataFrame(metrics_rows); fold_df=pd.DataFrame(fold_rows)
 # paired candidate deltas on the same exact player-game rows
 wide=joined.pivot_table(index=keys+['model'],columns='feature_set',values='prediction',aggfunc='first').reset_index()
 targets=joined.drop_duplicates(keys)[keys+['target_pdk','nba_PLAYER_ID','rookie_season','low_history_nonrookie','experienced_team_change','nba_history_games_before_target']]
 wide=wide.merge(targets,on=keys,how='left',validate='many_to_one')
 delta_rows=[]
 for model,g0 in wide.groupby('model'):
  delta_groups={'all':'__all__','rookie_season':'rookie_season','low_history_nonrookie':'low_history_nonrookie','experienced_team_change':'experienced_team_change','stable_veteran':'__stable_veteran__'}
  for cohort,maskcol in delta_groups.items():
   if maskcol=='__all__': g=g0
   elif maskcol=='__stable_veteran__': g=g0.loc[pd.to_numeric(g0.nba_history_games_before_target,errors='coerce').fillna(0).ge(100) & ~g0.experienced_team_change.fillna(False) & ~g0.rookie_season.fillna(False)]
   else: g=g0.loc[g0[maskcol].fillna(False)]
   if not {'adapter_features','expanded_lags'}.issubset(g.columns) or g[['adapter_features','expanded_lags','target_pdk']].isna().any().any(): continue
   a=np.abs(g.adapter_features-g.target_pdk); b=np.abs(g.expanded_lags-g.target_pdk)
   delta_rows.append({'model':model,'cohort':cohort,'n':len(g),'players':int(g.nba_PLAYER_ID.nunique()),'mae_adapter':float(a.mean()),'mae_expanded':float(b.mean()),'delta_mae_expanded_minus_adapter':float((b-a).mean()),'bias_adapter':float((g.adapter_features-g.target_pdk).mean()),'bias_expanded':float((g.expanded_lags-g.target_pdk).mean())})
 delta=pd.DataFrame(delta_rows)
 metrics_df.to_csv(METRICS,index=False);fold_df.to_csv(FOLDS,index=False)
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'source_predictions':str(PRED.relative_to(ROOT)),'source_training_data':str(DATA.relative_to(ROOT)),'prediction_rows':len(pred),'joined_rows':len(joined),'join_missing_player_id':int(joined.nba_PLAYER_ID.isna().sum()),'holdout_2025_26_loaded':False,'prospective_2026_27_loaded':False,'rookie_definition':'first observed season in which the archived prior-NBA-game date is missing; applies to the whole player-season, as a proxy for rookie/debut season','low_history_nonrookie_definition':'fewer than five prior Dunkest player-games and not classified as NBA rookie season','experienced_team_change_definition':'target team differs from previous observed team for same NBA player in strictly earlier target-date row','delta_metrics':delta.to_dict('records'),'cohort_metrics':metrics_df.to_dict('records'),'fold_metrics':fold_df.to_dict('records'),'production_changed':False}
 AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
 report=['# Role / rotation cohort audit — V1','',f"Generated UTC: {audit['created_utc']}",'','## Design','','Reuses the same outer-fold predictions from the PDK lag-feature ablation; no models were retrained and no 2025/26 holdout or 2026/27 prospective data was loaded. Cohort tags use player history/team metadata and are diagnostics, not model inputs. Team change is detected when the target team differs from the previous observed team for that NBA player on an earlier target date. Rookie-season classification requires a row with no archived prior NBA game date and marks that player-season; low-history non-rookies are separately defined as fewer than five prior Dunkest games without the rookie-season tag.','','## Feature impact: expanded lags minus adapter feature set','','Negative delta MAE means expanded lags help.','',delta.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Metrics by model and cohort','',metrics_df.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Per-season cohort metrics','',fold_df.to_string(index=False,float_format=lambda x:f'{x:.4f}'),'','## Interpretation safeguards','','- NBA rookie status is an archive-derived proxy and may miss players whose first observed linked game is late in a season; counts are included for review.','- Team-change flags are based on previous observed linked Dunkest/NBA team, not an independently certified transaction feed. This is a rotation-change proxy, not proof of an official trade/free-agency event.','- This audit measures PDK player-game error only and does not certify lineup outcomes.','- No production weights or features were changed by this diagnostic.','','No commit or push.','']
 REPORT.write_text('\n'.join(report),encoding='utf-8')
 print('COHORT DELTAS\n'+delta.to_string(index=False,float_format=lambda x:f'{x:.4f}'),flush=True);print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
if __name__=='__main__':main()
