#!/usr/bin/env python3
"""Leakage-aware comparison of single-/multi-season models and recent-score baselines.

Uses certified official Dunkest PDK targets and the production feature adapter.
All learned models train strictly before each test season. Baselines use only
lagged pregame PDK means, with a training-only median fallback. No production
files or model settings are changed.
"""
from __future__ import annotations
import json, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/processed/dunkest_pdk_game_training_2020-26_v3.parquet'
ROOKIE=ROOT/'data/rookie_college.csv'
OUT=ROOT/'reports/audit'
STAMP='20261014_v2'
METRICS=OUT/f'dunkest_model_comparison_{STAMP}_metrics.csv'
COHORTS=OUT/f'dunkest_model_comparison_{STAMP}_cohorts.csv'
PRED=OUT/f'dunkest_model_comparison_{STAMP}_predictions.csv'
PAIRED=OUT/f'dunkest_model_comparison_{STAMP}_paired_bootstrap.csv'
REPORT=OUT/f'dunkest_model_comparison_{STAMP}.md'
AUDIT=OUT/f'dunkest_model_comparison_{STAMP}.json'
SEASONS=['2020-21','2021-22','2022-23','2023-24','2024-25','2025-26']
TEST_SEASONS=SEASONS[2:]


def norm_name(x):
    x=unicodedata.normalize('NFKD',str(x)).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',x).strip()


def metric(y,p):
    y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
    return {'n':int(len(e)), 'mae':float(np.mean(np.abs(e))),
            'rmse':float(np.sqrt(np.mean(e**2))), 'bias_pred_minus_actual':float(np.mean(e))}


def markdown_table(frame):
    if frame.empty: return '_No evaluable rows._'
    f=frame.copy().fillna('')
    cols=list(map(str,f.columns)); rows=[[str(v).replace('|','\\|').replace('\n',' ') for v in row] for row in f.astype(str).itertuples(index=False,name=None)]
    widths=[max(len(cols[i]),*(len(r[i]) for r in rows)) for i in range(len(cols))]
    return '\n'.join(['| '+' | '.join(cols[i].ljust(widths[i]) for i in range(len(cols)))+' |','| '+' | '.join('-'*w for w in widths)+' |',*['| '+' | '.join(r[i].ljust(widths[i]) for i in range(len(cols)))+' |' for r in rows]])


