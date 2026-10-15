#!/usr/bin/env python3
"""Build a separate audit-only derivative of historical weekly-round tables.

Raw Parquets are never edited. Confirmed contaminated scopes are omitted from
this derivative; all other scopes are retained with explicit review metadata.
This artifact is NOT certified for training or as a per-game target source.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/dunkest_history_v2'
PROCESSED = ROOT / 'data/processed'
REPORTS = ROOT / 'reports/audit'
STEM = 'dunkest_week_round_audit_derivative_v1'
DERIVATIVE = PROCESSED / f'{STEM}.parquet'
MANIFEST_JSON = REPORTS / f'{STEM}.json'
MANIFEST_MD = REPORTS / f'{STEM}.md'
MANIFEST_CSV = REPORTS / f'{STEM}_files.csv'


def main() -> None:
    for p in (DERIVATIVE, MANIFEST_JSON, MANIFEST_MD, MANIFEST_CSV):
        if p.exists(): raise SystemExit(f'Refusing to overwrite existing output: {p}')
    qpath = REPORTS / 'dunkest_week_round_quarantine_manifest_v2.json'
    exact_path = REPORTS / 'dunkest_week_round_boxscore_signature_corroboration_v1.csv'
    if not qpath.exists() or not exact_path.exists():
        raise SystemExit('Required v2 quarantine manifest or exact-signature audit is missing.')
    q = json.loads(qpath.read_text(encoding='utf-8'))
    quarantine = set(q.get('confirmed_quarantine_files', []))
    file_status = {x['source_file']: x['evidence_status'] for x in q['manifest_rows']}
    exact = pd.read_csv(exact_path, dtype={'table_season_id': str, 'nba_game_id': str})
    exact = exact[exact['cluster_status'].eq('isolated_exact_boxscore_signature_candidate')]
    row_candidates = {}
    for _, r in exact.iterrows():
        for field in ('source_file_avg', 'source_file_tot'):
            source = 'data/raw/dunkest_history_v2/' + str(r[field])
            row_candidates.setdefault(source, set()).add(str(r['player_name']).casefold().strip())
    paths = sorted(RAW.glob('season_*_week_*_round_*_*.parquet'))
    if not paths: raise SystemExit(f'No source Parquets found under {RAW}')
    included=[]; file_rows=[]; excluded=[]
    for path in paths:
        rel=path.relative_to(ROOT).as_posix()
        try: rows=len(pd.read_parquet(path, columns=['id']))
        except Exception as e: raise RuntimeError(f'Cannot inspect {rel}: {e}') from e
        status=file_status.get(rel, 'not_flagged_by_current_scan_not_certified')
        if rel in quarantine:
            excluded.append({'source_file':rel,'source_rows':rows,'status':'confirmed_cross_season_contamination_quarantine','reason':'15-player PHI-MIN cluster from NBA season 2021-22 found in a source scope labelled season ID 5 / expected 2020-21'})
            file_rows.append({'source_file':rel,'source_rows':rows,'included_in_derivative':False,'source_audit_status':status,'exact_signature_candidate_players':'','action':'Excluded from this audit-only derivative pending source reconciliation'})
            continue
        df=pd.read_parquet(path).copy()
        names=(df['player_name'].astype(str).str.casefold().str.strip() if 'player_name' in df else pd.Series('',index=df.index))
        candidate_names=row_candidates.get(rel,set())
        df['source_file_audit']=rel
        df['source_audit_status']=status
        df['row_exact_full_boxscore_candidate']=names.isin(candidate_names)
        df['row_exact_candidate_player']=names.where(names.isin(candidate_names), '')
        df['audit_only_not_certified']=True
        df['eligible_for_training_from_this_derivative']=False
        included.append(df)
        file_rows.append({'source_file':rel,'source_rows':rows,'included_in_derivative':True,'source_audit_status':status,'exact_signature_candidate_players':'; '.join(sorted(candidate_names)),'action':'Retained with audit metadata; not certified for training'})
    if not included: raise SystemExit('No source files remain for derivative.')
    combined=pd.concat(included,ignore_index=True,sort=False)
    PROCESSED.mkdir(parents=True,exist_ok=True); REPORTS.mkdir(parents=True,exist_ok=True)
    combined.to_parquet(DERIVATIVE,index=False)
    file_manifest=pd.DataFrame(file_rows)
    file_manifest.to_csv(MANIFEST_CSV,index=False)
    summary={
      'generated_utc':datetime.now(timezone.utc).isoformat(),
      'artifact_type':'audit-only derivative; not a certified clean dataset',
      'source_directory':RAW.relative_to(ROOT).as_posix(),
      'derivative_path':DERIVATIVE.relative_to(ROOT).as_posix(),
      'file_manifest_csv':MANIFEST_CSV.relative_to(ROOT).as_posix(),
      'source_files_found':len(paths),'source_files_included':len(included),'source_files_excluded_confirmed_quarantine':len(excluded),
      'source_rows_excluded':sum(x['source_rows'] for x in excluded),'derivative_rows':int(len(combined)),
      'source_bytes_read':sum(x.stat().st_size for x in paths),'derivative_bytes':DERIVATIVE.stat().st_size,
      'source_status_counts':file_manifest['source_audit_status'].value_counts().to_dict(),
      'exact_isolated_signature_candidates':len(exact),'exact_candidate_rows_flagged_in_derivative':int(combined['row_exact_full_boxscore_candidate'].sum()),
      'confirmed_quarantine_files':sorted(quarantine),'excluded_source_scopes':excluded,
      'rules':['No raw file was changed.','Only the two confirmed season-5/week-43/round-2 avg/tot files are excluded.','All other files are retained with source path and audit status.','Four isolated exact-signature candidates are row-flagged in both avg/tot where present; their files are not excluded.','Every row is explicitly marked audit_only_not_certified=True and eligible_for_training_from_this_derivative=False.','Absence from current candidate scans is not evidence of clean season scope.'],
      'not_for':['training','official target construction','backtest labels','production use'],
      'source_manifest':'reports/audit/dunkest_week_round_quarantine_manifest_v2.json'
    }
    MANIFEST_JSON.write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    lines=['# Weekly-round audit derivative (v1)','',f"Generated UTC: {summary['generated_utc']}",'','## Purpose','', 'This is an audit-only derivative with provenance and review flags. It is not a certified clean dataset, official per-game target table, or training input.','', '## Build summary','',f"- Source files discovered: **{len(paths)}**",f"- Files retained: **{len(included)}**",f"- Confirmed contaminated files excluded: **{len(excluded)}**",f"- Rows excluded with those files: **{summary['source_rows_excluded']}**",f"- Rows in derivative: **{len(combined)}**",f"- Isolated exact-signature candidate rows flagged: **{summary['exact_candidate_rows_flagged_in_derivative']}**",'', '## Excluded scopes','']
    for x in excluded: lines.append(f"- `{x['source_file']}` — {x['source_rows']} rows; confirmed PHI–MIN cross-season cluster.")
    lines += ['', '## Metadata added','', '- `source_file_audit`: original relative source path.', '- `source_audit_status`: confirmed scope review status or `not_flagged_by_current_scan_not_certified`.', '- `row_exact_full_boxscore_candidate` and `row_exact_candidate_player`: row-level flags for the four isolated exact-signature candidates.', '- `audit_only_not_certified=True` and `eligible_for_training_from_this_derivative=False`: explicit safety guards.', '', '## Important limitations','', 'The remaining rows are not certified as correctly season-scoped. The endpoint root cause is unresolved, and current scans may miss other contaminated rows. Do not use this derivative for training, target construction, backtests, or production. The raw archive is unchanged.', '', f"Parquet: `{DERIVATIVE.relative_to(ROOT)}`",f"JSON: `{MANIFEST_JSON.relative_to(ROOT)}`",f"File manifest CSV: `{MANIFEST_CSV.relative_to(ROOT)}`",'']
    MANIFEST_MD.write_text('\n'.join(lines),encoding='utf-8')
    # Re-open the written parquet and assert the explicit safety flags survived serialization.
    check=pd.read_parquet(DERIVATIVE,columns=['audit_only_not_certified','eligible_for_training_from_this_derivative','row_exact_full_boxscore_candidate'])
    assert len(check)==len(combined) and check['audit_only_not_certified'].all() and (~check['eligible_for_training_from_this_derivative']).all()
    assert int(check['row_exact_full_boxscore_candidate'].sum())==summary['exact_candidate_rows_flagged_in_derivative']
    print('Derivative:',DERIVATIVE)
    print('Rows:',len(combined),'included files:',len(included),'excluded files:',len(excluded))
    print('Flagged singleton candidate rows:',summary['exact_candidate_rows_flagged_in_derivative'])
    print('Status counts:',summary['source_status_counts'])
    print('Safety assertions: PASS')

if __name__=='__main__': main()
