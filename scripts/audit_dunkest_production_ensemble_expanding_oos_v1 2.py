#!/usr/bin/env python3
"""Expanding-origin OOS audit of the production model-zoo ensemble and its intervals.

Uses certified Dunkest targets and the exact production feature adapter/model zoo.
Each season is predicted by models trained only on earlier seasons. Interval
quantiles for a test season are fitted only from prior seasons' OOS residuals.
Audit only: never writes production settings, models, or prediction artifacts.
"""
from __future__ import annotations
import json, warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/processed/dunkest_pdk_game_training_2020-26_v3.parquet'
OUT = ROOT / 'reports/audit'
STAMP = '20261014_v1'
REPORT = OUT / f'dunkest_production_ensemble_expanding_oos_{STAMP}.md'
AUDIT = OUT / f'dunkest_production_ensemble_expanding_oos_{STAMP}.json'
METRICS = OUT / f'dunkest_production_ensemble_expanding_oos_{STAMP}_metrics.csv'
PREDS = OUT / f'dunkest_production_ensemble_expanding_oos_{STAMP}_predictions.csv'
CACHE = Path('/tmp/dunkest_production_ensemble_expanding_oos_20261014_v1')
INTERVALS = OUT / f'dunkest_production_ensemble_expanding_oos_{STAMP}_intervals.csv'
TEST_SEASONS = ['2021-22', '2022-23', '2023-24', '2024-25', '2025-26']


def metric_row(season, method, actual, pred, n_train, train_seasons, cutoff):
    actual = np.asarray(actual, dtype=float); pred = np.asarray(pred, dtype=float)
    err = pred - actual
    return {'test_season': season, 'method': method, 'n': len(actual), 'train_rows': n_train,
            'train_seasons': ';'.join(train_seasons), 'train_cutoff': cutoff,
            'mae': float(mean_absolute_error(actual, pred)),
            'rmse': float(np.sqrt(mean_squared_error(actual, pred))),
            'bias_pred_minus_actual': float(err.mean()),
            'median_error': float(np.median(err))}


def interval_stats(test, q, method, cal_seasons, cohort):
    y = test.actual_pdk.to_numpy(float)
    p = test.prediction.to_numpy(float)
    q10, q50, q90 = map(float, q)
    # residual = prediction - actual; invert residual quantiles to score bounds.
    lower, upper = p - q90, p - q10
    corrected = p - q50
    return {'test_season': str(test.test_season.iloc[0]), 'method': method,
            'calibration_seasons': ';'.join(cal_seasons), 'cohort': cohort, 'n': len(test),
            'q10_residual': q10, 'q50_residual': q50, 'q90_residual': q90,
            'lower_tail_coverage': float((y >= lower).mean()),
            'upper_tail_coverage': float((y <= upper).mean()),
            'central_80_coverage': float(((y >= lower) & (y <= upper)).mean()),
            'mean_interval_width': float((upper-lower).mean()),
            'raw_mae': float(np.mean(np.abs(p-y))),
            'median_corrected_mae': float(np.mean(np.abs(corrected-y))),
            'median_corrected_bias': float(np.mean(corrected-y))}


def md_table(df, columns):
    view = df[columns].copy().round(4).fillna('').astype(str)
    heads = list(columns); rows = view.values.tolist()
    widths = [max([len(heads[i])] + [len(row[i]) for row in rows]) for i in range(len(heads))]
    return '\n'.join(['| '+' | '.join(heads[i].ljust(widths[i]) for i in range(len(heads)))+' |',
                      '| '+' | '.join('-'*w for w in widths)+' |'] +
                     ['| '+' | '.join(row[i].ljust(widths[i]) for i in range(len(heads)))+' |' for row in rows])


