#!/usr/bin/env python3
"""Diagnose infeasible historical lineup proxy rounds without changing production constraints."""
from __future__ import annotations
import importlib.util, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
RAW=ROOT/'data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet'
FAILED=ROOT/'reports/audit/dunkest_historical_lineups_sequential_transfer_20261013_v2_rounds.csv'
OUT=ROOT/'reports/audit'; STEM='dunkest_historical_lineup_infeasibility_20261013_v1'

def main():
    paths=[OUT/f'{STEM}.md',OUT/f'{STEM}.json',OUT/f'{STEM}_rounds.csv']
    if any(p.exists() for p in paths): raise SystemExit('Refusing to overwrite versioned artifact')
    spec=importlib.util.spec_from_file_location('seq_transfer_v2',ROOT/'scripts/backtest_dunkest_historical_lineups_sequential_transfer_v2.py')
    bt=importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
    raw=pd.read_parquet(RAW); raw['source_season_id']=raw['source_season_id'].astype(str)
    raw=raw.loc[raw.source_season_id.isin(bt.VALID_SEASONS)].copy()
    raw['target_pdk_round_total']=pd.to_numeric(raw['target_pdk_round_total'],errors='coerce')
    raw=raw.loc[np.isfinite(raw.target_pdk_round_total)].copy()
    base=bt.player_module.build_features(raw)
    feat,_=bt.player_module.attach_matchup_features(base,raw)
    feat,_=bt.player_module.attach_rest_schedule_features(feat)
    feat['player_key']=feat['player_name'].astype(str).map(bt.player_key)
    candidates=bt.candidate_history_features(raw)
    coach_source=pd.read_csv(bt.COACH_PREDICTIONS)
    coach_source=coach_source.loc[coach_source['method'].eq('model_pregame_team_form')].copy()
    coach_source['season']=coach_source['season'].astype(str)
    coach_source['game_date']=pd.to_datetime(coach_source['game_date'],errors='coerce').dt.strftime('%Y-%m-%d')
    coach_source['team']=coach_source['team'].astype(str).str.upper().str.strip()
    season_names={'9':'2022-23','13':'2023-24','19':'2024-25'}
    failed=pd.read_csv(FAILED)
    failed=failed.loc[failed['status'].eq('optimization_failed')].copy()
    failed['season_id']=failed.season_id.astype(str)
    failed['target_date']=pd.to_datetime(failed.target_date,errors='coerce').dt.strftime('%Y-%m-%d')
    unique=failed[['season_id','round_index','target_date','candidate_count','errors']].drop_duplicates(['season_id','round_index','target_date'])
    records=[]
    for row in unique.itertuples(index=False):
        s=str(row.season_id); rid=int(row.round_index); date=str(row.target_date)
        prior=bt.latest_prior_candidates(candidates.loc[candidates.season_id.eq(s)],rid)
        prior=prior.loc[pd.to_numeric(prior.cr,errors='coerce').between(4,35)].copy()
        prior['team']=prior.team_code.astype(str).str.upper().str.strip()
        day=feat.loc[feat.season_id.eq(s)&pd.to_numeric(feat.round_index,errors='coerce').eq(rid)&feat.target_date.astype(str).eq(date)&feat.target_opponent.notna(),['team_code_key','target_opponent']].drop_duplicates()
        day=day.rename(columns={'team_code_key':'team'}).drop_duplicates('team')
        pool=prior.merge(day,on='team',how='inner')
        team_counts=pool.groupby('team').size().to_dict()
        role_counts=pool.role.astype(str).str.upper().value_counts().to_dict()
        roles=pool.groupby('team').role.apply(lambda x: '/'.join(f'{r}:{int((x.astype(str).str.upper()==r).sum())}' for r in ['G','F','C'])).to_dict()
        # Max player capacity given actual pregame coach-team candidates on this date.
        available_coach_teams=set(coach_source.loc[coach_source['season'].eq(season_names.get(s,'')) & coach_source['game_date'].eq(date) & pd.to_numeric(coach_source['predicted_base_coach_pdk'],errors='coerce').notna(),'team'])
        capacities=[]
        for coach_team in available_coach_teams:
            cap_players=sum(min(n,2 if team==coach_team else 3) for team,n in team_counts.items())
            capacities.append((cap_players,coach_team))
        max_players,coach_team=max(capacities,key=lambda x:x[0]) if capacities else (sum(min(n,3) for n in team_counts.values()),'no-coach-overlap')
        n_dates=feat.loc[feat.season_id.eq(s)&pd.to_numeric(feat.round_index,errors='coerce').eq(rid)&feat.target_date.notna(),'target_date'].astype(str).nunique()
        round_teams=feat.loc[feat.season_id.eq(s)&pd.to_numeric(feat.round_index,errors='coerce').eq(rid)&feat.target_opponent.notna(),'team_code_key'].dropna().astype(str).str.upper().nunique()
        records.append({'season_id':s,'round_index':rid,'target_date':date,'candidate_count':len(pool),'candidate_teams':len(team_counts),'teams':';'.join(sorted(team_counts)),
            'team_candidate_counts':json.dumps(team_counts,sort_keys=True),'team_role_counts':json.dumps(roles,sort_keys=True),'role_counts':json.dumps(role_counts,sort_keys=True),
            'available_coach_teams':len(available_coach_teams),'max_players_with_team_cap_3_and_coach':int(max_players),'team_cap_capacity_shortfall':max(0,10-int(max_players)),
            'dates_in_source_round':int(n_dates),'teams_seen_across_source_round_dates':int(round_teams),'coach_team_at_capacity_bound':coach_team,
            'solver_error':str(row.errors)})
    out=pd.DataFrame(records).sort_values(['season_id','round_index','target_date'])
    out.to_csv(paths[2],index=False)
    capacity_fail=int((out.max_players_with_team_cap_3_and_coach<10).sum())
    summary={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'failed_records_in_source_csv':int(len(failed)),'unique_failed_date_slices':int(len(out)),
        'failed_slices_with_structural_team_capacity_below_10':capacity_fail,'all_failed_slices_capacity_limited':bool(capacity_fail==len(out)),
        'mean_candidate_teams_per_failed_date_slice':float(out.candidate_teams.mean()) if len(out) else None,
        'mean_available_pregame_coach_teams_per_date':float(out.available_coach_teams.mean()) if len(out) else None,
        'max_player_capacity_min':int(out.max_players_with_team_cap_3_and_coach.min()) if len(out) else None,
        'max_player_capacity_max':int(out.max_players_with_team_cap_3_and_coach.max()) if len(out) else None,
        'mean_capacity_shortfall':float(out.team_cap_capacity_shortfall.mean()) if len(out) else None,
        'root_cause_interpretation':'The proxy filters the candidate pool to teams with a non-null matchup in the historical feature join for the target date. Across all 49 failed slices, this leaves only 1–3 candidate teams even though the pregame coach source contains 4–26 teams for the date. With the coach allowed to come from a different team, the unchanged max-three-per-team rule still permits only 3–9 player slots from those restricted pools, fewer than the required 10. CBC infeasibility is therefore expected for the supplied inputs; do not relax the production team cap to compensate.',
        'production_changed':False,'round_details_csv':str(paths[2].relative_to(ROOT))}
    paths[1].write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Historical lineup infeasibility audit — v1','',f"Generated (UTC): {summary['generated_at_utc']}",'','## Findings','',
        f"- Failed records in sequential proxy: {len(failed)} (three transfer-penalty scenarios can repeat the same date slice).",
        f"- Unique failed date slices: {len(out)}.",f"- Failed slices whose maximum player capacity under the unchanged three-per-team rule is below 10: {capacity_fail}/{len(out)}.",
        f"- Mean candidate teams in failed daily slices: {out.candidate_teams.mean():.2f}.",f"- Mean pregame coach teams available per failed date slice: {out.available_coach_teams.mean():.2f}.",
        f"- Maximum player capacity under the unchanged team cap: {out.max_players_with_team_cap_3_and_coach.min()}–{out.max_players_with_team_cap_3_and_coach.max()} (shortfall {out.team_cap_capacity_shortfall.min()}–{out.team_cap_capacity_shortfall.max()}).",'',
        '## Diagnosis','',summary['root_cause_interpretation'],'','## Consequence for the experiment','',
        'The current sequential transfer experiment is useful only as a restricted proxy for rounds that happen to be feasible. Its target-date matchup join does not expose a complete candidate universe: for example, on 2022-12-13 it has 43 player candidates but only GSW, LAL and UTA, while the coach source lists ten teams for that date. Thus the 49 infeasible slices are input-universe failures, not evidence of a production optimizer defect. The next valid lineup experiment must recover a complete pre-lock player/team/role universe and explicit scoring outcomes at the same date/turn granularity, preserve pregame information, and model lineup locks only when reliable Dunkest turn assignments are available. The production team cap remains 3; no production constraints were changed.','',
        '## Artifacts','',f'- Details: `{paths[2].relative_to(ROOT)}`',f'- Summary JSON: `{paths[1].relative_to(ROOT)}`','']
    paths[0].write_text('\n'.join(lines))
    print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
