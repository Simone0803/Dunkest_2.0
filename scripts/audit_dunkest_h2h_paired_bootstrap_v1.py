#!/usr/bin/env python3
"""Paired round-cluster bootstrap for historical player-vs-opponent features."""
from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'
STEM='dunkest_h2h_paired_bootstrap_20261013_v1'
paths=[OUT/f'{STEM}.csv',OUT/f'{STEM}.json',OUT/f'{STEM}.md']
if any(p.exists() for p in paths): raise SystemExit('Refusing to overwrite existing versioned output')
V2=OUT/'dunkest_lagged_credit_matchup_walk_forward_20261013_v2_predictions.csv'
V4=OUT/'dunkest_lagged_credit_matchup_walk_forward_20261013_v4_predictions.csv'
KEY=['season_id','source_week','source_round','player_name']
FAMS={'expanded_matchup':'historical_form_plus_lagged_credit_and_expanded_matchup_v2',
      'h2h_unshrunk':'historical_form_plus_lagged_credit_expanded_matchup_and_h2h_v3',
      'h2h_shrunk':'historical_form_plus_lagged_credit_expanded_matchup_and_shrunk_h2h_v4'}
def read(path):
 d=pd.read_csv(path)
 d['season_id']=d['season_id'].astype(str)
 d['source_week']=pd.to_numeric(d['source_week'],errors='coerce').astype('Int64')
 d['source_round']=pd.to_numeric(d['source_round'],errors='coerce').astype('Int64')
 d['actual_pdk_round_total']=pd.to_numeric(d['actual_pdk_round_total'],errors='coerce')
 d['predicted_pdk_round_total']=pd.to_numeric(d['predicted_pdk_round_total'],errors='coerce')
 d=d[d.feature_family.isin(FAMS.values())].copy()
 d['abs_error']=(d.predicted_pdk_round_total-d.actual_pdk_round_total).abs()
 d['sq_error']=(d.predicted_pdk_round_total-d.actual_pdk_round_total)**2
 return d
v2=read(V2); v4=read(V4); pieces=[]
for label,fam in FAMS.items():
 src=v2 if label=='expanded_matchup' else v4
 x=src[src.feature_family.eq(fam)].copy()
 x=x.rename(columns={'predicted_pdk_round_total':f'pred_{label}','abs_error':f'abs_{label}','sq_error':f'sq_{label}'})
 pieces.append(x[KEY+['actual_pdk_round_total',f'pred_{label}',f'abs_{label}',f'sq_{label}']])
