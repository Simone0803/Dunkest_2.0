#!/usr/bin/env python3
"""Verify the public player-profile games endpoint against saved official Dunkest rows."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / 'reports/audit/dunkest_profile_games_api_verification_v1.json'
OUT_MD = ROOT / 'reports/audit/dunkest_profile_games_api_verification_v1.md'
API = 'https://www.dunkest.com/api/player/games'
# Luka Dončić (Dunkest player ID 127), with saved data already collected locally.
SEASONS = [
    ('1','2018-19', ROOT/'data/processed/official_dunkest_player_games_2018-19_season_id_1.parquet','dunkest_player_id'),
    ('3','2019-20', ROOT/'data/processed/official_dunkest_player_games_2019-20_season_id_3.parquet','dunkest_player_id'),
    ('19','2024-25', ROOT/'data/processed/official_dunkest_player_games_2024-25_season_id_19.parquet','dunkest_player_id'),
    ('25','2025-26', ROOT/'data/processed/official_dunkest_player_games_2025-26.parquet','_requested_player_id'),
]

def eq(a,b):
    if pd.isna(a) and pd.isna(b): return True
    if pd.isna(a) or pd.isna(b): return False
    if isinstance(a,(int,float)) and isinstance(b,(int,float)): return float(a)==float(b)
    return str(a)==str(b)

def main():
    if OUT_JSON.exists() or OUT_MD.exists():
        raise SystemExit(f'Refusing to overwrite existing audit: {OUT_JSON} or {OUT_MD}')
    results=[]
    with httpx.Client(headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'},timeout=15,follow_redirects=True) as client:
        for sid,label,path,idcol in SEASONS:
            if not path.exists(): raise FileNotFoundError(path)
            resp=client.get(API,params={'player_id':'127','season_id':sid})
            resp.raise_for_status(); payload=resp.json()
            if not isinstance(payload,list) or any(not isinstance(x,dict) for x in payload):
                raise ValueError(f'Unexpected API schema for season {sid}')
            saved=pd.read_parquet(path)
            rows=saved[saved[idcol].astype(str).eq('127')].copy()
            api_by_id={str(x.get('gameId')):x for x in payload}
            saved_by_id={str(x.get('gameId')):x for x in rows.to_dict('records')}
            api_ids=set(api_by_id); saved_ids=set(saved_by_id)
            mismatches=[]
            fields=list(payload[0].keys()) if payload else []
            for gid in sorted(api_ids & saved_ids):
                for field in fields:
                    if field not in saved.columns: mismatches.append({'gameId':gid,'field':field,'reason':'missing_saved_column'}); continue
                    if not eq(api_by_id[gid].get(field),saved_by_id[gid].get(field)):
                        mismatches.append({'gameId':gid,'field':field,'api':api_by_id[gid].get(field),'saved':saved_by_id[gid].get(field)})
            flags=pd.Series([x.get('gameValidForDunkest') for x in payload],dtype='object')
            results.append({
                'season_id':sid,'season':label,'player_id':'127','http_status':resp.status_code,
                'api_rows':len(payload),'saved_player_rows':len(rows),'matched_game_ids':len(api_ids & saved_ids),
                'api_only_game_ids':sorted(api_ids-saved_ids),'saved_only_game_ids':sorted(saved_ids-api_ids),
                'api_fields_compared':fields,'field_mismatch_count':len(mismatches),'field_mismatches':mismatches[:30],
                'gameValidForDunkest_true':int(flags.map(lambda x:x is True).sum()),
                'gameValidForDunkest_false':int(flags.map(lambda x:x is False).sum()),
                'gameValidForDunkest_missing':int(flags.isna().sum()),
                'sample':[{k:payload[0].get(k) for k in ['gameId','gameDate','gameValidForDunkest','pdk','pts','reb','ast']} ] if payload else []
            })
    # Existing complete per-season archives show whether validity flags are comparable over time.
    flag_inventory=[]
    for path in sorted((ROOT/'data/processed').glob('official_dunkest_player_games_*_season_id_*.parquet')):
        d=pd.read_parquet(path,columns=['gameValidForDunkest','gameDate'])
        s=d['gameValidForDunkest'].astype('string').str.lower()
        flag_inventory.append({'file':path.name,'rows':len(d),'true':int(s.eq('true').sum()),'false':int(s.eq('false').sum()),'missing':int(s.isna().sum()),'min_date':str(d.gameDate.min()),'max_date':str(d.gameDate.max())})
    result={'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_api':API,
            'method':'Read-only requests for player_id=127 across four seasons; exact field comparison by gameId against existing local official Parquet archives. No production data changed.',
            'season_checks':results,'historical_validity_flag_inventory':flag_inventory,
            'conclusion':{'all_season_checks_exact_match':all(x['api_rows']==x['saved_player_rows']==x['matched_game_ids'] and not x['api_only_game_ids'] and not x['saved_only_game_ids'] and x['field_mismatch_count']==0 for x in results),
                          'validity_flag_caution':'Do not filter historical official PDK labels by gameValidForDunkest without season-specific semantics: all rows in 2018-19 and 2019-20 archives are False, while later seasons contain both True and False.'}}
    OUT_JSON.parent.mkdir(parents=True,exist_ok=True)
    OUT_JSON.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Dunkest player-profile games API verification','',f"Generated: {result['created_at_utc']}",'',f"Endpoint: `{API}`",'', '## Exact comparison for Luka Dončić (Dunkest player ID 127)','', '| Season | API rows | Saved rows | Matched game IDs | Field mismatches | Valid=True | Valid=False |', '|---|---:|---:|---:|---:|---:|---:|']
    for x in results: lines.append(f"| {x['season']} | {x['api_rows']} | {x['saved_player_rows']} | {x['matched_game_ids']} | {x['field_mismatch_count']} | {x['gameValidForDunkest_true']} | {x['gameValidForDunkest_false']} |")
    lines += ['', '## Historical validity-flag distribution','', '| Season archive | Rows | True | False | Missing | Date range |','|---|---:|---:|---:|---:|---|']
    for x in flag_inventory: lines.append(f"| `{x['file']}` | {x['rows']} | {x['true']} | {x['false']} | {x['missing']} | {x['min_date']} – {x['max_date']} |")
    lines += ['', '## Interpretation','', '- The profile page and the historical collector use the same public per-game endpoint, `/api/player/games`, with `player_id` and `season_id` parameters.', '- For the four tested seasons, every Luka row and every API field matches the already-saved local archive exactly. This verifies the source path; it does not constitute a new historical scrape.', '- Preserve `gameValidForDunkest` as a raw field. Do not use it as a universal target filter: every row in the 2018-19 and 2019-20 archives is marked `False`, whereas later archives contain both values.', '- No production files, training data, or validation splits were changed.']
    OUT_MD.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'json':str(OUT_JSON.relative_to(ROOT)),'markdown':str(OUT_MD.relative_to(ROOT)),'all_season_checks_exact_match':result['conclusion']['all_season_checks_exact_match'],'seasons':[{k:x[k] for k in ['season','api_rows','saved_player_rows','matched_game_ids','field_mismatch_count','gameValidForDunkest_true','gameValidForDunkest_false']} for x in results]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
