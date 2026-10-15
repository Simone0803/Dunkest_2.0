#!/usr/bin/env python3
"""Build an audit-only v3 linkage dataset with conservative date-assisted exact matches."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/processed/dunkest_historical_game_linked_rows_20261013_v2.parquet'
RAW=ROOT/'data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet'
OFF=ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
OUT=ROOT/'data/processed'; RPT=ROOT/'reports/audit'; STEM='dunkest_historical_game_linked_rows_20261013_v3_date_assisted'
PARQUET=OUT/f'{STEM}.parquet'; ROWS=RPT/f'{STEM}_resolved_rows.csv'; UNRES=RPT/f'{STEM}_unresolved_rows.csv'; ROUNDS=RPT/f'{STEM}_round_dates.csv'; AUDIT=RPT/f'{STEM}.json'; REPORT=RPT/f'{STEM}.md'
VALID={'true','1'}
STAT_PAIRS=[('pts','pts'),('reb','reb'),('ast','ast'),('stl','stl'),('blk','blk'),('blka','blka'),('fgm','fgm'),('fga','fga'),('tpm','tpm'),('tpa','tpa'),('ftm','ftm'),('fta','fta'),('oreb','oreb'),('dreb','dreb'),('tov','tov'),('pf','pf'),('plus_minus','plusMinus')]
def team_norm(s): return s.astype('string').str.upper().str.strip()
def num(s): return pd.to_numeric(s,errors='coerce')
def main():
    paths=[PARQUET,ROWS,UNRES,ROUNDS,AUDIT,REPORT]
    if any(p.exists() for p in paths): raise SystemExit('Refusing to overwrite existing v3 artifacts')
    # The historical player-week-round table is the source of truth for every row/stat.
    # Join only linkage metadata from v2 by natural key; never join historical stats by row position.
    d=pd.read_parquet(RAW).copy().reset_index(drop=True)
    d['source_season_id']=d.source_season_id.astype(str)
    for c in ['source_week','source_round']: d[c]=num(d[c]).astype('Int64')
    d['id']=d.id.astype(str)
    d['source_row_id']=np.arange(len(d),dtype=int)
    keys=['source_season_id','source_week','source_round','id']
    if d.duplicated(keys).any(): raise RuntimeError('Raw source keys are not unique')
    base=pd.read_parquet(BASE).copy()
    base['source_season_id']=base.source_season_id.astype(str)
    for c in ['source_week','source_round']: base[c]=num(base[c]).astype('Int64')
    base['id']=base.id.astype(str)
    meta=['strict_candidate_count','strict_candidate_dates','strict_candidate_games','strict_candidate_teams',
          'loose_candidate_count','loose_candidate_dates','loose_candidate_games','loose_candidate_teams',
          'link_status','linked_nba_game_date','linked_nba_game_id','linked_nba_game_team_code',
          'linked_nba_game_opponent_team_code','gameValidForDunkest_observed','linked_nba_matchup',
          'linked_official_pdk','linked_official_dunkest_player_id','linked_player_team_win','linked_game_overtime',
          'team_code_semantics_note','link_method']
    if base.duplicated(keys).any(): raise RuntimeError('V2 linkage metadata keys are not unique')
    d=d.merge(base[keys+meta],on=keys,how='left',validate='one_to_one')
    d['source_team_code']=d['team_code']
    d['source_team_name']=d['team_name']
    d['source_pdk']=d['target_pdk_round_total']
    d['team_code_semantics_note']=d['team_code_semantics_note'].fillna('original source team; no official game link in v2')
    d['linked_game_team_differs_from_source']=d.linked_nba_game_team_code.astype('string').str.upper().str.strip().ne(d.source_team_code.astype('string').str.upper().str.strip()) & d.linked_nba_game_team_code.notna()
    d['linked_nba_game_date']=pd.to_datetime(d.linked_nba_game_date,errors='coerce').dt.strftime('%Y-%m-%d')
    d['gameValidForDunkest_observed']=d.gameValidForDunkest_observed.astype('string')
    valid=d.gameValidForDunkest_observed.str.lower().isin(VALID)
    unique=d.link_status.isin(['unique_exact_team_signature','unique_boxscore_pdk_match_team_code_differs','unique_boxscore_pdk_match_nba_team_unknown'])
    usable=d.loc[valid & unique & d.linked_nba_game_date.notna()].copy()
    round_rows=[]
    for (sid,w,r),g in usable.groupby(['source_season_id','source_week','source_round'],dropna=False):
        counts=g.linked_nba_game_date.value_counts()
        if counts.empty: continue
        round_rows.append({'source_season_id':str(sid),'source_week':int(w),'source_round':int(r),'unique_player_date_links':int(g.id.nunique()),'date_candidates':int(len(counts)),'target_date_candidate':str(counts.index[0]),'date_confidence':float(counts.iloc[0]/len(g)),'date_ready':bool(g.id.nunique()>=10 and counts.iloc[0]/len(g)>=0.75)})
    roundmap=pd.DataFrame(round_rows)
    if roundmap.empty: raise RuntimeError('No round dates could be inferred')
    roundmap.loc[~roundmap.date_ready,'target_date_candidate']=np.nan
    roundmap.to_csv(ROUNDS,index=False)
    d=d.merge(roundmap[['source_season_id','source_week','source_round','target_date_candidate','date_confidence','date_ready']],on=['source_season_id','source_week','source_round'],how='left',validate='many_to_one')
    d['date_assisted_candidate_count']=0
    d['date_assisted_game_id']=pd.Series(pd.NA,index=d.index,dtype='string')
    d['date_assisted_team_code']=pd.Series(pd.NA,index=d.index,dtype='string')
    d['date_assisted_opponent_team_code']=pd.Series(pd.NA,index=d.index,dtype='string')
    d['date_assisted_status']='not_eligible'
    unresolved=d.linked_nba_game_team_code.isna() | ~valid | ~unique
    eligible=unresolved & d.date_ready.fillna(False) & num(d.gp).eq(1)
    eligible_idx=d.index[eligible]
    d.loc[eligible,'date_assisted_status']='no_unique_exact_candidate'
    off=pd.read_parquet(OFF)
    off=off.loc[off.gameValidForDunkest.astype(str).str.lower().isin(VALID)].copy()
    off['season_id']=off.season_id.astype(str); off['id']=off.dunkest_player_id.astype(str)
    off['candidate_date']=pd.to_datetime(off.gameDate,errors='coerce').dt.strftime('%Y-%m-%d')
    off['candidate_team']=team_norm(off.nba_TEAM_ABBREVIATION)
    off['candidate_game_id']=off.nba_GAME_ID.astype('string').str.replace(r'\.0$','',regex=True)
    off['candidate_pdk']=num(off.pdk).round(2)
    off_cols=['season_id','id','candidate_date','candidate_team','opponentTeamCode','candidate_game_id','candidate_pdk']+[o for _,o in STAT_PAIRS]
    offm=off[off_cols].rename(columns={o:f'off_{o}' for _,o in STAT_PAIRS})
    candidates=d.loc[eligible_idx,['source_season_id','id','target_date_candidate','target_pdk_round_total','source_row_id']+[s for s,_ in STAT_PAIRS]].copy()
    candidates=candidates.rename(columns={'source_season_id':'season_id','target_date_candidate':'candidate_date','target_pdk_round_total':'source_pdk'})
    candidates=candidates.merge(offm,left_on=['season_id','id','candidate_date'],right_on=['season_id','id','candidate_date'],how='left')
    candidates['pdk_match']=num(candidates.source_pdk).round(2).eq(candidates.candidate_pdk)
    candidates['all_17_stats_match']=True
    for src,official in STAT_PAIRS:
        a=num(candidates[src]).round(2); b=num(candidates[f'off_{official}']).round(2)
        candidates['all_17_stats_match'] &= a.eq(b)|(a.isna()&b.isna())
    exact=candidates[candidates.candidate_game_id.notna() & candidates.pdk_match & candidates.all_17_stats_match].drop_duplicates(['source_row_id','candidate_game_id','candidate_team'])
    cand_counts=exact.groupby('source_row_id').apply(lambda g:g[['candidate_game_id','candidate_team']].drop_duplicates().shape[0],include_groups=False)
    d.loc[eligible_idx,'date_assisted_candidate_count']=candidates.groupby('source_row_id').candidate_game_id.apply(lambda s:s.dropna().nunique()).reindex(eligible_idx).fillna(0).astype(int).to_numpy()
    exact_counts=exact.groupby('source_row_id').size()
    exact_unique_ids=cand_counts[cand_counts.eq(1)].index
    exact_unambig=exact[exact.source_row_id.isin(exact_unique_ids)].drop_duplicates('source_row_id')
    # Assert source-row IDs uniquely identify records in the base v2 dataset.
    if d.source_row_id.duplicated().any(): raise RuntimeError('source_row_id is not unique in v2 dataset')
    row_index=d.set_index('source_row_id').index
    resolved_ids=set(exact_unambig.source_row_id.tolist())
    for _,row in exact_unambig.iterrows():
        ix=d.index[d.source_row_id.eq(row.source_row_id)]
        if len(ix)!=1: raise RuntimeError(f'Expected one source row for {row.source_row_id}')
        i=ix[0]
        d.at[i,'date_assisted_game_id']=str(row.candidate_game_id)
        d.at[i,'date_assisted_team_code']=str(row.candidate_team)
        d.at[i,'date_assisted_opponent_team_code']=str(row.opponentTeamCode) if pd.notna(row.opponentTeamCode) else pd.NA
        d.at[i,'date_assisted_status']='unique_exact_pdk_and_17_stats_on_independent_round_date'
        d.at[i,'date_assisted_candidate_count']=int(cand_counts.loc[row.source_row_id])
        d.at[i,'link_method_v3']='round_date_assisted_exact_pdk_and_17_stats'
        d.at[i,'linked_nba_game_date']=str(row.candidate_date)
        d.at[i,'linked_nba_game_id']=str(row.candidate_game_id)
        d.at[i,'linked_nba_game_team_code']=str(row.candidate_team)
        d.at[i,'linked_nba_game_opponent_team_code']=str(row.opponentTeamCode) if pd.notna(row.opponentTeamCode) else pd.NA
        d.at[i,'linked_nba_matchup']=f"{row.candidate_team} vs {row.opponentTeamCode}" if pd.notna(row.opponentTeamCode) else pd.NA
        d.at[i,'linked_official_pdk']=float(row.candidate_pdk)
        d.at[i,'linked_game_team_differs_from_source']=bool(str(row.candidate_team).upper()!=str(d.at[i,'source_team_code']).upper())
    # Rows with exact candidates but >1 distinct official game remain unresolved.
    ambig_ids=set(cand_counts[cand_counts.gt(1)].index.tolist())
    for sid in ambig_ids:
        d.loc[d.source_row_id.eq(sid),'date_assisted_status']='ambiguous_multiple_exact_candidates'
    # Rows with one candidate but no exact signature get an explicit failure status.
    d.loc[eligible & d.date_assisted_status.eq('no_unique_exact_candidate') & d.date_assisted_candidate_count.gt(0),'date_assisted_status']='date_candidates_but_signature_mismatch'
    d['link_status_v3']=d.link_status.astype(str)
    d.loc[d.source_row_id.isin(resolved_ids),'link_status_v3']='date_assisted_exact_pdk_and_17_stats'
    d['link_method_v3']=d.link_method.astype(str)
    d.loc[d.source_row_id.isin(resolved_ids),'link_method_v3']='round_date_assisted_exact_pdk_and_17_stats'
    d['linked_game_team_differs_from_source_v3']=d.linked_nba_game_team_code.astype('string').str.upper().str.strip().ne(d.source_team_code.astype('string').str.upper().str.strip()) & d.linked_nba_game_team_code.notna()
    d['link_is_date_assisted_v3']=d.source_row_id.isin(resolved_ids)
    d.to_parquet(PARQUET,index=False)
    resolved=d[d.link_is_date_assisted_v3].copy()
    resolved.to_csv(ROWS,index=False)
    unresolved_rows=d[eligible & ~d.link_is_date_assisted_v3].copy()
    unresolved_rows.to_csv(UNRES,index=False)
    base_linked=int((d.linked_nba_game_date.notna() & valid & unique).sum())
    v3_linked=int((d.linked_nba_game_date.notna() & valid & unique).sum()+len(resolved))
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'base_rows':int(len(d)),'eligible_date_assisted_rows':int(eligible.sum()),'date_assisted_unique_resolutions':int(len(resolved)),'date_assisted_resolved_team_differs_from_source':int(resolved.linked_game_team_differs_from_source_v3.sum()),'eligible_unresolved_rows':int(len(unresolved_rows)),'unresolved_status_counts':{str(k):int(v) for k,v in unresolved_rows.date_assisted_status.value_counts().items()},'multi_game_rows_never_assisted':int((num(d.gp).gt(1)&d.link_is_date_assisted_v3).sum()),'base_unique_valid_links':base_linked,'v3_unique_valid_links_including_date_assisted':v3_linked,'date_ready_rounds':int(roundmap.date_ready.sum()),'rounds_total':int(len(roundmap)),'method':'For rows unresolved by v2, only gp=1 rows on an independently inferred round date (>=10 unique links and >=75% date agreement) are considered. A link is accepted only if one unique official-valid candidate matches rounded source PDK and all 17 box-score fields. Source team is not used to select the candidate.','guardrails':['Experimental dataset only; no production code/config or labels changed.','Unresolved and ambiguous candidates remain unresolved.','Missing game rows are not interpreted as DNP or OUT.','Historical outcome linkage is not a pre-lock roster/availability snapshot.','Frozen 2026/27 GW1 holdout remains untouched until 2026-10-23T12:00:00Z.'],'artifacts':{'parquet':str(PARQUET.relative_to(ROOT)),'resolved_rows':str(ROWS.relative_to(ROOT)),'unresolved_rows':str(UNRES.relative_to(ROOT)),'round_dates':str(ROUNDS.relative_to(ROOT)),'json':str(AUDIT.relative_to(ROOT)),'markdown':str(REPORT.relative_to(ROOT))}}
    AUDIT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# Historical game-linked rows v3 — date-assisted exact-signature linkage','',f"Generated UTC: {result['generated_at_utc']}",'','## Coverage','',f"- Base rows: **{len(d):,}**.",f"- Independently date-ready rounds: **{int(roundmap.date_ready.sum()):,}/{len(roundmap):,}**.",f"- Unresolved single-game rows considered: **{int(eligible.sum()):,}**.",f"- Uniquely resolved using exact PDK + 17-stat signature: **{len(resolved):,}**.",f"- Of those, official NBA team differs from source team: **{int(resolved.linked_game_team_differs_from_source_v3.sum()):,}**.",f"- Remaining unresolved among considered rows: **{len(unresolved_rows):,}**.",'','### Remaining unresolved statuses','','| Status | Rows |','|---|---:|']
    for k,v in result['unresolved_status_counts'].items(): lines.append(f'| {k} | {v:,} |')
    lines += ['','## Method and guardrails','',result['method'],'','This is a separate experimental dataset. Original source team/name/PDK fields and v2 linkage status are preserved. Date-assisted links are marked in separate fields and have an explicit `link_status_v3`; ambiguous or unmatched rows are not imputed. The round date is derived from other unique historical links, but the resulting mapping remains retrospective outcome linkage and does not provide a complete pre-lock market snapshot.','', '## Artifacts',f'- Parquet: `{PARQUET.relative_to(ROOT)}`',f'- Date-assisted rows: `{ROWS.relative_to(ROOT)}`',f'- Unresolved considered rows: `{UNRES.relative_to(ROOT)}`',f'- Round-date evidence: `{ROUNDS.relative_to(ROOT)}`',f'- JSON: `{AUDIT.relative_to(ROOT)}`','', '## Guardrails','',*['- '+g for g in result['guardrails']],'']
    REPORT.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
