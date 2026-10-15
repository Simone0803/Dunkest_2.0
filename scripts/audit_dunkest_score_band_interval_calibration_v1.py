#!/usr/bin/env python3
"""Past-only OOS residual-interval calibration by forecast score band."""
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'
PRED=OUT/'dunkest_multiseason_production_ensemble_walk_forward_20261014_v1_predictions.csv'
STEM='dunkest_score_band_interval_calibration_20261014_v1'
FILES=[OUT/f'{STEM}.json',OUT/f'{STEM}.md',OUT/f'{STEM}_metrics.csv',OUT/f'{STEM}_cohorts.csv']
BINS=[-np.inf,5,10,15,20,25,np.inf]; LABELS=['<5','5-10','10-15','15-20','20-25','25+']
def diag(g,method,season,band):
 y=g.actual_pdk.to_numpy(float); p=g.predicted_pdk.to_numpy(float); q10=g.q10.to_numpy(float); q50=g.q50.to_numpy(float); q90=g.q90.to_numpy(float)
 lo=p-q90; med=p-q50; hi=p-q10
 return {'test_season':season,'method':method,'cohort':band,'n':len(g),'lower_tail_coverage':float(np.mean(y>=lo)),'upper_tail_coverage':float(np.mean(y<=hi)),'central_80_coverage':float(np.mean((y>=lo)&(y<=hi))),'mean_interval_width':float(np.mean(hi-lo)),'median_bias_after_offset':float(np.mean(med-y)),'median_absolute_error':float(np.mean(np.abs(med-y)))}
