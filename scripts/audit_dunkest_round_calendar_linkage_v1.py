#!/usr/bin/env python3
"""Read-only audit of whether archived Dunkest week/round stats can validate gameValidForDunkest."""
from __future__ import annotations
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GAMES = ROOT / 'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
WEEK_DIR = ROOT / 'data/raw/dunkest_history'
WIDE = ROOT / 'data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet'
OUT_JSON = ROOT / 'reports/audit/dunkest_round_calendar_linkage_v1.json'
OUT_MD = ROOT / 'reports/audit/dunkest_round_calendar_linkage_v1.md'


def main() -> None:
    games = pd.read_parquet(GAMES, columns=['season_id','season_label','gameDate','gameValidForDunkest','pdk','dunkest_player_name','nba_match_status'])
    games['gameDate'] = pd.to_datetime(games['gameDate'], errors='coerce')
    seasons = []
    for (sid, label), part in games.groupby(['season_id','season_label'], dropna=False):
        flags = part['gameValidForDunkest'].value_counts(dropna=False)
        seasons.append({
            'season_id': str(sid), 'season_label': str(label), 'game_rows': int(len(part)),
            'date_min': str(part['gameDate'].min().date()) if part['gameDate'].notna().any() else None,
            'date_max': str(part['gameDate'].max().date()) if part['gameDate'].notna().any() else None,
            'valid_true_rows': int(flags.get(True, 0)), 'valid_false_rows': int(flags.get(False, 0)),
            'valid_null_rows': int(part['gameValidForDunkest'].isna().sum()),
            'unique_players': int(part['dunkest_player_name'].nunique()),
            'nba_matched_rows': int((part['nba_match_status'] == 'matched_player_date_opponent').sum()),
        })

    archive_files = sorted(WEEK_DIR.glob('season_*_week_*_round_*_*.parquet'))
    per_season = defaultdict(lambda: {'files': 0, 'rows': 0, 'weeks': set(), 'rounds': set(), 'types': set(), 'date_columns': set(), 'columns': set(), 'sample_files': []})
    file_summaries = []
    date_tokens = ('date','time','timestamp','nba_game_id','game_date','gameid')
    for path in archive_files:
        m = re.match(r'season_(\d+)_week_(\d+)_round_(\d+)_(avg|tot)\.parquet$', path.name)
        if not m:
            continue
        sid, week, rnd, stat_type = m.groups()
        frame = pd.read_parquet(path)
        rec = per_season[sid]
        rec['files'] += 1; rec['rows'] += len(frame); rec['weeks'].add(int(week)); rec['rounds'].add(int(rnd)); rec['types'].add(stat_type)
        rec['columns'].update(frame.columns)
        date_cols = [c for c in frame.columns if any(t in c.lower() for t in date_tokens)]
        rec['date_columns'].update(date_cols)
        if len(rec['sample_files']) < 3:
            rec['sample_files'].append(path.name)
        file_summaries.append({'file': str(path.relative_to(ROOT)), 'season_id': sid, 'week': int(week), 'round': int(rnd), 'type': stat_type, 'rows': int(len(frame)), 'date_columns': date_cols})

    archives = []
    for sid, rec in sorted(per_season.items(), key=lambda kv: int(kv[0])):
        archives.append({
            'season_id': sid, 'files': rec['files'], 'rows': rec['rows'],
            'unique_weeks': len(rec['weeks']), 'week_min': min(rec['weeks']) if rec['weeks'] else None,
            'week_max': max(rec['weeks']) if rec['weeks'] else None,
            'rounds': sorted(rec['rounds']), 'types': sorted(rec['types']),
            'date_columns': sorted(rec['date_columns']), 'sample_files': rec['sample_files'],
            'has_any_date_or_game_id_field': bool(rec['date_columns']),
        })

    wide_info = {'exists': WIDE.exists()}
    if WIDE.exists():
        wide = pd.read_parquet(WIDE)
        wide_info.update({'rows': int(len(wide)), 'season_ids': sorted(wide['source_season_id'].astype(str).unique().tolist()),
                          'date_or_game_id_columns': [c for c in wide.columns if any(t in c.lower() for t in date_tokens)],
                          'has_player_week_round_keys': all(c in wide.columns for c in ['id','source_season_id','source_week','source_round'])})

    payload = {
        'audit': 'dunkest_round_calendar_linkage_v1',
        'purpose': 'Determine whether available historical week/round snapshots independently establish the game-level semantics of gameValidForDunkest.',
        'game_source': str(GAMES.relative_to(ROOT)), 'game_seasons': seasons,
        'weekly_archive_dir': str(WEEK_DIR.relative_to(ROOT)), 'weekly_archives': archives,
        'wide_dataset': wide_info,
        'findings': [
            'The enriched game-level archive has dated game rows and the flag, but these alone do not identify the fantasy-round calendar rule.',
            'Archived week/round parquet files are player aggregates keyed by season/week/round and avg/tot; the inspected schemas contain no game date, timestamp, NBA game ID, or per-game key.',
            'Weekly archive coverage is uneven across seasons; only seasons with files can be compared, and even those files do not directly map a fantasy round to a date interval.',
            'Therefore a direct independent validation of gameValidForDunkest from these archives is not possible without a dated Dunkest round calendar, timestamped snapshot, or another authoritative source linking rounds to games.'
        ],
        'decision': 'Do not infer or relabel the flag from weekly archives. Keep raw gameValidForDunkest and official PDK unchanged; retain the strict official-target policy and existing walk-forward splits.',
        'limitations': ['This is a schema/linkage audit, not proof of the business rule behind the flag.', 'No source files were modified; only this new audit JSON/Markdown and script are written.'],
        'archive_file_count': len(file_summaries),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + '\n')
    lines = [
        '# Dunkest week/round calendar linkage audit v1', '',
        '## Objective',
        'Check whether the archived historical Dunkest weekly/round tables can independently validate the game-level `gameValidForDunkest` flag.', '',
        '## Game-level archive by season', '',
        '| Season | Rows | Date range | Flag true | Flag false | NBA matched |',
        '|---|---:|---|---:|---:|---:|'
    ]
    for s in seasons:
        lines.append(f"| {s['season_label']} (ID {s['season_id']}) | {s['game_rows']:,} | {s['date_min']} – {s['date_max']} | {s['valid_true_rows']:,} | {s['valid_false_rows']:,} | {s['nba_matched_rows']:,} |")
    lines += ['', '## Weekly archive coverage', '', '| Season ID | Files | Rows | Weeks | Rounds | Date/game-ID columns |', '|---:|---:|---:|---:|---|---|']
    for a in archives:
        lines.append(f"| {a['season_id']} | {a['files']} | {a['rows']:,} | {a['week_min']}–{a['week_max']} ({a['unique_weeks']} distinct) | {', '.join(map(str,a['rounds']))} | {', '.join(a['date_columns']) or 'none'} |")
    lines += ['', '## Findings', ''] + [f'- {x}' for x in payload['findings']]
    lines += ['', '## Decision', '', payload['decision'], '', '## Guardrails', '', '- No changes to raw game data, PDK values, training targets, production model, validation splits, or walk-forward settings.', '- No commit, revert, or overwrite of existing artifacts.', '- Full machine-readable inventory: `reports/audit/dunkest_round_calendar_linkage_v1.json`.', '']
    OUT_MD.write_text('\n'.join(lines))
    print(f'Wrote {OUT_JSON.relative_to(ROOT)}')
    print(f'Wrote {OUT_MD.relative_to(ROOT)}')
    print(f'Game seasons: {len(seasons)}; weekly archive files inspected: {len(file_summaries)}')
    print('Archive coverage:')
    for a in archives:
        print(f"  season {a['season_id']}: files={a['files']}, rows={a['rows']}, weeks={a['unique_weeks']}, date/game-id fields={a['date_columns']}")
    print('Decision: no independently dated mapping; flag semantics remain unverified.')

if __name__ == '__main__':
    main()
