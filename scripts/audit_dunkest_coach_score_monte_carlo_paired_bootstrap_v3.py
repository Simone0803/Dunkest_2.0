#!/usr/bin/env python3
"""Paired game-cluster bootstrap for Monte Carlo vs direct coach-score forecast."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'reports/audit/dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v4_predictions.csv'
OUT=ROOT/'reports/audit'; STEM='dunkest_coach_score_monte_carlo_paired_bootstrap_2018-26_v3'
CSV=OUT/f'{STEM}.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
REPS=10000; SEED=20261013

def bootstrap(d, season_label):
    cols=['actual_base_coach_pdk','predicted_coach_pdk_monte_carlo','direct_model_pdk','baseline_previous10_pdk']
    d=d.dropna(subset=cols).copy()
    # Cluster at game level: the two opposing coaches in a game are not independent.
    game=d.groupby(['season','game_id'],sort=False).agg(
        mc_abs=('predicted_coach_pdk_monte_carlo',lambda x: np.nan),
    )
    records=[]
    for (season,gid),g in d.groupby(['season','game_id'],sort=False):
        y=g.actual_base_coach_pdk.to_numpy(float)
        mc=np.abs(g.predicted_coach_pdk_monte_carlo.to_numpy(float)-y).mean()
        direct=np.abs(g.direct_model_pdk.to_numpy(float)-y).mean()
        prev10=np.abs(g.baseline_previous10_pdk.to_numpy(float)-y).mean()
        records.append({'season':season,'game_id':gid,'mc_mae':mc,'direct_mae':direct,'prev10_mae':prev10})
    gdf=pd.DataFrame(records)
    rng=np.random.default_rng(SEED)
    result=[]
    for comparator in ['direct_mae','prev10_mae']:
        delta=gdf['mc_mae'].to_numpy()-gdf[comparator].to_numpy()
        draws=np.empty(REPS)
        for i in range(REPS):
            if season_label=='pooled_2022-26':
                # Stratified cluster bootstrap preserves the equal season weighting.
                sample_parts=[]
                for season,sg in gdf.groupby('season',sort=True):
                    ids=rng.integers(0,len(sg),size=len(sg))
                    sample_parts.append((sg['mc_mae'].to_numpy()-sg[comparator].to_numpy())[ids])
                draws[i]=np.concatenate(sample_parts).mean()
            else:
                ids=rng.integers(0,len(delta),size=len(delta)); draws[i]=delta[ids].mean()
        result.append({'period':season_label,'comparator':comparator.replace('_mae',''),'games':len(gdf),
                       'mean_mc_mae':float(gdf.mc_mae.mean()),'mean_comparator_mae':float(gdf[comparator].mean()),
                       'mean_paired_mae_delta_mc_minus_comparator':float(delta.mean()),
                       'bootstrap_95ci_low':float(np.quantile(draws,.025)),
                       'bootstrap_95ci_high':float(np.quantile(draws,.975)),
                       'probability_mc_mae_lower_bootstrap':float(np.mean(draws<0)),
                       'game_win_rate_mc_lower_abs_error':float(np.mean(delta<0)),
                       'bootstrap_replicates':REPS})
    return result

def main():
    for p in (CSV,JSON,MD):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    d=pd.read_csv(INPUT)
    rows=bootstrap(d,'pooled_2022-26')
    for season,g in d.groupby('season',sort=True): rows.extend(bootstrap(g,str(season)))
    out=pd.DataFrame(rows); out.to_csv(CSV,index=False)
    audit={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'input':str(INPUT.relative_to(ROOT)),'bootstrap_replicates':REPS,'seed':SEED,'resampling_unit':'NBA game (paired two-team coach outcomes clustered together)','pooled_stratification':'equal number of game clusters resampled within each of the four seasons','results':rows,'production_changed':False,'interpretation':'Intervals estimate uncertainty in paired MAE differences on the available walk-forward seasons. They do not recover missing historical coach CR prices.'}
    JSON.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# Paired bootstrap: coach-score Monte Carlo vs baselines — V1','','10,000 paired bootstrap replicates, resampling NBA games as clusters so the two opposing coach outcomes remain together. Pooled intervals are stratified by season. Negative MAE delta favours Monte Carlo.','','| Period | Comparator | MAE delta MC − comparator | 95% bootstrap CI | P(MC better) | Game win rate |','|---|---|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['period']} | {r['comparator']} | {r['mean_paired_mae_delta_mc_minus_comparator']:+.3f} | [{r['bootstrap_95ci_low']:+.3f}, {r['bootstrap_95ci_high']:+.3f}] | {r['probability_mc_mae_lower_bootstrap']:.3f} | {r['game_win_rate_mc_lower_abs_error']:.3f} |")
    lines += ['', '## Interpretation', '', 'These are paired predictive-error comparisons for neutral-credit base coach scores, not exact credit-adjusted historical Dunkest PDK. Historical coach CR pairs remain unavailable. No production code/configuration changed.','','## Artifacts','',f'- CSV: `{CSV.relative_to(ROOT)}`',f'- JSON: `{JSON.relative_to(ROOT)}`','']
    MD.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'status':'completed','pooled': [r for r in rows if r['period']=='pooled_2022-26'],'outputs':[str(p.relative_to(ROOT)) for p in (CSV,JSON,MD)]},indent=2))
if __name__=='__main__': raise SystemExit(main())