def main():
 if any(p.exists() for p in FILES): raise SystemExit('Refusing to overwrite versioned outputs')
 d=pd.read_csv(PRED); d=d.loc[d.method.eq('all_prior_seasons') & d.test_season.isin(['2022-23','2023-24','2024-25'])].copy()
 for c in ['predicted_pdk','actual_pdk','history_games']: d[c]=pd.to_numeric(d[c],errors='coerce')
 d=d.dropna(subset=['predicted_pdk','actual_pdk']); d['resid']=d.predicted_pdk-d.actual_pdk; d['band']=pd.cut(d.predicted_pdk,BINS,labels=LABELS,right=False)
 metrics=[]; cohorts=[]; folds=[]
 for season in ['2023-24','2024-25']:
  cal=d.loc[d.test_season.lt(season)].copy(); test=d.loc[d.test_season.eq(season)].copy()
  if cal.empty or test.empty: raise SystemExit(f'Missing fold {season}')
  qglobal=np.quantile(cal.resid,[.1,.5,.9]); pooled=test.copy(); pooled[['q10','q50','q90']]=np.tile(qglobal,(len(pooled),1))
  metrics.append(diag(pooled,'pooled_residual_quantiles',season,'all'))
  band_summary={}
  for band in LABELS:
   cg=cal.loc[cal.band.astype(str).eq(band),'resid']; tg=test.loc[test.band.astype(str).eq(band)].copy()
   if len(tg)==0: continue
   n=len(cg); alpha=n/(n+1000.0)
   qb=np.quantile(cg,[.1,.5,.9]) if n>=100 else qglobal
   q=alpha*qb+(1-alpha)*qglobal
   tg[['q10','q50','q90']]=np.tile(q,(len(tg),1))
   cohorts.append(diag(tg,'score_band_residual_quantiles',season,str(band)))
   # Same exact predicted band with pooled intervals, for paired comparison.
   tp=test.loc[test.band.astype(str).eq(band)].copy(); tp[['q10','q50','q90']]=np.tile(qglobal,(len(tp),1))
   cohorts.append(diag(tp,'pooled_residual_quantiles',season,str(band)))
   band_summary[str(band)]={'n_cal':int(n),'n_test':int(len(tg)),'q10_q50_q90':q.tolist(),'shrinkage_alpha':float(alpha)}
  # low history and high-score predicted cohorts, compared to pooled baseline.
  for label,mask in [('predicted_ge_20',test.predicted_pdk.ge(20)),('low_history_le_5',test.history_games.le(5)),('history_gt_5',test.history_games.gt(5))]:
   g=test.loc[mask].copy()
   if len(g)<30: continue
   q= np.quantile(cal.resid,[.1,.5,.9])
   g[['q10','q50','q90']]=np.tile(q,(len(g),1)); cohorts.append(diag(g,'pooled_residual_quantiles',season,label))
  folds.append({'test_season':season,'calibration_seasons':sorted(cal.test_season.unique()),'n_cal':len(cal),'n_test':len(test),'pooled_q10_q50_q90':qglobal.tolist(),'bands':band_summary})
  # overall score-band method predictions reconstructed across bands for aggregate diagnostic
  allg=[]
  for band in LABELS:
   cg=cal.loc[cal.band.astype(str).eq(band),'resid']; tg=test.loc[test.band.astype(str).eq(band)].copy()
   if tg.empty: continue
   n=len(cg); alpha=n/(n+1000.0); qb=np.quantile(cg,[.1,.5,.9]) if n>=100 else qglobal; q=alpha*qb+(1-alpha)*qglobal
   tg[['q10','q50','q90']]=np.tile(q,(len(tg),1)); allg.append(tg)
  metrics.append(diag(pd.concat(allg),'score_band_residual_quantiles',season,'all'))
 m=pd.DataFrame(metrics); c=pd.DataFrame(cohorts); m.to_csv(FILES[2],index=False); c.to_csv(FILES[3],index=False)
 payload={'created_utc':datetime.now(timezone.utc).isoformat(),'source':str(PRED.relative_to(ROOT)),'calibration':'strictly prior-season production-ensemble OOF residual q10/q50/q90, forecast score bands, shrinkage n/(n+1000)','folds':folds,'production_changed':False,'holdout_policy':'2025/26 excluded from this new experiment; 2026/27 GW1 untouched','metrics':metrics,'cohort_metrics':cohorts,'promotion_rule':'Only consider production integration if central coverage improves toward 0.80 and tail coverage toward 0.90 across both folds, without materially wider intervals or subgroup failures.'}
 FILES[0].write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
 lines=['# Score-band prediction interval calibration — past-only OOS','',f"Generated UTC: {payload['created_utc']}",'','## Protocol','','- Residuals are prediction minus actual from the production-ensemble OOF predictions.','- For each test season, residual quantiles are fitted only on strictly earlier seasons.','- Quantiles are estimated by forecast score band and shrunk toward the pooled residual quantiles with alpha = n/(n+1000).','- Target score is never used to choose the band. 2025/26 and 2026/27 GW1 are excluded. No production code/configuration changed.','','## Overall interval metrics','','| Season | Method | N | Lower-tail coverage | Upper-tail coverage | Central 80% coverage | Mean width | Median-offset bias | Median-adjusted MAE |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
 for r in metrics: lines.append(f"| {r['test_season']} | {r['method']} | {r['n']} | {r['lower_tail_coverage']:.4f} | {r['upper_tail_coverage']:.4f} | {r['central_80_coverage']:.4f} | {r['mean_interval_width']:.3f} | {r['median_bias_after_offset']:+.3f} | {r['median_absolute_error']:.4f} |")
 lines += ['','## Score-band coverage','','| Season | Method | Forecast band | N | Lower tail | Upper tail | Central 80% | Mean width | Median bias |','|---|---|---|---:|---:|---:|---:|---:|---:|']
 for r in cohorts:
  if r['cohort'] in LABELS: lines.append(f"| {r['test_season']} | {r['method']} | {r['cohort']} | {r['n']} | {r['lower_tail_coverage']:.4f} | {r['upper_tail_coverage']:.4f} | {r['central_80_coverage']:.4f} | {r['mean_interval_width']:.3f} | {r['median_bias_after_offset']:+.3f} |")
 lines += ['','## Other cohorts','','| Season | Method | Cohort | N | Central 80% | Mean width | Median bias |','|---|---|---|---:|---:|---:|---:|']
 for r in cohorts:
  if r['cohort'] not in LABELS: lines.append(f"| {r['test_season']} | {r['method']} | {r['cohort']} | {r['n']} | {r['central_80_coverage']:.4f} | {r['mean_interval_width']:.3f} | {r['median_bias_after_offset']:+.3f} |")
 lines += ['','## Decision','','This experiment is diagnostic only. A band-specific calibrator is not automatically better: its central coverage should approach 0.80, marginal lower/upper coverage 0.90, and widths should not expand excessively. These are historical folds, not a pristine final holdout.','',f'- Metrics: `{FILES[2].relative_to(ROOT)}`',f'- Cohorts: `{FILES[3].relative_to(ROOT)}`',f'- Audit JSON: `{FILES[0].relative_to(ROOT)}`','']
 FILES[1].write_text('\n'.join(lines)); print(m.to_string(index=False,float_format=lambda x:f'{x:.4f}')); print('REPORT',FILES[1])
if __name__=='__main__': main()
