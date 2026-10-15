#!/usr/bin/env python3
"""Cross-check Dunkest's published valid/invalid game rule against archived game-level flags."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
OUT_JSON = ROOT / 'reports/audit/dunkest_validity_flag_official_source_v1.json'
OUT_MD = ROOT / 'reports/audit/dunkest_validity_flag_official_source_v1.md'
SOURCES = [
    {
        'title': 'Calendario Dunkest NBA: squadre a riposo e punteggi medi',
        'url': 'https://www.dunkest.com/it/nba/notizie/fantabasket/18229/calendario-dunkest-nba-squadre-valide-punteggi-medi',
        'published': '2025-09-25',
        'evidence': 'La giornata fantasy NBA può durare più giorni; se una squadra ricompare nella stessa giornata, conta una sola partita e non necessariamente la prima in ordine cronologico. La squadra non valida non prende punteggio. L’articolo dichiara che il calendario completo è disponibile nella sezione Calendario dell’app.',
    },
    {
        'title': 'Calendario Dunkest: la Giornata e i Turni di Gioco',
        'url': 'https://www.dunkest.com/it/notizie/fantabasket/8774/calendario-dunkest-cosa-sono-giornata-turni',
        'published': 'official Dunkest guide; page crawled 2026-10-12',
        'evidence': 'Conferma che le giornate NBA Dunkest coprono un numero variabile di giorni e che, se una squadra compare più volte, soltanto una partita attribuisce punti.',
    },
]

def main() -> None:
    cols = ['season_id','season_label','gameId','gameDate','gameValidForDunkest','pdk','dunkest_player_id','nba_TEAM_ABBREVIATION','nba_match_status']
    df = pd.read_parquet(SOURCE, columns=cols)
    matched = df[df['nba_match_status'].eq('matched_player_date_opponent')].copy()
    keys = ['season_id','season_label','gameId','gameDate','nba_TEAM_ABBREVIATION']
    team_games = matched.groupby(keys, dropna=False).agg(
        flag_n=('gameValidForDunkest','nunique'),
        flag=('gameValidForDunkest','first'),
        player_rows=('dunkest_player_id','size'),
        players=('dunkest_player_id','nunique'),
        pdk_nonnull_rows=('pdk','count'),
    ).reset_index()
    seasons = []
    for (sid,label), g in team_games.groupby(['season_id','season_label'], dropna=False):
        flags = g['flag'].value_counts(dropna=False)
        source_rows = matched[(matched['season_id'].astype(str)==str(sid))]
        seasons.append({
            'season_id': str(sid), 'season_label': str(label),
            'team_games': int(len(g)), 'true_team_games': int(flags.get(True,0)),
            'false_team_games': int(flags.get(False,0)), 'null_team_games': int(g['flag'].isna().sum()),
            'team_games_with_mixed_player_flags': int((g['flag_n'] > 1).sum()),
            'player_rows': int(len(source_rows)),
            'false_flag_player_rows_with_pdk': int(source_rows.loc[source_rows['gameValidForDunkest'].eq(False),'pdk'].notna().sum()),
            'false_flag_player_rows': int(source_rows['gameValidForDunkest'].eq(False).sum()),
        })
    payload = {
        'audit': 'dunkest_validity_flag_official_source_v1',
        'source_dataset': str(SOURCE.relative_to(ROOT)),
        'official_sources': SOURCES,
        'method': 'Count distinct season/game/date/team records using only rows matched to NBA player/date/opponent; then check whether player rows within each team-game disagree on the flag and whether PDK remains populated for false-flag rows.',
        'season_results': seasons,
        'interpretation': [
            'Official Dunkest documentation establishes the intended product rule: a team can have multiple NBA games in one Dunkest fantasy matchday, but only one game is eligible to contribute points; the eligible game is not necessarily the first chronologically.',
            'For seasons 2020/21 through 2024/25, archived game-level flags are consistent across players within every matched team-game, and false-flag player rows still have PDK values. This is consistent with false meaning “this NBA game does not count for Dunkest scoring,” not “the score is missing or zero.”',
            'For seasons 2018/19 and 2019/20, every archived flag is false. This is inconsistent with using the field as a reliable valid/invalid discriminator in those seasons; treat it as legacy/unverified rather than evidence that every game was excluded.',
            'The documentation explains the rule but does not publish a downloadable historical round-to-date mapping. Therefore it validates the conceptual meaning, not a complete row-by-row reconstruction of historical fantasy rounds.',
        ],
        'decision': 'Keep the raw flag and official PDK unchanged. Continue strict training only on gameValidForDunkest=True for seasons where the flag is populated with both true and false values and the existing audit policy permits use (2020/21 onward). Do not reinterpret 2018/19 or 2019/20 as valid targets without independent historical evidence.',
        'guardrails': ['No raw data, target, model, split, or backtest files modified.', 'No reconstructed proxy substituted for official PDK.', 'This audit does not establish historical round boundaries or exception handling for postponed games.'],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    lines = [
        '# Dunkest official validity rule and historical flag audit v1', '',
        '## Official sources', '',
        f"1. [{SOURCES[0]['title']}]({SOURCES[0]['url']}) — {SOURCES[0]['evidence']}",
        f"2. [{SOURCES[1]['title']}]({SOURCES[1]['url']}) — {SOURCES[1]['evidence']}", '',
        '## Archived flag consistency', '',
        '| Season | Team-games | True | False | Mixed flags within team-game | False-flag player rows with PDK / total false rows |',
        '|---|---:|---:|---:|---:|---:|'
    ]
    for s in seasons:
        lines.append(f"| {s['season_label']} (ID {s['season_id']}) | {s['team_games']:,} | {s['true_team_games']:,} | {s['false_team_games']:,} | {s['team_games_with_mixed_player_flags']:,} | {s['false_flag_player_rows_with_pdk']:,} / {s['false_flag_player_rows']:,} |")
    lines += ['', '## Interpretation', ''] + [f'- {x}' for x in payload['interpretation']]
    lines += ['', '## Decision and safeguards', '', payload['decision'], ''] + [f'- {x}' for x in payload['guardrails']] + ['', '']
    OUT_MD.write_text('\n'.join(lines))
    print(f'Wrote {OUT_JSON.relative_to(ROOT)}')
    print(f'Wrote {OUT_MD.relative_to(ROOT)}')
    for s in seasons:
        print(f"{s['season_label']}: team-games={s['team_games']}, true={s['true_team_games']}, false={s['false_team_games']}, mixed={s['team_games_with_mixed_player_flags']}, false rows with PDK={s['false_flag_player_rows_with_pdk']}/{s['false_flag_player_rows']}")

if __name__ == '__main__':
    main()