def main():
    for p in (REPORT, AUDIT, METRICS, PREDS, INTERVALS):
        if p.exists(): raise SystemExit(f'Refusing to overwrite existing artifact: {p}')
    if not DATA.exists(): raise SystemExit(f'Missing certified training dataset: {DATA}')
    from dunkest.config import Settings
    from dunkest.models.multiseason_training import adapt_certified_training_rows
    from dunkest.models.predictor import train_models, _ensemble_predict, _inference_minutes_baseline, _apply_projection_weights

    source = pd.read_parquet(DATA)
    data = adapt_certified_training_rows(source, include_2025_26=True)
    seasons = sorted(data.season_label.astype(str).unique())
    prediction_frames = []; metric_rows = []; fold_details = []
    CACHE.mkdir(parents=True, exist_ok=True)
    settings = Settings(training_target='target_pdk_official', random_state=42)

    for season in TEST_SEASONS:
        train_seasons = [s for s in seasons if s < season]
        train = data.loc[data.season_label.astype(str).isin(train_seasons)].copy()
        test = data.loc[data.season_label.astype(str).eq(season)].copy()
        if train.empty or test.empty: raise SystemExit(f'Missing train/test rows for fold {season}')
        train_end = pd.to_datetime(train.GAME_DATE).max()
        test_start = pd.to_datetime(test.GAME_DATE).min()
        if not train_end < test_start:
            raise SystemExit(f'Temporal leakage: train ends {train_end} >= test starts {test_start} for {season}')
        if train.target_pdk_official.isna().any() or test.target_pdk_official.isna().any():
            raise SystemExit(f'Non-certified target found in {season} fold; refusing row drops.')
        cache_pred = CACHE / f'{season}.csv'
        cache_meta = CACHE / f'{season}.json'
        if cache_pred.exists() and cache_meta.exists():
            out = pd.read_csv(cache_pred)
            meta = json.loads(cache_meta.read_text(encoding='utf-8'))
            if len(out) != len(test) or out.test_season.astype(str).ne(season).any():
                raise SystemExit(f'Invalid cached OOS rows for {season}; remove {CACHE} and rerun.')
            prediction_frames.append(out)
            metric_rows.extend(meta['metric_rows'])
            fold_details.append(meta['fold_detail'])
            print(f'Loaded cached {season}: train={len(train):,}, test={len(test):,}', flush=True)
            continue
        fold_metric_rows = []
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', category=FutureWarning)
            models, _ = train_models(settings, train, target_column='target_pdk_official',
                                     sample_weight=train['_training_sample_weight'])
        # Mirror the production multi-season absolute-target inference path.
        models['_prediction_is_absolute'] = True
        raw = _ensemble_predict(models, test)
        baseline = _inference_minutes_baseline(models, test)
        ensemble_score = pd.Series(baseline.to_numpy(float) + raw, index=test.index, dtype=float).clip(lower=0.0)
        prior = pd.to_numeric(test.get('pdk_season_mean', pd.Series(np.nan, index=test.index)), errors='coerce')
        components = pd.DataFrame({'minutes': baseline, 'ensemble': ensemble_score, 'prior': prior}, index=test.index)
        projected = _apply_projection_weights(components, models.get('_projection_weights', {'minutes':0.0,'ensemble':1.0,'prior':0.0}))
        projected = projected.where(projected.notna(), ensemble_score).clip(lower=0.0)
        out = pd.DataFrame({
            'test_season': season, 'game_date': pd.to_datetime(test.GAME_DATE).dt.strftime('%Y-%m-%d'),
            'player_id': test.PLAYER_ID.astype(str), 'player_name': test.PLAYER_NAME.astype(str),
            'game_id': test.GAME_ID.astype(str), 'actual_pdk': test.target_pdk_official.astype(float),
            'prediction': projected.astype(float), 'residual_pred_minus_actual': projected.astype(float)-test.target_pdk_official.astype(float),
            'history_games_before_target': pd.to_numeric(test.history_games_before_target, errors='coerce'),
            'baseline_prev10': pd.to_numeric(test.get('pdk_mean_10', pd.Series(np.nan,index=test.index)), errors='coerce'),
            'baseline_season_mean': prior,
        }, index=test.index)
        prediction_frames.append(out.reset_index(drop=True))
        fold_metric_rows.append(metric_row(season, 'production_core_ensemble', out.actual_pdk, out.prediction,
                                           len(train), train_seasons, train_end.strftime('%Y-%m-%d')))
        for baseline_name, baseline_values in [('baseline_prev10', out.baseline_prev10), ('baseline_season_mean', out.baseline_season_mean)]:
            finite = baseline_values.notna() & np.isfinite(baseline_values.to_numpy(float, na_value=np.nan))
            if finite.sum() >= 100:
                fold_metric_rows.append(metric_row(season, baseline_name, out.loc[finite,'actual_pdk'], baseline_values.loc[finite],
                                                   len(train), train_seasons, train_end.strftime('%Y-%m-%d')))
        fold_detail = {'test_season':season,'train_seasons':train_seasons,'train_rows':len(train),
                       'test_rows':len(test),'train_end':train_end.strftime('%Y-%m-%d'),
                       'test_start':test_start.strftime('%Y-%m-%d'),
                       'model_weights':models.get('_weights',{}),
                       'projection_weights':models.get('_projection_weights',{}),
                       'calibration_samples_inside_fold_trainer':models.get('_calibration_samples',0),
                       'feature_columns':models.get('_feature_cols',[])}
        metric_rows.extend(fold_metric_rows)
        out.to_csv(cache_pred,index=False)
        cache_meta.write_text(json.dumps({'metric_rows':fold_metric_rows,'fold_detail':fold_detail},indent=2,default=str)+'\n',encoding='utf-8')
        fold_details.append(fold_detail)
        print(f'Completed {season}: train={len(train):,}, test={len(test):,}, weights={models.get("_weights",{})}', flush=True)

    preds = pd.concat(prediction_frames, ignore_index=True)
    history = pd.to_numeric(preds.history_games_before_target, errors='coerce')
    preds['history_cohort'] = np.select([history.le(5), history.le(10)], ['low_history_0_5','history_6_10'], default='history_over_10')
    metrics = pd.DataFrame(metric_rows)
    interval_rows = []
    for season in TEST_SEASONS:
        test = preds.loc[preds.test_season.eq(season)].copy()
        cal = preds.loc[preds.test_season.isin([s for s in TEST_SEASONS if s < season])].copy()
        if cal.empty:
            continue
        cal_seasons = sorted(cal.test_season.unique().tolist())
        residuals = cal.residual_pred_minus_actual.to_numpy(float)
        qglobal = np.quantile(residuals, [.10,.50,.90])
        interval_rows.append(interval_stats(test, qglobal, 'pooled_prior_oos_residuals', cal_seasons, 'all'))
        for cohort in ['low_history_0_5','history_6_10','history_over_10']:
            cal_c = cal.loc[cal.history_cohort.eq(cohort)]
            test_c = test.loc[test.history_cohort.eq(cohort)]
            if test_c.empty: continue
            if len(cal_c) >= 500:
                qc = np.quantile(cal_c.residual_pred_minus_actual.to_numpy(float), [.10,.50,.90])
                alpha = min(1.0, len(cal_c)/500.0)
                qcohort = alpha*qc + (1-alpha)*qglobal
                interval_rows.append(interval_stats(test_c, qcohort, 'cohort_shrunk_prior_oos_residuals', cal_seasons, cohort))
            interval_rows.append(interval_stats(test_c, qglobal, 'pooled_prior_oos_residuals', cal_seasons, cohort))
    intervals = pd.DataFrame(interval_rows)
    metrics.to_csv(METRICS,index=False); preds.to_csv(PREDS,index=False); intervals.to_csv(INTERVALS,index=False)
    created = datetime.now(timezone.utc).isoformat()
    audit = {'created_utc':created,'dataset':str(DATA.relative_to(ROOT)),
             'label':'certified official Dunkest PDK targets only',
             'test_seasons':TEST_SEASONS,'folds':fold_details,
             'method':'Exact production train_models model zoo and production feature adapter; per-season model trained only on earlier certified seasons; projection weights fitted only on that training window; interval quantiles fit only on prior-season OOS residuals.',
             'interval_sign_convention':'residual = prediction - actual; score lower = prediction - q90(residual); score upper = prediction - q10(residual).',
             'limits':['This audits the core production model-zoo ensemble and its training-window projection layer, not the final market-specific forecast after current-role minutes allocation, historical-PDK model blending, rookie priors, and availability weighting. Those post-processing inputs lack complete authentic historical pre-lock snapshots and cannot be reconstructed without inventing data.',
                       '2025/26 has already been examined in earlier project experiments and is not a globally untouched holdout.',
                       'No production model, calibrator, configuration, or optimizer objective was changed.'],
             'production_changed':False,'artifacts':{'report':str(REPORT.relative_to(ROOT)),'metrics':str(METRICS.relative_to(ROOT)),'predictions':str(PREDS.relative_to(ROOT)),'intervals':str(INTERVALS.relative_to(ROOT))}}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
    report=['# Production core ensemble: expanding-origin OOS and interval calibration audit','',f'Generated UTC: {created}','','## Protocol','',
            '- Certified official Dunkest PDK labels only; no proxy label fallback.','- Exact production feature adapter, model zoo, inverse-MAE model weights, fold-local imputation, sample weighting, and projection-weight fitting.','- Each test season is predicted by a model trained only on earlier seasons; date cutoffs are asserted.','- For each test season, empirical residual quantiles use only earlier out-of-sample season predictions.','- Residual = prediction minus actual; score interval lower = prediction − q90(residual), upper = prediction − q10(residual).','- This is an audit only. No production code/configuration/model artifact was changed.','','## Point-score metrics','',md_table(metrics,['test_season','method','n','train_rows','train_seasons','mae','rmse','bias_pred_minus_actual','median_error']),'','## Expanding-origin interval calibration','',md_table(intervals,['test_season','method','calibration_seasons','cohort','n','lower_tail_coverage','upper_tail_coverage','central_80_coverage','mean_interval_width','raw_mae','median_corrected_mae','median_corrected_bias']),'','Nominal central 80% coverage is 80%; marginal lower/upper coverage is 90%. Cohort quantiles are shrunk toward pooled quantiles, and only used when the prior OOS cohort contains at least 500 rows.','','## Critical boundary: core ensemble versus final player forecast','',
            'The audit validates the core production model-zoo ensemble and the projection layer that can be reconstructed from certified historical rows. It does **not** validate the complete final inference output consumed by the optimizer: current-market role/minutes allocation, the separately blended historical PDK model, rookie-prior adjustments, and play-probability weighting also affect the final score. Authentic historical pre-lock snapshots needed to reconstruct those transformations are not available consistently. Therefore these results can reject weak calibration candidates, but they are not sufficient to promote a new calibrator to production.','','## Fold diagnostics','',
            '| Test season | Training seasons | Train rows | Test rows | Model weights | Projection weights |','|---|---|---:|---:|---|---|']
    for f in fold_details: report.append(f"| {f['test_season']} | {'; '.join(f['train_seasons'])} | {f['train_rows']} | {f['test_rows']} | `{json.dumps(f['model_weights'],sort_keys=True)}` | `{json.dumps(f['projection_weights'],sort_keys=True)}` |")
    report += ['', '## Artifacts','',f'- Metrics: `{METRICS.relative_to(ROOT)}`',f'- Row-level predictions: `{PREDS.relative_to(ROOT)}`',f'- Interval diagnostics: `{INTERVALS.relative_to(ROOT)}`',f'- Audit JSON: `{AUDIT.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(report),encoding='utf-8')
    print('\nPOINT METRICS\n'+metrics.to_string(index=False,float_format=lambda x:f'{x:.4f}'),flush=True)
    print('\nINTERVALS\n'+intervals.to_string(index=False,float_format=lambda x:f'{x:.4f}'),flush=True)
    print(f'REPORT={REPORT}',flush=True)

if __name__ == '__main__': main()
