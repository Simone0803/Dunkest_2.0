#!/usr/bin/env python3
"""Expanding-origin out-of-sample interval calibration audit.

Uses saved walk-forward Random Forest predictions and certified PDK labels.
For each test season, residual quantiles are learned only from earlier seasons.
Compares one pooled residual distribution with history-cohort quantiles. This
is an audit only: it does not alter production forecasts or uncertainty code.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PRED=ROOT/'data/processed/dunkest_pdk_game_walk_forward_predictions_2020-26_v3.csv'
TRAIN=ROOT/'data/processed/dunkest_pdk_game_training_2020-26_v3.parquet'
OUT=ROOT/'reports/audit'
STAMP='20261014_v2'
METRICS=OUT/f'dunkest_uncertainty_expanding_oos_{STAMP}_metrics.csv'
COHORTS=OUT/f'dunkest_uncertainty_expanding_oos_{STAMP}_cohorts.csv'
REPORT=OUT/f'dunkest_uncertainty_expanding_oos_{STAMP}.md'
AUDIT=OUT/f'dunkest_uncertainty_expanding_oos_{STAMP}.json'
TEST=['2023-24','2024-25','2025-26']
CALIBRATION=['2022-23','2023-24','2024-25']


def stats(g,method,season,cal_seasons,cohort):
    y=g.target_pdk.to_numpy(float); p=g.prediction.to_numpy(float)
    qlo=float(g.q10.iloc[0]); qhi=float(g.q90.iloc[0]); q50=float(g.q50.iloc[0])
    # residual is prediction - actual, so invert residual quantiles to get target-score intervals.
    lo=p-qhi; hi=p-qlo; med=p-q50
    return {'test_season':season,'method':method,'calibration_seasons':';'.join(cal_seasons),'cohort':cohort,'n':len(g),'q10_residual':qlo,'q50_residual':q50,'q90_residual':qhi,'lower_tail_coverage':float((y>=lo).mean()),'upper_tail_coverage':float((y<=hi).mean()),'central_80_coverage':float(((y>=lo)&(y<=hi)).mean()),'mean_interval_width':float(np.mean(hi-lo)),'median_bias_after_offset':float(np.mean(med-y)),'raw_mae':float(np.mean(np.abs(p-y))),'median_adjusted_mae':float(np.mean(np.abs(med-y)))}


def main():
    for p in [METRICS,COHORTS,REPORT,AUDIT]:
        if p.exists(): raise SystemExit(f'Refusing to overwrite: {p}')
    pred=pd.read_csv(PRED)
    pred=pred.loc[pred.prediction_season.isin(set(CALIBRATION)|set(TEST))].copy()
    pred['game_date']=pd.to_datetime(pred.game_date,errors='coerce').dt.strftime('%Y-%m-%d')
    pred['dunkest_player_id']=pd.to_numeric(pred.dunkest_player_id,errors='coerce').astype('Int64')
    pred['gameId']=pd.to_numeric(pred.gameId,errors='coerce').astype('Int64')
    pred['target_pdk']=pd.to_numeric(pred.target_pdk,errors='coerce')
    pred['prediction']=pd.to_numeric(pred.random_forest,errors='coerce')
    pred=pred.dropna(subset=['target_pdk','prediction','dunkest_player_id','gameId','game_date'])
    feat=pd.read_parquet(TRAIN,columns=['season_label','game_date','gameId','dunkest_player_id','history_games_before_target'])
    feat['game_date']=pd.to_datetime(feat.game_date,errors='coerce').dt.strftime('%Y-%m-%d')
    feat['dunkest_player_id']=pd.to_numeric(feat.dunkest_player_id,errors='coerce').astype('Int64')
    feat['gameId']=pd.to_numeric(feat.gameId,errors='coerce').astype('Int64')
    pred=pred.merge(feat,on=['season_label','game_date','gameId','dunkest_player_id'],how='left',validate='one_to_one')
    if pred.history_games_before_target.isna().any():
        raise SystemExit(f'Cannot join history cohort for {int(pred.history_games_before_target.isna().sum())} prediction rows; no silent cohort inference.')
    h=pd.to_numeric(pred.history_games_before_target,errors='coerce')
    pred['history_cohort']=np.select([h.le(5),h.le(10)],['low_history_0_5','history_6_10'],default='history_over_10')
    pred['residual']=pred.prediction-pred.target_pdk
    metric_rows=[]; cohort_rows=[]; folds=[]
    for season in TEST:
        cal_seasons=[s for s in CALIBRATION if s < season]
        cal=pred.loc[pred.prediction_season.isin(cal_seasons)].copy()
        test=pred.loc[pred.prediction_season.eq(season)].copy()
        if cal.empty or test.empty: raise SystemExit(f'Missing calibration/test rows for {season}')
        qglobal=np.quantile(cal.residual,[.10,.50,.90])
        gtest=test.copy(); gtest[['q10','q50','q90']]=np.tile(qglobal,(len(gtest),1))
        metric_rows.append(stats(gtest,'pooled_residual_quantiles',season,cal_seasons,'all'))
        for cohort in ['low_history_0_5','history_6_10','history_over_10']:
            cg=cal.loc[cal.history_cohort.eq(cohort)]
            tg=test.loc[test.history_cohort.eq(cohort)].copy()
            if len(cg)<500 or tg.empty: continue
            qc=np.quantile(cg.residual,[.10,.50,.90])
            # Shrink cohort quantiles toward the global empirical quantiles; 500 rows -> full cohort estimate.
            alpha=min(1.0,len(cg)/500.0)
            qs=alpha*qc+(1-alpha)*qglobal
            tg[['q10','q50','q90']]=np.tile(qs,(len(tg),1))
            cohort_rows.append(stats(tg,'cohort_residual_quantiles',season,cal_seasons,cohort))
            # Include pooled intervals on exactly the same cohort for a paired comparison.
            tg2=test.loc[test.history_cohort.eq(cohort)].copy(); tg2[['q10','q50','q90']]=np.tile(qglobal,(len(tg2),1))
            cohort_rows.append(stats(tg2,'pooled_residual_quantiles',season,cal_seasons,cohort))
        folds.append({'test_season':season,'calibration_seasons':cal_seasons,'n_calibration':len(cal),'n_test':len(test),'calibration_residual_quantiles':{'q10':float(qglobal[0]),'q50':float(qglobal[1]),'q90':float(qglobal[2])},'test_history_coverage':test.history_cohort.value_counts().to_dict()})
    metrics=pd.DataFrame(metric_rows); cohorts=pd.DataFrame(cohort_rows)
    metrics.to_csv(METRICS,index=False); cohorts.to_csv(COHORTS,index=False)
    audit={'created_utc':datetime.now(timezone.utc).isoformat(),'prediction_source':str(PRED.relative_to(ROOT)),'history_source':str(TRAIN.relative_to(ROOT)),'prediction_model':'saved walk-forward Random Forest predictions; not the current multi-model production ensemble','test_seasons':TEST,'folds':folds,'methods':'expanding-origin residual q10/q50/q90 from prior OOF seasons only; cohort residual quantiles compared against pooled quantiles on identical cohort rows; cohort estimates shrunk to pooled when calibration n < 500','production_changed':False,'holdout_caveat':'2025/26 has been examined in prior experiments and is not globally untouched.'}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    def table(df,cols):
        x=df[cols].copy().round(4).fillna('').astype(str)
        heads=list(map(str,cols)); rows=x.values.tolist()
        widths=[max([len(heads[i])]+[len(row[i]) for row in rows]) for i in range(len(heads))]
        lines=['| '+' | '.join(heads[i].ljust(widths[i]) for i in range(len(heads)))+' |','| '+' | '.join('-'*w for w in widths)+' |']
        lines += ['| '+' | '.join(row[i].ljust(widths[i]) for i in range(len(heads)))+' |' for row in rows]
        return '\n'.join(lines)
    report=['# Dunkest uncertainty calibration — expanding-origin OOS audit','',f"Generated UTC: {audit['created_utc']}",'','## Protocol','','- Saved expanding-window RF predictions; residual calibration uses only strictly earlier seasons.','- Test seasons: 2023/24, 2024/25, 2025/26.','- Compares pooled residual quantiles with per-history-cohort quantiles on the same cohort rows.','- Quantiles are prediction residuals (prediction minus actual); interval endpoints are prediction plus q10/q90.','- No production configuration or forecasts are changed.','', '## Overall test-fold metrics','',table(metrics,['test_season','calibration_seasons','n','q10_residual','q50_residual','q90_residual','lower_tail_coverage','upper_tail_coverage','central_80_coverage','mean_interval_width','median_bias_after_offset','raw_mae','median_adjusted_mae']),'','## Cohort interval diagnostics','',table(cohorts,['test_season','method','cohort','n','q10_residual','q50_residual','q90_residual','lower_tail_coverage','upper_tail_coverage','central_80_coverage','mean_interval_width','median_bias_after_offset','raw_mae','median_adjusted_mae']),'','## Interpretation','','A nominal 80% central interval should have central_80_coverage near 0.80; lower- and upper-tail coverages near 0.90 are the marginal one-sided checks. Cohort quantiles should only be preferred if they improve out-of-sample coverage without making intervals needlessly wide. This audit uses RF OOF forecasts as a calibration proxy and does not certify the current production ensemble. The point-score median offset is diagnostic only and is not promoted without consistent OOS MAE improvement.','', '## Artifacts','',f'- Metrics: `{METRICS.relative_to(ROOT)}`',f'- Cohorts: `{COHORTS.relative_to(ROOT)}`',f'- Audit: `{AUDIT.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(report),encoding='utf-8')
    print('OVERALL\n'+metrics.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
    print('\nCOHORTS\n'+cohorts.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
    print(f'\nREPORT={REPORT}')

if __name__=='__main__': main()
