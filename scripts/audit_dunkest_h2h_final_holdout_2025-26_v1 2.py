#!/usr/bin/env python3
"""Untouched 2025/26 game-level holdout test for player-vs-opponent history.

No production files are modified. Training seasons are 2020/21-2024/25; test
season is 2025/26. H2H features use only valid historical PDK targets on earlier
calendar dates, including prior games within the test season (online one-step-ahead).
"""
from __future__ import annotations
import importlib.util, json, re
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
ROOT=Path(__file__).resolve().parents[1]; PROC=ROOT/'data/processed'; OUT=ROOT/'reports/audit'
DATA=PROC/'dunkest_pdk_game_training_2020-26_v3.parquet'
STEM='dunkest_h2h_final_holdout_2025-26_v1'
PRED=OUT/f'{STEM}_predictions.csv'; METRICS=OUT/f'{STEM}_metrics.csv'; AUDIT=OUT/f'{STEM}.json'; REPORT=OUT/f'{STEM}.md'
mod_path=ROOT/'scripts/validate_dunkest_historical_pdk_training_v2.py'
spec=importlib.util.spec_from_file_location('dunkest_training_schema',mod_path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
NUMERIC=list(mod.NUMERIC_FEATURES); CATEGORICAL=list(mod.CATEGORICAL_FEATURES); TARGET='target_pdk'
TRAIN_SEASONS={'5','7','9','13','19'}; TEST_SEASON='25'
SEASON_NAMES={'5':'2020-21','7':'2021-22','9':'2022-23','13':'2023-24','19':'2024-25','25':'2025-26'}
def key(s): return re.sub(r'[^a-z0-9]','',str(s).lower())
def attach_h2h(df):
 d=df.copy().reset_index(drop=True)
 d['game_date']=pd.to_datetime(d.game_date,errors='coerce')
 d['player_key']=d.dunkest_player_name.map(key)
 d['opponent_key']=d.opponentTeamCode.astype(str).str.upper().str.strip()
 d[TARGET]=pd.to_numeric(d[TARGET],errors='coerce')
 if d[["game_date","player_key","opponent_key",TARGET]].isna().any().any(): raise RuntimeError('Null H2H identity/date/target found')
 d=d.sort_values(['game_date','season_id','dunkest_player_id','gameId'],kind='stable').reset_index(drop=True)
 dates=d.game_date.to_numpy(dtype='datetime64[ns]'); players=d.player_key.to_numpy(); opponents=d.opponent_key.to_numpy(); scores=d[TARGET].to_numpy(float)
 prev_mean=pd.to_numeric(d.get('prev5_pdk_mean'),errors='coerce').to_numpy(float)
 h2h_mean=np.full(len(d),np.nan); h2h_last=np.full(len(d),np.nan); h2h_n=np.zeros(len(d),float)
 # Sorted per-key arrays + searchsorted(left) exclude every game on the target date.
 groups={}
 for (player,opp),g in d.groupby(['player_key','opponent_key'],sort=False):
  groups[(player,opp)]=(g.game_date.to_numpy(dtype='datetime64[ns]'),g[TARGET].to_numpy(float))
 for i,(player,opp,date) in enumerate(zip(players,opponents,dates)):
  gd=groups.get((player,opp))
  if gd is None: continue
  gdates,gscores=gd; end=int(np.searchsorted(gdates,date,side='left'))
  if end==0: continue
  hist=gscores[max(0,end-5):end]; hist=hist[np.isfinite(hist)]
  if len(hist): h2h_mean[i]=float(hist.mean()); h2h_last[i]=float(hist[-1]); h2h_n[i]=len(hist)
 d['h2h_pdk_mean_prev5']=h2h_mean; d['h2h_pdk_last']=h2h_last; d['h2h_valid_games_prev5']=h2h_n
 # Three pseudo-observations from the player's general prior-five-game PDK mean.
 shrunk=np.full(len(d),np.nan); have_prior=np.isfinite(prev_mean); have_h2h=h2h_n>0
 both=have_prior & have_h2h
 shrunk[both]=(h2h_mean[both]*h2h_n[both]+3*prev_mean[both])/(h2h_n[both]+3)
 shrunk[have_prior & ~have_h2h]=prev_mean[have_prior & ~have_h2h]
 shrunk[~have_prior & have_h2h]=h2h_mean[~have_prior & have_h2h]
 d['h2h_pdk_mean_shrunk_prev5']=shrunk
 return d,{'rows_with_prior_h2h':int((h2h_n>0).sum()),'rows_with_prior_h2h_fraction':float((h2h_n>0).mean()),
  'rows_with_prior_h2h_pdk':int(np.isfinite(h2h_mean).sum()),'player_opponent_groups':int(len(groups)),
  'same_day_exclusion':'searchsorted side=left excludes all games dated on the target date',
  'shrinkage':'(n_h2h * mean_h2h + 3 * prior_prev5_pdk_mean) / (n_h2h + 3); falls back to whichever prior is available'}
def score(y,p,name):
 err=p-y
 return {'model':name,'n':int(len(y)),'mae':float(mean_absolute_error(y,p)),
  'rmse':float(np.sqrt(mean_squared_error(y,p))),'bias_pred_minus_actual':float(err.mean()),'r2':float(r2_score(y,p))}
def main():
 for p in [PRED,METRICS,AUDIT,REPORT]:
  if p.exists(): raise SystemExit(f'Refusing to overwrite versioned output: {p}')
 if not DATA.exists(): raise SystemExit(f'Missing {DATA}')
 d=pd.read_parquet(DATA)
 required={'season_id','game_date','dunkest_player_id','dunkest_player_name','gameId','opponentTeamCode',TARGET,'prev5_pdk_mean','prev10_pdk_mean'}
 if not required.issubset(d.columns): raise SystemExit(f'Missing columns: {sorted(required-set(d.columns))}')
 d['season_id']=d.season_id.astype(str); d['game_date']=pd.to_datetime(d.game_date,errors='coerce'); d[TARGET]=pd.to_numeric(d[TARGET],errors='coerce')
 if d.duplicated(['season_id','dunkest_player_id','gameId']).any(): raise SystemExit('Duplicate player-game key')
 if d[TARGET].isna().any() or d.game_date.isna().any(): raise SystemExit('Null game-level target/date')
 if set(d.loc[d.season_id.isin(TRAIN_SEASONS),'season_id'].unique())!=TRAIN_SEASONS: raise SystemExit('Unexpected training season coverage')
 if set(d.loc[d.season_id.eq(TEST_SEASON),'season_id'].unique())!={TEST_SEASON}: raise SystemExit('2025/26 holdout missing')
 d,audit_h2h=attach_h2h(d)
 train=d[d.season_id.isin(TRAIN_SEASONS)].copy(); test=d[d.season_id.eq(TEST_SEASON)].copy()
 base_features=NUMERIC+CATEGORICAL
 h2h_features=base_features+['h2h_pdk_mean_shrunk_prev5','h2h_pdk_last','h2h_valid_games_prev5']
 forbidden={TARGET,'pdk','nba_PTS','nba_REB','nba_AST','nba_MIN','nba_GAME_ID','nba_PLAYER_ID','nba_match_status','gameId','nba_GAME_ID'}
 if forbidden.intersection(h2h_features): raise SystemExit(f'Forbidden feature leakage: {forbidden.intersection(h2h_features)}')
 ytr=train[TARGET].to_numpy(float); yte=test[TARGET].to_numpy(float)
 models={}
 for name,features in [('random_forest_baseline',base_features),('random_forest_h2h_shrunk',h2h_features)]:
  model_numeric = NUMERIC if name == 'random_forest_baseline' else NUMERIC + ['h2h_pdk_mean_shrunk_prev5','h2h_pdk_last','h2h_valid_games_prev5']
  model=mod.make_model('random_forest',model_numeric,CATEGORICAL)
  # Explicit numeric/categorical partition; h2h variables are numeric.
  model.fit(train[features],ytr); models[name]=model.predict(test[features])
 median=float(np.median(ytr)); prev10=pd.to_numeric(test.prev10_pdk_mean,errors='coerce').fillna(median).to_numpy(float)
 metrics=[score(yte,models['random_forest_baseline'],'random_forest_baseline'),score(yte,models['random_forest_h2h_shrunk'],'random_forest_h2h_shrunk'),score(yte,prev10,'baseline_prev10_mean')]
 metrics_df=pd.DataFrame(metrics); metrics_df['train_rows']=len(train); metrics_df['test_season']='2025-26'; metrics_df['train_seasons']='2020-21;2021-22;2022-23;2023-24;2024-25'
 pred=test[['season_id','season_label','game_date','gameId','dunkest_player_id','dunkest_player_name','opponentTeamCode','nba_match_status',TARGET,'lag1_pdk','prev5_pdk_mean','prev10_pdk_mean','h2h_pdk_mean_prev5','h2h_pdk_mean_shrunk_prev5','h2h_pdk_last','h2h_valid_games_prev5']].copy()
 pred['prediction_random_forest_baseline']=models['random_forest_baseline']; pred['prediction_random_forest_h2h_shrunk']=models['random_forest_h2h_shrunk']; pred['prediction_baseline_prev10_mean']=prev10
 pred['abs_error_rf_baseline']=np.abs(pred.prediction_random_forest_baseline-yte); pred['abs_error_rf_h2h']=np.abs(pred.prediction_random_forest_h2h_shrunk-yte); pred['abs_error_prev10']=np.abs(prev10-yte)
 # Paired cluster bootstrap by target calendar date; compare absolute error of the two RFs.
 dates=pred.game_date.dt.strftime('%Y-%m-%d').to_numpy(); unique_dates=np.unique(dates)
 delta=pred.abs_error_rf_h2h.to_numpy()-pred.abs_error_rf_baseline.to_numpy()
 sums=[]; counts=[]
 for day in unique_dates:
  ix=np.flatnonzero(dates==day); sums.append(float(delta[ix].sum())); counts.append(int(len(ix)))
 sums=np.array(sums); counts=np.array(counts); rng=np.random.default_rng(20261013); B=10000; boot=np.empty(B)
 for i in range(B):
  pick=rng.integers(0,len(unique_dates),size=len(unique_dates)); boot[i]=sums[pick].sum()/counts[pick].sum()
 ci=[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))]
 audit={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'dataset':str(DATA.relative_to(ROOT)),'target':TARGET,
  'train_seasons':{s:SEASON_NAMES[s] for s in sorted(TRAIN_SEASONS,key=int)},'test_season':SEASON_NAMES[TEST_SEASON],
  'train_rows':len(train),'test_rows':len(test),'baseline_feature_count':len(base_features),'h2h_feature_count':len(h2h_features),
  'baseline_features':base_features,'h2h_added_features':['h2h_pdk_mean_shrunk_prev5','h2h_pdk_last','h2h_valid_games_prev5'],
  'h2h_feature_audit':audit_h2h,'evaluation_protocol':'Fixed 2025/26 final season holdout; train on valid official PDK labels 2020/21–2024/25. Within test season this is online one-step-ahead: only earlier dates may inform player-vs-opponent history.',
  'bootstrap':{'replicates':B,'cluster':'target calendar date','comparison':'RF with shrunk H2H minus baseline RF absolute error; negative favors H2H','delta_mae':float(delta.mean()),'ci95':ci,'fraction_bootstrap_delta_below_zero':float(np.mean(boot<0))},
  'metrics':metrics,'production_changed':False,'limitations':['Game-level PDK holdout is not the same target as Dunkest weekly-round total.','2025/26 test is online one-step-ahead, not a whole-season batch forecast.','Historical official PDK labels in 2018/19 and 2019/20 remain excluded from supervised training because their validity flags are false.']}
 PRED.parent.mkdir(parents=True,exist_ok=True); pred.assign(game_date=pred.game_date.dt.strftime('%Y-%m-%d')).to_csv(PRED,index=False); metrics_df.to_csv(METRICS,index=False); AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n')
 rf=metrics[0]; h2h=metrics[1]; base=metrics[2]
 report=f'''# Player-vs-opponent history — final 2025/26 holdout\n\nGenerated UTC: {audit['generated_at_utc']}\n\n## Protocol\n\n- Train on official-valid game-level Dunkest PDK targets from 2020/21–2024/25 ({len(train):,} player-games).\n- Evaluate once on the untouched 2025/26 season ({len(test):,} player-games).\n- Compare the same Random Forest architecture and training rows, with the baseline feature set versus three H2H features.\n- H2H history is grouped by normalized player name and opponent. `searchsorted(side='left')` excludes every same-day game; only earlier official-valid target rows contribute.\n- The 2025/26 setting is online one-step-ahead: later test rows may use prior dated 2025/26 outcomes, but not current/future labels.\n\n## Results\n\n| Model | MAE | RMSE | Bias | R² |\n|---|---:|---:|---:|---:|\n| Random Forest baseline | {rf['mae']:.4f} | {rf['rmse']:.4f} | {rf['bias_pred_minus_actual']:.4f} | {rf['r2']:.4f} |\n| Random Forest + shrunk H2H | {h2h['mae']:.4f} | {h2h['rmse']:.4f} | {h2h['bias_pred_minus_actual']:.4f} | {h2h['r2']:.4f} |\n| Previous-10 PDK mean | {base['mae']:.4f} | {base['rmse']:.4f} | {base['bias_pred_minus_actual']:.4f} | {base['r2']:.4f} |\n\nPaired bootstrap by target calendar date, 10,000 replicates: RF+H2H minus baseline RF delta MAE **{delta.mean():.4f}**, 95% CI **[{ci[0]:.4f}, {ci[1]:.4f}]**. Fraction of bootstrap estimates below zero: {np.mean(boot<0):.4f}.\n\n## H2H coverage\n\n- Rows with prior player-vs-opponent games: {audit_h2h['rows_with_prior_h2h']:,} / {len(d):,} ({audit_h2h['rows_with_prior_h2h_fraction']:.1%}).\n- Distinct player-opponent groups: {audit_h2h['player_opponent_groups']:,}.\n- Shrinkage uses three pseudo-observations from the player's general previous-five-game PDK mean.\n\n## Interpretation and production decision\n\nThis is the key independent-season check for the H2H idea. If the confidence interval excludes zero, it supports a robust incremental gain on the 2025/26 game-level target. It still does not automatically justify production integration: the production predictor must reproduce the same pre-lock feature logic, and this game-level PDK target differs from the weekly-round total used in the earlier experiment. Production model/configuration remains unchanged.\n\n## Artifacts\n\n- Predictions: `{PRED.relative_to(ROOT)}`\n- Metrics: `{METRICS.relative_to(ROOT)}`\n- Audit: `{AUDIT.relative_to(ROOT)}`\n'''
 REPORT.write_text(report)
 print(json.dumps({'status':'completed','metrics':metrics,'paired_bootstrap':audit['bootstrap'],'h2h_coverage':audit_h2h,'artifacts':[str(p.relative_to(ROOT)) for p in [PRED,METRICS,AUDIT,REPORT]]},indent=2))
if __name__=='__main__': main()
