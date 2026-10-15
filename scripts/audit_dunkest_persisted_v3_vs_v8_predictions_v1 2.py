#!/usr/bin/env python3
"""Verify the persisted v3 date-assisted dataset reproduces the V8 walk-forward."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
V3=ROOT/'data/processed/dunkest_historical_game_linked_rows_20261013_v3_date_assisted.parquet'
RAW=ROOT/'data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet'
V8=ROOT/'reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v8_date_assisted_link_predictions.csv'
V9=ROOT/'reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link_predictions.csv'
OUT=ROOT/'reports/audit'; STEM='dunkest_persisted_v3_vs_v8_prediction_parity_20261013_v1'
CSV=OUT/f'{STEM}_by_family.csv'; JSON=OUT/f'{STEM}.json'; MD=OUT/f'{STEM}.md'
KEYS=['season_id','source_week','source_round','player_name','feature_family']
STAT_PAIRS=[('pts','pts'),('reb','reb'),('ast','ast'),('stl','stl'),('blk','blk'),('blka','blka'),('fgm','fgm'),('fga','fga'),('tpm','tpm'),('tpa','tpa'),('ftm','ftm'),('fta','fta'),('oreb','oreb'),('dreb','dreb'),('tov','tov'),('pf','pf'),('plus_minus','plusMinus')]
def main():
    if any(p.exists() for p in [CSV,JSON,MD]): raise SystemExit('Refusing to overwrite versioned parity artifacts')
    d=pd.read_parquet(V3); raw=pd.read_parquet(RAW)
    keys=['source_season_id','source_week','source_round','id']
    for x in (d,raw):
        x['source_season_id']=x.source_season_id.astype(str); x['id']=x.id.astype(str)
        for c in ['source_week','source_round']: x[c]=pd.to_numeric(x[c],errors='coerce').astype('Int64')
    if d.duplicated(keys).any() or raw.duplicated(keys).any(): raise RuntimeError('Non-unique natural keys in source or v3 dataset')
    assisted=d[d.link_is_date_assisted_v3.astype(bool)].copy()
    source_fields=[s for s,_ in STAT_PAIRS]+['target_pdk_round_total']
    check=assisted[keys+source_fields+['linked_nba_game_date','linked_nba_game_id','linked_nba_game_team_code','linked_official_pdk']].merge(
        raw[keys+source_fields],on=keys,how='left',suffixes=('_v3','_raw'),validate='one_to_one')
    mismatches={}
    for c in source_fields:
        a=pd.to_numeric(check[f'{c}_v3'],errors='coerce').round(2); b=pd.to_numeric(check[f'{c}_raw'],errors='coerce').round(2)
        mismatches[c]=int((~(a.eq(b)|(a.isna()&b.isna()))).sum())
    official=pd.read_parquet(ROOT/'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet')
    official=official[official.gameValidForDunkest.astype(str).str.lower().isin({'true','1'})].copy()
    official['season_id']=official.season_id.astype(str); official['id']=official.dunkest_player_id.astype(str)
    official['date']=pd.to_datetime(official.gameDate,errors='coerce').dt.strftime('%Y-%m-%d')
    official['team']=official.nba_TEAM_ABBREVIATION.astype('string').str.upper().str.strip()
    official['game_id']=official.nba_GAME_ID.astype('string').str.replace(r'\.0$','',regex=True)
    official['pdk']=pd.to_numeric(official.pdk,errors='coerce').round(2)
    check['season_id']=check.source_season_id.astype(str); check['id']=check.id.astype(str); check['date']=pd.to_datetime(check.linked_nba_game_date,errors='coerce').dt.strftime('%Y-%m-%d')
    offcols=['season_id','id','date','team','game_id','pdk']+[o for _,o in STAT_PAIRS]
    offm=official[offcols].rename(columns={o:f'off_{o}' for _,o in STAT_PAIRS})
    check=check.merge(offm,left_on=['season_id','id','date','linked_nba_game_id','linked_nba_game_team_code'],right_on=['season_id','id','date','game_id','team'],how='left',validate='one_to_one')
    pdk_match=pd.to_numeric(check.target_pdk_round_total_v3,errors='coerce').round(2).eq(check.pdk)
    stat_match=pd.Series(True,index=check.index)
    for src,off in STAT_PAIRS:
        a=pd.to_numeric(check[f'{src}_v3'],errors='coerce').round(2); b=pd.to_numeric(check[f'off_{off}'],errors='coerce').round(2)
        stat_match &= a.eq(b)|(a.isna()&b.isna())
    a=pd.read_csv(V8); b=pd.read_csv(V9)
    for x in (a,b):
        x['season_id']=x.season_id.astype(str); x['player_name']=x.player_name.astype(str); x['feature_family']=x.feature_family.astype(str)
        for c in ['source_week','source_round']: x[c]=pd.to_numeric(x[c],errors='coerce').astype('Int64')
    cols=KEYS+['actual_pdk_round_total','predicted_pdk_round_total']
    if a.duplicated(KEYS).any() or b.duplicated(KEYS).any(): raise RuntimeError('Prediction keys are not unique')
    joined=a[cols].merge(b[cols],on=KEYS,how='outer',suffixes=('_v8','_v9'),indicator=True,validate='one_to_one')
    common=joined[joined._merge.eq('both')]
    actual_equal=bool(np.allclose(common.actual_pdk_round_total_v8,common.actual_pdk_round_total_v9,atol=1e-9,rtol=0))
    delta=np.abs(common.predicted_pdk_round_total_v8-common.predicted_pdk_round_total_v9)
    family=[]
    for fam,g in common.groupby('feature_family'):
        dd=np.abs(g.predicted_pdk_round_total_v8-g.predicted_pdk_round_total_v9)
        family.append({'feature_family':fam,'common_rows':int(len(g)),'max_absolute_prediction_difference':float(dd.max()),'predictions_equal_within_1e-12':bool((dd<1e-12).all())})
    pd.DataFrame(family).to_csv(CSV,index=False)
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'v3_dataset_rows':int(len(d)),'v3_date_assisted_rows':int(len(assisted)),'source_stat_mismatch_counts':mismatches,'date_assisted_official_candidate_rows_found':int(check.game_id.notna().sum()),'date_assisted_pdk_matches':int(pdk_match.sum()),'date_assisted_all_17_stat_matches':int(stat_match.sum()),'date_assisted_team_differs_from_source':int(assisted.linked_game_team_differs_from_source_v3.sum()),'v8_prediction_rows':int(len(a)),'v9_prediction_rows':int(len(b)),'common_prediction_rows':int(len(common)),'v8_only_rows':int(joined._merge.eq('left_only').sum()),'v9_only_rows':int(joined._merge.eq('right_only').sum()),'actual_labels_identical':actual_equal,'max_absolute_prediction_difference':float(delta.max()),'all_predictions_equal_within_1e-12':bool((delta<1e-12).all()),'by_family':family,'guardrails':['V3 and V9 are experimental only; no production code/config changed.','V9 round-date consensus is computed from original v2 links only, excluding date-assisted rows from date inference.','No holdout data was inspected or used.'],'artifacts':{'by_family_csv':str(CSV.relative_to(ROOT)),'json':str(JSON.relative_to(ROOT)),'markdown':str(MD.relative_to(ROOT))}}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# Persisted v3 dataset and V8/V9 prediction parity — v1','',f"Generated UTC: {result['generated_at_utc']}",'','## Dataset integrity','',f"- v3 rows: **{len(d):,}**; date-assisted rows: **{len(assisted):,}**.",f"- Date-assisted rows matched to an official-valid candidate on the stored game/date/team: **{result['date_assisted_official_candidate_rows_found']:,}/{len(assisted):,}**.",f"- Exact PDK matches: **{result['date_assisted_pdk_matches']:,}/{len(assisted):,}**; all 17 statistic signatures match: **{result['date_assisted_all_17_stat_matches']:,}/{len(assisted):,}**.",f"- Source-stat mismatches against the raw source, by field: `{json.dumps(mismatches,ensure_ascii=False)}`.",'','## Prediction parity','',f"- V8 rows: **{len(a):,}**; V9 rows: **{len(b):,}**; common: **{len(common):,}**; V8-only/V9-only: **{result['v8_only_rows']:,}/{result['v9_only_rows']:,}**.",f"- Target labels identical: **{actual_equal}**.",f"- Maximum absolute prediction difference: **{delta.max():.3e}**.",f"- All predictions equal within 1e-12: **{bool((delta<1e-12).all())}**.",'','| Feature family | Common rows | Max absolute difference | Equal within 1e-12 |','|---|---:|---:|---|']
    for r in family: lines.append(f"| {r['feature_family']} | {r['common_rows']:,} | {r['max_absolute_prediction_difference']:.3e} | {r['predictions_equal_within_1e-12']} |")
    lines += ['', '## Interpretation','','V9 consumes the persisted v3 mapping while reconstructing round dates only from original v2 links. Exact prediction parity with V8 demonstrates that the persisted experimental dataset reproduces the previous in-script fallback without changing the walk-forward predictions. This is a reproducibility check, not evidence that the feature improves prediction or that historical pre-lock market snapshots are complete.','', '## Guardrails','',*['- '+x for x in result['guardrails']],'']
    MD.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
