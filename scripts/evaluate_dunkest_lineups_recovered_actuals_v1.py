#!/usr/bin/env python3
"""Re-score V7 lineups with weekly outcomes plus explicit game/team-based zero candidates."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
LINEUPS=ROOT/'reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_lineups.csv'
PLAYERS=ROOT/'reports/audit/dunkest_missing_player_round_outcomes_20261014_v2_selected_players.csv'
STEM='dunkest_lineups_recovered_actuals_20261014_v1'; OUT=ROOT/'reports/audit'
CSV=OUT/f'{STEM}_rounds.csv'; BOOTCSV=OUT/f'{STEM}_paired_bootstrap.csv'; REPORT=OUT/f'{STEM}.md'; JSON=OUT/f'{STEM}.json'
def main():
    for p in (CSV,BOOTCSV,REPORT,JSON):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    l=pd.read_csv(LINEUPS); p=pd.read_csv(PLAYERS)
    p['season_id']=p.season_id.astype(str); l['season_id']=l.season_id.astype(str)
    keys=['season_id','round_index','strategy']
    if p.duplicated(keys+['player_key']).any(): raise SystemExit('Duplicate player outcomes for a selected lineup')
    summary=p.groupby(keys).agg(
        selected_player_rows=('player_key','size'),
        weekly_observed=('recovery_status',lambda s:int((s=='weekly_round_score_observed').sum())),
        valid_game_recovered=('recovery_status',lambda s:int((s=='valid_game_score_recovered').sum())),
        zero_candidates=('recovery_status',lambda s:int(s.isin(['explicit_nonvalid_game_row_zero_candidate','team_played_player_row_absent_zero_candidate']).sum())),
        unresolved=('recovery_status',lambda s:int(s.isin(['team_did_not_play_identity_or_candidate_mismatch','player_identity_or_team_unresolved']).sum())),
        recovered_player_total=('candidate_score',lambda s:float(pd.to_numeric(s,errors='coerce').sum(min_count=10))),
    ).reset_index()
    d=l.merge(summary,on=keys,how='left',validate='one_to_one')
    d['realized_coach_base_score']=pd.to_numeric(d.realized_coach_base_score,errors='coerce')
    d['recovered_total_score']=d['recovered_player_total']+d['realized_coach_base_score']
    d['complete_recovered_proxy']=d.selected_player_rows.eq(10)&d.unresolved.eq(0)&d.recovered_player_total.notna()&d.realized_coach_base_score.notna()
    d['zero_candidate_share']=d.zero_candidates/10.0
    d.to_csv(CSV,index=False)
    paired=d.loc[d.complete_recovered_proxy].pivot(index=['season_id','round_index'],columns='strategy',values='recovered_total_score').dropna()
    paired=paired.reset_index()
    if not {'model','previous5_baseline'}.issubset(paired.columns): raise SystemExit(f'Expected strategy columns absent: {paired.columns.tolist()}')
    paired['delta_model_minus_baseline']=paired['model']-paired['previous5_baseline']
    paired.to_csv(BOOTCSV,index=False)
    comparisons=[]; rng=np.random.default_rng(20261014); nboot=50000
    for sid,g in paired.groupby('season_id',sort=True):
        comparisons.append({'season_id':str(sid),'n':int(len(g)),'mean_delta':float(g.delta_model_minus_baseline.mean()),'model_win_rate':float((g.delta_model_minus_baseline>0).mean())})
    if len(paired):
        byseason=[(str(s),g.delta_model_minus_baseline.to_numpy(float)) for s,g in paired.groupby('season_id',sort=True)]
        n=len(paired); weights=[len(x)/n for _,x in byseason]; boots=np.zeros(nboot)
        for (_,v),w in zip(byseason,weights): boots+=w*v[rng.integers(0,len(v),size=(nboot,len(v)))].mean(axis=1)
        lo,hi=np.quantile(boots,[.025,.975]); delta=paired.delta_model_minus_baseline.to_numpy(float)
        paired_stats={'n_paired_rounds':int(len(paired)),'mean_delta_model_minus_baseline':float(delta.mean()),'median_delta':float(np.median(delta)),
          'model_win_rate':float(np.mean(delta>0)),'bootstrap_95_ci':[float(lo),float(hi)],'by_season':comparisons}
    else: paired_stats={'n_paired_rounds':0}
    ready=d.loc[d.complete_recovered_proxy]
    proxy_stats={}
    for strategy,g in ready.groupby('strategy'):
        e=pd.to_numeric(g.expected_team_pdk,errors='coerce').to_numpy(float)-g.recovered_total_score.to_numpy(float)
        ok=np.isfinite(e); e=e[ok]
        proxy_stats[strategy]={'n':int(len(e)),'mean_expected':float(g.expected_team_pdk.mean()),'mean_recovered_actual':float(g.recovered_total_score.mean()),
          'mae_expected_score':float(np.mean(np.abs(e))),'rmse_expected_score':float(np.sqrt(np.mean(e**2))),
          'bias_expected_minus_actual':float(np.mean(e)),'mean_zero_candidate_share':float(g.zero_candidate_share.mean())}
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'selected_lineup_strategy_rows':int(len(d)),
      'fully_scored_recovered_proxy_rows':int(d.complete_recovered_proxy.sum()),'rows_with_unknown_or_mismatched_player':int((~d.complete_recovered_proxy).sum()),
      'player_score_status_counts':{str(k):int(v) for k,v in p.recovery_status.value_counts().items()},
      'paired_strategy_comparison':paired_stats,'forecast_score_calibration_diagnostics':proxy_stats,
      'score_policy':'Player points use official weekly outcomes when present. Missing outcomes are assigned 0 only when an explicit gameValidForDunkest=False row exists or the lagged team has a fixture but no player row. These zero candidates are a reconstructed proxy, not certified official actuals. Any selected player with a team fixture mismatch or unresolved identity excludes that lineup. Coach score is the existing NBA-result-derived neutral-price coach proxy.',
      'limitations':['This is not a certified historical Dunkest backtest: zero candidates and coach scores remain proxy-derived.',
       'Lagged team codes may be stale after trades; no-fixture mismatches are excluded.',
       'Lineups are independently optimized per round, not a sequential roster with transfer malus.']}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    lines=['# Recovered historical lineup score audit — V1','',f"Generated UTC: {result['generated_at_utc']}",'',
      f"Lineup-strategy rows fully scored under recovered-outcome proxy: **{result['fully_scored_recovered_proxy_rows']} / {result['selected_lineup_strategy_rows']}**.",'',
      '## Strategy comparison','']
    if paired_stats.get('n_paired_rounds',0):
        lines += [f"- Paired rounds: **{paired_stats['n_paired_rounds']}**",f"- Model minus baseline mean: **{paired_stats['mean_delta_model_minus_baseline']:.2f} PDK**",f"- Median delta: {paired_stats['median_delta']:.2f} PDK",f"- Model win rate: {paired_stats['model_win_rate']:.1%}",f"- Season-stratified paired bootstrap 95% CI: **[{paired_stats['bootstrap_95_ci'][0]:.2f}, {paired_stats['bootstrap_95_ci'][1]:.2f}]**",'', '| Season ID | Paired rounds | Mean delta | Model win rate |','|---:|---:|---:|---:|']
        lines += [f"| {x['season_id']} | {x['n']} | {x['mean_delta']:.2f} | {x['model_win_rate']:.1%} |" for x in comparisons]
    else: lines += ['No paired rounds were fully scoreable under this proxy.']
    lines += ['', '## Expected lineup score calibration diagnostics','', '| Strategy | n | Mean expected | Mean recovered proxy actual | MAE | RMSE | Bias expected − actual | Mean zero-candidate share |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for strategy,x in proxy_stats.items(): lines.append(f"| {strategy} | {x['n']} | {x['mean_expected']:.2f} | {x['mean_recovered_actual']:.2f} | {x['mae_expected_score']:.2f} | {x['rmse_expected_score']:.2f} | {x['bias_expected_minus_actual']:.2f} | {x['mean_zero_candidate_share']:.1%} |")
    lines += ['', '## Interpretation', '', 'This is a broader sensitivity analysis than the previous strict observed-only subset, because it includes explicit zero candidates backed by a game row or a team fixture. It remains a proxy: it cannot distinguish a true DNP from an incorrect historical identity with full certainty. Do not treat this as production validation.', '', '## Limitations', '']+[f'- {x}' for x in result['limitations']]+['',f'Per-lineup outcomes: `{CSV.relative_to(ROOT)}`',f'Paired-round table: `{BOOTCSV.relative_to(ROOT)}`',f'Machine-readable summary: `{JSON.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines)); print(json.dumps(result,indent=2))
if __name__=='__main__': main()
