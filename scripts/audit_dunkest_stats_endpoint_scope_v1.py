#!/usr/bin/env python3
"""Read-only test of public Dunkest stats-table season/week/round scoping.

Writes only new versioned audit artifacts. Does not touch raw data or production code.
"""
from __future__ import annotations
import hashlib, json, time
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/audit'
STEM = 'dunkest_stats_endpoint_scope_v1'
BASE = 'https://www.dunkest.com/api'
HEADERS = {'User-Agent': 'dunkest-optimizer/0.1 (+research)', 'Accept': 'application/json, text/html;q=0.9'}
FOCUS = {
    'Tyrese Maxey','Isaiah Joe','Furkan Korkmaz','Danny Green','Seth Curry','Anthony Edwards',
    "D'Angelo Russell",'Malik Beasley','Matisse Thybulle','Tobias Harris','Jaden McDaniels',
    'Joel Embiid','Naz Reid','Karl-Anthony Towns','Jarred Vanderbilt',
    'Juan Toscano-Anderson','Nickeil Alexander-Walker','Sandro Mamukelashvili','Jaden Springer'
}
SCOPES = [
    ('s5_w43_r2_avg_minimal',5,43,'2','avg','minimal'),
    ('s5_w43_r2_avg_full',5,43,'2','avg','full'),
    ('s7_w43_r2_avg_minimal',7,43,'2','avg','minimal'),
    ('s5_w43_r2_tot_minimal',5,43,'2','tot','minimal'),
    ('s5_w43_r2_tot_full',5,43,'2','tot','full'),
    ('s7_w43_r2_tot_minimal',7,43,'2','tot','minimal'),
    ('s5_w40_r3_tot',5,40,'3','tot','minimal'),
    ('s7_w40_r3_tot',7,40,'3','tot','minimal'),
    ('s5_w53_r2_tot',5,53,'2','tot','minimal'),
    ('s7_w53_r2_tot',7,53,'2','tot','minimal'),
    ('s9_w20_r2_tot',9,20,'2','tot','minimal'),
    ('s13_w20_r1_tot',13,20,'1','tot','minimal'),
    ('s19_w20_r1_tot',19,20,'1','tot','minimal'),
    ('s9_w40_r2_tot',9,40,'2','tot','minimal'),
]

