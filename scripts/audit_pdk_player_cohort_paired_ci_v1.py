#!/usr/bin/env python3
"""Paired date-cluster CI for existing OOS PDK predictions, stratified by player cohort.
No retraining, no holdout 2025/26, no prospective 2026/27 data, no source mutation.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports'/'audit'
SRC=OUT/'dunkest_pdk_lag_rotation_feature_ablation_20261014_v1_predictions.csv'
TAG='dunkest_pdk_player_cohort_paired_ci_20261015_v1'
paths=[OUT/f'{TAG}.json',OUT/f'{TAG}.md',OUT/f'{TAG}_cohorts.csv']
if any(p.exists() for p in paths): raise SystemExit(f'Refusing to overwrite: {TAG}')
if not SRC.exists(): raise SystemExit(f'Missing source: {SRC}')
df=pd.read_csv(SRC)
req={'season_id','game_date','gameId','dunkest_player_id','history_games_before_target','target_minutes','target_pdk','prediction','model','feature_set'}
if req-set(df): raise SystemExit(f'Missing columns: {sorted(req-set(df))}')
if set(pd.to_numeric(df.season_id,errors='coerce').dropna().astype(int))-{9,13,19}: raise SystemExit('Unexpected season; holdout exclusion failed')
variants={'expanded_lags','rotation_aware'}; df=df[df.feature_set.isin(variants)].copy()
key=['season_id','game_date','gameId','dunkest_player_id','model']
if df.duplicated(key+['feature_set']).any(): raise SystemExit('Duplicate paired keys')
a=df[df.feature_set.eq('expanded_lags')]; b=df[df.feature_set.eq('rotation_aware')]
p=a.merge(b,on=key,suffixes=('_a','_b'),validate='one_to_one')
if len(p)!=len(a) or len(p)!=len(b): raise SystemExit('Incomplete pairing')
for c in ['target_pdk','target_minutes','history_games_before_target']:
 if not np.allclose(p[f'{c}_a'],p[f'{c}_b'],equal_nan=True): raise SystemExit(f'Paired mismatch: {c}')
p['date_cluster']=p.season_id.astype(str)+'|'+p.game_date.astype(str)
p['abs_a']=(p.target_pdk_a-p.prediction_a).abs(); p['abs_b']=(p.target_pdk_b-p.prediction_b).abs()
p['sq_a']=(p.target_pdk_a-p.prediction_a)**2; p['sq_b']=(p.target_pdk_b-p.prediction_b)**2
p['err_a']=p.prediction_a-p.target_pdk_a; p['err_b']=p.prediction_b-p.target_pdk_b
hist=pd.to_numeric(p.history_games_before_target_a,errors='coerce'); mins=pd.to_numeric(p.target_minutes_a,errors='coerce'); actual=pd.to_numeric(p.target_pdk_a,errors='coerce')
p['cohort_history']=np.select([hist.eq(0),hist.lt(5),hist.lt(20) & hist.ge(5),hist.ge(20)],['no_prior_games','history_1_4','history_5_19','history_20_plus'],default='history_unknown')
p['cohort_minutes']=np.select([mins.lt(15),mins.lt(30),mins.ge(30)],['minutes_lt15','minutes_15_29','minutes_ge30'],default='minutes_unknown')
p['cohort_actual']=np.select([actual.ge(25),actual.lt(10)],['actual_pdk_ge25','actual_pdk_lt10'],default='actual_pdk_10_24_99')
SEED=20261015; B=2000; rng=np.random.default_rng(SEED); records=[]
def evaluate(g,model,axis,cohort):
 if len(g)<50:return
 cols=['abs_a','abs_b','sq_a','sq_b','err_a','err_b']
 bydate=g.groupby(['season_id','date_cluster'],sort=False)[cols].agg(['sum','count'])
 season_data={}
 for sid in g.season_id.unique():
  z=bydate.loc[int(sid)]; sums=np.column_stack([z[(c,'sum')].to_numpy() for c in cols]); counts=z[(cols[0],'count')].to_numpy(float)
  season_data[int(sid)]=(sums,counts)
 boot=np.empty((B,3))
 for j in range(B):
  agg=np.zeros(6); n=0
  for sums,counts in season_data.values():
   ix=rng.integers(0,len(counts),len(counts)); agg+=sums[ix].sum(axis=0); n+=counts[ix].sum()
  m=agg/n; boot[j]=[m[1]-m[0],np.sqrt(m[3])-np.sqrt(m[2]),m[5]-m[4]]
 vals=[]
 for i in range(3): vals.append([float(np.quantile(boot[:,i],.025)),float(np.quantile(boot[:,i],.975))])
 records.append({'model':model,'axis':axis,'cohort':cohort,'n':len(g),'players':int(g.dunkest_player_id.nunique()),'date_clusters':int(g.date_cluster.nunique()),'expanded_mae':float(g.abs_a.mean()),'rotation_mae':float(g.abs_b.mean()),'delta_mae':float(g.abs_b.mean()-g.abs_a.mean()),'delta_mae_ci95':vals[0],'expanded_rmse':float(np.sqrt(g.sq_a.mean())),'rotation_rmse':float(np.sqrt(g.sq_b.mean())),'delta_rmse':float(np.sqrt(g.sq_b.mean())-np.sqrt(g.sq_a.mean())),'delta_rmse_ci95':vals[1],'delta_bias':float(g.err_b.mean()-g.err_a.mean()),'delta_bias_ci95':vals[2]})
for model,g0 in p.groupby('model'):
 evaluate(g0,model,'all','all')
 for axis in ['cohort_history','cohort_minutes','cohort_actual']:
  for cohort,g in g0.groupby(axis): evaluate(g,model,axis.removeprefix('cohort_'),cohort)
summary={'generated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'source':str(SRC.relative_to(ROOT)),'seasons':['2022/23','2023/24','2024/25'],'excluded':['2025/26 final holdout','2026/27 GW1 prospective frozen test'],'paired_rows':len(p),'date_clusters':int(p.date_cluster.nunique()),'bootstrap_resamples':B,'bootstrap_unit':'target game date, resampled within season, paired predictions kept together','delta':'rotation_aware minus expanded_lags; negative MAE/RMSE is better','minimum_cohort_n':50,'caveats':['Only existing saved OOS predictions; no retraining.','Cohort labels use target minutes/score for post-hoc error diagnosis, not model inputs.','Actual-score cohorts describe error conditional on realized outcome, not a pre-match actionable segment.','Does not certify lineup realized-score improvement or causal effect.','No production feature or weight changes.'],'results':records}
paths[0].write_text(json.dumps(summary,indent=2)); pd.DataFrame(records).to_csv(paths[2],index=False)
lines=['# Paired player-cohort uncertainty audit — V1','',f"Generated UTC: {summary['generated_at_utc']}",'','## Protocol','',f"- Source: `{SRC.relative_to(ROOT)}`",f"- Paired rows: {len(p):,}; date clusters: {p.date_cluster.nunique():,}; bootstrap resamples: {B:,}.",' - Same targets and keys for both variants; target dates resampled within each season.','- Only 2022/23–2024/25 outer folds; no 2025/26 holdout or frozen 2026/27 GW1 loaded.','- Δ = rotation-aware minus expanded-lags; negative MAE/RMSE favours rotation-aware.','- Cohorts with fewer than 50 rows omitted.','', '## Results','', '| Model | Axis | Cohort | N | Players | Dates | Δ MAE [95% CI] | Δ RMSE [95% CI] | Δ bias |','|---|---|---|---:|---:|---:|---:|---:|---:|']
for r in records:
 c=r['delta_mae_ci95']; d=r['delta_rmse_ci95']; lines.append(f"| {r['model']} | {r['axis']} | {r['cohort']} | {r['n']:,} | {r['players']} | {r['date_clusters']} | {r['delta_mae']:+.4f} [{c[0]:+.4f}, {c[1]:+.4f}] | {r['delta_rmse']:+.4f} [{d[0]:+.4f}, {d[1]:+.4f}] | {r['delta_bias']:+.4f} |")
lines += ['', '## Interpretation','', '- CI entirely below zero: evidence of lower error for that cohort on these folds; CI crossing zero: inconclusive; CI above zero: evidence of a small regression.','- Minutes and realized-score strata are retrospective diagnostics, not known pre-match decision variables.','- No cohort result alone authorizes a production promotion; this is player-game accuracy, not realized lineup score.','- No weights/features changed.','', '## Artifacts',f'- JSON: `{paths[0].relative_to(ROOT)}`',f'- CSV: `{paths[2].relative_to(ROOT)}`','']
paths[1].write_text('\n'.join(lines)); print(json.dumps({'report':str(paths[1].relative_to(ROOT)),'json':str(paths[0].relative_to(ROOT)),'csv':str(paths[2].relative_to(ROOT)),'paired_rows':len(p),'results':records},indent=2))
