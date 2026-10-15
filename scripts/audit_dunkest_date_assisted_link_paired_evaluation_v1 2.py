#!/usr/bin/env python3
"""Paired round-clustered evaluation of corrected-link V7 vs date-assisted V8."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
V7=ROOT/'reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v7_corrected_team_link_predictions.csv'
V8=ROOT/'reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v8_date_assisted_link_predictions.csv'
OUT=ROOT/'reports/audit'; STEM='dunkest_date_assisted_link_paired_eval_20261013_v1'
ROWS=OUT/f'{STEM}_paired_rows.csv'; SUMMARY=OUT/f'{STEM}_summary.csv'; SEASON=OUT/f'{STEM}_by_season.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
KEYS=['season_id','source_week','source_round','player_name','feature_family']
FAMILIES=['historical_form_plus_lagged_credit_and_expanded_matchup_v2','historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6']
def metrics(y,p):
 e=p-y; return {'n':int(len(y)),'mae':float(np.mean(np.abs(e))),'rmse':float(np.sqrt(np.mean(e*e))),'bias':float(np.mean(e))}
def bootstrap(g,reps=10000,seed=20261013):
 rng=np.random.default_rng(seed); clusters=[]
 for sid,ss in g.groupby('season_id'):
  arr=[]
  for _,cc in ss.groupby(['source_week','source_round']):
   e7=cc.pred_v7.to_numpy(float)-cc.actual.to_numpy(float); e8=cc.pred_v8.to_numpy(float)-cc.actual.to_numpy(float)
   arr.append((len(cc),np.abs(e8).sum()-np.abs(e7).sum(),(e8*e8).sum(),(e7*e7).sum(),e8.sum()-e7.sum()))
  clusters.append((sid,np.asarray(arr,dtype=float)))
 vals=np.empty((reps,3),dtype=float)
 for i in range(reps):
  n=0; da=0; s8=0; s7=0; db=0
  for _,a in clusters:
   pick=rng.integers(0,len(a),size=len(a)); n+=a[pick,0].sum(); da+=a[pick,1].sum(); s8+=a[pick,2].sum(); s7+=a[pick,3].sum(); db+=a[pick,4].sum()
  vals[i]=[da/n,np.sqrt(s8/n)-np.sqrt(s7/n),db/n]
 return {'delta_mae_ci95':[float(v) for v in np.quantile(vals[:,0],[.025,.975])], 'delta_rmse_ci95':[float(v) for v in np.quantile(vals[:,1],[.025,.975])], 'delta_bias_ci95':[float(v) for v in np.quantile(vals[:,2],[.025,.975])], 'bootstrap_replicates':reps,'cluster_unit':'source week/round, resampled within held-out season','seed':seed}
def main():
 for p in [ROWS,SUMMARY,SEASON,JSON,MD]:
  if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
 a=pd.read_csv(V7); b=pd.read_csv(V8)
 for d in (a,b):
  for c in ['season_id','player_name','feature_family']: d[c]=d[c].astype(str)
  for c in ['source_week','source_round']: d[c]=pd.to_numeric(d[c],errors='coerce').astype('Int64')
 a=a.rename(columns={'actual_pdk_round_total':'actual_v7','predicted_pdk_round_total':'pred_v7'})
 b=b.rename(columns={'actual_pdk_round_total':'actual_v8','predicted_pdk_round_total':'pred_v8'})
 left=a[KEYS+['actual_v7','pred_v7']]; right=b[KEYS+['actual_v8','pred_v8']]
 if left.duplicated(KEYS).any() or right.duplicated(KEYS).any(): raise RuntimeError('Prediction keys not unique; refusing many-to-many comparison')
 joined=left.merge(right,on=KEYS,how='outer',indicator=True,validate='one_to_one')
 common=joined[joined._merge.eq('both')].copy()
 if not np.allclose(common.actual_v7.to_numpy(float),common.actual_v8.to_numpy(float),atol=1e-9,rtol=0): raise RuntimeError('Target labels differ on common rows')
 common=common.rename(columns={'actual_v7':'actual'})
 common['abs_err_v7']=(common.pred_v7-common.actual).abs(); common['abs_err_v8']=(common.pred_v8-common.actual).abs()
 common['sq_err_v7']=(common.pred_v7-common.actual)**2; common['sq_err_v8']=(common.pred_v8-common.actual)**2
 common['delta_abs_err_v8_minus_v7']=common.abs_err_v8-common.abs_err_v7
 common.to_csv(ROWS,index=False)
 summary=[]; by_season=[]
 for fam in FAMILIES:
  g=common[common.feature_family.eq(fam)].copy()
  if g.empty: continue
  m7=metrics(g.actual.to_numpy(float),g.pred_v7.to_numpy(float)); m8=metrics(g.actual.to_numpy(float),g.pred_v8.to_numpy(float)); boot=bootstrap(g)
  summary.append({'feature_family':fam,'paired_rows':len(g),'v7_mae':m7['mae'],'v8_mae':m8['mae'],'delta_mae_v8_minus_v7':m8['mae']-m7['mae'],'v7_rmse':m7['rmse'],'v8_rmse':m8['rmse'],'delta_rmse_v8_minus_v7':m8['rmse']-m7['rmse'],'v7_bias':m7['bias'],'v8_bias':m8['bias'],'delta_bias_v8_minus_v7':m8['bias']-m7['bias'],'round_clusters':int(g[['season_id','source_week','source_round']].drop_duplicates().shape[0]),**boot})
  for sid,ss in g.groupby('season_id'):
   m7s=metrics(ss.actual.to_numpy(float),ss.pred_v7.to_numpy(float)); m8s=metrics(ss.actual.to_numpy(float),ss.pred_v8.to_numpy(float))
   by_season.append({'feature_family':fam,'season_id':sid,'paired_rows':len(ss),'v7_mae':m7s['mae'],'v8_mae':m8s['mae'],'delta_mae_v8_minus_v7':m8s['mae']-m7s['mae'],'v7_rmse':m7s['rmse'],'v8_rmse':m8s['rmse'],'delta_rmse_v8_minus_v7':m8s['rmse']-m7s['rmse']})
 sm=pd.DataFrame(summary); ss=pd.DataFrame(by_season); sm.to_csv(SUMMARY,index=False); ss.to_csv(SEASON,index=False)
 cov={'v7_prediction_rows':int(len(a)),'v8_prediction_rows':int(len(b)),'common_prediction_rows':int(len(common)),'v7_only_rows':int(joined._merge.eq('left_only').sum()),'v8_only_rows':int(joined._merge.eq('right_only').sum()),'paired_rows_by_family':common.groupby('feature_family').size().to_dict()}
 result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'coverage':cov,'summary':sm.to_dict('records'),'by_season':ss.to_dict('records'),'interpretation_rule':'Negative delta_mae_v8_minus_v7 favors date-assisted V8 on identical held-out player-rounds. Confidence intervals resample full week-round clusters within held-out season. Because V8 can expand the training sample, this paired comparison measures predictive change on common test rows but is not a single-factor causal estimate.','guardrails':['No production model/config changed.','V8 is experimental and not promoted automatically.','Date-assisted mapping is allowed only for gp=1 rows with a unique official-valid same-date candidate matching rounded PDK and all 17 box-score fields.','The frozen 2026/27 GW1 holdout remains untouched until 2026-10-23T12:00:00Z.'],'artifacts':{'paired_rows':str(ROWS.relative_to(ROOT)),'summary':str(SUMMARY.relative_to(ROOT)),'by_season':str(SEASON.relative_to(ROOT)),'json':str(JSON.relative_to(ROOT)),'markdown':str(MD.relative_to(ROOT))}}
 JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
 lines=['# Date-assisted exact-signature linkage — paired walk-forward evaluation v1','',f"Generated UTC: {result['generated_at_utc']}",'','## Pairing and coverage','',f"- V7 prediction rows: **{len(a):,}**; V8 prediction rows: **{len(b):,}**.",f"- Common held-out predictions: **{len(common):,}**; V7-only: **{cov['v7_only_rows']:,}**; V8-only: **{cov['v8_only_rows']:,}**.",'','## Paired model results','','| Feature family | Paired rows | V7 MAE | V8 MAE | Δ MAE (V8−V7) | 95% round-bootstrap CI | V7 RMSE | V8 RMSE | Δ RMSE |','|---|---:|---:|---:|---:|---|---:|---:|---:|']
 for r in summary:
  ci=r['delta_mae_ci95']; lines.append(f"| {r['feature_family']} | {r['paired_rows']:,} | {r['v7_mae']:.4f} | {r['v8_mae']:.4f} | {r['delta_mae_v8_minus_v7']:+.4f} | [{ci[0]:+.4f}, {ci[1]:+.4f}] | {r['v7_rmse']:.4f} | {r['v8_rmse']:.4f} | {r['delta_rmse_v8_minus_v7']:+.4f} |")
 lines += ['','## By held-out season','','| Feature family | Season ID | Paired rows | V7 MAE | V8 MAE | Δ MAE |','|---|---:|---:|---:|---:|---:|']
 for r in by_season: lines.append(f"| {r['feature_family']} | {r['season_id']} | {r['paired_rows']:,} | {r['v7_mae']:.4f} | {r['v8_mae']:.4f} | {r['delta_mae_v8_minus_v7']:+.4f} |")
 lines += ['','## Decision policy','','A negative delta favors V8 on common held-out rows. Promotion requires a stable improvement with round-clustered intervals, consistent season-level behavior, and a documented linkage audit. Regardless of metrics, this is retrospective outcome linkage—not a complete pre-lock market snapshot. No production change follows from this experiment alone.','','## Artifacts',f'- Paired rows: `{ROWS.relative_to(ROOT)}`',f'- Summary: `{SUMMARY.relative_to(ROOT)}`',f'- By season: `{SEASON.relative_to(ROOT)}`',f'- JSON: `{JSON.relative_to(ROOT)}`','']
 MD.write_text('\n'.join(lines),encoding='utf-8')
 print(json.dumps({'coverage':cov,'summary':summary,'by_season':by_season,'artifacts':result['artifacts']},indent=2,default=str))
if __name__=='__main__': main()
