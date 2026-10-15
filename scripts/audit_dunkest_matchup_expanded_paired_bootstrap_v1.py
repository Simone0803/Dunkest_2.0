#!/usr/bin/env python3
"""Paired, season-stratified cluster bootstrap for expanded matchup features."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/audit'
STEM='dunkest_matchup_expanded_paired_bootstrap_20261013_v1'
CSV=OUT/f'{STEM}.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
V1=OUT/'dunkest_lagged_credit_matchup_walk_forward_20261013_v1_predictions.csv'
V2=OUT/'dunkest_lagged_credit_matchup_walk_forward_20261013_v2_predictions.csv'
for p in (CSV,JSON,MD):
    if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
FAMILIES={
 'expanded_v2':'historical_form_plus_lagged_credit_and_expanded_matchup_v2',
 'matchup_v1':'historical_form_plus_lagged_credit_and_matchup',
 'credit_only':'historical_form_plus_lagged_credit',
}
KEY=['season_id','source_week','source_round','player_name']
def load(path, v2=False):
 d=pd.read_csv(path)
 d=d[d.feature_family.isin(FAMILIES.values())].copy()
 d['abs_error']=(pd.to_numeric(d.predicted_pdk_round_total)-pd.to_numeric(d.actual_pdk_round_total)).abs()
 d['squared_error']=(pd.to_numeric(d.predicted_pdk_round_total)-pd.to_numeric(d.actual_pdk_round_total))**2
 return d
v1=load(V1); v2=load(V2)
# Align only model predictions with identical held-out player-round targets.
frames=[]
for label,fam in FAMILIES.items():
 src=v2 if label=='expanded_v2' else v1
 source_family = fam if label in ('expanded_v2','credit_only') else 'historical_form_plus_lagged_credit_and_matchup'
 d=src[src.feature_family.eq(source_family)].copy()
 d=d.rename(columns={'predicted_pdk_round_total':f'pred_{label}'})
 d[f'abs_{label}']=(pd.to_numeric(d[f'pred_{label}'])-pd.to_numeric(d.actual_pdk_round_total)).abs()
 d[f'sq_{label}']=(pd.to_numeric(d[f'pred_{label}'])-pd.to_numeric(d.actual_pdk_round_total))**2
 keep=KEY+['actual_pdk_round_total',f'pred_{label}',f'abs_{label}',f'sq_{label}']
 frames.append(d[keep])
wide=frames[0]
for d in frames[1:]: wide=wide.merge(d.drop(columns=['actual_pdk_round_total']),on=KEY,how='inner',validate='one_to_one')
if len(wide)<50000: raise RuntimeError(f'Unexpected paired sample size: {len(wide)}')
wide['round_cluster']=wide.season_id.astype(str)+'|'+wide.source_week.astype(str)+'|'+wide.source_round.astype(str)
wide['season_id']=wide.season_id.astype(str)
comparisons=[('expanded_v2','matchup_v1'),('expanded_v2','credit_only')]
rng=np.random.default_rng(20261013); B=10000
rows=[]; bootstrap_detail={}
for season in sorted(wide.season_id.unique()):
 sub=wide[wide.season_id.eq(season)].copy(); clusters=sub.round_cluster.unique()
 for a,b in comparisons:
  delta=sub[f'abs_{a}'].to_numpy()-sub[f'abs_{b}'].to_numpy()
  rows.append({'scope':season,'comparison':f'{a}_minus_{b}','n_player_rounds':len(sub),'n_rounds':len(clusters),
    'mae_a':float(sub[f'abs_{a}'].mean()),'mae_b':float(sub[f'abs_{b}'].mean()),'delta_mae_a_minus_b':float(delta.mean()),
    'rmse_a':float(np.sqrt(sub[f'sq_{a}'].mean())),'rmse_b':float(np.sqrt(sub[f'sq_{b}'].mean())),
    'round_win_rate_a_better':float(sub.groupby('round_cluster').apply(lambda g:(g[f'abs_{a}'].mean()<g[f'abs_{b}'].mean()),include_groups=False).mean())})
# Stratified cluster bootstrap: resample whole rounds within each held-out season.
for a,b in comparisons:
 all_draws=[]; season_draws={}
 for season in sorted(wide.season_id.unique()):
  sub=wide[wide.season_id.eq(season)].copy()
  group_indices=[np.flatnonzero(sub.round_cluster.to_numpy()==c) for c in sub.round_cluster.unique()]
  diffs=np.empty(B)
  for j in range(B):
   chosen=rng.integers(0,len(group_indices),size=len(group_indices))
   idx=np.concatenate([group_indices[k] for k in chosen])
   diffs[j]=np.mean(sub[f'abs_{a}'].to_numpy()[idx]-sub[f'abs_{b}'].to_numpy()[idx])
  season_draws[season]=diffs
 # Each season contributes equal weight to the pooled bootstrap estimate, matching macro-average folds.
 pooled=np.mean(np.vstack([season_draws[s] for s in sorted(season_draws)]),axis=0)
 bootstrap_detail[f'{a}_minus_{b}']={'pooled_delta_ci95':[float(np.quantile(pooled,.025)),float(np.quantile(pooled,.975))],
   'bootstrap_fraction_delta_below_zero':float(np.mean(pooled<0)),
   'per_season':{s:{'ci95':[float(np.quantile(v,.025)),float(np.quantile(v,.975))], 'fraction_below_zero':float(np.mean(v<0))} for s,v in season_draws.items()}}
 rows.append({'scope':'pooled_macro_season_bootstrap','comparison':f'{a}_minus_{b}','n_player_rounds':len(wide),'n_rounds':wide.round_cluster.nunique(),
  'mae_a':float(wide.groupby('season_id')[f'abs_{a}'].mean().mean()),'mae_b':float(wide.groupby('season_id')[f'abs_{b}'].mean().mean()),
  'delta_mae_a_minus_b':float(np.mean([wide.loc[wide.season_id.eq(s),f'abs_{a}'].mean()-wide.loc[wide.season_id.eq(s),f'abs_{b}'].mean() for s in sorted(wide.season_id.unique())])),
  'rmse_a':float(np.mean([np.sqrt(wide.loc[wide.season_id.eq(s),f'sq_{a}'].mean()) for s in sorted(wide.season_id.unique())])),
  'rmse_b':float(np.mean([np.sqrt(wide.loc[wide.season_id.eq(s),f'sq_{b}'].mean()) for s in sorted(wide.season_id.unique())])),
  'round_win_rate_a_better':float(np.mean([wide.groupby('round_cluster').apply(lambda g:(g[f'abs_{a}'].mean()<g[f'abs_{b}'].mean()),include_groups=False).mean()]))})
metrics=pd.DataFrame(rows); metrics.to_csv(CSV,index=False)
audit={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'paired_rows':len(wide),'round_clusters':int(wide.round_cluster.nunique()),'test_seasons':sorted(wide.season_id.unique()),
 'bootstrap_replicates':B,'bootstrap_unit':'Dunkest season-week-round cluster; resampling is stratified by held-out season and all player outcomes in a sampled round stay together.',
 'comparisons':bootstrap_detail,'production_changed':False,'interpretation':'This is a small incremental-feature test. The pooled bootstrap uses equal weight per held-out season; it is not evidence for changing production unless gains are practically material and robust.'}
JSON.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n')
lines=['# Expanded matchup features — paired cluster bootstrap','',f"Generated UTC: {audit['generated_at_utc']}",'',f"Paired sample: {len(wide):,} player-round rows, {wide.round_cluster.nunique():,} season-week-round clusters.",'','## Metrics','',metrics.to_string(index=False),'','## Paired bootstrap (10,000 replicates)','']
for comp,v in bootstrap_detail.items():
 lines += [f"### {comp}",f"- Macro-season delta MAE 95% CI: [{v['pooled_delta_ci95'][0]:.4f}, {v['pooled_delta_ci95'][1]:.4f}] (negative favors expanded matchup).",f"- Fraction of bootstrap estimates below zero: {v['bootstrap_fraction_delta_below_zero']:.4f}.",'- Per-season intervals:']
 for s,x in v['per_season'].items(): lines.append(f"  - {s}: [{x['ci95'][0]:.4f}, {x['ci95'][1]:.4f}], fraction below zero {x['fraction_below_zero']:.4f}.")
lines += ['', '## Decision','', 'Expanded matchup adds defensive STL/BLK/TOV, possession/pace proxies, and 5-game recent trends. Treat any tiny gain as exploratory: do not change production unless the effect is both statistically stable and practically meaningful. Historical matchup date mapping and lagged-credit caveats remain unchanged.', '']
MD.write_text('\n'.join(lines))
print(json.dumps({'status':'completed','metrics':metrics.to_dict('records'),'bootstrap':bootstrap_detail,'artifacts':[str(p.relative_to(ROOT)) for p in (CSV,JSON,MD)]},indent=2))
