#!/usr/bin/env python3
"""Past-only post-selection calibration for historical Dunkest lineup score forecasts."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_lineups.csv'
STEM='dunkest_lineup_postselection_calibration_20261014_v1'
OUT=ROOT/'reports/audit'
CSV=OUT/f'{STEM}.csv'; REPORT=OUT/f'{STEM}.md'; JSON=OUT/f'{STEM}.json'


def fit_affine(x: np.ndarray,y: np.ndarray) -> tuple[float,float]:
    """Fit a conservative affine mapping actual = intercept + slope * expected."""
    x=np.asarray(x,float); y=np.asarray(y,float)
    ok=np.isfinite(x)&np.isfinite(y); x=x[ok]; y=y[ok]
    if len(x)<20 or np.std(x)<1e-8:
        raise ValueError('insufficient calibration history')
    slope=float(np.polyfit(x,y,1)[0])
    slope=float(np.clip(slope,0.0,2.0))
    intercept=float(np.mean(y)-slope*np.mean(x))
    return intercept,slope


def main():
    for p in (CSV,REPORT,JSON):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    d=pd.read_csv(INPUT)
    d['season_id']=d['season_id'].astype(str)
    d['round_index']=pd.to_numeric(d['round_index'],errors='coerce')
    d['expected_team_pdk']=pd.to_numeric(d['expected_team_pdk'],errors='coerce')
    d['actual_proxy']=pd.to_numeric(d['realized_team_score_proxy_zero_missing'],errors='coerce')
    d=d.sort_values(['season_id','round_index','strategy'],kind='stable')
    rows=[]
    for strategy,g in d.groupby('strategy',sort=False):
        history=[]
        for _,r in g.sort_values(['season_id','round_index'],kind='stable').iterrows():
            x=float(r['expected_team_pdk']) if pd.notna(r['expected_team_pdk']) else np.nan
            y=float(r['actual_proxy']) if pd.notna(r['actual_proxy']) else np.nan
            if len(history)>=20:
                hx=np.array([z[0] for z in history],float); hy=np.array([z[1] for z in history],float)
                intercept,slope=fit_affine(hx,hy)
                calibrated=intercept+slope*x if np.isfinite(x) else np.nan
                calibration_n=len(history)
            else:
                intercept=np.nan; slope=np.nan; calibrated=np.nan; calibration_n=len(history)
            rows.append({
                'season_id':str(r['season_id']),'season':r['season'],'round_index':int(r['round_index']),
                'strategy':strategy,'expected_team_pdk_raw':x,'realized_team_score_proxy':y,
                'expected_team_pdk_postselection_calibrated':calibrated,
                'calibration_history_rounds':calibration_n,'calibration_intercept':intercept,'calibration_slope':slope,
                'calibration_ready':bool(calibration_n>=20 and np.isfinite(calibrated)),
            })
            if np.isfinite(x) and np.isfinite(y): history.append((x,y))
    out=pd.DataFrame(rows)
    out.to_csv(CSV,index=False)
    metrics=[]
    for strategy,g in out.groupby('strategy'):
        raw=g.dropna(subset=['expected_team_pdk_raw','realized_team_score_proxy'])
        ready=g.loc[g['calibration_ready']].dropna(subset=['expected_team_pdk_postselection_calibrated','realized_team_score_proxy'])
        def m(pred,actual):
            e=pd.to_numeric(pred,errors='coerce').to_numpy(float)-pd.to_numeric(actual,errors='coerce').to_numpy(float)
            ok=np.isfinite(e); e=e[ok]
            return {'n':int(len(e)),'mae':float(np.mean(np.abs(e))) if len(e) else None,'rmse':float(np.sqrt(np.mean(e**2))) if len(e) else None,'bias_pred_minus_actual':float(np.mean(e)) if len(e) else None}
        metrics.append({'strategy':strategy,'raw':m(raw['expected_team_pdk_raw'],raw['realized_team_score_proxy']),
                        'postselection_calibrated':m(ready['expected_team_pdk_postselection_calibrated'],ready['realized_team_score_proxy']),
                        'calibrated_rounds':int(len(ready)),
                        'mean_slope':float(ready['calibration_slope'].mean()) if len(ready) else None,
                        'mean_intercept':float(ready['calibration_intercept'].mean()) if len(ready) else None})
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'input':str(INPUT.relative_to(ROOT)),
            'method':'For each strategy, fit actual_proxy = intercept + slope * expected_team_pdk on prior rounds only, across prior test seasons and prior rounds of the current season. Calibration starts after 20 prior evaluated rounds. Slope is constrained to [0,2]. This adjusts the forecast score after lineup selection; it does not change selected lineups.',
            'metrics':metrics,'limitations':['Realized outcomes use the explicit zero-for-missing proxy from V7, not fully observed official scores.','Historical market/availability/coach credits and transfer malus remain incomplete.','Post-selection calibration adjusts score forecasts only and does not change lineup selection.']}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    lines=['# Expanding post-selection calibration of Dunkest lineup forecasts','',f"Generated UTC: {result['generated_at_utc']}",'',
           '## Method','',result['method'],'','## Results','','| Strategy | Raw MAE | Calibrated MAE | Raw RMSE | Calibrated RMSE | Raw bias | Calibrated bias | Calibrated rounds |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for z in metrics:
        raw=z['raw']; cal=z['postselection_calibrated']
        fmt=lambda v: 'n/a' if v is None else f'{v:.3f}'
        lines.append(f"| {z['strategy']} | {fmt(raw['mae'])} | {fmt(cal['mae'])} | {fmt(raw['rmse'])} | {fmt(cal['rmse'])} | {fmt(raw['bias_pred_minus_actual'])} | {fmt(cal['bias_pred_minus_actual'])} | {z['calibrated_rounds']} |")
    lines += ['', '## Limitations', '']+[f'- {x}' for x in result['limitations']]+['',f'Per-round output: `{CSV.relative_to(ROOT)}`',f'Machine-readable report: `{JSON.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines))
    print(json.dumps({'status':'completed','metrics':metrics,'outputs':[str(CSV.relative_to(ROOT)),str(REPORT.relative_to(ROOT)),str(JSON.relative_to(ROOT))]},indent=2))

if __name__=='__main__': main()
