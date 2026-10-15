#!/usr/bin/env python3
"""Audit what the profile UI and historical records do (and do not) establish about gameValidForDunkest."""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path
import httpx
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/processed'
API='https://www.dunkest.com/api/player/games'
PROFILE='https://www.dunkest.com/it/giocatore/127/luka-doncic'
OUT_JSON=ROOT/'reports/audit/dunkest_validity_flag_semantics_v1.json'
OUT_MD=ROOT/'reports/audit/dunkest_validity_flag_semantics_v1.md'
SEASONS=[('1','2018-19',RAW/'official_dunkest_player_games_2018-19_season_id_1.parquet','dunkest_player_id'),('3','2019-20',RAW/'official_dunkest_player_games_2019-20_season_id_3.parquet','dunkest_player_id'),('5','2020-21',RAW/'official_dunkest_player_games_2020-21_season_id_5.parquet','dunkest_player_id'),('7','2021-22',RAW/'official_dunkest_player_games_2021-22_season_id_7.parquet','dunkest_player_id'),('9','2022-23',RAW/'official_dunkest_player_games_2022-23_season_id_9.parquet','dunkest_player_id'),('13','2023-24',RAW/'official_dunkest_player_games_2023-24_season_id_13.parquet','dunkest_player_id'),('19','2024-25',RAW/'official_dunkest_player_games_2024-25_season_id_19.parquet','dunkest_player_id'),('25','2025-26',RAW/'official_dunkest_player_games_2025-26.parquet','_requested_player_id')]

