#!/usr/bin/env python3
"""Independent paired date-cluster uncertainty audit for existing PDK ablation predictions.

Read-only with respect to source datasets. Writes uniquely versioned report artifacts;
never trains a model and never loads the frozen 2026/27 GW1 bundle or 2025/26 holdout.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'reports' / 'audit'
SOURCE = AUDIT / 'dunkest_pdk_lag_rotation_feature_ablation_20261014_v1_predictions.csv'
TAG = 'dunkest_pdk_rotation_ablation_paired_ci_20261015_v2'
OUT_JSON = AUDIT / f'{TAG}.json'
OUT_MD = AUDIT / f'{TAG}.md'
OUT_CSV = AUDIT / f'{TAG}_comparisons.csv'
SEED, BOOTSTRAPS = 20261015, 2000
if any(p.exists() for p in (OUT_JSON, OUT_MD, OUT_CSV)):
    raise SystemExit(f'Refusing to overwrite versioned output: {TAG}')
if not SOURCE.exists():
    raise SystemExit(f'Missing source predictions: {SOURCE}')

df = pd.read_csv(SOURCE)
required = {'season_id','game_date','gameId','dunkest_player_id','target_pdk','prediction','model','feature_set','history_games_before_target','target_minutes'}
missing = required - set(df.columns)
if missing: raise SystemExit(f'Missing required columns: {sorted(missing)}')
# This audit is restricted to outer folds 2022/23–2024/25; final 2025/26 holdout is excluded.
if set(df['season_id'].dropna().astype(int)) - {9,13,19}:
    raise SystemExit('Unexpected season in source; refusing to include a holdout or unknown season.')
sets = {'expanded_lags','rotation_aware'}
if not sets.issubset(set(df.feature_set.unique())): raise SystemExit('Required ablation variants missing.')
df = df[df.feature_set.isin(sets)].copy()
key=['season_id','game_date','gameId','dunkest_player_id','model']
if df.duplicated(key+['feature_set']).any(): raise SystemExit('Duplicate row keys within feature set.')
a=df[df.feature_set=='expanded_lags'].copy(); b=df[df.feature_set=='rotation_aware'].copy()
paired=a.merge(b,on=key,suffixes=('_expanded','_rotation'),validate='one_to_one')
if len(paired) != len(a) or len(paired) != len(b):
    raise SystemExit(f'Unpaired rows: expanded={len(a)}, rotation={len(b)}, paired={len(paired)}')
for col in ['target_pdk','target_minutes','history_games_before_target']:
    if not np.allclose(paired[f'{col}_expanded'],paired[f'{col}_rotation'],equal_nan=True):
        raise SystemExit(f'Target/stratum mismatch in paired rows: {col}')
paired['abs_expanded']=(paired.target_pdk_expanded-paired.prediction_expanded).abs()
paired['abs_rotation']=(paired.target_pdk_rotation-paired.prediction_rotation).abs()
paired['sq_expanded']=(paired.target_pdk_expanded-paired.prediction_expanded)**2
paired['sq_rotation']=(paired.target_pdk_rotation-paired.prediction_rotation)**2
paired['err_expanded']=paired.prediction_expanded-paired.target_pdk_expanded
paired['err_rotation']=paired.prediction_rotation-paired.target_pdk_rotation
paired['date_cluster']=paired.season_id.astype(str)+'|'+paired.game_date.astype(str)
# Cluster bootstrap: sample distinct target dates with replacement within each season.
rng=np.random.default_rng(SEED)
records=[]
def metrics(frame, model, cohort):
    n=len(frame)
    if n==0:return
    mae_a=frame.abs_expanded.mean(); mae_b=frame.abs_rotation.mean()
    rmse_a=float(np.sqrt(frame.sq_expanded.mean())); rmse_b=float(np.sqrt(frame.sq_rotation.mean()))
    bias_a=frame.err_expanded.mean(); bias_b=frame.err_rotation.mean()
    # Aggregate each date into sufficient statistics; bootstrap date clusters via vectorized sums.
    cols=['abs_expanded','abs_rotation','sq_expanded','sq_rotation','err_expanded','err_rotation']
    clusters=frame.groupby(['season_id','date_cluster'],sort=False)[cols].agg(['sum','count'])
    season_groups={}
    for season in frame.season_id.unique():
        sub=clusters.loc[int(season)]
        # all metric columns share the same per-date count
        sums=np.column_stack([sub[(c,'sum')].to_numpy() for c in cols])
        counts=sub[(cols[0],'count')].to_numpy(dtype=float)
        season_groups[int(season)]=(sums,counts)
    d_mae=np.empty(BOOTSTRAPS); d_rmse=np.empty(BOOTSTRAPS); d_bias=np.empty(BOOTSTRAPS)
    for j in range(BOOTSTRAPS):
        agg=np.zeros(6,dtype=float); total_n=0.0
        for sums,counts in season_groups.values():
            ix=rng.integers(0,len(counts),size=len(counts))
            agg += sums[ix].sum(axis=0); total_n += counts[ix].sum()
        mae_e,mae_r,sq_e,sq_r,err_e,err_r=agg/total_n
        d_mae[j]=mae_r-mae_e
        d_rmse[j]=np.sqrt(sq_r)-np.sqrt(sq_e)
        d_bias[j]=err_r-err_e
    def ci(v): return [float(np.quantile(v,.025)),float(np.quantile(v,.975))]
    records.append({'model':model,'cohort':cohort,'n_paired':n,'date_clusters':int(frame.date_cluster.nunique()),
      'expanded_mae':float(mae_a),'rotation_mae':float(mae_b),'delta_mae_rotation_minus_expanded':float(mae_b-mae_a),'delta_mae_ci95':ci(d_mae),
      'expanded_rmse':rmse_a,'rotation_rmse':rmse_b,'delta_rmse_rotation_minus_expanded':rmse_b-rmse_a,'delta_rmse_ci95':ci(d_rmse),
      'expanded_bias':float(bias_a),'rotation_bias':float(bias_b),'delta_bias_rotation_minus_expanded':float(bias_b-bias_a),'delta_bias_ci95':ci(d_bias)})

for model in sorted(paired.model.unique()):
    sub=paired[paired.model==model].copy()
    metrics(sub,model,'all')
    metrics(sub[sub.target_pdk_expanded>=25],model,'actual_pdk_ge_25')
    metrics(sub[sub.history_games_before_target_expanded<5],model,'history_games_lt_5')
    metrics(sub[sub.history_games_before_target_expanded==0],model,'no_prior_games')
    # Team-change subset is intentionally not fabricated: this source has no verified team-change label.

summary={'audit':'paired-date-cluster-CI-for-PDK-rotation-ablation','generated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
 'read_only_sources':True,'source_predictions':str(SOURCE.relative_to(ROOT)),'seasons_included':['2022-23','2023-24','2024-25'],
 'final_holdout_2025_26_loaded':False,'prospective_2026_27_GW1_loaded':False,'n_source_rows_each_variant':{'expanded_lags':int(len(a)),'rotation_aware':int(len(b))},
 'n_paired_rows':int(len(paired)),'date_clusters':int(paired.date_cluster.nunique()),'bootstrap_resamples':BOOTSTRAPS,'seed':SEED,
 'bootstrap_unit':'target game date, resampled within season; paired variant predictions remain together',
 'delta_convention':'rotation_aware minus expanded_lags; negative MAE/RMSE delta favours rotation-aware',
 'limitations':['This compares saved OOS predictions from existing experiment, not a fresh training run.','It does not establish team-change causality because source rows have no verified team-change label.','It evaluates player-game prediction, not selected lineup realized score.','2025/26 holdout and frozen 2026/27 GW1 are excluded.'],'comparisons':records}
OUT_JSON.write_text(json.dumps(summary,indent=2))
pd.DataFrame(records).to_csv(OUT_CSV,index=False)
lines=['# PDK rotation-feature ablation: paired date-cluster confidence intervals — V2','',f"Generated UTC: {summary['generated_at_utc']}",'', '## Protocol','',f"- Source: `{SOURCE.relative_to(ROOT)}`; no model retraining.",'- Identical paired player-game rows and targets for expanded-lag and rotation-aware variants.','- Seasons: 2022/23–2024/25 only. 2025/26 final holdout and frozen 2026/27 GW1 were not loaded.','- 2,000 paired bootstrap resamples of target-date clusters, sampled within season.','- Delta = rotation-aware minus expanded-lag; negative MAE/RMSE favours rotation-aware.','',f"- Paired rows: {len(paired):,}; distinct season-date clusters: {paired.date_cluster.nunique():,}.",'','## Results','', '| Model | Cohort | N | Dates | Expanded MAE | Rotation MAE | Δ MAE (95% CI) | Expanded RMSE | Rotation RMSE | Δ RMSE (95% CI) |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for r in records:
 ci=r['delta_mae_ci95']; ci2=r['delta_rmse_ci95']
 lines.append(f"| {r['model']} | {r['cohort']} | {r['n_paired']:,} | {r['date_clusters']:,} | {r['expanded_mae']:.4f} | {r['rotation_mae']:.4f} | {r['delta_mae_rotation_minus_expanded']:+.4f} [{ci[0]:+.4f}, {ci[1]:+.4f}] | {r['expanded_rmse']:.4f} | {r['rotation_rmse']:.4f} | {r['delta_rmse_rotation_minus_expanded']:+.4f} [{ci2[0]:+.4f}, {ci2[1]:+.4f}] |")
lines += ['', '## Interpretation rules','', '- A confidence interval spanning zero is inconclusive for that metric and cohort.','- Even an interval below zero supports only a player-level predictive gain on these outer folds; it does not certify lineup-score improvement.','- No team-change claim is made: the source lacks a verified team-change label.','- Production configuration and model weights are unchanged.','', '## Artifacts','',f'- JSON: `{OUT_JSON.relative_to(ROOT)}`',f'- CSV: `{OUT_CSV.relative_to(ROOT)}`','- This report is an uncertainty audit over existing saved predictions; it is not a new holdout.','']
OUT_MD.write_text('\n'.join(lines))
print(json.dumps({'report':str(OUT_MD.relative_to(ROOT)),'json':str(OUT_JSON.relative_to(ROOT)),'csv':str(OUT_CSV.relative_to(ROOT)),'n_paired':len(paired),'results':records},indent=2))
