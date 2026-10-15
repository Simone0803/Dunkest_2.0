#!/usr/bin/env python3
"""Audit rows with legacy opponent coverage but no corrected linked-game opponent."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.names import player_key

ROOT=Path(__file__).resolve().parents[1]
COVER=ROOT/'reports/audit/dunkest_historical_matchup_team_link_coverage_20261013_v1_rows.csv'
RAW=ROOT/'data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet'
OFF=ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
LINK=ROOT/'data/processed/dunkest_historical_game_linked_rows_20261013_v2.parquet'
OUT=ROOT/'reports/audit'; STEM='dunkest_legacy_only_opponent_rows_20261013_v1'
CSV=OUT/f'{STEM}.csv'; SUMMARY=OUT/f'{STEM}_summary.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
SEASONS={'5','7','9','13','19'}
STAT_PAIRS=[('pts','pts'),('reb','reb'),('ast','ast'),('stl','stl'),('blk','blk'),('blka','blka'),('fgm','fgm'),('fga','fga'),('tpm','tpm'),('tpa','tpa'),('ftm','ftm'),('fta','fta'),('oreb','oreb'),('dreb','dreb'),('tov','tov'),('pf','pf'),('plus_minus','plusMinus')]
def norm_team(s): return s.astype('string').str.upper().str.strip()
def round_num(s): return pd.to_numeric(s,errors='coerce').round(2)
def main():
    for p in [CSV,SUMMARY,JSON,MD]:
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    cov=pd.read_csv(COVER)
    x=cov[cov.legacy_has_opponent.astype(bool)&~cov.corrected_has_opponent.astype(bool)].copy()
    x['season_id']=x.season_id.astype(str)
    x['player_key']=x.player_name.astype(str).map(player_key)
    x['legacy_target_date']=pd.to_datetime(x.legacy_target_date,errors='coerce').dt.strftime('%Y-%m-%d')
    x['pdk_key']=round_num(x.pdk_key)
    x=x.rename(columns={'link_status':'coverage_link_status'})
    raw=pd.read_parquet(RAW)
    raw['season_id']=raw.source_season_id.astype(str)
    raw=raw[raw.season_id.isin(SEASONS)].copy().reset_index(drop=True)
    raw['source_row_id']=np.arange(len(raw),dtype=int)
    raw['player_key']=raw.player_name.astype(str).map(player_key)
    raw['season_id']=raw.source_season_id.astype(str)
    # The coverage audit used the same season filter and original row order to define source_row_id.
    src_cols=['source_row_id','pts','reb','ast','stl','blk','blka','fgm','fga','tpm','tpa','ftm','fta','oreb','dreb','tov','pf','plus_minus']
    x=x.merge(raw[src_cols],on='source_row_id',how='left',validate='one_to_one')
    off=pd.read_parquet(OFF)
    off=off[off.gameValidForDunkest.astype(str).str.lower().isin({'true','1'})].copy()
    off['season_id']=off.season_id.astype(str)
    off['player_key']=off.dunkest_player_name.astype(str).map(player_key)
    off['nba_team_code']=norm_team(off.nba_TEAM_ABBREVIATION)
    off['candidate_date']=pd.to_datetime(off.gameDate,errors='coerce').dt.strftime('%Y-%m-%d')
    off['pdk_key_off']=round_num(off.pdk)
    # Keep one row per official player-game candidate; normally this is one, but don't assume it.
    ofcols=['season_id','player_key','candidate_date','nba_team_code','opponentTeamCode','pdk_key_off','nba_GAME_ID','nba_MIN','pts','reb','ast','stl','blk','blka','fgm','fga','tpm','tpa','ftm','fta','oreb','dreb','tov','pf','plusMinus','nba_match_status']
    off_for_merge=off[ofcols].rename(columns={c:f'off_{c}' for c in ofcols if c not in {'season_id','player_key','candidate_date'}})
    src_fields=['source_week','source_round','id','player_name','gp','source_team_code','legacy_target_opponent','corrected_target_date','corrected_target_opponent','coverage_link_status','pdk_key']+[s for s,_ in STAT_PAIRS]
    cand=x[['source_row_id','season_id','player_key','legacy_target_date']+src_fields].merge(
        off_for_merge,left_on=['season_id','player_key','legacy_target_date'],right_on=['season_id','player_key','candidate_date'],how='left')
    cand['has_official_date_game']=cand.off_nba_GAME_ID.notna()
    cand['source_team_match']=cand.source_team_code.astype('string').str.upper().str.strip().eq(cand.off_nba_team_code)
    cand['pdk_match']=cand.pdk_key.eq(cand.off_pdk_key_off)
    pairs=[(s,o) for s,o in STAT_PAIRS]
    for s,o in pairs:
        cand[f'diff_{s}']=pd.to_numeric(cand[s],errors='coerce').ne(pd.to_numeric(cand[f'off_{o}'],errors='coerce'))
        # Two missing values count as equal, but a missing value on only one side does not.
        both_missing=pd.to_numeric(cand[s],errors='coerce').isna()&pd.to_numeric(cand[f'off_{o}'],errors='coerce').isna()
        cand.loc[both_missing,f'diff_{s}']=False
    diff_cols=[f'diff_{s}' for s,_ in pairs]
    cand['all_17_boxscore_fields_match']=~cand[diff_cols].any(axis=1)
    cand['legacy_opponent_matches_official_game']=cand.legacy_target_opponent.astype('string').str.upper().str.strip().eq(cand.off_opponentTeamCode.astype('string').str.upper().str.strip())
    cand.loc[~cand.has_official_date_game,['source_team_match','pdk_match','all_17_boxscore_fields_match','legacy_opponent_matches_official_game']]=False
    # Choose the strongest same-date official candidate for each source row: team, PDK, then stat match.
    cand['candidate_score']=cand.source_team_match.astype(int)*4+cand.pdk_match.astype(int)*2+cand.all_17_boxscore_fields_match.astype(int)
    cand=cand.sort_values(['source_row_id','candidate_score','off_nba_GAME_ID'],ascending=[True,False,True],na_position='last')
    best=cand.drop_duplicates('source_row_id',keep='first').copy()
    best['official_date_candidate_count']=cand[cand.has_official_date_game].groupby('source_row_id').size().reindex(best.source_row_id).fillna(0).to_numpy(dtype=int)
    link=pd.read_parquet(LINK)
    link['season_id']=link.source_season_id.astype(str)
    link['source_week']=pd.to_numeric(link.source_week,errors='coerce')
    link['source_round']=pd.to_numeric(link.source_round,errors='coerce')
    link['id']=link.id.astype(str)
    best['source_week']=pd.to_numeric(best.source_week,errors='coerce')
    best['source_round']=pd.to_numeric(best.source_round,errors='coerce')
    best['id']=best.id.astype(str)
    linkcols=['season_id','source_week','source_round','id','link_status','strict_candidate_count','strict_candidate_dates','strict_candidate_teams','loose_candidate_count','loose_candidate_dates','loose_candidate_teams','linked_nba_game_date','linked_nba_game_team_code','linked_nba_game_opponent_team_code','team_code_semantics_note']
    best=best.merge(link[linkcols].rename(columns={'link_status':'linked_dataset_status'}),on=['season_id','source_week','source_round','id'],how='left',validate='one_to_one')
    best['evidence_class']=np.select([
        pd.to_numeric(best.gp,errors='coerce').ne(1),
        ~best.has_official_date_game,
        best.has_official_date_game&best.source_team_match&best.pdk_match&best.legacy_opponent_matches_official_game,
        best.has_official_date_game&~best.source_team_match,
        best.has_official_date_game&best.source_team_match&~best.legacy_opponent_matches_official_game,
    ],['multi_game_aggregate_not_single_game','no_official_player_game_on_inferred_date','team_and_opponent_confirmed','source_team_disagrees_with_official_team','team_matches_but_opponent_disagrees'],default='official_game_found_needs_review')
    # More precise row-level categories are mutually exclusive and countable.
    best['row_class']=np.select([
        pd.to_numeric(best.gp,errors='coerce').ne(1),
        ~best.has_official_date_game,
        best.has_official_date_game&~best.source_team_match,
        best.has_official_date_game&best.source_team_match&best.pdk_match&best.all_17_boxscore_fields_match&best.legacy_opponent_matches_official_game,
        best.has_official_date_game&best.source_team_match&best.legacy_opponent_matches_official_game,
    ],['multi_game_aggregate_not_single_game','no_player_game_record_on_date','NBA_team_differs_from_source_team','exact_boxscore_pdk_team_and_opponent_confirmed','team_and_opponent_confirmed_but_signature_differs'],default='other')
    # Keep review-friendly columns plus individual statistic mismatch flags.
    cols=['source_row_id','season_id','source_week','source_round','id','player_name','gp','source_team_code','pdk_key','legacy_target_date','legacy_target_opponent','corrected_target_date','corrected_target_opponent','coverage_link_status','linked_dataset_status','strict_candidate_count','strict_candidate_dates','strict_candidate_teams','loose_candidate_count','loose_candidate_dates','loose_candidate_teams','official_date_candidate_count','off_nba_GAME_ID','off_nba_team_code','off_opponentTeamCode','off_nba_MIN','off_pdk_key_off','source_team_match','pdk_match','all_17_boxscore_fields_match','legacy_opponent_matches_official_game','row_class','evidence_class']+diff_cols
    best[cols].to_csv(CSV,index=False)
    byclass=best.groupby(['season_id','row_class'],dropna=False).size().rename('rows').reset_index()
    byclass.to_csv(SUMMARY,index=False)
    result={
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),'audited_rows':int(len(best)),
      'single_game_rows_gp1':int(pd.to_numeric(best.gp,errors='coerce').eq(1).sum()),
      'multi_game_aggregate_rows_gp_gt1':int(pd.to_numeric(best.gp,errors='coerce').gt(1).sum()),
      'official_player_game_found_on_inferred_date_gp1':int((pd.to_numeric(best.gp,errors='coerce').eq(1)&best.has_official_date_game).sum()),
      'no_official_player_game_record_on_inferred_date_gp1':int((pd.to_numeric(best.gp,errors='coerce').eq(1)&~best.has_official_date_game).sum()),
      'source_team_matches_official_team_gp1':int((pd.to_numeric(best.gp,errors='coerce').eq(1)&best.has_official_date_game&best.source_team_match).sum()),
      'source_team_differs_from_official_team_gp1':int((pd.to_numeric(best.gp,errors='coerce').eq(1)&best.has_official_date_game&~best.source_team_match).sum()),
      'legacy_opponent_matches_official_opponent_gp1':int((pd.to_numeric(best.gp,errors='coerce').eq(1)&best.has_official_date_game&best.legacy_opponent_matches_official_game).sum()),
      'pdk_match_count_gp1':int((pd.to_numeric(best.gp,errors='coerce').eq(1)&best.has_official_date_game&best.pdk_match).sum()),
      'all_17_boxscore_fields_match_count_gp1':int((pd.to_numeric(best.gp,errors='coerce').eq(1)&best.has_official_date_game&best.all_17_boxscore_fields_match).sum()),
      'exact_date_assisted_link_candidates_gp1':int((pd.to_numeric(best.gp,errors='coerce').eq(1)&best.has_official_date_game&best.pdk_match&best.all_17_boxscore_fields_match).sum()),
      'row_class_counts':{str(k):int(v) for k,v in best.row_class.value_counts().items()},
      'link_status_counts':{str(k):int(v) for k,v in best.linked_dataset_status.fillna('<no link row>').value_counts().items()},
      'season_counts':{str(k):int(v) for k,v in best.groupby('season_id').size().items()},
      'stat_mismatch_frequency':{s:int(best[f'diff_{s}'].sum()) for s,_ in pairs},
      'artifacts':{'row_csv':str(CSV.relative_to(ROOT)),'summary_csv':str(SUMMARY.relative_to(ROOT)),'json':str(JSON.relative_to(ROOT)),'markdown':str(MD.relative_to(ROOT))},
      'guardrails':['Audit-only; no production code, model, labels, temporal splits, or coefficients changed.','No claim that missing player-game rows mean DNP or OUT; source coverage may be incomplete.','Historical weekly rows are not treated as pre-lock roster snapshots.','Frozen 2026/27 GW1 holdout remains untouched until 2026-10-23T12:00:00Z.']}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# Audit of legacy-only opponent coverage — v1','',f"Generated UTC: {result['generated_at_utc']}",'',
      '## Scope','',
      f"Inspected **{len(best)}** rows where the legacy method supplies an opponent but the corrected full-signature link does not. This is a diagnostic audit, not model selection.",'',
      '## Findings','',
      f"- Single-game source rows (gp=1): **{result['single_game_rows_gp1']}**; multi-game aggregate rows (gp>1), excluded from one-game linkage: **{result['multi_game_aggregate_rows_gp_gt1']}**.",
      f"- Among gp=1 rows, official player-game row on the inferred date: **{result['official_player_game_found_on_inferred_date_gp1']}**; no row: **{result['no_official_player_game_record_on_inferred_date_gp1']}**.",
      f"- Among gp=1 rows, source Dunkest team equals official NBA team: **{result['source_team_matches_official_team_gp1']}**; differs: **{result['source_team_differs_from_official_team_gp1']}**.",
      f"- Among gp=1 rows, legacy opponent equals official opponent: **{result['legacy_opponent_matches_official_opponent_gp1']}**.",
      f"- Rounded PDK matches official game PDK: **{result['pdk_match_count_gp1']}**; all 17 box-score fields match: **{result['all_17_boxscore_fields_match_count_gp1']}**.",
      f"- Rows with a date-assisted exact PDK+17-stat candidate: **{result['exact_date_assisted_link_candidates_gp1']}** (before accepting the approach outside this audit).",'',
      '### Row classification','',
      '| Class | Rows |','|---|---:|']
    for k,v in result['row_class_counts'].items(): lines.append(f'| {k} | {v:,} |')
    lines += ['', '### Link-status counts','','| Link status | Rows |','|---|---:|']
    for k,v in result['link_status_counts'].items(): lines.append(f'| {k} | {v:,} |')
    lines += ['', '## Interpretation','','The legacy-only set is heterogeneous. Six rows have gp>1 and represent multi-game aggregates, so they must not receive a single-game opponent link. Of the 445 gp=1 rows, 405 have an exact same-date PDK+17-stat candidate whose official NBA team and opponent agree with the legacy assignment; 23 have exact PDK+17-stat candidates but the official NBA team differs from the source Dunkest team, so the legacy opponent is wrong for that NBA game; two have same-team/date candidates but fail the exact 17-stat signature; and 15 have no official player-game row on the inferred date. Thus, an independent round-date consensus can potentially disambiguate 428 exact PDK+stat signatures (405 same-team and 23 corrected-team links) without weakening the signature rule. This is an audit hypothesis only: date-assisted linking must be implemented and validated as a separate experimental dataset before model use. Absence from this archive does not prove DNP/OUT.','','## Artifacts',f'- Detailed row-level audit: `{CSV.relative_to(ROOT)}`',f'- Counts by season/class: `{SUMMARY.relative_to(ROOT)}`',f'- Machine-readable summary: `{JSON.relative_to(ROOT)}`','', '## Guardrails','',*['- '+g for g in result['guardrails']],'']
    MD.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
