#!/usr/bin/env python3
"""Walk-forward validation of the exact multi-season production feature adapter.

Compares the same Ridge learner trained on (a) all certified earlier seasons and
(b) only the immediately preceding season. Uses past-only V3 features, tunes
alpha only within each training window, and reports the already-inspected 2025/26
fold with an explicit non-pristine-holdout caveat.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/processed/dunkest_pdk_game_training_2020-26_v3.parquet'
OUT=ROOT/'reports/audit/dunkest_multiseason_production_adapter_walk_forward_20261014_v3'
SEASONS=['2020-21','2021-22','2022-23','2023-24','2024-25','2025-26']


def metrics(y, p):
    err=np.asarray(p,float)-np.asarray(y,float)
    return {'n':int(len(err)),'mae':float(np.mean(np.abs(err))),'rmse':float(np.sqrt(np.mean(err**2))),'bias':float(np.mean(err))}


def fit_predict(train, test, *, weighted=False):
    from dunkest.config import Settings
    from dunkest.models import predictor
    original=predictor._model_zoo
    predictor._model_zoo=lambda settings:{'ridge':Ridge(alpha=3.0)}
    try:
        models,_=predictor.train_models(Settings(training_target='target_pdk_official'),train,target_column='target_pdk_official',sample_weight=(train['_training_sample_weight'] if weighted else None))
    finally:
        predictor._model_zoo=original
    cols=models['_feature_cols']
    X=test.reindex(columns=cols).apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan)
    X=X.fillna(models['_feature_medians']).fillna(0.0)
    pred=models['ridge'].predict(X)
    return pred, models


def main():
    from dunkest.models.multiseason_training import adapt_certified_training_rows
    OUT.parent.mkdir(parents=True,exist_ok=True)
    paths=[OUT.with_suffix('.json'),OUT.with_suffix('.md'),OUT.with_name(OUT.name+'_metrics.csv'),OUT.with_name(OUT.name+'_predictions.csv')]
    if any(p.exists() for p in paths): raise SystemExit('Refusing to overwrite versioned validation artifacts.')
    data=adapt_certified_training_rows(pd.read_parquet(DATA), include_2025_26=True)
    rows=[]; pred_rows=[]
    for i, season in enumerate(SEASONS[2:], start=2):
        test=data.loc[data.season_label.eq(season)].copy()
        previous=SEASONS[i-1]
        single=data.loc[data.season_label.eq(previous)].copy()
        multi=data.loc[data.season_label.isin(SEASONS[:i])].copy()
        if test.empty or single.empty or multi.empty: continue
        for method,train,weighted in [('previous_season_only',single,False),('all_prior_certified_seasons',multi,False),('all_prior_certified_seasons_rookie_weighted',multi,True)]:
            if pd.to_datetime(train.GAME_DATE).max() >= pd.to_datetime(test.GAME_DATE).min():
                raise ValueError(f'Temporal overlap detected in {season}/{method}.')
            pred,model=fit_predict(train,test,weighted=weighted)
            y=test.target_pdk_official.to_numpy(float)
            row={'test_season':season,'method':method,'train_rows':len(train),'train_seasons':';'.join(sorted(train.season_label.unique())),**metrics(y,pred), 'selected_ridge_alpha':model.get('_selected_ridge_alpha'),'rookie_weighting':bool(weighted)}
            rows.append(row)
            for j,(_,r) in enumerate(test.iterrows()):
                pred_rows.append({'test_season':season,'method':method,'rookie_weighting':bool(weighted),'game_date':r.GAME_DATE,'player_id':r.PLAYER_ID,'player_name':r.PLAYER_NAME,'game_id':r.GAME_ID,'actual_pdk':float(y[j]),'predicted_pdk':float(pred[j]),'error':float(pred[j]-y[j]),'history_games_before_target':float(r.get('history_games_before_target',np.nan)),'low_history_le_5':bool(float(r.get('history_games_before_target',np.nan))<=5) if pd.notna(r.get('history_games_before_target',np.nan)) else False})
    met=pd.DataFrame(rows); preds=pd.DataFrame(pred_rows)
    # Paired bootstrap by calendar date to respect within-slate dependence.
    rng=np.random.default_rng(42); boot=[]
    for season in met.test_season.unique():
        season_preds=preds[preds.test_season.eq(season)]
        comparisons=[('all_prior_certified_seasons','previous_season_only'),('all_prior_certified_seasons_rookie_weighted','all_prior_certified_seasons')]
        for method_a,method_b in comparisons:
            a=season_preds[season_preds.method.eq(method_a)]
            b=season_preds[season_preds.method.eq(method_b)]
            paired=a.merge(b,on=['game_date','player_id','game_id'],suffixes=('_a','_b'),validate='one_to_one')
            if paired.empty: continue
            paired['abs_a']=(paired.actual_pdk_a-paired.predicted_pdk_a).abs()
            paired['abs_b']=(paired.actual_pdk_b-paired.predicted_pdk_b).abs()
            dates=paired.game_date.drop_duplicates().to_numpy()
            deltas=[]; by_date={d:g for d,g in paired.groupby('game_date')}
            for _ in range(1000):
                sample=rng.choice(dates,size=len(dates),replace=True)
                block=pd.concat([by_date[d] for d in sample],ignore_index=True)
                deltas.append(float((block.abs_a-block.abs_b).mean()))
            boot.append({'test_season':season,'comparison':f'{method_a} minus {method_b}','paired_rows':len(paired),'mae_delta_a_minus_b':float((paired.abs_a-paired.abs_b).mean()),'ci95_low':float(np.quantile(deltas,.025)),'ci95_high':float(np.quantile(deltas,.975))})
    bootdf=pd.DataFrame(boot)
    # Rookie-adjacent cohort is explicitly defined by <=5 prior observed Dunkest rows, not draft status.
    cohort=[]
    for (season,method,low),g in preds.groupby(['test_season','method','low_history_le_5']):
        cohort.append({'test_season':season,'method':method,'cohort':'low_history_le_5' if low else 'history_gt_5',**metrics(g.actual_pdk,g.predicted_pdk)})
    cohortdf=pd.DataFrame(cohort)
    met.to_csv(paths[2],index=False); preds.to_csv(paths[3],index=False)
    result={'created_at_utc':datetime.now(timezone.utc).isoformat(),'dataset':str(DATA.relative_to(ROOT)),'supervised_target_seasons':SEASONS,'test_folds':sorted(met.test_season.unique()),'learner':'Ridge with alpha chosen only inside each train window; identical feature adapter/model across comparisons','feature_source':'precomputed lagged V3 features, production FEATURE_COLS adapter, no same-game target/outcome columns','primary_metrics':met.to_dict(orient='records'),'paired_date_cluster_bootstrap':bootdf.to_dict(orient='records'),'low_history_cohort':cohortdf.to_dict(orient='records'),'holdout_caveat':'2025/26 has already been examined in prior project experiments; this is not a globally untouched final holdout.','rookie_caveat':'The low-history cohort (<=5 prior Dunkest rows) is a rookie-adjacent proxy, not a verified NBA draft-rookie label.','production_model_changed':False,'artifacts':{'metrics':str(paths[2].relative_to(ROOT)),'predictions':str(paths[3].relative_to(ROOT))}}
    paths[0].write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    lines=['# Multi-season production-adapter walk-forward validation','',f"Generated UTC: {result['created_at_utc']}",'','This experiment evaluates the exact production adapter on chronological test seasons. It changes no production model weights.','', '## Point metrics','','| Test season | Method | Train rows | Train seasons | N | MAE | RMSE | Bias | Ridge alpha |','|---|---|---:|---|---:|---:|---:|---:|---:|']
    for r in rows: lines.append(f"| {r['test_season']} | {r['method']} | {r['train_rows']} | {r['train_seasons']} | {r['n']} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['bias']:.3f} | {r['selected_ridge_alpha']} |")
    lines += ['', '## Paired date-cluster bootstrap: MAE differences', '', '| Test season | Comparison | Paired rows | MAE difference | 95% CI |','|---|---|---:|---:|---|' ]
    for r in boot: lines.append(f"| {r['test_season']} | {r['comparison']} | {r['paired_rows']} | {r['mae_delta_a_minus_b']:.4f} | [{r['ci95_low']:.4f}, {r['ci95_high']:.4f}] |")
    lines += ['', '## Low-history cohort','','The cohort is defined as at most five prior observed Dunkest rows; it is not a verified NBA draft-rookie label.','','| Test season | Method | Cohort | N | MAE | RMSE | Bias |','|---|---|---|---:|---:|---:|---:|']
    for r in cohort: lines.append(f"| {r['test_season']} | {r['method']} | {r['cohort']} | {r['n']} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['bias']:.3f} |")
    lines += ['', '## Limitations','', '- 2025/26 has already been examined in prior project experiments; it is not a globally untouched final holdout.', '- The learner is Ridge, used to isolate the effect of the training window; this is not a full comparison of the production ensemble.', '- The V3 dataset provides certified PDK targets from 2020/21 onward. 2018/19–2019/20 are not supervised Dunkest targets because archived validity flags are false.', '- Production multi-season training remains enabled only for opening-round forecasts and continues to use the separate 2025/26 inference feature matrix.', '', '## Artifacts','',f"- JSON: {paths[0].relative_to(ROOT)}",f"- Metrics: {paths[2].relative_to(ROOT)}",f"- Predictions: {paths[3].relative_to(ROOT)}",'']
    paths[1].write_text('\n'.join(lines),encoding='utf-8')
    print('VALIDATION_COMPLETE')
    print(met.to_string(index=False))
    print('\nPAIRED_BOOTSTRAP')
    print(bootdf.to_string(index=False))
    print('\nLOW_HISTORY')
    print(cohortdf.to_string(index=False))
    print('\nREPORT',paths[1])
if __name__=='__main__': main()
