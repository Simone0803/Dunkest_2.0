#!/usr/bin/env python3
"""Diagnose V9 walk-forward residuals by season, lagged credit, and prior PDK.

Read-only with respect to source/model data. Uses saved expanding-origin OOF
predictions only; does not touch the prospective 2026/27 holdout or production.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link_predictions.csv'
OUT = ROOT / 'reports/audit'
FAMILY_MATCH = 'historical_form_plus_lagged_credit_and_expanded_matchup_v2'
FAMILY_REST = 'historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6'
FAMILY_BASE = 'baseline_previous5_mean'
BOOT = 2000
SEED = 20261013

def metrics(g, pred_col):
    e = g[pred_col].to_numpy(float) - g['actual_pdk_round_total'].to_numpy(float)
    return {'n': int(len(g)), 'mae': float(np.mean(np.abs(e))), 'rmse': float(np.sqrt(np.mean(e*e))), 'bias_pred_minus_actual': float(np.mean(e))}

def paired_delta_ci(g: pd.DataFrame, pred_a: str, pred_b: str, rng: np.random.Generator, reps: int = BOOT):
    """Delta MAE B-A, resampling round clusters within each season."""
    if len(g) == 0:
        return {'delta_mae_b_minus_a': np.nan, 'ci95_low': np.nan, 'ci95_high': np.nan, 'n_round_clusters': 0}
    z = g.copy()
    z['_cluster'] = z['season_id'].astype(str) + ':' + z['round_index'].astype(str)
    z['_delta'] = (z[pred_b] - z['actual_pdk_round_total']).abs() - (z[pred_a] - z['actual_pdk_round_total']).abs()
    observed = float(z['_delta'].mean())
    season_clusters = {}
    for season, sg in z.groupby('season_id'):
        cl = {k: v['_delta'].to_numpy(float) for k, v in sg.groupby('_cluster')}
        season_clusters[season] = list(cl.values())
    draws = np.empty(reps, dtype=float)
    for i in range(reps):
        total, n = 0.0, 0
        for clist in season_clusters.values():
            if not clist: continue
            ix = rng.integers(0, len(clist), size=len(clist))
            for j in ix:
                vals = clist[j]
                total += float(vals.sum()); n += len(vals)
        draws[i] = total / n if n else np.nan
    lo, hi = np.nanquantile(draws, [0.025, 0.975])
    return {'delta_mae_b_minus_a': observed, 'ci95_low': float(lo), 'ci95_high': float(hi), 'n_round_clusters': int(z['_cluster'].nunique())}

def main():
    if not SRC.exists(): raise SystemExit(f'Missing source predictions: {SRC}')
    df = pd.read_csv(SRC)
    key = ['season_id', 'season', 'round_index', 'source_week', 'source_round', 'player_name', 'actual_pdk_round_total', 'target_date', 'target_opponent']
    needed = set(key + ['feature_family', 'predicted_pdk_round_total', 'lagged_cr', 'lag1_pdk'])
    missing = sorted(needed - set(df.columns))
    if missing: raise SystemExit(f'Missing columns: {missing}')
    df['predicted_pdk_round_total'] = pd.to_numeric(df['predicted_pdk_round_total'], errors='coerce')
    df['actual_pdk_round_total'] = pd.to_numeric(df['actual_pdk_round_total'], errors='coerce')
    df['lagged_cr'] = pd.to_numeric(df['lagged_cr'], errors='coerce')
    df['lag1_pdk'] = pd.to_numeric(df['lag1_pdk'], errors='coerce')
    wide = df.pivot_table(index=key, columns='feature_family', values='predicted_pdk_round_total', aggfunc='first').reset_index()
    meta = df.groupby(key, dropna=False, as_index=False).agg(lagged_cr=('lagged_cr','first'), lag1_pdk=('lag1_pdk','first'))
    wide = wide.merge(meta, on=key, how='left', validate='one_to_one')
    comparisons = [(FAMILY_MATCH, FAMILY_REST, 'rest_schedule_minus_expanded_matchup'), (FAMILY_BASE, FAMILY_MATCH, 'expanded_matchup_minus_previous5_baseline'), (FAMILY_BASE, FAMILY_REST, 'rest_schedule_minus_previous5_baseline')]
    overall, byseason, segments = [], [], []
    rng = np.random.default_rng(SEED)
    for a,b,label in comparisons:
        common = wide.dropna(subset=[a,b,'actual_pdk_round_total']).copy()
        ma = metrics(common, a); mb = metrics(common, b)
        ci = paired_delta_ci(common, a, b, rng)
        overall.append({'comparison':label,'model_a':a,'model_b':b,'n_common':len(common),'mae_a':ma['mae'],'mae_b':mb['mae'],'rmse_a':ma['rmse'],'rmse_b':mb['rmse'],'bias_a':ma['bias_pred_minus_actual'],'bias_b':mb['bias_pred_minus_actual'],**ci})
        for season, g in common.groupby('season'):
            aa,bb=metrics(g,a),metrics(g,b)
            byseason.append({'comparison':label,'season':season,'n_common':len(g),'mae_a':aa['mae'],'mae_b':bb['mae'],'delta_mae_b_minus_a':bb['mae']-aa['mae'],'rmse_a':aa['rmse'],'rmse_b':bb['rmse'],'bias_a':aa['bias_pred_minus_actual'],'bias_b':bb['bias_pred_minus_actual']})
    # Main focus: whether rest/schedule gains are concentrated in interpretable lagged-market strata.
    a,b=FAMILY_MATCH,FAMILY_REST
    common=wide.dropna(subset=[a,b,'actual_pdk_round_total']).copy()
    for col, label, q in [('lagged_cr','lagged_cr_quartile',4),('lag1_pdk','lag1_pdk_quartile',4)]:
        sub=common.loc[common[col].notna()].copy()
        try: sub['segment'] = pd.qcut(sub[col], q=q, duplicates='drop')
        except ValueError: continue
        for segment,g in sub.groupby('segment', observed=True):
            aa,bb=metrics(g,a),metrics(g,b)
            ci=paired_delta_ci(g,a,b,rng,reps=1000)
            segments.append({'dimension':label,'segment':str(segment),'n':len(g),'mae_expanded_matchup':aa['mae'],'mae_rest_schedule':bb['mae'],'delta_mae_rest_minus_matchup':bb['mae']-aa['mae'],'rmse_expanded_matchup':aa['rmse'],'rmse_rest_schedule':bb['rmse'],'bias_expanded_matchup':aa['bias_pred_minus_actual'],'bias_rest_schedule':bb['bias_pred_minus_actual'],**ci})
    # Large-error profile for the primary model; descriptive only.
    residual=common.copy(); residual['abs_error']=abs(residual[b]-residual['actual_pdk_round_total']); residual['error']=residual[b]-residual['actual_pdk_round_total']
    residual['abs_error_decile']=pd.qcut(residual['abs_error'].rank(method='first'),10,labels=False)
    error_profile=[]
    for dec,g in residual.groupby('abs_error_decile'):
        error_profile.append({'absolute_error_decile':int(dec)+1,'n':len(g),'mean_abs_error':float(g['abs_error'].mean()),'mean_signed_error':float(g['error'].mean()),'mean_actual_pdk':float(g['actual_pdk_round_total'].mean()),'mean_predicted_pdk':float(g[b].mean()),'mean_lagged_cr':float(g['lagged_cr'].mean()),'mean_lag1_pdk':float(g['lag1_pdk'].mean())})
    stamp='20261013_v1'
    paths={'overall':OUT/f'dunkest_v9_residual_segments_{stamp}_overall.csv','season':OUT/f'dunkest_v9_residual_segments_{stamp}_by_season.csv','segments':OUT/f'dunkest_v9_residual_segments_{stamp}_market_segments.csv','errors':OUT/f'dunkest_v9_residual_segments_{stamp}_error_deciles.csv','report':OUT/f'dunkest_v9_residual_segments_{stamp}.md','json':OUT/f'dunkest_v9_residual_segments_{stamp}.json'}
    pd.DataFrame(overall).to_csv(paths['overall'],index=False); pd.DataFrame(byseason).to_csv(paths['season'],index=False); pd.DataFrame(segments).to_csv(paths['segments'],index=False); pd.DataFrame(error_profile).to_csv(paths['errors'],index=False)
    payload={'created_utc':datetime.now(timezone.utc).isoformat(),'source_predictions':str(SRC.relative_to(ROOT)),'source_rows':len(df),'wide_player_rounds':len(wide),'bootstrap_replicates_overall':BOOT,'bootstrap_replicates_segments':1000,'bootstrap_seed':SEED,'primary_comparison':'rest/schedule versus expanded matchup','selection_or_tuning_performed':False,'prospective_holdout_read':False,'overall':overall,'by_season':byseason,'market_segments':segments,'absolute_error_deciles':error_profile,'limitations':['Diagnostics use saved expanding-origin out-of-fold predictions only; no model fitting, feature selection, or hyperparameter tuning is performed.','Segments use lagged CR and prior-round PDK only; these are descriptive strata, not causal explanations.','The historical source does not provide a complete pre-lock market snapshot or reliable DNP/OUT labels.','No production code/configuration or frozen 2026/27 GW1 holdout was modified.']}
    paths['json'].write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    def table(rows, cols):
        if not rows:return '(no rows)'
        d=pd.DataFrame(rows)[cols].copy().round(4)
        cols=[str(c) for c in d.columns]
        rows=[[str(v) for v in row] for row in d.itertuples(index=False,name=None)]
        widths=[max(len(cols[i]), *(len(row[i]) for row in rows)) for i in range(len(cols))]
        head='| '+' | '.join(cols[i].ljust(widths[i]) for i in range(len(cols)))+' |'
        sep='| '+' | '.join('-'*widths[i] for i in range(len(cols)))+' |'
        body=['| '+' | '.join(row[i].ljust(widths[i]) for i in range(len(cols)))+' |' for row in rows]
        return '\n'.join([head,sep,*body])
    report=['# V9 walk-forward residual-segment audit','',f"Created UTC: {payload['created_utc']}",'','## Scope','','Descriptive audit of persisted V9 expanding-origin OOF predictions. No refitting, model selection, or production changes; prospective 2026/27 GW1 holdout was not read.','',f"Source rows: {len(df):,}; unique player-round keys: {len(wide):,}.",'','## Overall paired comparisons','',table(overall,['comparison','n_common','mae_a','mae_b','delta_mae_b_minus_a','ci95_low','ci95_high','rmse_a','rmse_b']),'','Delta and confidence interval are for MAE(model B) minus MAE(model A); negative favors B. Bootstrap resamples historical round clusters within each season.','', '## By held-out season','',table(byseason,['comparison','season','n_common','mae_a','mae_b','delta_mae_b_minus_a']),'','## Rest/schedule effect by lagged market segment','',table(segments,['dimension','segment','n','mae_expanded_matchup','mae_rest_schedule','delta_mae_rest_minus_matchup','ci95_low','ci95_high']),'','Negative delta favors adding rest/schedule features. Segment intervals are exploratory and not multiplicity-adjusted.','', '## Absolute-error deciles for rest/schedule model','',table(error_profile,['absolute_error_decile','n','mean_abs_error','mean_signed_error','mean_actual_pdk','mean_predicted_pdk','mean_lagged_cr','mean_lag1_pdk']),'','## Interpretation guardrails','',*[f'- {x}' for x in payload['limitations']],'','## Artifacts','',*[f'- `{p.relative_to(ROOT)}`' for p in paths.values()],'']
    paths['report'].write_text('\n'.join(report),encoding='utf-8')
    print('REPORT',paths['report']); print('OVERALL'); print(pd.DataFrame(overall).to_string(index=False)); print('SEASON'); print(pd.DataFrame(byseason).to_string(index=False)); print('SEGMENTS'); print(pd.DataFrame(segments).to_string(index=False)); print('ERROR DECILES'); print(pd.DataFrame(error_profile).to_string(index=False))
if __name__=='__main__': main()
