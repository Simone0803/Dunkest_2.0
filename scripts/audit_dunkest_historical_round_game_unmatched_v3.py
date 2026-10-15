#!/usr/bin/env python3
"""Diagnose unmatched weekly rows by testing historical team identity separately."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.names import player_key

ROOT=Path(__file__).resolve().parents[1]
STATS=ROOT/'data/processed/dunkest_historical_stats_2020-25_v2.parquet'
OFFICIAL=ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
PREV=ROOT/'reports/audit/dunkest_historical_round_game_mapping_20261013_v1_rows.csv'
OUT=ROOT/'reports/audit'; STEM='dunkest_historical_round_game_unmatched_20261013_v3'
ROW=OUT/f'{STEM}_rows.csv'; SEASON=OUT/f'{STEM}_seasons.csv'; ROUND=OUT/f'{STEM}_rounds.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
PAIRS=[('pts','pts'),('reb','reb'),('ast','ast'),('stl','stl'),('blk','blk'),('blka','blka'),('fgm','fgm'),('fga','fga'),('tpm','tpm'),('tpa','tpa'),('ftm','ftm'),('fta','fta'),('oreb','oreb'),('dreb','dreb'),('tov','tov'),('pf','pf'),('plus_minus','plusMinus')]
def num(s): return pd.to_numeric(s,errors='coerce').round(2)

def main():
    for p in [ROW,SEASON,ROUND,JSON,MD]:
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    src=pd.read_parquet(STATS)
    src=src[src.source_stats_type.astype(str).eq('tot')].copy().reset_index(drop=True)
    src['row_id']=np.arange(len(src)); src['season_id']=src.source_season_id.astype(str)
    src['player_key']=src.player_name.astype(str).map(player_key)
    src['team_src']=src.team_code.astype(str).str.upper().str.strip(); src['pdk_src']=num(src.pdk)
    for a,_ in PAIRS: src[a+'_sig']=num(src[a])
    u=pd.read_csv(PREV); u=u[u.link_status.eq('no_full_boxscore_signature_match')].copy()
    u=u.drop(columns=[c for c in ['exact_candidate_dates','exact_candidate_games','exact_candidate_flags'] if c in u.columns])
    su=src[src.row_id.isin(u.row_id.astype(int))].copy()
    if len(su)!=len(u): raise RuntimeError(f'row_id mismatch: source={len(su)}, audit={len(u)}')
    off=pd.read_parquet(OFFICIAL); off['season_id']=off.season_id.astype(str)
    off['player_key']=off.dunkest_player_name.astype(str).map(player_key)
    off['team_off']=off.nba_TEAM_ABBREVIATION.astype(str).str.upper().str.strip()
    off['pdk_off']=num(off.pdk); off['game_date']=pd.to_datetime(off.gameDate,errors='coerce').dt.strftime('%Y-%m-%d')
    off['game_id_norm']=off.gameId.astype(str).str.replace(r'\.0$','',regex=True)
    off['valid_flag']=off.gameValidForDunkest.astype(str)
    for _,b in PAIRS: off[b+'_sig']=num(off[b])
    stat_l=['season_id','player_key']+[a+'_sig' for a,_ in PAIRS]
    stat_r=['season_id','player_key']+[b+'_sig' for _,b in PAIRS]
    base=['row_id','season_id','source_week','source_round','player_name','team_src','pdk_src']
    left=su[base+['player_key']+[a+'_sig' for a,_ in PAIRS]].copy()
    right=off[stat_r+['pdk_off','team_off','game_date','game_id_norm','valid_flag']].drop_duplicates()
    full=left.merge(right,left_on=stat_l+['pdk_src'],right_on=stat_r+['pdk_off'],how='left')
    full_agg=full.groupby('row_id').agg(
        exact_candidate_games=('game_id_norm','nunique'),
        exact_candidate_dates=('game_date','nunique'),
        exact_candidate_teams=('team_off',lambda x:';'.join(sorted(x.dropna().unique()))),
        exact_candidate_dates_list=('game_date',lambda x:';'.join(sorted(x.dropna().astype(str).unique()))),
        exact_candidate_flags=('valid_flag',lambda x:';'.join(sorted(x.dropna().astype(str).unique()))),
    ).reset_index()
    stats=left.merge(right,left_on=stat_l,right_on=stat_r,how='left')
    stats_agg=stats.groupby('row_id').agg(
        stat_only_candidate_games=('game_id_norm','nunique'),
        stat_only_candidate_dates=('game_date','nunique'),
        stat_only_candidate_teams=('team_off',lambda x:';'.join(sorted(x.dropna().unique()))),
        stat_only_candidate_pdk=('pdk_off',lambda x:';'.join(map(str,sorted(x.dropna().unique())))),
        stat_only_candidate_dates_list=('game_date',lambda x:';'.join(sorted(x.dropna().astype(str).unique()))),
    ).reset_index()
    out=u.merge(full_agg,on='row_id',how='left',validate='one_to_one').merge(stats_agg,on='row_id',how='left',validate='one_to_one')
    for c in ['exact_candidate_games','exact_candidate_dates','stat_only_candidate_games','stat_only_candidate_dates']:
        out[c]=out[c].fillna(0).astype(int)
    out['team_matches_exact_candidate']=out.apply(lambda r: bool(r.team in r.exact_candidate_teams.split(';')) if isinstance(r.exact_candidate_teams,str) and r.exact_candidate_teams else False,axis=1)
    out['diagnosis']=np.select([
        out.exact_candidate_games.gt(0)&~out.team_matches_exact_candidate,
        out.exact_candidate_games.gt(0)&out.team_matches_exact_candidate,
        out.stat_only_candidate_games.gt(0),
    ],[
        'exact_player_pdk_boxscore_match_but_team_code_differs',
        'exact_player_pdk_boxscore_match_team_same_but_v1_signature_missed',
        'boxscore_stats_match_but_pdk_differs',
    ],default='no_exact_boxscore_signature_even_without_team_or_pdk')
    keep=['row_id','id','cr','team_id','team_code','team_name','position','pdk','min','starter']+[a for a,_ in PAIRS]+['fouls_received','plus','slug','source_week','source_round']
    out=out.merge(su[[c for c in keep if c in su.columns]],on='row_id',how='left',suffixes=('','_source'),validate='one_to_one')
    out.to_csv(ROW,index=False)
    season=out.groupby('season_id').agg(
        unmatched_rows=('row_id','size'),
        diagnosis_counts=('diagnosis',lambda s:json.dumps(s.value_counts().to_dict(),sort_keys=True)),
        team_mismatch_exact=('diagnosis',lambda s:int(s.eq('exact_player_pdk_boxscore_match_but_team_code_differs').sum())),
        stats_match_pdk_diff=('diagnosis',lambda s:int(s.eq('boxscore_stats_match_but_pdk_differs').sum()))
    ).reset_index()
    season.to_csv(SEASON,index=False)
    rounds=out.groupby(['season_id','source_week','source_round']).agg(
        unmatched_rows=('row_id','size'),
        team_mismatch_exact=('diagnosis',lambda s:int(s.eq('exact_player_pdk_boxscore_match_but_team_code_differs').sum())),
        pdk_mismatch=('diagnosis',lambda s:int(s.eq('boxscore_stats_match_but_pdk_differs').sum())),
        no_stats_signature=('diagnosis',lambda s:int(s.eq('no_exact_boxscore_signature_even_without_team_or_pdk').sum())),
        source_teams=('team',lambda s:';'.join(sorted(set(s.dropna().astype(str))))),
        matched_official_teams=('exact_candidate_teams',lambda s:';'.join(sorted(set(t for val in s.dropna().astype(str) for t in val.split(';') if t))))
    ).reset_index().sort_values(['season_id','source_week','source_round'])
    rounds.to_csv(ROUND,index=False)
    counts=out.diagnosis.value_counts().to_dict(); total=len(out)
    exact=out.exact_candidate_games.gt(0); mismatch=exact&~out.team_matches_exact_candidate
    report={
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),'unmatched_rows_v1':total,
        'diagnosis_counts':{str(k):int(v) for k,v in counts.items()},
        'exact_player_pdk_17_stats_match_ignoring_team':int(exact.sum()),
        'of_exact_matches_source_team_differs':int(mismatch.sum()),
        'of_exact_matches_source_team_same':int((exact&out.team_matches_exact_candidate).sum()),
        'fraction_unmatched_explained_by_team_code_mismatch':float(mismatch.sum()/total),
        'stats_match_pdk_differs':int(out.diagnosis.eq('boxscore_stats_match_but_pdk_differs').sum()),
        'no_exact_stats_signature_even_without_team_or_pdk':int(out.diagnosis.eq('no_exact_boxscore_signature_even_without_team_or_pdk').sum()),
        'seasons':season.to_dict('records'),'round_groups':len(rounds),
        'method':'For each v1-unmatched row, match season, canonical player, PDK rounded to two decimals and all 17 boxscore statistics while excluding source team_code. A second join ignores both team and PDK to identify residual score-key discrepancies.',
        'guardrails':['Team mismatch is an observed identity discrepancy, not an automatic instruction to rewrite team history.','No source row, training label, official PDK, production code/config, or frozen holdout was changed.','No unmatched row is inferred to be a DNP or zero.','Frozen 2026/27 GW1 holdout remains untouched until cutoff 2026-10-23T12:00:00Z.'],
        'artifacts':{'rows_csv':str(ROW.relative_to(ROOT)),'seasons_csv':str(SEASON.relative_to(ROOT)),'rounds_csv':str(ROUND.relative_to(ROOT)),'json':str(JSON.relative_to(ROOT)),'markdown':str(MD.relative_to(ROOT))},
        'production_changed':False}
    JSON.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
    lines=[
        '# Historical Dunkest unmatched weekly rows — team identity diagnosis v3','',
        f"Generated UTC: {report['generated_at_utc']}",'','## Result','',
        f"The v1 audit had **{total:,}** unmatched rows under the strict season + player + team + PDK + 17-stat signature. When the source team field is excluded but season, canonical player, PDK and all 17 statistics remain exact, **{int(exact.sum()):,}/{total:,} ({exact.mean():.1%})** find an official game candidate.",'',
        f"- Exact PDK + 17-stat match, but source team differs: **{int(mismatch.sum()):,} ({mismatch.sum()/total:.1%} of unmatched rows)**.",
        f"- Exact PDK + 17-stat match, source team agrees: **{int((exact&out.team_matches_exact_candidate).sum()):,}**.",
        f"- Boxscore statistics match but PDK differs (ignoring team): **{report['stats_match_pdk_differs']:,}**.",
        f"- No exact 17-stat signature even when team and PDK are ignored: **{report['no_exact_stats_signature_even_without_team_or_pdk']:,}**.",
        '','## Interpretation','',
        'The dominant issue is the source team identity attached to the historical weekly row, not the PDK value or the 17 boxscore fields: for almost all unmatched rows, the same player-game outcome and PDK are present in the official archive under a different NBA team code. This is consistent with a current/round-level roster association being attached to historical game stats, but this audit alone does not establish the exact upstream mechanism or whether team_code is intended to mean historical game team versus Dunkest team assignment.','',
        'Do not simply overwrite team_code with the matched NBA team. Preserve source semantics until they are documented. Any future backtest must use the official game team/date for matchup features while separately retaining the Dunkest fantasy-team identity if that is what the weekly source field encodes.','',
        '## Guardrails','','- Diagnostic only; no data correction or label change was applied.','- Do not treat unmatched rows as zero, DNP, or ineligible outcomes.','- Production model/configuration and the frozen 2026/27 GW1 holdout are unchanged.','- The holdout remains frozen until **2026-10-23 12:00 UTC**.','','## Artifacts',
        f'- Row-level exact candidate/team comparisons: {ROW.relative_to(ROOT)}',
        f'- Season summary: {SEASON.relative_to(ROOT)}',
        f'- Week-round summary: {ROUND.relative_to(ROOT)}',
        f'- JSON: {JSON.relative_to(ROOT)}','']
    MD.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['unmatched_rows_v1','diagnosis_counts','exact_player_pdk_17_stats_match_ignoring_team','of_exact_matches_source_team_differs','of_exact_matches_source_team_same','fraction_unmatched_explained_by_team_code_mismatch','stats_match_pdk_differs','no_exact_stats_signature_even_without_team_or_pdk','artifacts']},indent=2,default=str))
if __name__=='__main__': main()
