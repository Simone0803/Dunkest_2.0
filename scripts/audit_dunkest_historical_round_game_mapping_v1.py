#!/usr/bin/env python3
"""Audit week-round -> NBA game linkage using full boxscore signatures.

Read-only on source datasets. This is an audit of observed row-level linkage, not
an official calendar reconstruction and not a training/backtest data builder.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from dunkest.names import player_key

ROOT = Path(__file__).resolve().parents[1]
STATS = ROOT / 'data/processed/dunkest_historical_stats_2020-25_v2.parquet'
OFFICIAL = ROOT / 'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
OUT = ROOT / 'reports/audit'
STEM = 'dunkest_historical_round_game_mapping_20261013_v1'
ROW_CSV = OUT / f'{STEM}_rows.csv'
ROUND_CSV = OUT / f'{STEM}_rounds.csv'
JSON_OUT = OUT / f'{STEM}.json'
MD_OUT = OUT / f'{STEM}.md'
STAT_PAIRS = [
    ('pts','pts'), ('reb','reb'), ('ast','ast'), ('stl','stl'), ('blk','blk'),
    ('blka','blka'), ('fgm','fgm'), ('fga','fga'), ('tpm','tpm'), ('tpa','tpa'),
    ('ftm','ftm'), ('fta','fta'), ('oreb','oreb'), ('dreb','dreb'), ('tov','tov'),
    ('pf','pf'), ('plus_minus','plusMinus'),
]

def main() -> None:
    for p in (ROW_CSV, ROUND_CSV, JSON_OUT, MD_OUT):
        if p.exists():
            raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    wide = pd.read_parquet(STATS)
    wide = wide.loc[wide['source_stats_type'].astype(str).eq('tot')].copy()
    wide['season_id'] = wide['source_season_id'].astype(str)
    wide['source_week'] = pd.to_numeric(wide['source_week'], errors='coerce').astype('Int64')
    wide['source_round'] = pd.to_numeric(wide['source_round'], errors='coerce').astype('Int64')
    wide['player_key'] = wide['player_name'].astype(str).map(player_key)
    wide['team'] = wide['team_code'].astype(str).str.upper().str.strip()
    wide['pdk_key'] = pd.to_numeric(wide['pdk'], errors='coerce').round(2)
    wide['gp_num'] = pd.to_numeric(wide['gp'], errors='coerce')
    wide['row_id'] = np.arange(len(wide), dtype=int)

    official = pd.read_parquet(OFFICIAL)
    official['season_id'] = official['season_id'].astype(str)
    official['player_key'] = official['dunkest_player_name'].astype(str).map(player_key)
    official['team'] = official['nba_TEAM_ABBREVIATION'].astype(str).str.upper().str.strip()
    official['pdk_key'] = pd.to_numeric(official['pdk'], errors='coerce').round(2)
    official['game_date'] = pd.to_datetime(official['gameDate'], errors='coerce').dt.strftime('%Y-%m-%d')
    official['game_id_norm'] = official['gameId'].astype(str).str.replace(r'\.0$', '', regex=True)
    official['valid_flag'] = official['gameValidForDunkest'].astype(str)
    for left, right in STAT_PAIRS:
        wide[left + '_sig'] = pd.to_numeric(wide[left], errors='coerce').round(2)
        official[right + '_sig'] = pd.to_numeric(official[right], errors='coerce').round(2)

    # A week-round total with gp>1 is an aggregate and cannot be linked to one NBA game.
    eligible = wide.loc[wide['gp_num'].eq(1)].copy()
    left_keys = ['season_id','player_key','team','pdk_key'] + [a + '_sig' for a, _ in STAT_PAIRS]
    right_keys = ['season_id','player_key','team','pdk_key'] + [b + '_sig' for _, b in STAT_PAIRS]
    right_cols = right_keys + ['game_date','game_id_norm','valid_flag','opponentTeamCode','nba_MATCHUP']
    merged = eligible.merge(official[right_cols].drop_duplicates(), left_on=left_keys, right_on=right_keys, how='left', validate='many_to_many')
    per_row = merged.groupby('row_id', dropna=False).agg(
        exact_candidate_dates=('game_date','nunique'),
        exact_candidate_games=('game_id_norm','nunique'),
        exact_candidate_flags=('valid_flag', lambda s: s.dropna().nunique()),
    )
    row_audit = eligible[['row_id','season_id','source_week','source_round','id','player_name','team','gp_num','pdk','min','pts','reb','ast','stl','blk','tov','plus_minus']].merge(per_row, left_on='row_id', right_index=True, how='left')
    row_audit[['exact_candidate_dates','exact_candidate_games','exact_candidate_flags']] = row_audit[['exact_candidate_dates','exact_candidate_games','exact_candidate_flags']].fillna(0).astype(int)
    row_audit['link_status'] = np.select(
        [row_audit['exact_candidate_dates'].eq(1), row_audit['exact_candidate_dates'].gt(1)],
        ['unique_full_boxscore_signature', 'ambiguous_full_boxscore_signature'], default='no_full_boxscore_signature_match')
    unique_rows = merged.loc[merged['row_id'].isin(row_audit.loc[row_audit['link_status'].eq('unique_full_boxscore_signature'),'row_id']) & merged['game_date'].notna()].drop_duplicates(['row_id','game_date'])
    # Preserve one row per source row/date; any repeated same-date game records remain visible in counts.
    date_by_row = unique_rows[['row_id','game_date','game_id_norm','valid_flag','opponentTeamCode','nba_MATCHUP']].drop_duplicates(['row_id','game_date'])
    row_audit = row_audit.merge(date_by_row[['row_id','game_date','game_id_norm','valid_flag','opponentTeamCode','nba_MATCHUP']], on='row_id', how='left', validate='one_to_one')
    row_audit.to_csv(ROW_CSV, index=False)

    round_rows = []
    for (sid, week, rnd), source_group in wide.groupby(['season_id','source_week','source_round'], dropna=False):
        ids = set(source_group.loc[pd.to_numeric(source_group['gp'], errors='coerce').eq(1), 'row_id'].astype(int))
        rg = row_audit.loc[row_audit['row_id'].isin(ids)].copy()
        linked = rg.loc[rg['link_status'].eq('unique_full_boxscore_signature') & rg['game_date'].notna()].copy()
        dates = linked['game_date'].value_counts()
        mapped_date = str(dates.index[0]) if not dates.empty else ''
        date_span = int((pd.to_datetime(dates.index.max()) - pd.to_datetime(dates.index.min())).days) if len(dates) > 1 else 0
        flags = linked['valid_flag'].astype(str).str.lower()
        source_teams = sorted(source_group['team'].dropna().astype(str).unique().tolist())
        linked_teams = sorted(linked['team'].dropna().astype(str).unique().tolist())
        true_teams = sorted(linked.loc[flags.isin(['true','1']), 'team'].dropna().astype(str).unique().tolist())
        false_teams = sorted(linked.loc[flags.isin(['false','0']), 'team'].dropna().astype(str).unique().tolist())
        round_rows.append({
            'season_id': str(sid), 'source_week': int(week), 'source_round': int(rnd),
            'source_rows': int(len(source_group)), 'source_gp1_rows': int(len(rg)),
            'source_gp_gt1_rows': int((pd.to_numeric(source_group['gp'], errors='coerce') > 1).sum()),
            'unique_signature_rows': int(rg['link_status'].eq('unique_full_boxscore_signature').sum()),
            'ambiguous_signature_rows': int(rg['link_status'].eq('ambiguous_full_boxscore_signature').sum()),
            'unmatched_signature_rows': int(rg['link_status'].eq('no_full_boxscore_signature_match').sum()),
            'unique_signature_coverage': float(rg['link_status'].eq('unique_full_boxscore_signature').mean()) if len(rg) else np.nan,
            'unique_mapped_dates': int(len(dates)), 'dominant_mapped_date': mapped_date,
            'dominant_date_share_of_linked_rows': float(dates.iloc[0] / len(linked)) if len(linked) else np.nan,
            'mapped_date_span_days': date_span, 'source_team_count': len(source_teams),
            'mapped_team_count': len(linked_teams), 'valid_true_rows': int(flags.isin(['true','1']).sum()),
            'valid_false_rows': int(flags.isin(['false','0']).sum()),
            'valid_true_team_count': len(true_teams), 'valid_false_team_count': len(false_teams),
            'source_teams': ';'.join(source_teams), 'mapped_teams': ';'.join(linked_teams),
            'valid_true_teams': ';'.join(true_teams), 'valid_false_teams': ';'.join(false_teams),
        })
    rounds = pd.DataFrame(round_rows).sort_values(['season_id','source_week','source_round'])
    rounds.to_csv(ROUND_CSV, index=False)

    linked_all = row_audit['link_status'].eq('unique_full_boxscore_signature')
    flag_counts = row_audit.loc[linked_all,'valid_flag'].astype(str).value_counts().to_dict()
    status_counts = row_audit['link_status'].value_counts().to_dict()
    round_date_counts = rounds['unique_mapped_dates'].value_counts().sort_index().to_dict()
    example = rounds.loc[rounds['season_id'].eq('9') & rounds['source_week'].eq(22) & rounds['source_round'].eq(3)]
    example_record = example.iloc[0].to_dict() if not example.empty else {}
    season_summary = row_audit.groupby('season_id').agg(
        rows=('row_id','size'), unique_links=('link_status',lambda s:int(s.eq('unique_full_boxscore_signature').sum())),
        ambiguous=('link_status',lambda s:int(s.eq('ambiguous_full_boxscore_signature').sum())),
        unmatched=('link_status',lambda s:int(s.eq('no_full_boxscore_signature_match').sum())),
    ).reset_index().to_dict('records')
    report = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_week_round_rows': int(len(wide)), 'gp1_rows_audited': int(len(row_audit)),
        'full_signature_status_counts': {str(k):int(v) for k,v in status_counts.items()},
        'mapped_flag_counts': {str(k):int(v) for k,v in flag_counts.items()},
        'round_count': int(len(rounds)), 'rounds_with_one_mapped_date': int(rounds['unique_mapped_dates'].eq(1).sum()),
        'rounds_with_multiple_mapped_dates': int(rounds['unique_mapped_dates'].gt(1).sum()),
        'round_mapped_date_count_distribution': {str(k):int(v) for k,v in round_date_counts.items()},
        'median_unique_signature_coverage_per_round': float(rounds['unique_signature_coverage'].median()),
        'median_mapped_team_count': float(rounds['mapped_team_count'].median()),
        'example_season9_week22_round3': example_record,
        'by_season': season_summary,
        'method': 'A source weekly-round tot row is linked to the official per-player game archive only when season, canonical player, NBA team, PDK (2 decimals), and 17 boxscore statistics match. Only gp=1 rows are eligible for a single-game link. The validity flag is recorded as observed; this audit does not infer or redefine its official semantics.',
        'interpretation': [
            'Full boxscore signatures are substantially more specific than PDK-only date joins, which can map the same score to multiple dates and inject unrelated teams into a round matchup map.',
            'A unique game link is evidence that a weekly row resembles a specific NBA boxscore, not proof that the archive contains the full eligible market or that every missing row is a zero.',
            'A source round may have a clean dominant date but only a subset of teams/player rows. These tables are outcome archives, not complete pre-lock candidate snapshots.',
            'Do not automatically repair, remove, relabel, or train on unmatched rows based on this audit. Do not change production model, official labels, or the frozen 2026/27 GW1 holdout.'
        ],
        'artifacts': {'rows_csv':str(ROW_CSV.relative_to(ROOT)),'rounds_csv':str(ROUND_CSV.relative_to(ROOT)),'json':str(JSON_OUT.relative_to(ROOT)),'markdown':str(MD_OUT.relative_to(ROOT))},
        'production_changed': False,
    }
    JSON_OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str)+'\n', encoding='utf-8')
    lines = [
        '# Historical Dunkest round-to-game mapping audit — v1','',
        f"Generated UTC: {report['generated_at_utc']}",'',
        '## Method','',
        'For rows with `gp=1`, this audit matches the historical `tot` table to the official player-game archive on season, canonical player identity, NBA team, PDK rounded to two decimals, and 17 boxscore fields. PDK-only joins are not used as final evidence. Source data and labels are read-only.','',
        '## Coverage','',
        f"- Source weekly-round rows inspected: **{len(wide):,}**.",
        f"- Rows with `gp=1` audited: **{len(row_audit):,}**.",
        f"- Unique full-signature matches: **{status_counts.get('unique_full_boxscore_signature',0):,} ({status_counts.get('unique_full_boxscore_signature',0)/max(1,len(row_audit)):.1%})**.",
        f"- Ambiguous signatures: **{status_counts.get('ambiguous_full_boxscore_signature',0):,}**.",
        f"- No full-signature match: **{status_counts.get('no_full_boxscore_signature_match',0):,}**.",
        f"- Week-rounds: **{len(rounds)}**; one mapped date in **{report['rounds_with_one_mapped_date']}**, multiple mapped dates in **{report['rounds_with_multiple_mapped_dates']}**.",
        f"- Median unique-signature coverage per round: **{report['median_unique_signature_coverage_per_round']:.1%}**; median mapped team count: **{report['median_mapped_team_count']:.0f}**.",'',
        '## Example: season 9, week 22, round 3 (2022-12-13)','',
        f"- Source rows: **{example_record.get('source_rows','n/a')}**; unique full-signature matches: **{example_record.get('unique_signature_rows','n/a')}**; unmatched rows: **{example_record.get('unmatched_signature_rows','n/a')}**.",
        f"- Teams in source table: `{example_record.get('source_teams','')}`.",
        f"- Teams represented by unique signature matches: `{example_record.get('mapped_teams','')}`.",
        f"- Teams with observed `gameValidForDunkest=True` among linked rows: `{example_record.get('valid_true_teams','')}`.",'',
        'This explains why a PDK-only target-date join can make the optimizer see a team (for example, a team whose source row does not match that date’s boxscore) while omitting other teams: the outcome table is not a full pre-lock market snapshot. It does not establish why any individual unmatched row is absent or whether it should be relabelled.','',
        '## Findings','',*[f'- {x}' for x in report['interpretation']], '',
        '## Decision and guardrails','',
        '- Keep the historical weekly tables as outcome archives; do not use them alone to claim complete pre-lock market coverage.',
        '- Keep the production team cap, prediction model, official PDK values, and temporal splits unchanged.',
        '- Do not inspect or tune against the frozen prospective 2026/27 GW1 holdout before its cutoff.',
        '- No source data, production code/config, or existing versioned artifact was modified by this audit.','',
        '## Artifacts','',f"- Row-level audit: `{ROW_CSV.relative_to(ROOT)}`",f"- Round summary: `{ROUND_CSV.relative_to(ROOT)}`",f"- JSON: `{JSON_OUT.relative_to(ROOT)}`",'']
    MD_OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['gp1_rows_audited','full_signature_status_counts','mapped_flag_counts','round_count','rounds_with_one_mapped_date','rounds_with_multiple_mapped_dates','median_unique_signature_coverage_per_round','median_mapped_team_count','example_season9_week22_round3','artifacts']}, indent=2, default=str))

if __name__ == '__main__':
    main()
