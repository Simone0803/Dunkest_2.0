#!/usr/bin/env python3
"""Paired round bootstrap comparing V7 calibrated zero-inclusive strategy with V6 raw strategy."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
V6=ROOT/'reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v6_rounds.csv'
V7=ROOT/'reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_rounds.csv'
STEM='dunkest_v6_v7_lineup_strategy_paired_bootstrap_20261014_v1'
CSV=ROOT/'reports/audit'/f'{STEM}.csv'; REPORT=ROOT/'reports/audit'/f'{STEM}.md'; JSON=ROOT/'reports/audit'/f'{STEM}.json'
def main():
    for p in (CSV,REPORT,JSON):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    a=pd.read_csv(V6); b=pd.read_csv(V7)
    keys=['season_id','round_index']
    cols=['season_id','round_index','model_realized_team_score_proxy_zero_missing','baseline_realized_team_score_proxy_zero_missing','proxy_status']
    a=a.loc[a['proxy_status'].eq('evaluated_proxy'),cols].copy()
    b=b.loc[b['proxy_status'].eq('evaluated_proxy'),cols].copy()
    d=a.merge(b,on=keys,how='inner',suffixes=('_v6','_v7'),validate='one_to_one')
    strategies={
        'model_v7_calibrated_zero_inclusive_minus_model_v6_raw':('model_realized_team_score_proxy_zero_missing_v7','model_realized_team_score_proxy_zero_missing_v6'),
        'baseline_v7_calibrated_minus_baseline_v6_raw':('baseline_realized_team_score_proxy_zero_missing_v7','baseline_realized_team_score_proxy_zero_missing_v6'),
    }
    rng=np.random.default_rng(20261014); nboot=50000; results=[]; per_round=d[keys].copy()
    for label,(new,old) in strategies.items():
        delta=pd.to_numeric(d[new],errors='coerce')-pd.to_numeric(d[old],errors='coerce')
        d[label]=delta
        valid=d.loc[delta.notna()].copy()
        groups=[(str(s),g[label].to_numpy(float)) for s,g in valid.groupby('season_id',sort=True)]
        total=sum(len(x) for _,x in groups); weights=[len(x)/total for _,x in groups]
        boot=np.zeros(nboot)
        for (_,values),w in zip(groups,weights):
            idx=rng.integers(0,len(values),size=(nboot,len(values)))
            boot+=w*values[idx].mean(axis=1)
        lo,hi=np.quantile(boot,[.025,.975]); v=valid[label].to_numpy(float)
        results.append({'comparison':label,'paired_rounds':int(len(v)),'mean_delta':float(v.mean()),'median_delta':float(np.median(v)),
                        'win_rate_new_strategy':float(np.mean(v>0)),'bootstrap_95_ci':[float(lo),float(hi)],
                        'bootstrap_nonpositive':int(np.sum(boot<=0)),'by_season':[{'season_id':s,'n':int(len(x)),'mean_delta':float(x.mean()),'win_rate':float(np.mean(x>0))} for s,x in groups]})
    d.to_csv(CSV,index=False)
    obj={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'paired_rounds':int(len(d)),'bootstrap_replicates':nboot,'seed':20261014,
         'method':'Paired season-stratified bootstrap on identical season_id/round_index rows. V6 is the observed-row-trained player model; V7 uses zero-inclusive proxy training and past-only role/history residual calibration. All realized strategy scores in this comparison use the same zero-for-missing evaluation proxy.',
         'comparisons':results,'limitations':['Zero-inclusive labels assume a missing player-week-round row means 0 points; this is a proxy, not official observation.','Candidate pool, CR/role and availability are reconstructed rather than certified pre-lock state.','Coach price and transfer malus remain proxies.']}
    JSON.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
    lines=['# Paired strategy comparison: V6 vs V7','',f"Generated UTC: {obj['generated_at_utc']}",'',f"Paired rounds: {len(d)}",'','## Comparisons','']
    for z in results:
        lines += [f"### {z['comparison']}",'',f"- Mean paired delta: **{z['mean_delta']:.3f} PDK**",f"- Median paired delta: {z['median_delta']:.3f} PDK",f"- New strategy wins: **{z['win_rate_new_strategy']:.1%}**",f"- Season-stratified bootstrap 95% CI: **[{z['bootstrap_95_ci'][0]:.3f}, {z['bootstrap_95_ci'][1]:.3f}]**",'', '| Season ID | Rounds | Mean delta | Win rate |','|---:|---:|---:|---:|']
        lines += [f"| {x['season_id']} | {x['n']} | {x['mean_delta']:.3f} | {x['win_rate']:.1%} |" for x in z['by_season']]+['']
    lines += ['## Limitations','']+[f'- {x}' for x in obj['limitations']]+['',f'Paired per-round data: `{CSV.relative_to(ROOT)}`',f'Machine-readable report: `{JSON.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines))
    print(json.dumps({'status':'completed','comparisons':results,'outputs':[str(CSV.relative_to(ROOT)),str(REPORT.relative_to(ROOT)),str(JSON.relative_to(ROOT))]},indent=2))
if __name__=='__main__': main()
