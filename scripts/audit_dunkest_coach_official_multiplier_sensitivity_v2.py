#!/usr/bin/env python3
"""Compare walk-forward coach base-score models after official multiplier scenarios."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.rules.coach import coach_coefficient
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_predictions.csv'
OUT=ROOT/'reports/audit'
STEM='dunkest_coach_official_multiplier_sensitivity_2018-26_v2'
METRICS=OUT/f'{STEM}_metrics.csv'; AUDIT=OUT/f'{STEM}.json'; REPORT=OUT/f'{STEM}.md'
DIFFS=[0.0,1.5,3.0,5.0,7.0,10.0,14.0,16.0]
METHODS=['model_pregame_team_form','baseline_previous5_base_score','baseline_previous10_base_score','baseline_train_median']
def transform(base,diff,higher):
    if not np.isfinite(base): return float('nan')
    c=coach_coefficient(diff,higher,base>=0)
    return float(base*c if base>=0 else base/c)
def main():
    for p in (METRICS,AUDIT,REPORT):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    d=pd.read_csv(INPUT)
    rows=[]
    for method,g in d.groupby('method'):
        if method not in METHODS: continue
        g=g.copy()
        for c in ('actual_base_coach_pdk','predicted_base_coach_pdk'):
            g[c]=pd.to_numeric(g[c],errors='coerce')
        g=g.dropna(subset=['actual_base_coach_pdk','predicted_base_coach_pdk'])
        for diff in DIFFS:
            band='0-0.99' if diff<1 else '1-1.99' if diff<2 else '2-3.99' if diff<4 else '4-5.99' if diff<6 else '6-7.99' if diff<8 else '8-11.99' if diff<12 else '12-15.99' if diff<16 else '16+'
            for side,higher in [('higher_price',True),('lower_price',False)]:
                a=np.array([transform(x,diff,higher) for x in g.actual_base_coach_pdk],float)
                p=np.array([transform(x,diff,higher) for x in g.predicted_base_coach_pdk],float)
                rows.append({'test_season':'pooled','method':method,'cr_difference_scenario':diff,'coach_price_side':side,'coefficient_band':band,'positive_score_multiplier':coach_coefficient(diff,higher,True),'negative_score_divisor':coach_coefficient(diff,higher,False),'n':len(a),'mae_pdk':mean_absolute_error(a,p),'rmse_pdk':float(np.sqrt(mean_squared_error(a,p))),'bias_pred_minus_actual_pdk':float(np.mean(p-a)),'scenario_is_historical_market':False})
                for season,sg in g.groupby('season'):
                    aa=np.array([transform(x,diff,higher) for x in sg.actual_base_coach_pdk],float)
                    pp=np.array([transform(x,diff,higher) for x in sg.predicted_base_coach_pdk],float)
                    rows.append({'test_season':season,'method':method,'cr_difference_scenario':diff,'coach_price_side':side,'coefficient_band':band,'positive_score_multiplier':coach_coefficient(diff,higher,True),'negative_score_divisor':coach_coefficient(diff,higher,False),'n':len(aa),'mae_pdk':mean_absolute_error(aa,pp),'rmse_pdk':float(np.sqrt(mean_squared_error(aa,pp))),'bias_pred_minus_actual_pdk':float(np.mean(pp-aa)),'scenario_is_historical_market':False})
    metrics=pd.DataFrame(rows)
    checks=[]
    for diff,high,low in [(0,1,1),(1.5,.95,1.05),(3,.91,1.14),(5,.87,1.23),(7,.83,1.32),(10,.79,1.41),(14,.75,1.5),(16,.7,1.6)]:
        checks.append(bool(np.isclose(coach_coefficient(diff,True,True),high) and np.isclose(coach_coefficient(diff,False,True),low)))
    if not all(checks): raise AssertionError('Coefficient table mismatch with official thresholds.')
    metrics.to_csv(METRICS,index=False)
    pooled=metrics.loc[metrics.test_season.eq('pooled')]
    baseline=pooled.loc[pooled.method.eq('baseline_previous5_base_score'),['cr_difference_scenario','coach_price_side','mae_pdk']].rename(columns={'mae_pdk':'baseline_prev5_mae'})
    comparison=pooled.loc[pooled.method.eq('model_pregame_team_form')].merge(baseline,on=['cr_difference_scenario','coach_price_side'],validate='one_to_one')
    comparison['mae_improvement_vs_prev5']=comparison.baseline_prev5_mae-comparison.mae_pdk
    audit={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'input':str(INPUT.relative_to(ROOT)),'evaluated_rows':int(metrics.loc[metrics.test_season.eq('pooled'),'n'].max()),'methods':METHODS,'cr_difference_scenarios':DIFFS,'official_rule_source':'https://docs.dunkest.com/regolamento-it/regolamento-fantasy/punteggio-allenatori','official_coefficient_checks_passed':sum(checks),'historical_coach_market_available_for_test_seasons':False,'interpretation':'Multiplier rule application is deterministic and checked against the official regulation. Since historical coach CR pairs are not archived for these test seasons, all CR spreads are controlled sensitivity scenarios, not exact historical PDK evaluation.','production_changed':False}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# Coach base-score models with official Dunkest multiplier scenarios — V2','','This audit applies the official coach coefficient rule to the walk-forward predictions from the base-score model and its baselines.','','## Critical distinction','','The coefficient table is deterministic, but the scenario CR differences below are hypothetical because historical pregame coach CR pairs are not available for 2022/23–2025/26. These results quantify sensitivity; they do not certify exact historical PDK.','','## Pooled model vs previous-five baseline','','Positive values in `mae_improvement_vs_prev5` mean the model has lower MAE than the previous-five baseline. All figures are scenario results, not historical-market results.','','| CR difference | Coach price side | Model MAE | Previous-5 MAE | MAE improvement |','|---:|---|---:|---:|---:|']
    for _,r in comparison.iterrows(): lines.append(f"| {r.cr_difference_scenario:g} | {r.coach_price_side} | {r.mae_pdk:.3f} | {r.baseline_prev5_mae:.3f} | {r.mae_improvement_vs_prev5:+.3f} |")
    lines += ['', '## Conclusions','',f"- Official coefficient checks passed: {sum(checks)}/8.",f"- Methods evaluated: {', '.join(METHODS)}.",'- The base-score model is evaluated walk-forward on 2022/23, 2023/24, 2024/25 and 2025/26, using only prior-game features.','- Exact historical PDK validation still requires the two pregame CR values for each coach matchup; the official regulation alone does not supply those historical prices.','- Production model and configuration unchanged.','','## Artifacts','',f'- Metrics CSV: `{METRICS.relative_to(ROOT)}`',f'- Audit JSON: `{AUDIT.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'status':'completed','metric_rows':len(metrics),'pooled_rows':len(pooled),'official_checks_passed':sum(checks),'outputs':[str(p.relative_to(ROOT)) for p in (METRICS,AUDIT,REPORT)]},indent=2))
if __name__=='__main__': raise SystemExit(main())
