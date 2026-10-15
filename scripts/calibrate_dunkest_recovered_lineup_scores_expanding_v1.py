#!/usr/bin/env python3
"""Evaluate past-only post-selection score calibration on recovered lineup outcomes."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'reports/audit/dunkest_lineups_recovered_actuals_20261014_v2_rounds.csv'
STEM='dunkest_recovered_lineup_postselection_calibration_20261014_v1'; OUT=ROOT/'reports/audit'
CSV=OUT/f'{STEM}.csv'; REPORT=OUT/f'{STEM}.md'; JSON=OUT/f'{STEM}.json'
SEASON_ORDER={'2022-23':0,'2023-24':1,'2024-25':2}
def fit(x,y):
    x=np.asarray(x,float); y=np.asarray(y,float); ok=np.isfinite(x)&np.isfinite(y); x=x[ok]; y=y[ok]
    if len(x)<20 or np.std(x)<1e-8: return np.nan,np.nan
    slope=float(np.clip(np.polyfit(x,y,1)[0],0.0,2.0)); intercept=float(np.mean(y)-slope*np.mean(x)); return intercept,slope
def main():
    for p in (CSV,REPORT,JSON):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    d=pd.read_csv(INPUT); d=d.loc[d.complete_recovered_proxy.astype(bool)].copy()
    d['season_order']=d.season.map(SEASON_ORDER); d['round_index']=pd.to_numeric(d.round_index,errors='coerce')
    d['expected_team_pdk']=pd.to_numeric(d.expected_team_pdk,errors='coerce'); d['actual_proxy']=pd.to_numeric(d.recovered_team_score_proxy,errors='coerce')
    d=d.sort_values(['season_order','round_index','strategy'],kind='stable')
    outputs=[]
    for strategy,g in d.groupby('strategy',sort=False):
        history=[]
        for r in g.sort_values(['season_order','round_index'],kind='stable').itertuples(index=False):
            x=float(r.expected_team_pdk); y=float(r.actual_proxy)
            intercept,slope=fit([z[0] for z in history],[z[1] for z in history]) if len(history)>=20 else (np.nan,np.nan)
            calibrated=intercept+slope*x if np.isfinite(intercept) and np.isfinite(slope) else np.nan
            outputs.append({'season':r.season,'season_id':str(r.season_id),'round_index':int(r.round_index),'target_date':r.target_date,
              'strategy':strategy,'expected_raw':x,'actual_recovered_proxy':y,'expected_postselection_calibrated':calibrated,
              'history_rounds':len(history),'calibration_ready':bool(np.isfinite(calibrated)),'intercept':intercept,'slope':slope,
              'zero_candidate_share':float(r.zero_candidate_share)})
            history.append((x,y))
    out=pd.DataFrame(outputs); out.to_csv(CSV,index=False)
    metrics=[]
    for strategy,g in out.groupby('strategy'):
        for variant,col in [('raw','expected_raw'),('past_only_calibrated','expected_postselection_calibrated')]:
            q=g.dropna(subset=[col,'actual_recovered_proxy']); e=q[col].to_numpy(float)-q.actual_recovered_proxy.to_numpy(float)
            metrics.append({'strategy':strategy,'variant':variant,'n':len(q),'mae':float(np.mean(abs(e))) if len(q) else None,
              'rmse':float(np.sqrt(np.mean(e*e))) if len(q) else None,'bias_expected_minus_actual':float(np.mean(e)) if len(q) else None,
              'mean_zero_candidate_share':float(q.zero_candidate_share.mean()) if len(q) else None})
    obj={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'input':str(INPUT.relative_to(ROOT)),
      'method':'For each strategy, fit actual recovered proxy score = intercept + slope * expected lineup score on earlier fully scored rounds only. Calibration begins after 20 previous rounds, slope clipped to [0,2], and is used only to forecast the next round score; lineups are unchanged.',
      'metrics':metrics,'limitations':['Outcome scores include explicit zero candidates and are not certified official actuals.','Historical coach credit multipliers and transfer malus are still proxies.','This calibrates expected score after selection; it does not correct which players the optimizer selected.']}
    JSON.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
    lines=['# Past-only calibration of recovered Dunkest lineup scores — V1','',f"Generated UTC: {obj['generated_at_utc']}",'',obj['method'],'','## Results','','| Strategy | Variant | n | MAE | RMSE | Bias | Mean zero-candidate share |','|---|---|---:|---:|---:|---:|---:|']
    for m in metrics:
        fmt=lambda v:'n/a' if v is None else f'{v:.3f}'
        lines.append(f"| {m['strategy']} | {m['variant']} | {m['n']} | {fmt(m['mae'])} | {fmt(m['rmse'])} | {fmt(m['bias_expected_minus_actual'])} | {fmt(m['mean_zero_candidate_share'])} |")
    lines += ['', '## Limitations','']+[f'- {x}' for x in obj['limitations']]+['',f'Per-round calibration: `{CSV.relative_to(ROOT)}`',f'Machine-readable summary: `{JSON.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines)); print(json.dumps({'metrics':metrics,'outputs':[str(CSV.relative_to(ROOT)),str(REPORT.relative_to(ROOT)),str(JSON.relative_to(ROOT))]},indent=2))
if __name__=='__main__': main()
