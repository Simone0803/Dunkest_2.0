#!/usr/bin/env python3
"""Re-score historical V8 lineups with explicit slot multipliers and recovered coach outcomes."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.rules.roster import player_contribution_multiplier
ROOT=Path(__file__).resolve().parents[1]
LINEUPS=ROOT/'reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8_lineups.csv'
PLAYERS=ROOT/'reports/audit/dunkest_missing_player_round_outcomes_20261014_v2_selected_players.csv'
COACH=ROOT/'reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_predictions.csv'
STEM='dunkest_lineups_recovered_actuals_20261014_v2'; OUT=ROOT/'reports/audit'
CSV=OUT/f'{STEM}_rounds.csv'; BOOTCSV=OUT/f'{STEM}_paired_bootstrap.csv'; REPORT=OUT/f'{STEM}.md'; JSON=OUT/f'{STEM}.json'
def main():
    for p in (CSV,BOOTCSV,REPORT,JSON):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    l=pd.read_csv(LINEUPS); p=pd.read_csv(PLAYERS); c=pd.read_csv(COACH)
    l['season_id']=l.season_id.astype(str); p['season_id']=p.season_id.astype(str)
    c=c.loc[c.method.eq('model_pregame_team_form')].copy(); c['game_date']=pd.to_datetime(c.game_date,errors='coerce').dt.strftime('%Y-%m-%d')
    c['season']=c.season.astype(str); c['team']=c.team.astype(str).str.upper().str.strip()
    c=c.drop_duplicates(['season','game_date','team'],keep='last')
    coach_map={(str(r.season),str(r.game_date),str(r.team)):float(r.actual_base_coach_pdk) for r in c.itertuples() if pd.notna(r.actual_base_coach_pdk)}
    outcome_map={(str(r.season_id),int(r.round_index),str(r.strategy),str(r.player_name_selected)):r for r in p.itertuples(index=False)}
    rows=[]
    for line in l.itertuples(index=False):
        sid=str(line.season_id); ri=int(line.round_index); strategy=str(line.strategy); date=str(line.target_date)
        season=str(line.season); team=str(line.selected_coach_proxy_team).upper().strip()
        slot_items=[x.strip() for x in str(line.selected_player_slots).split(';') if x.strip()]
        player_sum=0.0; n_observed=0; n_zero=0; unresolved=[]
        for item in slot_items:
            if ':' not in item:
                unresolved.append(item); continue
            name,slot=item.rsplit(':',1); name=name.strip(); slot=slot.strip()
            rec=outcome_map.get((sid,ri,strategy,name))
            if rec is None or pd.isna(rec.candidate_score):
                unresolved.append(name); continue
            score=float(rec.candidate_score)
            if rec.recovery_status=='weekly_round_score_observed' or rec.recovery_status=='valid_game_score_recovered': n_observed+=1
            else: n_zero+=1
            player_sum += score*player_contribution_multiplier(slot in {'Starter','Captain'},slot=='Sixth Man',slot=='Captain')
        coach_score=coach_map.get((season,date,team),np.nan)
        complete=(len(slot_items)==10 and not unresolved and np.isfinite(coach_score))
        total=player_sum+coach_score if complete else np.nan
        rows.append({'season_id':sid,'season':season,'round_index':ri,'target_date':date,'strategy':strategy,
          'selected_players':str(line.selected_players),'selected_coach_proxy_team':team,'expected_team_pdk':float(line.expected_team_pdk),
          'recovered_weighted_player_score':player_sum if not unresolved else np.nan,'recovered_coach_base_score':coach_score,
          'recovered_team_score_proxy':total,'n_weekly_or_valid_game_scores':n_observed,'n_zero_candidates':n_zero,
          'n_unresolved_players':len(unresolved),'unresolved_player_names':'; '.join(unresolved),'complete_recovered_proxy':bool(complete),
          'zero_candidate_share':n_zero/10.0 if len(slot_items)==10 else np.nan})
    d=pd.DataFrame(rows); d.to_csv(CSV,index=False)
    complete=d.loc[d.complete_recovered_proxy].copy()
    paired=complete.pivot(index=['season_id','season','round_index','target_date'],columns='strategy',values='recovered_team_score_proxy').dropna().reset_index()
    if {'model','previous5_baseline'}.issubset(paired.columns):
        paired['delta_model_minus_baseline']=paired.model-paired.previous5_baseline
    else: paired['delta_model_minus_baseline']=np.nan
    paired.to_csv(BOOTCSV,index=False)
    rng=np.random.default_rng(20261014); nboot=50000
    if len(paired):
        byseason=[(str(s),g.delta_model_minus_baseline.to_numpy(float)) for s,g in paired.groupby('season_id',sort=True)]
        n=len(paired); boots=np.zeros(nboot)
        for _,v in byseason:
            idx=rng.integers(0,len(v),size=(nboot,len(v))); boots += (len(v)/n)*v[idx].mean(axis=1)
        lo,hi=np.quantile(boots,[.025,.975]); delta=paired.delta_model_minus_baseline.to_numpy(float)
        by=[{'season_id':s,'n':int(len(v)),'mean_delta':float(v.mean()),'win_rate':float(np.mean(v>0))} for s,v in byseason]
        pairstats={'n_paired_rounds':n,'mean_delta':float(delta.mean()),'median_delta':float(np.median(delta)),
          'model_win_rate':float(np.mean(delta>0)),'bootstrap_95_ci':[float(lo),float(hi)],'by_season':by}
    else: pairstats={'n_paired_rounds':0}
    score_metrics={}
    for strategy,g in complete.groupby('strategy'):
        err=pd.to_numeric(g.expected_team_pdk,errors='coerce').to_numpy(float)-g.recovered_team_score_proxy.to_numpy(float)
        score_metrics[strategy]={'n':int(len(g)),'mean_expected':float(g.expected_team_pdk.mean()),'mean_actual_proxy':float(g.recovered_team_score_proxy.mean()),
          'mae':float(np.mean(np.abs(err))),'rmse':float(np.sqrt(np.mean(err**2))),'bias_expected_minus_actual':float(np.mean(err)),
          'mean_zero_candidate_share':float(g.zero_candidate_share.mean())}
    status=p.recovery_status.value_counts().to_dict()
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'lineup_rows':int(len(d)),'fully_scored_recovered_proxy_rows':int(d.complete_recovered_proxy.sum()),
      'paired_strategy_rounds':int(len(paired)),'incomplete_lineup_rows':int((~d.complete_recovered_proxy).sum()),'player_recovery_status_counts':{str(k):int(v) for k,v in status.items()},
      'paired_strategy_comparison':pairstats,'expected_score_calibration':score_metrics,
      'score_policy':'Player score uses official weekly outcome when present. Missing score uses 0 only for an explicit non-valid game row or a lagged team fixture with no player row. The exact stored lineup slot determines starter/sixth/captain multiplier. Coach base actual is rejoined by season/date/team from the complete coach outcome archive, rather than relying on the optimizer metadata lookup.',
      'limitations':['Zero candidates are a sensitivity proxy, not certified official Dunkest scores.',
       'Lagged team assignment may be stale after trades; 123 selected-player instances have team/date mismatches and exclude their lineups.',
       'Coach credits/multipliers and transfer malus remain historical proxies; this evaluates fresh independent lineups, not sequential roster management.']}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    lines=['# Recovered historical lineup score audit — V2','',f"Generated UTC: {result['generated_at_utc']}",'',
      f"Fully scored lineups under recovered-outcome proxy: **{result['fully_scored_recovered_proxy_rows']} / {result['lineup_rows']}**.",f"Paired rounds with both strategies scoreable: **{len(paired)}**.",'',
      '## Paired strategy comparison','']
    if pairstats.get('n_paired_rounds',0):
        lines += [f"- Model minus baseline mean: **{pairstats['mean_delta']:.2f} PDK**",f"- Median delta: {pairstats['median_delta']:.2f} PDK",f"- Model win rate: {pairstats['model_win_rate']:.1%}",f"- Season-stratified paired bootstrap 95% CI: **[{pairstats['bootstrap_95_ci'][0]:.2f}, {pairstats['bootstrap_95_ci'][1]:.2f}]**",'', '| Season ID | Paired rounds | Mean delta | Model win rate |','|---:|---:|---:|---:|']
        lines += [f"| {z['season_id']} | {z['n']} | {z['mean_delta']:.2f} | {z['win_rate']:.1%} |" for z in pairstats['by_season']]
    else: lines += ['No paired rounds with complete scores.']
    lines += ['', '## Expected lineup score calibration','', '| Strategy | n | Expected mean | Recovered actual mean | MAE | RMSE | Bias expected − actual | Zero candidate share |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for strategy,z in score_metrics.items(): lines.append(f"| {strategy} | {z['n']} | {z['mean_expected']:.2f} | {z['mean_actual_proxy']:.2f} | {z['mae']:.2f} | {z['rmse']:.2f} | {z['bias_expected_minus_actual']:.2f} | {z['mean_zero_candidate_share']:.1%} |")
    lines += ['', '## Interpretation', '', 'The score reconstruction now applies the saved roster slot multipliers and joins coach actuals independently by team/date, avoiding the previous sparse coach-score lookup. Results remain proxy-based because missing weekly outcomes are not always distinguishable from historical identity/availability errors.', '', '## Limitations','']+[f'- {x}' for x in result['limitations']]+['',f'Per-lineup scores: `{CSV.relative_to(ROOT)}`',f'Paired rounds: `{BOOTCSV.relative_to(ROOT)}`',f'Machine-readable report: `{JSON.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines)); print(json.dumps(result,indent=2))
if __name__=='__main__': main()
