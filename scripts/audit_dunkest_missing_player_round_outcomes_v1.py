#!/usr/bin/env python3
"""Audit whether missing weekly player outcomes can be recovered from official game-level records."""
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
ROUNDS=ROOT/'reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_rounds.csv'
STEM='dunkest_missing_player_round_outcomes_20261014_v1'
OUT=ROOT/'reports/audit'; CSV=OUT/f'{STEM}_selected_players.csv'; REPORT=OUT/f'{STEM}.md'; JSON=OUT/f'{STEM}.json'
spec=importlib.util.spec_from_file_location('lineup_v7',ROOT/'scripts/backtest_dunkest_historical_lineups_gamelevel_actuals_v7.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def main():
    for p in (CSV,REPORT,JSON):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    weekly=pd.read_parquet(WEEKLY)
    weekly['season_id']=weekly['source_season_id'].astype(str)
    weekly['player_key']=weekly['player_name'].astype(str).map(mod.player_key)
    weekly['source_week']=pd.to_numeric(weekly['source_week'],errors='coerce')
    weekly['source_round']=pd.to_numeric(weekly['source_round'],errors='coerce')
    weekly['target_pdk_round_total']=pd.to_numeric(weekly['target_pdk_round_total'],errors='coerce')
    round_order=weekly[['season_id','source_week','source_round']].drop_duplicates().sort_values(['season_id','source_week','source_round'])
    round_order['round_index']=round_order.groupby('season_id').cumcount()+1
    weekly=weekly.merge(round_order,on=['season_id','source_week','source_round'],how='left',validate='many_to_one')
    games=pd.read_parquet(GAMES)
    games['season_id']=games['season_id'].astype(str)
    games['game_date']=pd.to_datetime(games['nba_GAME_DATE'],errors='coerce').dt.strftime('%Y-%m-%d')
    games['player_id_num']=pd.to_numeric(games['dunkest_player_id'],errors='coerce')
    games['pdk_num']=pd.to_numeric(games['pdk'],errors='coerce')
    games['valid']=games['gameValidForDunkest'].astype('boolean').fillna(False)
    games['nba_team']=games['nba_TEAM_ABBREVIATION'].astype(str).str.upper().str.strip()
    round_df=pd.read_csv(ROUNDS); round_df['season_id']=round_df['season_id'].astype(str)
    lineup_df=pd.read_csv(LINEUPS); lineup_df['season_id']=lineup_df['season_id'].astype(str)
    # Pre-index large tables to avoid repeated full-frame scans per selected player.
    weekly_scores={}
    for (sid,ri),g in weekly.groupby(['season_id','round_index'],sort=False):
        weekly_scores[(str(sid),int(ri))]=g.drop_duplicates('player_key',keep='last').set_index('player_key')['target_pdk_round_total'].to_dict()
    game_lookup={}
    for (sid,date,pid),g in games.groupby(['season_id','game_date','player_id_num'],dropna=True,sort=False):
        valid_rows=g.loc[g['valid']&g['pdk_num'].notna()]
        invalid_rows=g.loc[(~g['valid'])&g['pdk_num'].notna()]
        game_lookup[(str(sid),str(date),float(pid))]={
            'n_valid':int(len(valid_rows)),'n_invalid':int(len(invalid_rows)),
            'valid_score':float(valid_rows['pdk_num'].sum()) if len(valid_rows) else np.nan,
            'team_seen':';'.join(sorted(set(valid_rows['nba_team'].dropna().astype(str))))}
    target_rounds={}
    for (sid,ri),g in lineup_df.groupby(['season_id','round_index'],sort=False):
        target_rounds[(str(sid),int(ri))]=str(g['target_date'].iloc[0])
    prior_lookup={}
    for sid in sorted(lineup_df['season_id'].unique()):
        season_rows=weekly.loc[weekly['season_id'].eq(sid)].sort_values(['round_index','player_key'],kind='stable')
        for (round_sid,ri),date in target_rounds.items():
            if round_sid!=sid: continue
            prior=season_rows.loc[season_rows['round_index'].lt(ri)].drop_duplicates('player_key',keep='last')
            prior=prior[['player_key','id','player_name','team_code']].copy()
            prior['player_id_num']=pd.to_numeric(prior['id'],errors='coerce')
            prior_lookup[(sid,ri)]=prior.set_index('player_key').to_dict('index')
    records=[]
    for _,line in lineup_df.iterrows():
        sid=str(line['season_id']); ri=int(line['round_index']); date=str(line['target_date'])
        names=[x.strip() for x in str(line['selected_players']).split(';') if x.strip()]
        by_key=prior_lookup.get((sid,ri),{})
        actual_round=weekly_scores.get((sid,ri),{})
        for name in names:
            key=mod.player_key(name); info=by_key.get(key,{})
            pid=pd.to_numeric(info.get('player_id_num',np.nan),errors='coerce')
            observed=actual_round.get(key,np.nan)
            if pd.notna(observed):
                status='weekly_round_score_observed'; score=float(observed); n_valid=0; n_invalid=0; game_score=np.nan; team_seen=''
            elif pd.notna(pid):
                gm=game_lookup.get((sid,date,float(pid)),{'n_valid':0,'n_invalid':0,'valid_score':np.nan,'team_seen':''})
                n_valid=gm['n_valid']; n_invalid=gm['n_invalid']; team_seen=gm['team_seen']
                if n_valid:
                    game_score=float(gm['valid_score']); score=game_score; status='gamelevel_valid_score_recovered'
                elif n_invalid:
                    game_score=0.0; score=0.0; status='explicit_nonvalid_game_row_zero_candidate'
                else:
                    game_score=np.nan; score=np.nan; status='no_weekly_or_gamelevel_record'
            else:
                n_valid=0; n_invalid=0; game_score=np.nan; score=np.nan; team_seen=''; status='player_identity_unresolved'
            records.append({'season_id':sid,'round_index':ri,'strategy':line['strategy'],'player_name_selected':name,
                'player_key':key,'player_id':int(pid) if pd.notna(pid) else np.nan,'prior_team_code':info.get('team_code'),
                'target_date':date,'weekly_round_score':float(observed) if pd.notna(observed) else np.nan,
                'recovery_status':status,'gamelevel_valid_rows':int(n_valid),'gamelevel_nonvalid_rows':int(n_invalid),
                'gamelevel_valid_score':game_score,'recovered_or_observed_score':score,'gamelevel_team_codes':team_seen})
    out=pd.DataFrame(records); out.to_csv(CSV,index=False)
    counts=out['recovery_status'].value_counts().to_dict()
    per_line=out.groupby(['season_id','round_index','strategy'])['recovery_status'].agg(
        n_selected='size',n_weekly=lambda s:int((s=='weekly_round_score_observed').sum()),
        n_gamelevel_valid=lambda s:int((s=='gamelevel_valid_score_recovered').sum()),
        n_nonvalid=lambda s:int((s=='explicit_nonvalid_game_row_zero_candidate').sum()),
        n_unresolved=lambda s:int(s.isin(['no_weekly_or_gamelevel_record','player_identity_unresolved']).sum())).reset_index()
    summary={
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),'selected_player_rows':int(len(out)),
        'recovery_status_counts':{str(k):int(v) for k,v in counts.items()},
        'lineups_with_all_scores_recovered_or_observed':int((per_line['n_unresolved']==0).sum()),
        'lineup_rows':int(len(per_line)),
        'strict_zero_candidates':int((out['recovery_status']=='explicit_nonvalid_game_row_zero_candidate').sum()),
        'gamelevel_recovered':int((out['recovery_status']=='gamelevel_valid_score_recovered').sum()),
        'weekly_observed':int((out['recovery_status']=='weekly_round_score_observed').sum()),
        'limitations':['Game-level records are matched by season, target date, and Dunkest player ID; this is not a complete historical pre-lock market snapshot.',
          'An explicit gameValidForDunkest=False row is a candidate for zero actual score but may indicate market/identity mismatch; it is reported separately and not silently promoted into certified scoring.',
          'No row in either source remains unknown, not zero.']}
    JSON.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    lines=['# Missing player-round outcome recovery audit','',f"Generated UTC: {summary['generated_at_utc']}",'',
      f"Selected player instances audited: {len(out):,}",'','## Recovery status','','| Status | Count |','|---|---:|']
    lines += [f'| {k} | {v:,} |' for k,v in counts.items()]
    lines += ['',f"Lineup-strategy rows with all ten scores observed/recovered or explicit non-valid rows: {summary['lineups_with_all_scores_recovered_or_observed']} / {summary['lineup_rows']}.",'',
      'Explicit `gameValidForDunkest=False` records are kept separate from certified actual scores: they may indicate a genuine zero, but may also reveal a stale or incorrect historical candidate identity. A player with no weekly or game-level record is left unknown, never automatically treated as zero in strict metrics.','',
      '## Limitations','']+[f'- {x}' for x in summary['limitations']]+['',f'Selected-player audit: `{CSV.relative_to(ROOT)}`',f'Machine-readable summary: `{JSON.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines))
    print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
