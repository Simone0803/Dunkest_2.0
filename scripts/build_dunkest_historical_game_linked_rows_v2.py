#!/usr/bin/env python3
"""Build a non-destructive historical weekly-row -> official NBA game link dataset."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.names import player_key

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/processed/dunkest_historical_stats_2020-25_v2.parquet'
OFFICIAL=ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
OUT=ROOT/'data/processed'; AUDIT=ROOT/'reports/audit'
STEM='dunkest_historical_game_linked_rows_20261013_v2'
PARQUET=OUT/f'{STEM}.parquet'; CSV=AUDIT/f'{STEM}_summary.csv'
UNRESOLVED=AUDIT/f'{STEM}_unresolved.csv'; JSON=AUDIT/f'{STEM}.json'; MD=AUDIT/f'{STEM}.md'
PAIRS=[('pts','pts'),('reb','reb'),('ast','ast'),('stl','stl'),('blk','blk'),('blka','blka'),('fgm','fgm'),('fga','fga'),('tpm','tpm'),('tpa','tpa'),('ftm','ftm'),('fta','fta'),('oreb','oreb'),('dreb','dreb'),('tov','tov'),('pf','pf'),('plus_minus','plusMinus')]
def n(s): return pd.to_numeric(s,errors='coerce').round(2)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    for p in [PARQUET,CSV,UNRESOLVED,JSON,MD]:
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    src=pd.read_parquet(SOURCE)
    src=src[src.source_stats_type.astype(str).eq('tot')].copy().reset_index(drop=True)
    src['source_row_id']=np.arange(len(src),dtype=int)
    src['_season_key']=src.source_season_id.astype(str)
    src['_player_key']=src.player_name.astype(str).map(player_key)
    src['_source_team_key']=src.team_code.astype(str).str.upper().str.strip()
    src['_pdk_key']=n(src.pdk)
    src['_gp_num']=pd.to_numeric(src.gp,errors='coerce')
    for a,_ in PAIRS: src['_sig_'+a]=n(src[a])
    eligible=src[src._gp_num.eq(1)].copy()
    off=pd.read_parquet(OFFICIAL)
    off['_season_key']=off.season_id.astype(str)
    off['_player_key']=off.dunkest_player_name.astype(str).map(player_key)
    off['_nba_team_key']=off.nba_TEAM_ABBREVIATION.astype('string').str.upper().str.strip()
    off.loc[off['_nba_team_key'].isin(['','NAN','NONE','<NA>']),'_nba_team_key']=pd.NA
    off['_pdk_key']=n(off.pdk)
    off['_game_date']=pd.to_datetime(off.gameDate,errors='coerce').dt.strftime('%Y-%m-%d')
    off['_nba_game_id']=off.nba_GAME_ID.astype('string').str.replace(r'\.0$','',regex=True)
    off.loc[off['_nba_game_id'].isin(['','NAN','NONE','<NA>']),'_nba_game_id']=pd.NA
    off['_valid_flag']=off.gameValidForDunkest.astype(str)
    for _,b in PAIRS: off['_sig_'+b]=n(off[b])
    lstat=['_season_key','_player_key','_pdk_key']+['_sig_'+a for a,_ in PAIRS]
    rstat=['_season_key','_player_key','_pdk_key']+['_sig_'+b for _,b in PAIRS]
    strict_l=['_season_key','_player_key','_source_team_key','_pdk_key']+['_sig_'+a for a,_ in PAIRS]
    strict_r=['_season_key','_player_key','_nba_team_key','_pdk_key']+['_sig_'+b for _,b in PAIRS]
    candidate_cols=['_game_date','_nba_game_id','_nba_team_key','opponentTeamCode','_valid_flag','nba_MATCHUP','pdk','dunkest_player_id','playerTeamWin','gameOt']
    right=off[rstat+candidate_cols].drop_duplicates()
    left=eligible[['source_row_id']+strict_l].drop_duplicates(['source_row_id'])
    # Strict candidates require source team. Loose candidates ignore only source team.
    strict=left.merge(right,left_on=strict_l,right_on=strict_r,how='left')
    loose=left.merge(right,left_on=lstat,right_on=rstat,how='left')
    def summarize(frame,prefix):
        frame=frame[frame['_game_date'].notna()].copy()
        frame['_candidate_key']=frame['_game_date'].fillna('').astype(str)+'|'+frame['_nba_game_id'].fillna('').astype(str)+'|'+frame['_nba_team_key'].fillna('').astype(str)
        return frame.groupby('source_row_id').agg(
            **{prefix+'_count':('_candidate_key','nunique')},
            **{prefix+'_dates':('_game_date',lambda x:';'.join(sorted(x.dropna().astype(str).unique())))},
            **{prefix+'_games':('_nba_game_id',lambda x:';'.join(sorted(x.dropna().astype(str).unique())))},
            **{prefix+'_teams':('_nba_team_key',lambda x:';'.join(sorted(x.dropna().astype(str).unique())))},
        ).reset_index()
    strict_s=summarize(strict,'strict_candidate')
    loose_s=summarize(loose,'loose_candidate')
    meta=eligible[['source_row_id']].merge(strict_s,on='source_row_id',how='left',validate='one_to_one').merge(loose_s,on='source_row_id',how='left',validate='one_to_one')
    for c in ['strict_candidate_count','loose_candidate_count']: meta[c]=meta[c].fillna(0).astype(int)
    meta['link_status']=np.select([
        meta.strict_candidate_count.eq(1),
        meta.strict_candidate_count.gt(1),
        meta.strict_candidate_count.eq(0)&meta.loose_candidate_count.eq(1)&meta.loose_candidate_teams.fillna('').eq(''),
        meta.strict_candidate_count.eq(0)&meta.loose_candidate_count.eq(1)&meta.loose_candidate_teams.fillna('').ne(''),
        meta.strict_candidate_count.eq(0)&meta.loose_candidate_count.gt(1),
    ],[
        'unique_exact_team_signature','ambiguous_exact_team_signature',
        'unique_boxscore_pdk_match_nba_team_unknown','unique_boxscore_pdk_match_team_code_differs',
        'ambiguous_boxscore_pdk_match_without_team'
    ],default='unresolved_no_exact_signature')
    official_fields=['_game_date','_nba_game_id','_nba_team_key','opponentTeamCode','_valid_flag','nba_MATCHUP','pdk','dunkest_player_id','playerTeamWin','gameOt']
    strict_unique=strict[strict._game_date.notna()].merge(meta[['source_row_id','strict_candidate_count']],on='source_row_id',how='left')
    strict_unique=strict_unique[(strict_unique.strict_candidate_count.eq(1))].drop_duplicates(['source_row_id','_game_date','_nba_game_id','_nba_team_key'])
    strict_unique=strict_unique[['source_row_id']+official_fields]
    loose_unique=loose[loose._game_date.notna()].merge(meta[['source_row_id','strict_candidate_count','loose_candidate_count']],on='source_row_id',how='left')
    loose_unique=loose_unique[(loose_unique.strict_candidate_count.eq(0))&(loose_unique.loose_candidate_count.eq(1))].drop_duplicates(['source_row_id','_game_date','_nba_game_id','_nba_team_key'])
    loose_unique=loose_unique[['source_row_id']+official_fields]
    chosen=pd.concat([strict_unique,loose_unique],ignore_index=True)
    if chosen.source_row_id.duplicated().any(): raise RuntimeError('Unique-link selection produced duplicate source rows')
    rename={'_game_date':'linked_nba_game_date','_nba_game_id':'linked_nba_game_id','_nba_team_key':'linked_nba_game_team_code','opponentTeamCode':'linked_nba_game_opponent_team_code','_valid_flag':'gameValidForDunkest_observed','nba_MATCHUP':'linked_nba_matchup','pdk':'linked_official_pdk','dunkest_player_id':'linked_official_dunkest_player_id','playerTeamWin':'linked_player_team_win','gameOt':'linked_game_overtime'}
    chosen=chosen.rename(columns=rename)
    source_cols=[c for c in eligible.columns if not c.startswith('_') and c!='source_row_id']
    out=eligible[['source_row_id']+source_cols].merge(meta,on='source_row_id',how='left',validate='one_to_one').merge(chosen,on='source_row_id',how='left',validate='one_to_one')
    out['source_team_code']=out.team_code
    out['source_team_name']=out.team_name
    out['source_pdk']=out.pdk
    out['team_code_semantics_note']='original Dunkest weekly-row team; not assumed to be historical NBA game team'
    out['linked_game_team_differs_from_source']=out.linked_nba_game_team_code.fillna('').astype(str).ne(out.team_code.astype(str).str.upper().str.strip()) & out.linked_nba_game_team_code.notna()
    out['link_method']=np.select([
        out.link_status.eq('unique_exact_team_signature'),
        out.link_status.isin(['unique_boxscore_pdk_match_team_code_differs','unique_boxscore_pdk_match_nba_team_unknown']),
    ],[
        'season+player+source team+PDK+17 boxscore fields',
        'season+player+PDK+17 boxscore fields; source team excluded',
    ],default='')
    if len(out)!=len(eligible): raise RuntimeError('Output row count does not match gp=1 source universe')
    linked=out.linked_nba_game_date.notna()
    if int(linked.sum())!=int(out.link_status.isin(['unique_exact_team_signature','unique_boxscore_pdk_match_team_code_differs','unique_boxscore_pdk_match_nba_team_unknown']).sum()):
        raise RuntimeError('Linked status/date consistency check failed')
    exact=out.link_status.eq('unique_exact_team_signature')
    team_diff=out.link_status.eq('unique_boxscore_pdk_match_team_code_differs')
    team_unknown=out.link_status.eq('unique_boxscore_pdk_match_nba_team_unknown')
    unresolved=~linked
    if not out.loc[exact,'linked_nba_game_team_code'].astype(str).eq(out.loc[exact,'team_code'].astype(str).str.upper().str.strip()).all():
        raise RuntimeError('Strict-link team identity validation failed')
    if not out.loc[team_diff,'linked_nba_game_team_code'].astype(str).ne(out.loc[team_diff,'team_code'].astype(str).str.upper().str.strip()).all():
        raise RuntimeError('Team-free unique links do not all differ from source team')
    if not out.loc[team_unknown,'linked_nba_game_team_code'].isna().all():
        raise RuntimeError('Rows classified as NBA-team-unknown contain a team code')
    if not out.loc[unresolved,'linked_nba_game_date'].isna().all():
        raise RuntimeError('Ambiguous/unresolved row unexpectedly has a linked game date')
    pdk_delta=(n(out.loc[linked,'linked_official_pdk'])-n(out.loc[linked,'pdk'])).abs()
    if not pdk_delta.fillna(0).eq(0).all():
        raise RuntimeError('Linked source and official PDK values differ')
    out.to_parquet(PARQUET,index=False)
    summary=out.groupby(['source_season_id','link_status'],dropna=False).size().rename('rows').reset_index()
    summary.to_csv(CSV,index=False)
    out[~linked].to_csv(UNRESOLVED,index=False)
    status=out.link_status.value_counts(dropna=False).to_dict()
    by_season=out.groupby('source_season_id').link_status.value_counts().unstack(fill_value=0).to_dict('index')
    result={
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_tot_rows':int(len(src)),
        'source_gp1_rows':int(len(out)),
        'link_status_counts':{str(k):int(v) for k,v in status.items()},
        'linked_rows':int(linked.sum()),
        'linked_rows_with_team_code_mismatch':int(out.linked_game_team_differs_from_source.sum()),
        'by_season_id':{str(k):{str(a):int(b) for a,b in v.items()} for k,v in by_season.items()},
        'matching':'Exact PDK rounded to 2 decimals plus all 17 boxscore fields, canonical player and season. Prefer a unique source-team-inclusive signature; if absent, accept only a unique team-free candidate. Ambiguous and unresolved rows remain unlinked.',
        'source_hashes':{str(SOURCE.relative_to(ROOT)):sha(SOURCE),str(OFFICIAL.relative_to(ROOT)):sha(OFFICIAL)},
        'guardrails':['Original source team_code, team_name, PDK, boxscore fields and validity flag are preserved.','The linked NBA game team is stored separately and only populated for unique matches.','Ambiguous and unresolved rows are not imputed, relabeled, or interpreted as DNP/zero.','This derivative is not a pre-lock market snapshot and does not provide historical CR, injury, availability, or complete candidate universe.','Production code/config and frozen 2026/27 GW1 holdout were not changed; cutoff remains 2026-10-23T12:00:00Z.'],
        'artifacts':{'parquet':str(PARQUET.relative_to(ROOT)),'summary_csv':str(CSV.relative_to(ROOT)),'unresolved_csv':str(UNRESOLVED.relative_to(ROOT)),'json':str(JSON.relative_to(ROOT)),'markdown':str(MD.relative_to(ROOT))},
        'production_changed':False}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
    lines=[
        '# Historical Dunkest game-linked row dataset — v1','',f"Generated UTC: {result['generated_at_utc']}",'',
        '## Purpose','',
        'Creates a derived row-level dataset linking historical Dunkest total rows with gp=1 to official NBA player-game records. The original Dunkest team assignment remains unchanged in team_code; the historical NBA game team is stored separately as linked_nba_game_team_code. This is an outcome-link dataset, not a pre-lock market snapshot.','',
        '## Match policy','',
        '- First require season, canonical player, source team, PDK rounded to two decimals, and all 17 boxscore fields to identify one NBA game.',
        '- If the strict match is absent, exclude team from the key and accept a link only if exactly one official NBA game matches season, player, PDK and all 17 boxscore fields.',
        '- If multiple games match, preserve candidate counts and leave game fields null.',
        '- If no game matches, leave the row unresolved; never infer zero, DNP or ineligibility.','',
        '## Results','',
        f"- Source total rows: **{len(src):,}**; eligible gp=1 rows: **{len(out):,}**.",
        f"- Unique linked rows: **{int(linked.sum()):,} ({linked.mean():.1%})**.",
        f"- Unique links with team-code mismatch: **{result['linked_rows_with_team_code_mismatch']:,}**.",
        f"- Unique links whose Dunkest game record has no NBA team ID: **{int(out.link_status.eq('unique_boxscore_pdk_match_nba_team_unknown').sum()):,}**.",
        f"- Unlinked/ambiguous rows: **{len(out)-int(linked.sum()):,}**.",'',
        '## Data semantics and safeguards','',
        '- team_code and team_name are preserved as source fields; no global rewrite.',
        '- Linked NBA game team, opponent, date and game ID are separate derived fields.',
        '- gameValidForDunkest_observed records the official archive value; it is not inferred.',
        '- The output cannot be used as a complete historical market: historical credits, injury/availability snapshots, lock-time rosters and full candidate universe are still missing.',
        '- No production model/config, source file, target label, temporal split, or frozen prospective holdout was changed. No commit/push was performed.','',
        '## Artifacts','',
        f'- Parquet: {PARQUET.relative_to(ROOT)}',
        f'- Summary CSV: {CSV.relative_to(ROOT)}',
        f'- Ambiguous/unresolved CSV: {UNRESOLVED.relative_to(ROOT)}',
        f'- JSON: {JSON.relative_to(ROOT)}','']
    MD.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['source_tot_rows','source_gp1_rows','link_status_counts','linked_rows','linked_rows_with_team_code_mismatch','by_season_id','artifacts']},indent=2,default=str))
if __name__=='__main__': main()
