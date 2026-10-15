#!/usr/bin/env python3
"""Apply official Dunkest coach credit multipliers to walk-forward base-score forecasts.

Historical coach CR markets are not archived for the tested seasons. Therefore this
script evaluates deterministic rule application under explicit CR-difference scenarios;
it does not label these scenarios as exact historical PDK backtests.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.rules.coach import coach_coefficient

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_predictions.csv'
OUT = ROOT / 'reports/audit'
STEM = 'dunkest_coach_official_multiplier_sensitivity_2018-26_v1'
METRICS = OUT / f'{STEM}_metrics.csv'
SCENARIOS = OUT / f'{STEM}_scenarios.csv'
AUDIT = OUT / f'{STEM}.json'
REPORT = OUT / f'{STEM}.md'
# Exact thresholds from the official rule table, represented by differences inside each band.
CR_DIFF_SCENARIOS = [0.0, 1.5, 3.0, 5.0, 7.0, 10.0, 14.0, 16.0]

def transform(base: float, diff: float, coach_is_higher: bool) -> float:
    if not np.isfinite(base):
        return float('nan')
    coeff = coach_coefficient(diff, coach_is_higher, base >= 0.0)
    return float(base * coeff if base >= 0.0 else base / coeff)

def main() -> int:
    for path in (METRICS, SCENARIOS, AUDIT, REPORT):
        if path.exists():
            raise SystemExit(f'Refusing to overwrite versioned artifact: {path}')
    raw = pd.read_csv(INPUT)
    model = raw.loc[raw['method'].eq('model_pregame_team_form')].copy()
    if model.empty:
        raise RuntimeError('No model_pregame_team_form predictions in base-score artifact.')
    model['actual_base_coach_pdk'] = pd.to_numeric(model['actual_base_coach_pdk'], errors='coerce')
    model['predicted_base_coach_pdk'] = pd.to_numeric(model['predicted_base_coach_pdk'], errors='coerce')
    model = model.dropna(subset=['actual_base_coach_pdk', 'predicted_base_coach_pdk'])
    metric_rows, scenario_rows = [], []
    for diff in CR_DIFF_SCENARIOS:
        for side in ('higher_price', 'lower_price'):
            is_higher = side == 'higher_price'
            actual = np.array([transform(x, diff, is_higher) for x in model['actual_base_coach_pdk']], dtype=float)
            predicted = np.array([transform(x, diff, is_higher) for x in model['predicted_base_coach_pdk']], dtype=float)
            err = predicted - actual
            band = '0-0.99' if diff < 1 else '1-1.99' if diff < 2 else '2-3.99' if diff < 4 else '4-5.99' if diff < 6 else '6-7.99' if diff < 8 else '8-11.99' if diff < 12 else '12-15.99' if diff < 16 else '16+'
            mult_pos = coach_coefficient(diff, is_higher, True)
            mult_neg = coach_coefficient(diff, is_higher, False)
            metric_rows.append({
                'test_season': 'pooled', 'cr_difference_scenario': diff, 'coach_price_side': side,
                'coefficient_band': band, 'positive_score_multiplier': mult_pos,
                'negative_score_divisor': mult_neg, 'n': int(len(actual)),
                'mae_pdk': float(mean_absolute_error(actual, predicted)),
                'rmse_pdk': float(np.sqrt(mean_squared_error(actual, predicted))),
                'bias_pred_minus_actual_pdk': float(np.mean(err)),
                'scenario_is_historical_market': False,
            })
            for season, group in model.groupby('season'):
                a = np.array([transform(x, diff, is_higher) for x in group['actual_base_coach_pdk']], dtype=float)
                p = np.array([transform(x, diff, is_higher) for x in group['predicted_base_coach_pdk']], dtype=float)
                e = p - a
                scenario_rows.append({
                    'test_season': season, 'cr_difference_scenario': diff, 'coach_price_side': side,
                    'coefficient_band': band, 'positive_score_multiplier': mult_pos,
                    'negative_score_divisor': mult_neg, 'n': int(len(a)),
                    'mae_pdk': float(mean_absolute_error(a, p)),
                    'rmse_pdk': float(np.sqrt(mean_squared_error(a, p))),
                    'bias_pred_minus_actual_pdk': float(np.mean(e)),
                    'scenario_is_historical_market': False,
                })
    metrics = pd.DataFrame(metric_rows)
    per_season = pd.DataFrame(scenario_rows)
    # A rules regression check: thresholds and negative-score inverse rule.
    checks = []
    expected = [(0.0, 1.0, 1.0), (1.5, .95, 1.05), (3.0, .91, 1.14),
                (5.0, .87, 1.23), (7.0, .83, 1.32), (10.0, .79, 1.41),
                (14.0, .75, 1.50), (16.0, .70, 1.60)]
    for diff, high, low in expected:
        observed_high = coach_coefficient(diff, True, True)
        observed_low = coach_coefficient(diff, False, True)
        checks.append({'difference': diff, 'expected_high': high, 'observed_high': observed_high,
                       'expected_low': low, 'observed_low': observed_low,
                       'passed': bool(np.isclose(high, observed_high) and np.isclose(low, observed_low))})
    if not all(x['passed'] for x in checks):
        raise AssertionError(f'Official coefficient table mismatch: {checks}')
    metrics.to_csv(METRICS, index=False)
    per_season.to_csv(SCENARIOS, index=False)
    audit = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'input': str(INPUT.relative_to(ROOT)), 'input_rows': len(raw),
        'walk_forward_model_rows': len(model), 'test_seasons': sorted(model['season'].astype(str).unique()),
        'official_rule_source': 'https://docs.dunkest.com/regolamento-it/regolamento-fantasy/punteggio-allenatori',
        'rule_table_checks': checks, 'cr_difference_scenarios': CR_DIFF_SCENARIOS,
        'key_interpretation': 'The official multiplier formula is deterministic and reproduced. CR differences are controlled scenarios, not observed historical prices; these PDK metrics are sensitivity analyses, not exact historical PDK validation.',
        'historical_market_coverage': 'No historical coach CR snapshots were found for the tested seasons in the local market inventory; local timestamped coach markets cover the 2026/27 opener only.',
        'base_score_model_metrics_source': 'reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_metrics.csv',
        'production_changed': False,
        'limitations': [
            'Scenario CR differences are not actual historical coach quotations.',
            'Official current rule table was checked; historical rule versions have not been verified independently.',
            'The base model is evaluated chronologically; transformed metrics inherit the same test predictions and are sensitivity analysis only.'
        ]
    }
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    pooled = metrics.pivot(index='cr_difference_scenario', columns='coach_price_side', values='mae_pdk')
    lines = [
        '# Dunkest coach official multiplier sensitivity — V1', '',
        f"Generated UTC: {audit['generated_at_utc']}", '',
        '## Objective', '',
        'The base-score model is trained and evaluated without coach credits. This audit then applies the official deterministic multiplier to both each walk-forward prediction and its realized base score under explicit price-difference scenarios.', '',
        '## Official rule verification', '',
        'The coefficient table is checked against the official Dunkest rule page. Positive base scores are multiplied by the coefficient; negative base scores are divided by it. All threshold checks passed.', '',
        '| CR difference scenario | MAE if coach has higher price | MAE if coach has lower price |',
        '|---:|---:|---:|'
    ]
    for diff, row in pooled.iterrows():
        lines.append(f"| {diff:g} | {row.get('higher_price', float('nan')):.3f} | {row.get('lower_price', float('nan')):.3f} |")
    lines += ['', '## Interpretation', '',
        f"- Walk-forward base-score predictions analyzed: {len(model):,}.",
        '- These CR differences are controlled scenarios, not archived historical prices. Therefore the transformed MAE/RMSE show sensitivity to the official multiplier, not exact historical PDK accuracy.',
        '- To calculate exact historical PDK for a given game, the model also needs both coaches’ pregame CRs for that game. The rule table alone determines the coefficient only after that CR difference is known.',
        '- The base-score model metrics remain those in `dunkest_coach_base_points_walk_forward_2018-26_v1_metrics.csv`.', '',
        '## Artifacts', '',
        f'- Pooled scenario metrics: `{METRICS.relative_to(ROOT)}`',
        f'- Per-season scenario metrics: `{SCENARIOS.relative_to(ROOT)}`',
        f'- Audit JSON: `{AUDIT.relative_to(ROOT)}`', '',
        'Production model/configuration were not changed.', '']
    REPORT.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'status':'completed', 'rows':len(model), 'pooled_scenarios':len(metrics),
                      'rule_checks_passed':sum(x['passed'] for x in checks),
                      'outputs':[str(p.relative_to(ROOT)) for p in (METRICS,SCENARIOS,AUDIT,REPORT)]}, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
