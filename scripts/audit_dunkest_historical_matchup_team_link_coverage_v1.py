#!/usr/bin/env python3
"""Compare legacy team+PDK matchup linkage with full-signature historical game links."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.names import player_key

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet'
OFFICIAL=ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
LINKED=ROOT/'data/processed/dunkest_historical_game_linked_rows_20261013_v2.parquet'
TEAM_LOGS=ROOT/'data/processed/team_game_logs_2018-26_v1.parquet'
OUT=ROOT/'reports/audit'; STEM='dunkest_historical_matchup_team_link_coverage_20261013_v1'
ROWS=OUT/f'{STEM}_rows.csv'; ROUNDS=OUT/f'{STEM}_rounds.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
VALID_SEASONS={'5','7','9','13','19'}
UNIQUE_STATUSES={'unique_exact_team_signature','unique_boxscore_pdk_match_team_code_differs','unique_boxscore_pdk_match_nba_team_unknown'}
def num(s): return pd.to_numeric(s,errors='coerce').round(2)
def round_map(links,prefix):
    if links.empty: return pd.DataFrame(columns=['season_id','source_week','source_round',prefix+'_links',prefix+'_target_date',prefix+'_confidence',prefix+'_ready'])
    rows=[]
    for (sid,w,r),g in links.groupby(['season_id','source_week','source_round'],dropna=False):
        dates=g['candidate_date'].value_counts()
        if dates.empty: continue
        id_col='id' if 'id' in g.columns else 'id_key'
        n_links=int(g[[id_col]].drop_duplicates().shape[0])
        confidence=float(dates.iloc[0]/len(g))
        ready=confidence>=0.75 and n_links>=10
        rows.append({'season_id':str(sid),'source_week':int(w),'source_round':int(r),prefix+'_links':n_links,
                     prefix+'_target_date':str(dates.index[0]) if ready else '',
                     prefix+'_confidence':confidence,prefix+'_ready':bool(ready)})
    return pd.DataFrame(rows)
def main():
    for p in [ROWS,ROUNDS,JSON,MD]:
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    raw=pd.read_parquet(INPUT)
    raw['season_id']=raw.source_season_id.astype(str)
    raw=raw[raw.season_id.isin(VALID_SEASONS)].copy()
    raw['source_week']=pd.to_numeric(raw.source_week,errors='coerce').astype('Int64')
    raw['source_round']=pd.to_numeric(raw.source_round,errors='coerce').astype('Int64')
    raw['player_key']=raw.player_name.astype(str).map(player_key)
    raw['source_team_code']=raw.team_code.astype(str).str.upper().str.strip()
    raw['pdk_key']=num(raw.target_pdk_round_total)
    raw['id_key']=raw.id.astype(str)
    raw['source_row_id']=np.arange(len(raw),dtype=int)
    off=pd.read_parquet(OFFICIAL)
    off=off[off.gameValidForDunkest.astype(str).str.lower().isin({'true','1'})].copy()
    off['season_id']=off.season_id.astype(str)
    off['player_key']=off.dunkest_player_name.astype(str).map(player_key)
    off['nba_team_code']=off.nba_TEAM_ABBREVIATION.astype('string').str.upper().str.strip()
    off['pdk_key']=num(off.pdk)
    off['candidate_date']=pd.to_datetime(off.gameDate,errors='coerce').dt.strftime('%Y-%m-%d')
    off=off.dropna(subset=['candidate_date'])
    old_candidates=raw[['source_row_id','season_id','player_key','source_team_code','pdk_key','source_week','source_round','id']].merge(
        off[['season_id','player_key','nba_TEAM_ABBREVIATION','pdk_key','candidate_date']].assign(
            nba_TEAM_ABBREVIATION=lambda x:x.nba_TEAM_ABBREVIATION.astype('string').str.upper().str.strip()
        ).drop_duplicates(),
        left_on=['season_id','player_key','source_team_code','pdk_key'],
        right_on=['season_id','player_key','nba_TEAM_ABBREVIATION','pdk_key'],how='left')
    old_count=old_candidates.groupby('source_row_id').candidate_date.nunique(dropna=True)
    old_candidates['date_count']=old_candidates.source_row_id.map(old_count)
    old_unique=old_candidates[old_candidates.date_count.eq(1)&old_candidates.candidate_date.notna()].drop_duplicates(['source_row_id','candidate_date'])
    old_links=old_unique[['source_row_id','season_id','source_week','source_round','id','candidate_date']].copy()
    linked=pd.read_parquet(LINKED)
    linked['season_id']=linked.source_season_id.astype(str)
    linked['source_week']=pd.to_numeric(linked.source_week,errors='coerce').astype('Int64')
    linked['source_round']=pd.to_numeric(linked.source_round,errors='coerce').astype('Int64')
    linked['id_key']=linked.id.astype(str)
    linked['candidate_date']=pd.to_datetime(linked.linked_nba_game_date,errors='coerce').dt.strftime('%Y-%m-%d')
    linked=linked[linked.link_status.isin(UNIQUE_STATUSES)&linked.gameValidForDunkest_observed.astype(str).str.lower().isin({'true','1'})&linked.candidate_date.notna()].copy()
    # Join via Dunkest player ID and exact source round, retaining source team as separate metadata.
    new_links=raw[['source_row_id','season_id','source_week','source_round','id_key','source_team_code']].merge(
        linked[['season_id','source_week','source_round','id_key','candidate_date','linked_nba_game_team_code','linked_nba_game_opponent_team_code','link_status']],
        on=['season_id','source_week','source_round','id_key'],how='left',validate='one_to_one')
    new_links=new_links[new_links.candidate_date.notna()].copy()
    old_rm=round_map(old_links,'legacy')
    new_rm=round_map(new_links,'corrected')
    rounds=old_rm.merge(new_rm,on=['season_id','source_week','source_round'],how='outer')
    for c in ['legacy_ready','corrected_ready']: rounds[c]=rounds[c].fillna(False).astype(bool)
    rounds['ready_status']=np.select([
        rounds.legacy_ready&rounds.corrected_ready,
        ~rounds.legacy_ready&rounds.corrected_ready,
        rounds.legacy_ready&~rounds.corrected_ready,
    ],['ready_both','corrected_only','legacy_only'],default='ready_neither')
    rounds['date_agrees']=rounds.legacy_target_date.eq(rounds.corrected_target_date)&rounds.legacy_ready&rounds.corrected_ready
    # Construct team-game schedule: only complete two-team games are usable.
    teams=pd.read_parquet(TEAM_LOGS)
    teams['GAME_DATE']=pd.to_datetime(teams.GAME_DATE,errors='coerce').dt.strftime('%Y-%m-%d')
    teams['GAME_ID']=teams.GAME_ID.astype(str)
    teams['TEAM_ABBREVIATION']=teams.TEAM_ABBREVIATION.astype(str).str.upper().str.strip()
    pairs=[]
    for gid,g in teams.groupby('GAME_ID',sort=False):
        g=g.drop_duplicates('TEAM_ABBREVIATION')
        if len(g)!=2: continue
        a,b=g.iloc[0],g.iloc[1]
        pairs += [{'GAME_DATE':a.GAME_DATE,'team_code':a.TEAM_ABBREVIATION,'opponent_code':b.TEAM_ABBREVIATION},
                  {'GAME_DATE':b.GAME_DATE,'team_code':b.TEAM_ABBREVIATION,'opponent_code':a.TEAM_ABBREVIATION}]
    schedule=pd.DataFrame(pairs).dropna().drop_duplicates(['GAME_DATE','team_code'])
    round_date_cols=rounds[['season_id','source_week','source_round','legacy_target_date','legacy_ready','corrected_target_date','corrected_ready']]
    row=raw[['source_row_id','season_id','source_week','source_round','id','player_name','source_team_code','pdk_key','gp','target_pdk_round_total']].merge(round_date_cols,on=['season_id','source_week','source_round'],how='left',validate='many_to_one')
    row=row.merge(new_links[['source_row_id','linked_nba_game_team_code','linked_nba_game_opponent_team_code','link_status']],on='source_row_id',how='left',validate='one_to_one')
    row['legacy_target_opponent']=row[['legacy_target_date','source_team_code']].merge(
        schedule,left_on=['legacy_target_date','source_team_code'],right_on=['GAME_DATE','team_code'],how='left')['opponent_code'].to_numpy()
    row['corrected_target_opponent']=row[['corrected_target_date','linked_nba_game_team_code']].merge(
        schedule,left_on=['corrected_target_date','linked_nba_game_team_code'],right_on=['GAME_DATE','team_code'],how='left')['opponent_code'].to_numpy()
    row['legacy_has_opponent']=row.legacy_ready.fillna(False)&row.legacy_target_opponent.notna()
    row['corrected_has_opponent']=row.corrected_ready.fillna(False)&row.corrected_target_opponent.notna()
    row['opponent_coverage_gain']=row.corrected_has_opponent.astype(int)-row.legacy_has_opponent.astype(int)
    row.to_csv(ROWS,index=False)
    rounds.to_csv(ROUNDS,index=False)
    counts=rounds.ready_status.value_counts().to_dict()
    status=row.opponent_coverage_gain.value_counts().to_dict()
    row_season=row.groupby('season_id').agg(
        rows=('source_row_id','size'),
        legacy_opponent_rows=('legacy_has_opponent','sum'),corrected_opponent_rows=('corrected_has_opponent','sum'),
        rows_team_mismatch_link=('link_status',lambda s:int(s.eq('unique_boxscore_pdk_match_team_code_differs').sum())),
    ).reset_index()
    round_season=rounds.groupby('season_id').agg(
        legacy_ready_rounds=('legacy_ready','sum'),corrected_ready_rounds=('corrected_ready','sum'),
        corrected_only_rounds=('ready_status',lambda s:int(s.eq('corrected_only').sum())),
    ).reset_index()
    per_season=round_season.merge(row_season,on='season_id',how='outer')
    result={
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_rows':int(len(raw)),
        'legacy_unique_player_date_links':int(len(old_links)),
        'corrected_unique_valid_game_date_links':int(len(new_links)),
        'round_groups':int(len(rounds)),
        'round_readiness_comparison':{str(k):int(v) for k,v in counts.items()},
        'legacy_ready_rounds':int(rounds.legacy_ready.sum()),
        'corrected_ready_rounds':int(rounds.corrected_ready.sum()),
        'both_ready_date_agreement':int(rounds.date_agrees.sum()),
        'both_ready_date_disagreement':int((rounds.legacy_ready&rounds.corrected_ready&~rounds.date_agrees).sum()),
        'legacy_rows_with_opponent':int(row.legacy_has_opponent.sum()),
        'corrected_rows_with_opponent':int(row.corrected_has_opponent.sum()),
        'opponent_row_gain_distribution':{str(k):int(v) for k,v in status.items()},
        'per_season':per_season.to_dict('records'),
        'method':'Legacy date inference uses season+canonical player+source team+rounded target PDK against official-valid Dunkest per-game records, as in the v6 feature builder. Corrected date inference uses the versioned full-stat link dataset, restricted to observed gameValidForDunkest=True unique links. Both use the same >=10 links and >=75% dominant-date threshold. Opponent is looked up from team_game_logs using the round target date and (legacy source team or corrected linked NBA team).',
        'guardrails':['This is a coverage audit, not model tuning or a claim that weekly rows are pre-lock snapshots.','The linked dataset does not infer missing NBA teams; those rows cannot contribute team-specific opponent features.','No production code/config, source labels, temporal splits, or frozen holdout changed.','Frozen 2026/27 GW1 holdout remains untouched until 2026-10-23T12:00:00Z.'],
        'artifacts':{'rows_csv':str(ROWS.relative_to(ROOT)),'rounds_csv':str(ROUNDS.relative_to(ROOT)),'json':str(JSON.relative_to(ROOT)),'markdown':str(MD.relative_to(ROOT))},
        'production_changed':False}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
    lines=[
        '# Historical matchup linkage coverage audit — v1','',f"Generated UTC: {result['generated_at_utc']}",'',
        '## Question','',
        'Does separating the source Dunkest team from the historical NBA game team improve the date and opponent linkage used by the existing matchup/rest feature experiment? This audit measures coverage only; it does not retrain or change production.','',
        '## Overall results','',
        f"- Source rows inspected: **{len(raw):,}**.",
        f"- Legacy unique player/date links (source team + PDK): **{len(old_links):,}**.",
        f"- Corrected unique valid game/date links (full-stat linked dataset): **{len(new_links):,}**.",
        f"- Rounds meeting the existing date-confidence rule: legacy **{int(rounds.legacy_ready.sum())}**, corrected **{int(rounds.corrected_ready.sum())}**.",
        f"- Rounds ready under both methods with same target date: **{int(rounds.date_agrees.sum())}**.",
        f"- Rows with a schedule-derived opponent: legacy **{int(row.legacy_has_opponent.sum()):,}**, corrected **{int(row.corrected_has_opponent.sum()):,}**.",
        f"- Opponent coverage gain distribution (corrected minus legacy): {json.dumps({str(k):int(v) for k,v in status.items()},sort_keys=True)}.",'',
        '## By season','',
        '| Season ID | Rows | Legacy ready rounds | Corrected ready rounds | Legacy opponent rows | Corrected opponent rows | Team-mismatch links |',
        '|---:|---:|---:|---:|---:|---:|---:|']
    for r in per_season.to_dict('records'):
        lines.append(f"| {r['season_id']} | {r['rows']:,} | {r['legacy_ready_rounds']} | {r['corrected_ready_rounds']} | {r['legacy_opponent_rows']:,} | {r['corrected_opponent_rows']:,} | {r['rows_team_mismatch_link']:,} |")
    lines += ['','## Interpretation','','The corrected mapping only changes how an outcome row is associated with its historical NBA game. It does not change the source row’s PDK, credit, role, or Dunkest team field. A coverage increase would support testing an isolated walk-forward ablation that uses the linked NBA team for target-game matchup features, while retaining only past-only opponent form and rest inputs. It would not justify using the weekly archive as a pre-lock roster or participation dataset.','','## Artifacts',f"- Row-level comparison: {ROWS.relative_to(ROOT)}",f"- Round readiness comparison: {ROUNDS.relative_to(ROOT)}",f"- JSON: {JSON.relative_to(ROOT)}",'']
    MD.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['source_rows','legacy_unique_player_date_links','corrected_unique_valid_game_date_links','round_groups','round_readiness_comparison','legacy_ready_rounds','corrected_ready_rounds','both_ready_date_agreement','both_ready_date_disagreement','legacy_rows_with_opponent','corrected_rows_with_opponent','opponent_row_gain_distribution','per_season','artifacts']},indent=2,default=str))
if __name__=='__main__': main()
