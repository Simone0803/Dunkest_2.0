#!/usr/bin/env python3
"""Classify unmatched historical Dunkest weekly rows without changing labels."""
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
OUT=ROOT/'reports/audit'; STEM='dunkest_historical_round_game_unmatched_20261013_v2'
ROW=OUT/f'{STEM}_rows.csv'; SEASON=OUT/f'{STEM}_seasons.csv'; ROUND=OUT/f'{STEM}_rounds.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
PAIRS=[('pts','pts'),('reb','reb'),('ast','ast'),('stl','stl'),('blk','blk'),('blka','blka'),('fgm','fgm'),('fga','fga'),('tpm','tpm'),('tpa','tpa'),('ftm','ftm'),('fta','fta'),('oreb','oreb'),('dreb','dreb'),('tov','tov'),('pf','pf'),('plus_minus','plusMinus')]
def norm_num(s): return pd.to_numeric(s,errors='coerce').round(2)
def main():
 for p in [ROW,SEASON,ROUND,JSON,MD]:
  if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
 src=pd.read_parquet(STATS); src=src[src.source_stats_type.astype(str).eq('tot')].copy().reset_index(drop=True)
 src['row_id']=np.arange(len(src)); src['season_id']=src.source_season_id.astype(str); src['player_key']=src.player_name.astype(str).map(player_key); src['team']=src.team_code.astype(str).str.upper().str.strip(); src['pdk_key']=norm_num(src.pdk); src['gp_num']=pd.to_numeric(src.gp,errors='coerce')
 old=pd.read_csv(PREV); u=old[old.link_status.eq('no_full_boxscore_signature_match')].copy()
 # Ensure IDs map to the same filtered source rows.
 src_u=src[src.row_id.isin(u.row_id.astype(int))].copy()
 for a,_ in PAIRS: src_u[a+'_sig']=norm_num(src_u[a])
 if len(src_u)!=len(u): raise RuntimeError(f'row_id mismatch: {len(src_u)} source vs {len(u)} audit')
 off=pd.read_parquet(OFFICIAL); off['season_id']=off.season_id.astype(str); off['player_key']=off.dunkest_player_name.astype(str).map(player_key); off['team']=off.nba_TEAM_ABBREVIATION.astype(str).str.upper().str.strip(); off['pdk_key']=norm_num(off.pdk); off['game_date']=pd.to_datetime(off.gameDate,errors='coerce').dt.strftime('%Y-%m-%d'); off['game_id_norm']=off.gameId.astype(str).str.replace(r'\.0$','',regex=True)
 for a,b in PAIRS: src[a+'_sig']=norm_num(src[a]); off[b+'_sig']=norm_num(off[b])
 # Count candidate records at progressively stricter identity levels.
 k1=['season_id','player_key']; k2=k1+['team']; k3=k2+['pdk_key']
 def count_candidates(keys, name):
  counts=off.groupby(keys,dropna=False).size().rename(name).reset_index()
  return src_u.merge(counts,on=keys,how='left',validate='many_to_one')[name].fillna(0).astype(int)
 out=u.copy(); out['player_key']=src_u.player_key.to_numpy(); out['pdk_key']=src_u.pdk_key.to_numpy()
 out['same_player_season_records']=count_candidates(k1,'same_player_season_records').to_numpy()
 out['same_player_team_season_records']=count_candidates(k2,'same_player_team_season_records').to_numpy()
 out['same_player_team_pdk_records']=count_candidates(k3,'same_player_team_pdk_records').to_numpy()
 # Exact match on all 17 box-score statistics but ignoring PDK, to isolate target-value/rounding mismatch.
 stat_left=['season_id','player_key','team']+[a+'_sig' for a,_ in PAIRS]
 stat_right=['season_id','player_key','team']+[b+'_sig' for _,b in PAIRS]
 off_stats=off[stat_right+['game_date','game_id_norm','pdk_key','nba_MATCHUP']].drop_duplicates()
 src_stats=src_u[stat_left].copy(); src_stats['row_id']=src_u.row_id.to_numpy()
 stat_hits=src_stats.merge(off_stats,left_on=stat_left,right_on=stat_right,how='left')
 stat_agg=stat_hits.groupby('row_id').agg(stat_signature_candidate_games=('game_id_norm','nunique'),stat_signature_candidate_dates=('game_date','nunique'),stat_signature_pdk_values=('pdk_key',lambda x:';'.join(map(str,sorted(x.dropna().unique())))),stat_signature_dates=('game_date',lambda x:';'.join(sorted(x.dropna().astype(str).unique())))).reset_index()
 out=out.merge(stat_agg,on='row_id',how='left',validate='one_to_one')
 for c in ['stat_signature_candidate_games','stat_signature_candidate_dates']: out[c]=out[c].fillna(0).astype(int)
 # Check if player appears in official archive in another season, useful for detecting season coverage gaps.
 anyseason=off.groupby('player_key').agg(official_any_season_records=('game_id_norm','nunique'),official_seasons=('season_id',lambda x:';'.join(sorted(x.unique())))).reset_index()
 out=out.merge(anyseason,on='player_key',how='left',validate='many_to_one')
 out['official_any_season_records']=out.official_any_season_records.fillna(0).astype(int)
 out['classification']=np.select([
  out.stat_signature_candidate_games.gt(0),
  out.same_player_team_pdk_records.gt(0),
  out.same_player_team_season_records.gt(0),
  out.same_player_season_records.gt(0),
  out.official_any_season_records.gt(0),
 ],[
  'boxscore_stats_match_but_pdk_or_other_signature_field_differs',
  'player_team_and_pdk_exist_but_boxscore_signature_differs',
  'player_team_exist_but_pdk_or_boxscore_stats_differ',
  'player_exists_in_season_but_team_differs_or_trade_alias',
  'player_found_only_in_other_seasons_or_season_coverage_gap',
 ],default='player_not_found_in_official_archive_possible_alias_or_coverage_gap')
 # For rows with same player/team, summarize best observed differences on selected fields, not an inferred correction.
 # Keep original row columns and all source stats for reproducibility.
 src_cols=['row_id','first_name','last_name','cr','team_id','team_name','position','pdk','min','starter']+[a for a,_ in PAIRS]+['fouls_received','plus','slug','source_week','source_round']
 src_details=src_u[[c for c in src_cols if c in src_u.columns]].copy()
 out=out.merge(src_details,on='row_id',how='left',suffixes=('','_source'),validate='one_to_one')
 out.to_csv(ROW,index=False)
 seasons=out.groupby('season_id').agg(unmatched_rows=('row_id','size'),classification_counts=('classification',lambda s:json.dumps(s.value_counts().to_dict(),sort_keys=True)),mean_same_player_team_records=('same_player_team_season_records','mean'),rows_with_any_player_season_record=('same_player_season_records',lambda s:int(s.gt(0).sum())),rows_with_exact_stats_signature=('stat_signature_candidate_games',lambda s:int(s.gt(0).sum()))).reset_index()
 seasons.to_csv(SEASON,index=False)
 rounds=out.groupby(['season_id','source_week','source_round']).agg(unmatched_rows=('row_id','size'),classes=('classification',lambda s:';'.join(f'{k}:{v}' for k,v in s.value_counts().items())),teams=('team',lambda s:';'.join(sorted(set(s.dropna().astype(str))))),players=('player_name',lambda s:';'.join(s.astype(str).head(12)))).reset_index().sort_values(['season_id','source_week','source_round'])
 rounds.to_csv(ROUND,index=False)
 counts=out.classification.value_counts().to_dict()
 report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'unmatched_rows':len(out),'classification_counts':{str(k):int(v) for k,v in counts.items()},'season_summary':seasons.to_dict('records'),'rounds_with_unmatched_rows':len(rounds),'rows_with_player_team_season_candidate':int(out.same_player_team_season_records.gt(0).sum()),'rows_with_exact_stats_signature_ignoring_pdk':int(out.stat_signature_candidate_games.gt(0).sum()),'rows_with_same_player_team_pdk_candidate':int(out.same_player_team_pdk_records.gt(0).sum()),'method':'Classifies unmatched v1 rows using official-archive candidate counts by season/player/team/PDK and exact equality of 17 boxscore fields independent of PDK. It is diagnostic only; no labels are repaired.','guardrails':['No production code/config or source data changed.','No missing row is interpreted as a DNP, zero, injury, or official non-eligible row.','Name/team candidate matches do not establish a valid game-date match.','Do not inspect or tune against frozen 2026/27 GW1 holdout before 2026-10-23T12:00:00Z.'],'artifacts':{'rows_csv':str(ROW.relative_to(ROOT)),'seasons_csv':str(SEASON.relative_to(ROOT)),'rounds_csv':str(ROUND.relative_to(ROOT)),'json':str(JSON.relative_to(ROOT)),'markdown':str(MD.relative_to(ROOT))},'production_changed':False}
 JSON.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
 lines=['# Historical Dunkest unmatched weekly rows — diagnostic v2','',f"Generated UTC: {report['generated_at_utc']}",'','## Purpose','',f"The v1 full-signature audit found **{len(out):,} unmatched `gp=1` rows**. This diagnostic classifies them using official-archive candidate counts and exact boxscore-stat signatures independent of PDK. It does not repair or relabel records.",'','## Classification','']
 lines += [f'- `{k}`: **{v:,} ({v/len(out):.1%})**' for k,v in counts.items()]
 lines += ['', '## Key checks','',f"- Rows with at least one same-season player/team official record: **{report['rows_with_player_team_candidate'] if 'rows_with_player_team_candidate' in report else int(out.same_player_team_season_records.gt(0).sum()):,}**.",f"- Rows with exact 17-stat signature match when PDK is ignored: **{report['rows_with_exact_stats_signature_ignoring_pdk']:,}**.",f"- Rows with same-season player/team/PDK candidate but differing boxscore signature: **{report['rows_with_same_player_team_pdk_candidate']:,}**.",f"- Unmatched rows span **{len(rounds):,}** season-week-round groups.",'','## Interpretation limits','', '- Candidate counts are evidence for diagnosing archive joins, not proof of a valid date/game association.', '- A statistics match with a different PDK indicates a discrepancy to investigate; it does not establish which PDK is authoritative for training.', '- A player/team mismatch can reflect a trade, identity mapping, source convention, or archive coverage. No automatic alias correction is applied.', '- Missing archive records are not negative participation labels, zero scores, or evidence of ineligibility.', '- Production model, source datasets, training labels, and frozen prospective holdout remain unchanged.','', '## Artifacts','',f'- Row-level classifications: `{ROW.relative_to(ROOT)}`',f'- Season summary: `{SEASON.relative_to(ROOT)}`',f'- Round summary: `{ROUND.relative_to(ROOT)}`',f'- JSON: `{JSON.relative_to(ROOT)}`','']
 MD.write_text('\n'.join(lines),encoding='utf-8')
 print(json.dumps({k:report[k] for k in ['unmatched_rows','classification_counts','rows_with_player_team_season_candidate','rows_with_exact_stats_signature_ignoring_pdk','rows_with_same_player_team_pdk_candidate','rounds_with_unmatched_rows','artifacts']},indent=2,default=str))
if __name__=='__main__': main()