def main():
    if any(p.exists() for p in [METRICS,COHORTS,PRED,PAIRED,REPORT,AUDIT]):
        raise SystemExit('Refusing to overwrite versioned outputs.')
    from dunkest.models.multiseason_training import adapt_certified_training_rows
    from dunkest.config import Settings
    from dunkest.models import predictor
    data=adapt_certified_training_rows(pd.read_parquet(DATA),include_2025_26=True)
    data['season_label']=data['season_label'].astype(str)
    # Independent draft-year labels are a narrower cohort than the low-history proxy.
    rook=pd.read_csv(ROOKIE,usecols=['player_name','draft_year'])
    rook['draft_year']=pd.to_numeric(rook['draft_year'],errors='coerce')
    rook['name_key']=rook.player_name.map(norm_name)
    if rook.duplicated(['name_key','draft_year']).any():
        raise SystemExit('Ambiguous duplicate player identity within a draft class; refusing fuzzy assignments.')
    # Only use names that map to exactly one draft year; ambiguous same-name
    # identities are left unclassified instead of multiplying historical rows.
    unique_names=rook.groupby('name_key').draft_year.nunique(dropna=True)
    unambiguous=set(unique_names[unique_names.eq(1)].index)
    rook=rook.loc[rook.name_key.isin(unambiguous)].drop_duplicates('name_key').copy()
    rook['rookie_season']=rook.draft_year.astype('Int64').astype(str).map(lambda y: f'{int(y)}-{str(int(y)+1)[-2:]}' if y!='<NA>' else '')
    data['name_key']=data.PLAYER_NAME.map(norm_name)
    data=data.merge(rook[['name_key','draft_year','rookie_season']],on='name_key',how='left',validate='many_to_one')
    data['draft_rookie_season']=data.rookie_season.eq(data.season_label) & data.draft_year.notna()
    data['history_games_before_target']=pd.to_numeric(data.history_games_before_target,errors='coerce')
    data['history_cohort']=pd.cut(data.history_games_before_target,[-np.inf,0,5,10,np.inf],labels=['0_prior_rows','1_to_5_prior_rows','6_to_10_prior_rows','over_10_prior_rows']).astype('object')

    original=predictor._model_zoo
    predictor._model_zoo=lambda settings:{'ridge':__import__('sklearn.linear_model',fromlist=['Ridge']).Ridge()}
    metric_rows=[]; cohort_rows=[]; prediction_rows=[]; fold_notes=[]
    try:
        for idx,season in enumerate(TEST_SEASONS,start=2):
            test=data.loc[data.season_label.eq(season)].copy()
            prior=SEASONS[:idx]
            previous=SEASONS[idx-1]
            if test.empty: raise RuntimeError(f'Empty test fold: {season}')
            y=test.target_pdk_official.to_numpy(float)
            train_windows={
                'single_season':data.loc[data.season_label.eq(previous)].copy(),
                'multi_season':data.loc[data.season_label.isin(prior)].copy(),
                'multi_season_low_history_weighted':data.loc[data.season_label.isin(prior)].copy(),
            }
            for method,train in train_windows.items():
                if pd.to_datetime(train.GAME_DATE).max() >= pd.to_datetime(test.GAME_DATE).min():
                    raise RuntimeError(f'Temporal overlap: {method} / {season}')
                weighted=method.endswith('weighted')
                if weighted:
                    h=pd.to_numeric(train.history_games_before_target,errors='coerce')
                    train=train.copy(); train['_training_sample_weight']=np.select([h.le(5),h.le(10)],[1.25,1.10],default=1.0)
                models,_=predictor.train_models(Settings(training_target='target_pdk_official'),train,target_column='target_pdk_official',sample_weight=(train['_training_sample_weight'] if weighted else None))
                cols=models['_feature_cols']
                X=test.reindex(columns=cols).apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan)
                X=X.fillna(models['_feature_medians']).fillna(0.0)
                pred=np.asarray(models['ridge'].predict(X),float)
                prediction_rows.extend({'season':season,'method':method,'date':str(r.GAME_DATE)[:10],'player_id':str(r.PLAYER_ID),'player_name':r.PLAYER_NAME,'game_id':str(r.GAME_ID),'actual':float(y[j]),'prediction':float(pred[j]),'error':float(pred[j]-y[j]),'history_games':float(r.history_games_before_target) if pd.notna(r.history_games_before_target) else np.nan,'history_cohort':r.history_cohort,'draft_rookie':bool(r.draft_rookie_season)} for j,(_,r) in enumerate(test.iterrows()))
                metric_rows.append({'season':season,'method':method,'train_seasons':';'.join(prior if method!='single_season' else [previous]),'train_rows':len(train),'rookie_weighted':weighted,**metric(y,pred)})
            # Same-row baselines: recent official Dunkest score mean, all computed pregame.
            fallback=float(train_windows['multi_season'].target_pdk_official.median())
            for n,col in [(3,'prev3_pdk_mean'),(5,'prev5_pdk_mean'),(10,'prev10_pdk_mean')]:
                base=pd.to_numeric(test[col],errors='coerce').fillna(fallback).to_numpy(float)
                method=f'baseline_prev{n}_mean'
                prediction_rows.extend({'season':season,'method':method,'date':str(r.GAME_DATE)[:10],'player_id':str(r.PLAYER_ID),'player_name':r.PLAYER_NAME,'game_id':str(r.GAME_ID),'actual':float(y[j]),'prediction':float(base[j]),'error':float(base[j]-y[j]),'history_games':float(r.history_games_before_target) if pd.notna(r.history_games_before_target) else np.nan,'history_cohort':r.history_cohort,'draft_rookie':bool(r.draft_rookie_season)} for j,(_,r) in enumerate(test.iterrows()))
                metric_rows.append({'season':season,'method':method,'train_seasons':'lagged within player; fallback median from prior seasons','train_rows':0,'rookie_weighted':False,**metric(y,base)})
            fold_notes.append({'season':season,'n_test':len(test),'train_seasons':prior,'train_rows':len(train_windows['multi_season'])})
    finally:
        predictor._model_zoo=original

    pred=pd.DataFrame(prediction_rows)
    metrics=pd.DataFrame(metric_rows)
    # Evaluate model methods on exactly the same row set, including rookie cohort and history groups.
    rng=np.random.default_rng(20261014)
    def add_cohort(season,method,label,g):
        row={'season':season,'method':method,'cohort':label,**metric(g.actual,g.prediction)}
        # Date-cluster bootstrap CI for MAE; preserves within-slate dependence.
        grouped=g.assign(_abs_error=np.abs(g.prediction-g.actual)).groupby('date')._abs_error.agg(['sum','count'])
        dates=np.array(grouped.index,dtype=object); sums=grouped['sum'].to_numpy(float); counts=grouped['count'].to_numpy(float)
        if len(dates)>=2:
            boot=[]
            for _ in range(1000):
                ix=rng.integers(0,len(dates),size=len(dates))
                boot.append(float(sums[ix].sum()/counts[ix].sum()))
            row['mae_ci95_low']=float(np.quantile(boot,.025)); row['mae_ci95_high']=float(np.quantile(boot,.975)); row['date_clusters']=int(len(dates))
        else:
            row['mae_ci95_low']=np.nan; row['mae_ci95_high']=np.nan; row['date_clusters']=int(len(dates))
        cohort_rows.append(row)
    for (season,method,cohort_label),g in pred.groupby(['season','method','history_cohort'],dropna=False):
        add_cohort(season,method,str(cohort_label),g)
    for (season,method,rookie),g in pred.groupby(['season','method','draft_rookie'],dropna=False):
        add_cohort(season,method,'draft_rookie_class' if rookie else 'non_draft_rookie_class',g)
    cohort=pd.DataFrame(cohort_rows)
    # Paired date-cluster bootstrap of absolute-error differences; negative favours method A.
    paired_rows=[]
    comparisons=[('multi_season','single_season'),('multi_season','baseline_prev10_mean'),('multi_season_low_history_weighted','multi_season')]
    for season in TEST_SEASONS:
        season_pred=pred[pred.season.eq(season)]
        for a,b in comparisons:
            aa=season_pred[season_pred.method.eq(a)]; bb=season_pred[season_pred.method.eq(b)]
            paired=aa.merge(bb,on=['season','date','player_id','game_id','actual'],suffixes=('_a','_b'),validate='one_to_one')
            groups=[('all_rows',paired),('draft_rookie_class',paired[paired.draft_rookie_a.astype(bool)]),('low_history_le_5',paired[pd.to_numeric(paired.history_games_a,errors='coerce').le(5)])]
            for label,g in groups:
                if g.empty: continue
                g=g.copy(); g['delta']=np.abs(g.prediction_a-g.actual)-np.abs(g.prediction_b-g.actual)
                grouped=g.groupby('date').delta.agg(['sum','count']); dates=np.array(grouped.index,dtype=object); sums=grouped['sum'].to_numpy(float); counts=grouped['count'].to_numpy(float)
                if len(dates)>=2:
                    boot=[]
                    for _ in range(1000):
                        ix=rng.integers(0,len(dates),size=len(dates))
                        boot.append(float(sums[ix].sum()/counts[ix].sum()))
                    lo,hi=np.quantile(boot,[.025,.975])
                else: lo=hi=np.nan
                paired_rows.append({'season':season,'comparison':f'{a} minus {b}','cohort':label,'n':len(g),'date_clusters':len(dates),'mae_delta_a_minus_b':float(g.delta.mean()),'ci95_low':float(lo),'ci95_high':float(hi)})
    paired_df=pd.DataFrame(paired_rows)
    pooled=pred.groupby('method').apply(lambda g:pd.Series({'n':len(g),'mae':float(np.mean(np.abs(g.prediction-g.actual))),'rmse':float(np.sqrt(np.mean(np.square(g.prediction-g.actual)))),'bias_pred_minus_actual':float(np.mean(g.prediction-g.actual))}),include_groups=False).reset_index()
    # Season stability: lower standard deviation of seasonal MAE means more stable fold performance.
    stability=metrics.groupby('method').agg(seasons=('season','nunique'),mean_season_mae=('mae','mean'),std_season_mae=('mae','std'),min_season_mae=('mae','min'),max_season_mae=('mae','max'),mean_rmse=('rmse','mean'),mean_bias=('bias_pred_minus_actual','mean')).reset_index()
    OUT.mkdir(parents=True,exist_ok=True)
    metrics.to_csv(METRICS,index=False); cohort.to_csv(COHORTS,index=False); pred.to_csv(PRED,index=False); paired_df.to_csv(PAIRED,index=False)
    audit={'created_utc':datetime.now(timezone.utc).isoformat(),'dataset':str(DATA.relative_to(ROOT)),'target':'certified official Dunkest PDK only','model':'production feature adapter with Ridge learner; model-window effect isolated; inner training-only tuning remains in train_models','test_seasons':TEST_SEASONS,'baseline':'previous 3/5/10 official PDK scores; missing history uses prior-training median only','rookie_definition':'rookie season inferred by matching player name and draft year in data/rookie_college.csv; delayed NBA debuts and name-match omissions remain possible','history_categories':'0, 1-5, 6-10, >10 prior Dunkest rows','position_categories':'not reported: certified training dataset has no historical player-position field; do not infer position from opponent home/visitor flag','temporal_guards':'all model training seasons strictly precede each test season; same test rows scored for all methods','bootstrap':'1000 resamples of calendar-date clusters for cohort MAE confidence intervals and paired absolute-error deltas','folds':fold_notes,'stability':stability.to_dict(orient='records'),'pooled_metrics':pooled.to_dict(orient='records'),'paired_comparisons':paired_df.to_dict(orient='records'),'production_changed':False,'holdout_caveat':'2025/26 has already been examined by prior project experiments and is not globally untouched.'}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
    # compact tables: full detail stays in CSVs
    display=metrics[['season','method','n','mae','rmse','bias_pred_minus_actual']].copy()
    for c in ['mae','rmse','bias_pred_minus_actual']: display[c]=display[c].map(lambda x:f'{x:.3f}')
    stab=stability.copy()
    for c in ['mean_season_mae','std_season_mae','min_season_mae','max_season_mae','mean_rmse','mean_bias']: stab[c]=stab[c].map(lambda x:f'{x:.3f}')
    rookie=cohort[cohort.cohort.isin(['draft_rookie_class','non_draft_rookie_class'])].copy()
    pooled_display=pooled.copy()
    for c in ['mae','rmse','bias_pred_minus_actual']: pooled_display[c]=pooled_display[c].map(lambda x:f'{x:.3f}')
    pair_display=paired_df[(paired_df.cohort=='all_rows') & (paired_df.comparison.isin(['multi_season minus single_season','multi_season minus baseline_prev10_mean']))].copy()
    for c in ['mae_delta_a_minus_b','ci95_low','ci95_high']: pair_display[c]=pair_display[c].map(lambda x:f'{x:.3f}')
    for c in ['mae','rmse','bias_pred_minus_actual','mae_ci95_low','mae_ci95_high']: rookie[c]=rookie[c].map(lambda x:f'{x:.3f}')
    lines=['# Dunkest model comparison: training window, recent-score baselines and cohorts','',f"Generated UTC: {audit['created_utc']}",'','## Protocol','','- Official certified PDK targets only; test seasons 2022/23–2025/26.','- Identical test rows for single-season, multi-season, low-history-weighted multi-season, and previous-3/5/10-score baselines.','- The Ridge learner uses the production feature adapter; training windows and weights are the only model-side comparison.','- All training seasons precede the test season. Recent-score baselines use lagged values; missing history falls back to a median computed from prior seasons only.','- Rookie class is name/draft-year matched and is not a perfect NBA debut label. History cohorts are a complementary, broader proxy.','- Historical position is unavailable in this certified dataset, so position-wise claims are intentionally omitted.','- Confidence intervals use 1,000 bootstrap resamples of calendar-date clusters.','', '## Pooled metrics','',markdown_table(pooled_display),'','## Metrics by season','',markdown_table(display),'','## Stability across seasons','',markdown_table(stab),'','## Paired MAE comparisons (negative favours first method)','',markdown_table(pair_display[['season','comparison','n','mae_delta_a_minus_b','ci95_low','ci95_high']]),'','## Draft-rookie cohort (date-cluster MAE intervals)','',markdown_table(rookie[['season','method','cohort','n','date_clusters','mae','mae_ci95_low','mae_ci95_high','rmse','bias_pred_minus_actual']]),'','## Interpretation','','A multi-season model is preferable only if it improves error consistently without unacceptable bias. Compare its gains against the previous-score means: a small improvement over a weak single-season model is not sufficient if the simple baseline remains competitive. Rookie estimates should be read alongside cohort size, date-cluster confidence intervals and bias; name-based draft-year cohorts are imperfect, and the low-history proxy is not equivalent to a rookie label. 2025/26 is not a pristine holdout.','', '## Artifacts','',f'- Metrics: `{METRICS.relative_to(ROOT)}`',f'- Cohorts: `{COHORTS.relative_to(ROOT)}`',f'- Paired bootstrap: `{PAIRED.relative_to(ROOT)}`',f'- Per-game predictions: `{PRED.relative_to(ROOT)}`',f'- Audit: `{AUDIT.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines),encoding='utf-8')
    print('SEASON METRICS\n'+metrics.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
    print('\nSTABILITY\n'+stability.to_string(index=False,float_format=lambda x:f'{x:.4f}'))
    print('\nROOKIE COHORT\n'+rookie.to_string(index=False))
    print(f'\nREPORT={REPORT}')

if __name__=='__main__': main()