wide=pieces[0]
for x in pieces[1:]: wide=wide.merge(x.drop(columns='actual_pdk_round_total'),on=KEY,how='inner',validate='one_to_one')
if len(wide)<50000: raise RuntimeError(f'Unexpected paired rows: {len(wide)}')
wide['season_id']=wide.season_id.astype(str)
wide['round_cluster']=wide.season_id+'|'+wide.source_week.astype(str)+'|'+wide.source_round.astype(str)
comparisons=[('h2h_unshrunk','expanded_matchup'),('h2h_shrunk','expanded_matchup'),('h2h_shrunk','h2h_unshrunk')]
rng=np.random.default_rng(20261013); B=10000; metrics=[]; bootstrap={}
seasons=sorted(wide.season_id.unique())
for a,b in comparisons:
 detail={}; season_boot={}
 for season in seasons:
  sub=wide[wide.season_id.eq(season)].copy(); clusters=sub.round_cluster.unique()
  groups=[np.flatnonzero(sub.round_cluster.to_numpy()==c) for c in clusters]
  diff=sub[f'abs_{a}'].to_numpy()-sub[f'abs_{b}'].to_numpy()
  round_delta=sub.groupby('round_cluster').apply(lambda g:g[f'abs_{a}'].mean()-g[f'abs_{b}'].mean(),include_groups=False)
  metrics.append({'season':season,'comparison':f'{a}_minus_{b}','n':len(sub),'rounds':len(clusters),
    'mae_a':float(sub[f'abs_{a}'].mean()),'mae_b':float(sub[f'abs_{b}'].mean()),'delta_mae':float(diff.mean()),
    'rmse_a':float(np.sqrt(sub[f'sq_{a}'].mean())),'rmse_b':float(np.sqrt(sub[f'sq_{b}'].mean())),
    'round_win_rate_a_better':float((round_delta<0).mean())})
  draws=np.empty(B)
  for i in range(B):
   chosen=rng.integers(0,len(groups),size=len(groups)); idx=np.concatenate([groups[k] for k in chosen]); draws[i]=diff[idx].mean()
  season_boot[season]=draws
 pooled=np.mean(np.vstack([season_boot[s] for s in seasons]),axis=0)
 delta_macro=np.mean([wide.loc[wide.season_id.eq(s),f'abs_{a}'].mean()-wide.loc[wide.season_id.eq(s),f'abs_{b}'].mean() for s in seasons])
 metrics.append({'season':'macro_season','comparison':f'{a}_minus_{b}','n':len(wide),'rounds':int(wide.round_cluster.nunique()),
  'mae_a':float(np.mean([wide.loc[wide.season_id.eq(s),f'abs_{a}'].mean() for s in seasons])),
  'mae_b':float(np.mean([wide.loc[wide.season_id.eq(s),f'abs_{b}'].mean() for s in seasons])), 'delta_mae':float(delta_macro),
  'rmse_a':float(np.mean([np.sqrt(wide.loc[wide.season_id.eq(s),f'sq_{a}'].mean()) for s in seasons])),
  'rmse_b':float(np.mean([np.sqrt(wide.loc[wide.season_id.eq(s),f'sq_{b}'].mean()) for s in seasons])),
  'round_win_rate_a_better':float(np.mean([((wide[wide.season_id.eq(s)].groupby('round_cluster').apply(lambda g:g[f'abs_{a}'].mean()<g[f'abs_{b}'].mean(),include_groups=False)).mean()) for s in seasons]))})
 bootstrap[f'{a}_minus_{b}']={'macro_season_delta_mae_ci95':[float(np.quantile(pooled,.025)),float(np.quantile(pooled,.975))],
  'bootstrap_fraction_delta_below_zero':float(np.mean(pooled<0)),
  'per_season':{s:{'ci95':[float(np.quantile(v,.025)),float(np.quantile(v,.975))],'fraction_below_zero':float(np.mean(v<0))} for s,v in season_boot.items()}}
mdf=pd.DataFrame(metrics); mdf.to_csv(paths[0],index=False)
audit={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'paired_rows':len(wide),'round_clusters':int(wide.round_cluster.nunique()),'seasons':seasons,'bootstrap_replicates':B,
 'bootstrap_unit':'whole Dunkest season-week-round clusters, resampled within held-out season; macro-season pooled delta gives equal weight to each held-out season', 'comparisons':bootstrap,'production_changed':False}
paths[1].write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n')
lines=['# Player-vs-opponent features — paired cluster bootstrap','',f"Generated UTC: {audit['generated_at_utc']}",f"Paired targets: {len(wide):,}; round clusters: {wide.round_cluster.nunique():,}.",'','## Metrics','',mdf.to_string(index=False),'','## Bootstrap (10,000 replicates)','']
for name,d in bootstrap.items():
 lines += [f'### {name}',f"- Macro-season delta MAE 95% CI: [{d['macro_season_delta_mae_ci95'][0]:.4f}, {d['macro_season_delta_mae_ci95'][1]:.4f}] (negative favors the first model).",f"- Fraction below zero: {d['bootstrap_fraction_delta_below_zero']:.4f}."]
 for s,z in d['per_season'].items(): lines.append(f"- Season {s}: CI [{z['ci95'][0]:.4f}, {z['ci95'][1]:.4f}], fraction below zero {z['fraction_below_zero']:.4f}.")
lines += ['', '## Interpretation','', 'Historical head-to-head features are exploratory and depend on reconstructed player/opponent identity. The shrinkage feature uses three pseudo-observations from the player previous-five-round PDK mean. No production code or configuration was changed. A statistically detectable but tiny gain is not sufficient to promote a feature.', '']
paths[2].write_text('\n'.join(lines))
print(json.dumps({'status':'completed','metrics':mdf.to_dict('records'),'bootstrap':bootstrap,'artifacts':[str(p.relative_to(ROOT)) for p in paths]},indent=2))