def row_name(x): return (str(x.get('first_name',''))+' '+str(x.get('last_name',''))).strip()
def main():
    for ext in ('.json','.md','.csv'):
        if (OUT/f'{STEM}{ext}').exists(): raise SystemExit(f'Refusing to overwrite {STEM}{ext}')
    results=[]; rows=[]
    with httpx.Client(headers=HEADERS,timeout=35,follow_redirects=True) as c:
        for idx,(label,sid,week,rnd,typ,variant) in enumerate(SCOPES):
            params=[('season_id',str(sid)),('mode','dunkest'),('stats_type',typ),('weeks[]',str(week)),('rounds[]',rnd)]
            if variant=='full':
                params += [('teams[]',str(i)) for i in range(1,31)]
                params += [('positions[]',str(i)) for i in range(1,4)]
                params += [('player_search',''),('min_cr','1'),('max_cr','35'),('sort_by','pdk'),('sort_order','desc')]
            try:
                resp=c.get(BASE+'/stats/table',params=params); resp.raise_for_status(); data=resp.json()
                if not isinstance(data,list): raise ValueError(f'Expected list, got {type(data).__name__}')
                digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                item={'scope':label,'season_id':sid,'week':week,'round':rnd,'stats_type':typ,'query_variant':variant,'http_status':resp.status_code,'row_count':len(data),'payload_sha256':digest,'payload_sha256_16':digest[:16],'error':''}
                for x in data:
                    name=row_name(x)
                    if name in FOCUS:
                        rows.append({'scope':label,'season_id':sid,'week':week,'round':rnd,'stats_type':typ,'player_name':name,'team_code':x.get('team_code'),'pdk':x.get('pdk'),'gp':x.get('gp'),'pts':x.get('pts'),'reb':x.get('reb'),'ast':x.get('ast'),'stl':x.get('stl'),'blk':x.get('blk'),'tov':x.get('tov'),'plus_minus':x.get('plus_minus'),'min':x.get('min')})
                results.append(item)
            except Exception as e:
                results.append({'scope':label,'season_id':sid,'week':week,'round':rnd,'stats_type':typ,'query_variant':variant,'http_status':None,'row_count':None,'payload_sha256':'','payload_sha256_16':'','error':repr(e)})
            if idx < len(SCOPES)-1: time.sleep(.35)
    # Exact equality across the minimal/full request verifies that adding explicit table filters did not change this response.
    by={x['scope']:x for x in results}
    variant_pairs=[]
    for a,b in [('s5_w43_r2_avg_minimal','s5_w43_r2_avg_full'),('s5_w43_r2_tot_minimal','s5_w43_r2_tot_full')]:
        x,y=by[a],by[b]
        variant_pairs.append({'minimal_scope':a,'full_scope':b,'same_row_count':x.get('row_count')==y.get('row_count'),'same_payload_hash':bool(x.get('payload_sha256')) and x.get('payload_sha256')==y.get('payload_sha256')})
    report={'generated_utc':datetime.now(timezone.utc).isoformat(),'purpose':'Test whether the public stats endpoint returns stable, season-scoped responses for known weekly-round scopes. Read-only GET requests only.','endpoint':BASE+'/stats/table','scopes':results,'focus_rows':rows,'minimal_vs_full_request_comparisons':variant_pairs,'findings':{'confirmed_scope_s5_w43_r2_cluster_rows':sum(1 for r in rows if r['scope'] in ('s5_w43_r2_avg_minimal','s5_w43_r2_tot_minimal') and r['player_name'] in FOCUS),'interpretation':'A repeated cross-season boxscore cluster in a live season_id=5 response is evidence the returned table is contaminated or mis-scoped at source/query level; explicit season_id is present, and minimal/full request parity can rule out omitted team/position/sort filters as the cause. This test cannot identify the backend implementation defect.'},'safeguards':['Public read-only GET requests only','No raw Parquet modified','No production code/config/targets/splits/backtests modified','Isolated candidates are not automatically quarantined']}
    (OUT/f'{STEM}.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    import pandas as pd
    pd.DataFrame(results).to_csv(OUT/f'{STEM}_scopes.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/f'{STEM}_focus_rows.csv',index=False)
    lines=['# Dunkest stats endpoint scope audit (v1)','',f"Generated UTC: {report['generated_utc']}",'','## Scope requests','', '| Scope | HTTP | Rows | Payload hash (16) |','|---|---:|---:|---|']
    for x in results: lines.append(f"| `{x['scope']}` | {x.get('http_status') or 'ERROR'} | {x.get('row_count') if x.get('row_count') is not None else '—'} | `{x.get('payload_sha256_16','')}` |")
    lines += ['', '## Request-variant parity','', '| Minimal vs explicit filters | Same row count | Same exact payload |','|---|---|---|']
    for x in variant_pairs: lines.append(f"| `{x['minimal_scope']}` vs `{x['full_scope']}` | {x['same_row_count']} | {x['same_payload_hash']} |")
    lines += ['', '## Interpretation','', 'The `season_id` parameter is explicitly sent in every request. The audit compares minimal requests with the collector-style request including team/position/sort filters and queries the same week/round under related season IDs. Reproducing the PHI–MIN rows from the live endpoint means the issue is not caused solely by a local Parquet write. If minimal/full hashes match, the omitted optional filters are not responsible for that response. This does not reveal whether the backend has a stale cache, a faulty join, or another server-side season-scope issue.', '', 'The endpoint does not expose a public diagnostic explaining row provenance, so the exact root cause remains unverified. Keep the confirmed scope quarantined from clean derivatives and isolated rows review-only. No raw or production data changed.', '', f"JSON: `reports/audit/{STEM}.json`", f"Scope CSV: `reports/audit/{STEM}_scopes.csv`", f"Focus-row CSV: `reports/audit/{STEM}_focus_rows.csv`", '']
    (OUT/f'{STEM}.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Wrote new audit artifacts:',STEM)
    print('Scopes:',len(results),'errors:',sum(bool(x['error']) for x in results))
    print('Minimal/full parity:',variant_pairs)
    for x in results: print(x['scope'], 'rows=',x.get('row_count'),'hash=',x.get('payload_sha256_16'),'error=',x.get('error'))
if __name__=='__main__': main()
