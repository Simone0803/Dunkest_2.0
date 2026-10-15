#!/usr/bin/env python3
"""Paired, round-clustered evaluation of legacy V6 and corrected-link V7 predictions."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
V6=ROOT/'reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v6_rest_schedule_predictions.csv'
V7=ROOT/'reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v7_corrected_team_link_predictions.csv'
OUT=ROOT/'reports/audit'; STEM='dunkest_historical_matchup_team_link_paired_eval_20261013_v1'
ROWS=OUT/f'{STEM}_paired_rows.csv'; SUMMARY=OUT/f'{STEM}_summary.csv'; SEASON=OUT/f'{STEM}_by_season.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
KEYS=['season_id','source_week','source_round','player_name','feature_family']
MODEL_FAMILIES=[
'historical_form_plus_lagged_credit_and_expanded_matchup_v2',
'historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6',
]
def metric(y,p):
    e=p-y
    return {'n':int(len(y)),'mae':float(np.mean(np.abs(e))),'rmse':float(np.sqrt(np.mean(e*e))),'bias':float(np.mean(e))}
def bootstrap_cluster_delta(g,reps=10000,seed=20261013):
    # Resample source rounds with replacement within each held-out season.
    rng=np.random.default_rng(seed)
    clusters=[]
    for sid,ss in g.groupby('season_id'):
        arr=[]
        for _,cc in ss.groupby(['source_week','source_round']):
            ev6=cc.pred_v6.to_numpy(float)-cc.actual.to_numpy(float)
            ev7=cc.pred_v7.to_numpy(float)-cc.actual.to_numpy(float)
            arr.append((len(cc),np.abs(ev7).sum()-np.abs(ev6).sum(),(ev7*ev7).sum(),(ev6*ev6).sum(),ev7.sum()-ev6.sum()))
        clusters.append((sid,np.asarray(arr,dtype=float)))
    vals=np.empty((reps,3),dtype=float)
    for i in range(reps):
        n_tot=0; d_abs=0; sq7=0; sq6=0; d_err=0
        for sid,a in clusters:
            pick=rng.integers(0,len(a),size=len(a))
            n_tot+=a[pick,0].sum(); d_abs+=a[pick,1].sum()
            sq7+=a[pick,2].sum(); sq6+=a[pick,3].sum(); d_err+=a[pick,4].sum()
        vals[i]=[d_abs/n_tot,np.sqrt(sq7/n_tot)-np.sqrt(sq6/n_tot),d_err/n_tot]
    return {
        'delta_mae_ci95':[float(x) for x in np.quantile(vals[:,0],[0.025,0.975])],
        'delta_rmse_ci95':[float(x) for x in np.quantile(vals[:,1],[0.025,0.975])],
        'delta_bias_ci95':[float(x) for x in np.quantile(vals[:,2],[0.025,0.975])],
        'bootstrap_replicates':reps,'cluster_unit':'source week/round, resampled within held-out season','seed':seed,
    }
def main():
    for p in [ROWS,SUMMARY,SEASON,JSON,MD]:
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    a=pd.read_csv(V6); b=pd.read_csv(V7)
    for d in (a,b):
        for c in ['season_id','player_name','feature_family']: d[c]=d[c].astype(str)
        for c in ['source_week','source_round']: d[c]=pd.to_numeric(d[c],errors='coerce').astype('Int64')
    a=a.rename(columns={'actual_pdk_round_total':'actual_v6','predicted_pdk_round_total':'pred_v6'})
    b=b.rename(columns={'actual_pdk_round_total':'actual_v7','predicted_pdk_round_total':'pred_v7'})
    # Same target row must have the same observed label across runs.
    left=a[KEYS+['actual_v6','pred_v6']]
    right=b[KEYS+['actual_v7','pred_v7']]
    if left.duplicated(KEYS).any() or right.duplicated(KEYS).any():
        raise RuntimeError('Prediction keys are not unique; refusing a many-to-many comparison')
    joined=left.merge(right,on=KEYS,how='outer',indicator=True,validate='one_to_one')
    common=joined[joined._merge.eq('both')].copy()
    if not np.allclose(common.actual_v6.to_numpy(float),common.actual_v7.to_numpy(float),atol=1e-9,rtol=0):
        raise RuntimeError('V6 and V7 labels differ on common prediction rows')
    common=common.rename(columns={'actual_v6':'actual'})
    common['abs_err_v6']=(common.pred_v6-common.actual).abs()
    common['abs_err_v7']=(common.pred_v7-common.actual).abs()
    common['sq_err_v6']=(common.pred_v6-common.actual)**2
    common['sq_err_v7']=(common.pred_v7-common.actual)**2
    common['delta_abs_err_v7_minus_v6']=common.abs_err_v7-common.abs_err_v6
    common['delta_sq_err_v7_minus_v6']=common.sq_err_v7-common.sq_err_v6
    common.to_csv(ROWS,index=False)
    summary=[]; season_rows=[]
    for fam in MODEL_FAMILIES:
        g=common[common.feature_family.eq(fam)].copy()
        if g.empty: continue
        m6=metric(g.actual.to_numpy(float),g.pred_v6.to_numpy(float))
        m7=metric(g.actual.to_numpy(float),g.pred_v7.to_numpy(float))
        boot=bootstrap_cluster_delta(g)
        summary.append({'feature_family':fam,'paired_rows':len(g),'v6_mae':m6['mae'],'v7_mae':m7['mae'],'delta_mae_v7_minus_v6':m7['mae']-m6['mae'],
                        'v6_rmse':m6['rmse'],'v7_rmse':m7['rmse'],'delta_rmse_v7_minus_v6':m7['rmse']-m6['rmse'],
                        'v6_bias':m6['bias'],'v7_bias':m7['bias'],'delta_bias_v7_minus_v6':m7['bias']-m6['bias'],
                        'round_clusters':int(g[['season_id','source_week','source_round']].drop_duplicates().shape[0]),**boot})
        for sid,ss in g.groupby('season_id'):
            m6s=metric(ss.actual.to_numpy(float),ss.pred_v6.to_numpy(float));m7s=metric(ss.actual.to_numpy(float),ss.pred_v7.to_numpy(float))
            season_rows.append({'feature_family':fam,'season_id':sid,'paired_rows':len(ss),
                                'v6_mae':m6s['mae'],'v7_mae':m7s['mae'],'delta_mae_v7_minus_v6':m7s['mae']-m6s['mae'],
                                'v6_rmse':m6s['rmse'],'v7_rmse':m7s['rmse'],'delta_rmse_v7_minus_v6':m7s['rmse']-m6s['rmse']})
    sm=pd.DataFrame(summary); ss=pd.DataFrame(season_rows)
    sm.to_csv(SUMMARY,index=False);ss.to_csv(SEASON,index=False)
    cov={
        'v6_prediction_rows':int(len(a)),'v7_prediction_rows':int(len(b)),
        'common_prediction_rows':int(len(common)),
        'v6_only_rows':int(joined._merge.eq('left_only').sum()),
        'v7_only_rows':int(joined._merge.eq('right_only').sum()),
        'paired_rows_by_family':common.groupby('feature_family').size().to_dict(),
    }
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'coverage':cov,
            'summary':sm.to_dict('records'),'by_season':ss.to_dict('records'),
            'interpretation_rule':'Negative delta_mae_v7_minus_v6 favors corrected-link V7 on the exact same held-out player-round rows. The 95% interval resamples whole week-round clusters within each test season. V6/V7 training sets differ because corrected linkage expands matchup-ready historical rows, so this is a paired predictive comparison, not a single-factor causal estimate.',
            'guardrails':['No production model/config changed.','V7 is experimental and not promoted automatically.','The frozen 2026/27 GW1 holdout remains untouched until 2026-10-23T12:00:00Z.'],
            'artifacts':{'paired_rows':str(ROWS.relative_to(ROOT)),'summary':str(SUMMARY.relative_to(ROOT)),'by_season':str(SEASON.relative_to(ROOT)),'json':str(JSON.relative_to(ROOT)),'markdown':str(MD.relative_to(ROOT))}}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
    lines=['# Historical matchup team-link correction — paired walk-forward evaluation v1','',f"Generated UTC: {result['generated_at_utc']}",'',
    '## Pairing and coverage','',f"- V6 prediction rows: **{len(a):,}**; V7 rows: **{len(b):,}**.",
    f"- Exact common player-round predictions: **{len(common):,}**; V6-only: **{cov['v6_only_rows']:,}**; V7-only: **{cov['v7_only_rows']:,}**.",
    '- Labels are checked equal on all paired rows. The paired comparison does not mix a changed target label with a changed prediction.','',
    '## Paired model results','',
    '| Feature family | Paired rows | V6 MAE | V7 MAE | Δ MAE (V7−V6) | 95% round-bootstrap CI | V6 RMSE | V7 RMSE | Δ RMSE |',
    '|---|---:|---:|---:|---:|---|---:|---:|---:|']
    for r in summary:
        ci=r['delta_mae_ci95']
        lines.append(f"| {r['feature_family']} | {r['paired_rows']:,} | {r['v6_mae']:.4f} | {r['v7_mae']:.4f} | {r['delta_mae_v7_minus_v6']:+.4f} | [{ci[0]:+.4f}, {ci[1]:+.4f}] | {r['v6_rmse']:.4f} | {r['v7_rmse']:.4f} | {r['delta_rmse_v7_minus_v6']:+.4f} |")
    lines += ['','## By held-out season','',
    '| Feature family | Season ID | Paired rows | V6 MAE | V7 MAE | Δ MAE |',
    '|---|---:|---:|---:|---:|---:|']
    for r in season_rows:
        lines.append(f"| {r['feature_family']} | {r['season_id']} | {r['paired_rows']:,} | {r['v6_mae']:.4f} | {r['v7_mae']:.4f} | {r['delta_mae_v7_minus_v6']:+.4f} |")
    lines += ['','## Decision policy','',
    'A negative delta favors V7 on common held-out rows. Treat the result as supportive only if the round-clustered confidence interval excludes zero, the season-level results are not driven by one fold, and the expanded-coverage sample does not conceal a material data-quality issue. The corrected link is still a retrospective outcome linkage, not a historical pre-lock market snapshot. No production changes are made from this comparison alone.','',
    '## Artifacts',f"- Paired rows: {ROWS.relative_to(ROOT)}",f"- Summary: {SUMMARY.relative_to(ROOT)}",f"- By season: {SEASON.relative_to(ROOT)}",f"- JSON: {JSON.relative_to(ROOT)}",'']
    MD.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'coverage':cov,'summary':summary,'by_season':season_rows,'artifacts':result['artifacts']},indent=2,default=str))
if __name__=='__main__': main()
