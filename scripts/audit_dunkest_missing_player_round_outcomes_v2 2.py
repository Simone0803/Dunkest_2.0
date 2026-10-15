#!/usr/bin/env python3
"""Audit recovery of missing selected player-round outcomes using team-game evidence."""
from __future__ import annotations
import importlib.util, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
WEEKLY=ROOT/'data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet'
GAMES=ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
LINEUPS=ROOT/'reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_lineups.csv'
STEM='dunkest_missing_player_round_outcomes_20261014_v2'; OUT=ROOT/'reports/audit'
CSV=OUT/f'{STEM}_selected_players.csv'; REPORT=OUT/f'{STEM}.md'; JSON=OUT/f'{STEM}.json'
spec=importlib.util.spec_from_file_location('lineup_v7',ROOT/'scripts/backtest_dunkest_historical_lineups_gamelevel_actuals_v7.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def main():
    for p in (CSV,REPORT,JSON):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    weekly=pd.read_parquet(WEEKLY)
    weekly['season_id']=weekly.source_season_id.astype(str); weekly['player_key']=weekly.player_name.astype(str).map(mod.player_key)
    weekly['source_week']=pd.to_numeric(weekly.source_week,errors='coerce'); weekly['source_round']=pd.to_numeric(weekly.source_round,errors='coerce')
    weekly['target_pdk_round_total']=pd.to_numeric(weekly.target_pdk_round_total,errors='coerce')
    ro=weekly[['season_id','source_week','source_round']].drop_duplicates().sort_values(['season_id','source_week','source_round'])
    ro['round_index']=ro.groupby('season_id').cumcount()+1
    weekly=weekly.merge(ro,on=['season_id','source_week','source_round'],how='left',validate='many_to_one')
    games=pd.read_parquet(GAMES); games['season_id']=games.season_id.astype(str)
    games['date']=pd.to_datetime(games.nba_GAME_DATE,errors='coerce').dt.strftime('%Y-%m-%d')
    games['player_id_num']=pd.to_numeric(games.dunkest_player_id,errors='coerce'); games['pdk_num']=pd.to_numeric(games.pdk,errors='coerce')
    games['valid']=games.gameValidForDunkest.astype('boolean').fillna(False)
    games['team']=games.nba_TEAM_ABBREVIATION.astype(str).str.upper().str.strip()
    # Team schedule: any official player-game row establishes a team fixture that date.
    team_games=games[['season_id','date','team']].dropna().drop_duplicates()
    team_game_set=set(map(tuple,team_games[['season_id','date','team']].astype(str).to_numpy()))
    round_outcomes=weekly.drop_duplicates(['season_id','round_index','player_key'],keep='last')
    outcomes={(str(r.season_id),int(r.round_index),str(r.player_key)):float(r.target_pdk_round_total)
              for r in round_outcomes.itertuples() if pd.notna(r.target_pdk_round_total)}
    prior_rows=weekly.sort_values(['season_id','round_index','player_key']).drop_duplicates(['season_id','round_index','player_key'],keep='last')
    lines=pd.read_csv(LINEUPS); records=[]
    for _,line in lines.iterrows():
        sid=str(line.season_id); ri=int(line.round_index); date=str(line.target_date)
        selected=[x.strip() for x in str(line.selected_players).split(';') if x.strip()]
        prior=prior_rows.loc[prior_rows.season_id.eq(sid)&prior_rows.round_index.lt(ri)].drop_duplicates('player_key',keep='last')
        by_key={r.player_key:r._asdict() for r in prior.itertuples(index=False)}
        for name in selected:
            key=mod.player_key(name); info=by_key.get(key,{})
            pid=pd.to_numeric(info.get('id',np.nan),errors='coerce')
            team=str(info.get('team_code','')).upper().strip()
            observed=outcomes.get((sid,ri,key),np.nan)
            gm=games.loc[games.season_id.eq(sid)&games.date.eq(date)&games.player_id_num.eq(pid)] if pd.notna(pid) else games.iloc[0:0]
            valid=gm.loc[gm.valid & gm.pdk_num.notna()]; invalid=gm.loc[(~gm.valid)&gm.pdk_num.notna()]
            played= (sid,date,team) in team_game_set if team else False
            if pd.notna(observed): status='weekly_round_score_observed'; score=observed; evidence='official weekly archive'
            elif len(valid): status='valid_game_score_recovered'; score=float(valid.pdk_num.sum()); evidence='official game-level Dunkest-valid PDK'
            elif len(invalid): status='explicit_nonvalid_game_row_zero_candidate'; score=0.0; evidence='explicit gameValidForDunkest=False; not certified'
            elif played and pd.notna(pid): status='team_played_player_row_absent_zero_candidate'; score=0.0; evidence='team fixture exists but no player-game row; possible DNP/inactive, proxy only'
            elif not played and team: status='team_did_not_play_identity_or_candidate_mismatch'; score=np.nan; evidence='candidate selected despite no team fixture on target date'
            else: status='player_identity_or_team_unresolved'; score=np.nan; evidence='insufficient ID/team evidence'
            records.append({'season_id':sid,'round_index':ri,'strategy':line.strategy,'target_date':date,'player_name_selected':name,
                'player_key':key,'player_id':int(pid) if pd.notna(pid) else np.nan,'prior_team_code':team,
                'weekly_round_score':float(observed) if pd.notna(observed) else np.nan,'team_played_target_date':bool(played),
                'gamelevel_valid_rows':int(len(valid)),'gamelevel_nonvalid_rows':int(len(invalid)),
                'recovery_status':status,'candidate_score':score,'evidence':evidence})
    out=pd.DataFrame(records); out.to_csv(CSV,index=False)
    counts={str(k):int(v) for k,v in out.recovery_status.value_counts().items()}
    per=out.groupby(['season_id','round_index','strategy']).recovery_status.agg(
        n_selected='size',n_weekly=lambda s:int((s=='weekly_round_score_observed').sum()),
        n_valid=lambda s:int((s=='valid_game_score_recovered').sum()),
        n_zero_candidate=lambda s:int(s.isin(['explicit_nonvalid_game_row_zero_candidate','team_played_player_row_absent_zero_candidate']).sum()),
        n_unknown=lambda s:int(s.isin(['team_did_not_play_identity_or_candidate_mismatch','player_identity_or_team_unresolved']).sum())).reset_index()
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'selected_player_rows':int(len(out)),
      'recovery_status_counts':counts,'lineup_strategy_rows':int(len(per)),
      'rows_with_no_unknown_player_outcomes':int((per.n_unknown==0).sum()),
      'weekly_observed':int((out.recovery_status=='weekly_round_score_observed').sum()),
      'gamelevel_valid_recovered':int((out.recovery_status=='valid_game_score_recovered').sum()),
      'zero_candidates_not_certified':int(out.recovery_status.isin(['explicit_nonvalid_game_row_zero_candidate','team_played_player_row_absent_zero_candidate']).sum()),
      'unknown_or_team_mismatch':int(out.recovery_status.isin(['team_did_not_play_identity_or_candidate_mismatch','player_identity_or_team_unresolved']).sum()),
      'limitations':['Zero candidates are not promoted to certified official scores; the team schedule is inferred from player-game logs.',
      'A prior team may be stale after trades, so a no-fixture result can expose team-link errors rather than a true invalid lineup.',
      'The official weekly archive remains authoritative for observed outcomes; missing rows remain unknown unless the scenario explicitly assumes zero.']}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    lines=['# Missing player-round outcome recovery audit — V2','',f"Generated UTC: {result['generated_at_utc']}",'',f"Selected player instances audited: {len(out):,}",'','## Recovery status','','| Status | Count |','|---|---:|']
    lines += [f'| {k} | {v:,} |' for k,v in counts.items()]
    lines += ['',f"Lineup-strategy rows without unresolved outcomes: {result['rows_with_no_unknown_player_outcomes']} / {result['lineup_strategy_rows']}.",'',
      'The audit now checks whether the player’s lagged team had a fixture on the target date. A missing player row on a confirmed team fixture is classified as a zero candidate (possible DNP/inactive), not an official zero. A selected player whose team has no fixture is flagged as a candidate-pool/team-link error.','',
      '## Limitations','']+[f'- {x}' for x in result['limitations']]+['',f'Selected-player audit: `{CSV.relative_to(ROOT)}`',f'Machine-readable summary: `{JSON.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines)); print(json.dumps(result,indent=2))
if __name__=='__main__': main()
