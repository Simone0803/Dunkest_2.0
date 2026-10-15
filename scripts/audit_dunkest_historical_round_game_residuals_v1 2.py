#!/usr/bin/env python3
"""Focused diagnostic for the 19 rows without a team-free exact boxscore signature."""
from pathlib import Path
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from dunkest.names import player_key
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_rows.csv'
OFFICIAL=ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
OUT=ROOT/'reports/audit'; STEM='dunkest_historical_round_game_residuals_20261013_v1'
CSV=OUT/f'{STEM}.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
PAIRS=[('pts','pts'),('reb','reb'),('ast','ast'),('stl','stl'),('blk','blk'),('blka','blka'),('fgm','fgm'),('fga','fga'),('tpm','tpm'),('tpa','tpa'),('ftm','ftm'),('fta','fta'),('oreb','oreb'),('dreb','dreb'),('tov','tov'),('pf','pf'),('plus_minus','plusMinus')]
def n(x): return pd.to_numeric(x,errors='coerce').round(2)
def main():
    for p in [CSV,JSON,MD]:
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    residual=pd.read_csv(INPUT)
    residual=residual[residual.exact_candidate_games.eq(0)].copy()
    off=pd.read_parquet(OFFICIAL)
    off['season_id']=off.season_id.astype(str)
    off['player_key']=off.dunkest_player_name.astype(str).map(player_key)
    off['team_off']=off.nba_TEAM_ABBREVIATION.astype(str).str.upper()
    off['pdk_off']=n(off.pdk)
    off['date']=pd.to_datetime(off.gameDate,errors='coerce').dt.strftime('%Y-%m-%d')
    for a,b in PAIRS: off[b+'_sig']=n(off[b])
    rows=[]
    for _,r in residual.iterrows():
        c=off[(off.season_id==str(r.season_id)) & (off.player_key==player_key(r.player_name))].copy()
        pdk_candidates=c[c.pdk_off==round(float(r.pdk),2)]
        mismatch_counts=[]
        for _,g in c.iterrows():
            mismatches=0
            for a,b in PAIRS:
                x=pd.to_numeric(pd.Series([r[a]]),errors='coerce').round(2).iloc[0]
                y=g[b+'_sig']
                if pd.isna(x) and pd.isna(y): continue
                if pd.isna(x)!=pd.isna(y) or x!=y: mismatches+=1
            mismatch_counts.append(mismatches)
        min_mismatch=min(mismatch_counts) if mismatch_counts else np.nan
        nearest_idx=[i for i,v in enumerate(mismatch_counts) if v==min_mismatch] if mismatch_counts else []
        nearest=c.iloc[nearest_idx]
        rows.append({
            'row_id':int(r.row_id),'season_id':str(r.season_id),'source_week':int(r.source_week),'source_round':int(r.source_round),
            'player_name':r.player_name,'source_team':r.team,'source_pdk':float(r.pdk),
            'source_pts':r.pts,'source_reb':r.reb,'source_ast':r.ast,'source_min':r['min'],
            'official_player_game_rows_in_season':int(len(c)),
            'same_player_same_pdk_candidate_rows':int(len(pdk_candidates)),
            'same_pdk_candidate_dates':';'.join(sorted(pdk_candidates.date.dropna().astype(str).unique())),
            'same_pdk_candidate_teams':';'.join(sorted(pdk_candidates.team_off.dropna().astype(str).unique())),
            'min_differing_fields_among_17_stats':int(min_mismatch) if pd.notna(min_mismatch) else np.nan,
            'nearest_candidate_dates':';'.join(sorted(nearest.date.dropna().astype(str).unique())),
            'nearest_candidate_teams':';'.join(sorted(nearest.team_off.dropna().astype(str).unique())),
        })
    out=pd.DataFrame(rows).sort_values(['source_week','player_name'])
    out.to_csv(CSV,index=False)
    pdk_any=out.same_player_same_pdk_candidate_rows.gt(0)
    dist=out.min_differing_fields_among_17_stats.value_counts().sort_index().to_dict()
    report={
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),'residual_rows':int(len(out)),
        'source_round_counts':out.groupby(['source_week','source_round']).size().reset_index(name='rows').to_dict('records'),
        'rows_with_same_player_same_pdk_candidate':int(pdk_any.sum()),
        'rows_without_same_player_same_pdk_candidate':int((~pdk_any).sum()),
        'nearest_17_stat_field_mismatch_distribution':{str(k):int(v) for k,v in dist.items()},
        'minimum_stat_fields_differing':int(out.min_differing_fields_among_17_stats.min()),
        'maximum_stat_fields_differing':int(out.min_differing_fields_among_17_stats.max()),
        'interpretation':'All residual rows lack an exact 17-stat signature in the official season archive even when team and PDK are ignored. Same-player PDK matches, when present, are not proof of the same game/date; nearest-stat comparison is diagnostic only.',
        'guardrails':['No source row or training label was modified.','Do not infer DNP, zero, or official ineligibility from these mismatches.','Production model/config and frozen 2026/27 GW1 holdout unchanged.'],
        'artifacts':{'csv':str(CSV.relative_to(ROOT)),'json':str(JSON.relative_to(ROOT)),'markdown':str(MD.relative_to(ROOT))}}
    JSON.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
    lines=['# Residual unmatched historical rows — focused diagnosis v1','',f"Generated UTC: {report['generated_at_utc']}",'',f"Only **{len(out)}** rows remain after resolving the dominant team-code mismatch. They occur in season ID 5, source week 43 round 2 ({int((out.source_week==43).sum())} rows) and week 53 round 2 ({int((out.source_week==53).sum())} rows).",'',f"- Rows with a same-player/same-season PDK value somewhere in the official archive: **{int(pdk_any.sum())}**.",f"- Rows with no same-player/same-season PDK value: **{int((~pdk_any).sum())}**.",f"- Minimum number of the 17 boxscore fields differing from the nearest same-player game: **{report['minimum_stat_fields_differing']}**; maximum: **{report['maximum_stat_fields_differing']}**.",'', 'A PDK value that appears elsewhere in the season is not a valid game link: these rows still have no exact 17-stat signature, and the matching PDK may belong to an unrelated date. The nearest-stat comparison does not repair or relabel any row. These 19 should remain excluded from exact game linkage pending source-level provenance review; do not treat them as zero or DNP.','','## Artifacts',f'- CSV: {CSV.relative_to(ROOT)}',f'- JSON: {JSON.relative_to(ROOT)}',f'- Report: {MD.relative_to(ROOT)}','']
    MD.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['residual_rows','source_round_counts','rows_with_same_player_same_pdk_candidate','rows_without_same_player_same_pdk_candidate','nearest_17_stat_field_mismatch_distribution','minimum_stat_fields_differing','maximum_stat_fields_differing','artifacts']},indent=2,default=str))
if __name__=='__main__': main()