def count(x): return int(x)
def main():
    if OUT_JSON.exists() or OUT_MD.exists(): raise SystemExit(f'Refusing to overwrite existing audit: {OUT_JSON} or {OUT_MD}')
    with httpx.Client(headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'},timeout=20,follow_redirects=True) as client:
        page=client.get(PROFILE); page.raise_for_status(); html=page.text
    label_match=re.search(r'<label[^>]*for="onlyDunkestGamesCheckbox"[^>]*>(.*?)</label>',html,re.S)
    label=re.sub(r'\s+',' ',label_match.group(1)).strip() if label_match else None
    filter_snippet=None
    m=re.search(r'function filterGames\(data, filters\)\s*\{(.{0,1800}?)\n\s*\}',html,re.S)
    if m: filter_snippet=re.sub(r'\s+',' ',m.group(0)).strip()
    seasons=[]
    for sid,label_season,path,idcol in SEASONS:
        if not path.exists(): raise FileNotFoundError(path)
        df=pd.read_parquet(path).copy()
        df['valid']=df['gameValidForDunkest'].astype('boolean')
        df['pdk_numeric']=pd.to_numeric(df['pdk'],errors='coerce')
        df['date']=pd.to_datetime(df['gameDate'],errors='coerce')
        games=df.groupby('gameId',dropna=False)['valid'].agg(['size','sum','count'])
        # Boolean sum is true count; compare to group size to classify mixed/all-false/all-true.
        games['kind']='mixed'
        games.loc[games['sum'].eq(0),'kind']='all_false'
        games.loc[games['sum'].eq(games['size']),'kind']='all_true'
        flags=df['valid']
        pdk_by_flag=df.groupby('valid',dropna=False)['pdk_numeric'].agg(['count','mean','median','min','max']).reset_index()
        players=df.groupby(idcol,dropna=False).agg(rows=('valid','size'),true=('valid',lambda s:s.eq(True).sum()),false=('valid',lambda s:s.eq(False).sum()),first_date=('date','min'),last_date=('date','max')).reset_index()
        mixed_player_count=int(((players['true']>0)&(players['false']>0)).sum())
        seasons.append({'season_id':sid,'season':label_season,'file':path.name,'rows':len(df),'players':int(df[idcol].nunique()),'unique_game_ids':int(df['gameId'].nunique()),'date_min':str(df['date'].min().date()),'date_max':str(df['date'].max().date()),'true_rows':count(flags.eq(True).sum()),'false_rows':count(flags.eq(False).sum()),'missing_flags':count(flags.isna().sum()),'missing_pdk':count(df['pdk_numeric'].isna().sum()),'false_rows_with_pdk':count((flags.eq(False)&df['pdk_numeric'].notna()).sum()),'game_flag_patterns':{k:int(v) for k,v in games['kind'].value_counts().items()},'players_with_both_true_and_false':mixed_player_count,'pdk_distribution_by_flag':[{str(k): (None if pd.isna(v) else (v.item() if hasattr(v,'item') else v)) for k,v in row.items()} for row in pdk_by_flag.to_dict('records')]})
    # Independent live sample check for old/new seasons. It is only one player; local archive distribution above is complete for collected IDs.
    api_checks=[]
    with httpx.Client(headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'},timeout=15,follow_redirects=True) as client:
        for sid,season in [('1','2018-19'),('3','2019-20'),('5','2020-21'),('19','2024-25'),('25','2025-26')]:
            r=client.get(API,params={'player_id':'127','season_id':sid}); r.raise_for_status(); rows=r.json()
            api_checks.append({'season':season,'player_id':'127','status':r.status_code,'rows':len(rows),'true':sum(x.get('gameValidForDunkest') is True for x in rows),'false':sum(x.get('gameValidForDunkest') is False for x in rows),'missing':sum(x.get('gameValidForDunkest') is None for x in rows)})
    historical_round_archives={}
    for p in (ROOT/'data/raw/dunkest_history').glob('season_*_week_*_round_*_avg.parquet'):
        m=re.match(r'season_(\d+)_week_',p.name)
        if m: historical_round_archives[m.group(1)]=historical_round_archives.get(m.group(1),0)+1
    result={'created_at_utc':datetime.now(timezone.utc).isoformat(),'profile_url':PROFILE,'api_url':API,'profile_ui_evidence':{'validity_checkbox_label':label,'filter_function_snippet':filter_snippet,'interpretation':'The public profile UI only establishes that the checkbox excludes rows whose gameValidForDunkest is explicitly false. The frontend code does not explain why a row is false.'},'season_audit':seasons,'live_luka_sample':api_checks,'local_week_round_avg_archive_file_counts_by_season_id':historical_round_archives,'conclusions':['The endpoint returns non-null PDK values for many rows marked false; false is a validity/filter flag, not a missing-score indicator and must not be replaced with zero.','The profile UI applies the flag as a display filter, but neither its label nor its filtering code defines the business rule that sets the flag.','All collected rows for seasons 2018/19 and 2019/20 are false; therefore the strict valid-target policy yields zero target rows from those seasons. This alone does not prove their PDK numbers are arithmetically wrong, but their official Dunkest-game eligibility cannot be established from this flag.','In later seasons, true and false can coexist for a single Dunkest gameId and for a single player across different dates. Thus the flag is not merely a season-level indicator.','Keep raw PDK and raw flag, keep the current strict target selection for seasons with true flags, and exclude 2018/19–2019/20 from strict official-target training unless an independent historical round/calendar source verifies eligibility. No model or split was changed.']}
    OUT_JSON.parent.mkdir(parents=True,exist_ok=True); OUT_JSON.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    lines=['# Audit semantica `gameValidForDunkest`','',f"Creato: {result['created_at_utc']}",'',f"Pagina profilo: {PROFILE}",'',f"Endpoint partite: `{API}`",'', '## Evidenza dal frontend pubblico','',f"- Etichetta del filtro: **{label or 'non trovata'}**",'- Il codice del frontend scarta una riga quando il filtro è attivo e `gameValidForDunkest === false`. Non contiene una spiegazione della regola che genera il flag.','', '## Distribuzione per stagione','', '| Stagione | Righe | Giocatori | Partite API | True | False | PDK presente su False | Partite all-true | all-false | miste | Giocatori con entrambi i flag |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for s in seasons:
        gp=s['game_flag_patterns']; lines.append(f"| {s['season']} | {s['rows']} | {s['players']} | {s['unique_game_ids']} | {s['true_rows']} | {s['false_rows']} | {s['false_rows_with_pdk']} | {gp.get('all_true',0)} | {gp.get('all_false',0)} | {gp.get('mixed',0)} | {s['players_with_both_true_and_false']} |")
    lines += ['', '## Campione live: Luka Dončić','', '| Stagione | Partite | True | False |','|---|---:|---:|---:|']
    for x in api_checks: lines.append(f"| {x['season']} | {x['rows']} | {x['true']} | {x['false']} |")
    lines += ['', '## Interpretazione operativa',''] + [f'- {x}' for x in result['conclusions']]
    lines += ['', '## Archivi storici di round disponibili','', '| Season ID | File avg per settimana/round |','|---:|---:|']
    for sid,n in sorted(historical_round_archives.items(),key=lambda x:int(x[0])): lines.append(f'| {sid} | {n} |')
    lines += ['', 'Nessun target, modello, split o file di produzione è stato modificato.']
    OUT_MD.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'json':str(OUT_JSON.relative_to(ROOT)),'markdown':str(OUT_MD.relative_to(ROOT)),'ui_label':label,'seasons':[{k:s[k] for k in ['season','rows','true_rows','false_rows','false_rows_with_pdk','game_flag_patterns','players_with_both_true_and_false']} for s in seasons]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
