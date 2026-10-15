#!/usr/bin/env python3
"""Compare direct coach-score forecasting with a pregame Monte Carlo rule simulation.

Uses chronologically generated team-point forecasts (half-life 15 selected on 2024-25),
strictly prior team score volatility/correlation/overtime frequency, and the official
Dunkest coach scoring rules at equal credits. No historical coach CRs are invented.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.rules.coach import coach_points_from_outcomes

ROOT=Path(__file__).resolve().parents[1]
TEAM_LOGS=ROOT/'data/processed/team_game_logs_2018-26_v1.parquet'
POINT_FCST=ROOT/'reports/audit/coach_points_model_tuning_walk_forward_2018-26_v3.csv'
DIRECT=ROOT/'reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_predictions.csv'
OUTCOMES=ROOT/'reports/audit/dunkest_coach_base_points_walk_forward_2018-26_v1_outcomes.csv'
OUT=ROOT/'reports/audit'; STEM='dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v1'
PRED=OUT/f'{STEM}_predictions.csv'; METRICS=OUT/f'{STEM}_metrics.csv'; AUDIT=OUT/f'{STEM}.json'; REPORT=OUT/f'{STEM}.md'
TEST_SEASONS={'2022-23','2023-24','2024-25','2025-26'}
DRAWS=2048

def stable_seed(key: str)->int:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], 'big')

def _team_sd(scores, league_sd):
    a=np.asarray(scores,dtype=float); a=a[np.isfinite(a)]
    sample_sd=float(np.std(a,ddof=1)) if len(a)>1 else float(league_sd)
    if not np.isfinite(sample_sd): sample_sd=float(league_sd)
    degrees=max(len(a)-1,0)
    var=(degrees*sample_sd**2+10.0*league_sd**2)/(degrees+10.0)
    return float(np.clip(np.sqrt(var),8.0,18.0))

def _metric(y,p):
    y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
    return {'n':int(len(y)),'mae':float(mean_absolute_error(y,p)),
            'rmse':float(np.sqrt(mean_squared_error(y,p))), 'bias_pred_minus_actual':float(np.mean(e))}

def main():
    for p in (PRED,METRICS,AUDIT,REPORT):
        if p.exists(): raise SystemExit(f'Refusing to overwrite versioned artifact: {p}')
    logs=pd.read_parquet(TEAM_LOGS).copy()
    logs['GAME_DATE']=pd.to_datetime(logs.GAME_DATE,errors='coerce')
    logs['GAME_ID']=logs.GAME_ID.astype(str).str.zfill(10)
    logs['TEAM_ABBREVIATION']=logs.TEAM_ABBREVIATION.astype(str).str.upper().str.strip()
    logs['PTS']=pd.to_numeric(logs.PTS,errors='coerce'); logs['MIN']=pd.to_numeric(logs.MIN,errors='coerce')
    logs=logs.dropna(subset=['GAME_DATE','GAME_ID','TEAM_ABBREVIATION','PTS'])
    point=pd.read_csv(POINT_FCST)
    point=point.loc[np.isclose(pd.to_numeric(point.half_life_games,errors='coerce'),15.0)].copy()
    point['date']=pd.to_datetime(point.date,errors='coerce'); point['game_id']=point.game_id.astype(str).str.zfill(10)
    direct=pd.read_csv(DIRECT); direct['game_date']=pd.to_datetime(direct.game_date,errors='coerce'); direct['game_id']=direct.game_id.astype(str).str.zfill(10)
    outcomes=pd.read_csv(OUTCOMES); outcomes['game_date']=pd.to_datetime(outcomes.game_date,errors='coerce'); outcomes['game_id']=outcomes.game_id.astype(str).str.zfill(10)
    # Use one row per game for point predictions and join verified outcomes from the same game identity.
    point=point.sort_values(['date','game_id']).drop_duplicates(['season','game_id'])
    actual=outcomes.loc[outcomes.team.eq(outcomes.team),['season','game_id','game_date','team','opponent','team_points','opponent_points','overtime','actual_base_coach_pdk']].copy()
    history=[]; game_history=[]; records=[]
    log_games={}
    for (season,gid),g in logs.groupby(['SEASON','GAME_ID'],sort=False):
        if len(g)!=2: continue
        g=g.sort_values('TEAM_ABBREVIATION')
        row1,row2=g.iloc[0],g.iloc[1]
        overtime=bool(g.MIN.gt(240).any()) if g.MIN.notna().any() else False
        log_games[(str(season),str(gid))]={'date':g.GAME_DATE.min(),'rows':g,'overtime':overtime}
    point=point.loc[point.season.astype(str).isin(TEST_SEASONS)].sort_values(['date','game_id']).reset_index(drop=True)
    for date, day in point.groupby('date',sort=True):
        # Freeze history for every game on the date; only prior dates are available.
        all_scores=np.array([x['pts'] for x in history],float)
        league_mean=float(np.mean(all_scores)) if len(all_scores) else 100.0
        league_sd=float(np.clip(np.std(all_scores,ddof=1) if len(all_scores)>1 else 12.0,8.0,18.0))
        ot_rate=float((sum(x['overtime'] for x in game_history)+1.0)/(len(game_history)+25.0))
        if len(game_history)>=10:
            corr=float(np.corrcoef([x['home_pts'] for x in game_history],[x['away_pts'] for x in game_history])[0,1])
            corr=float(np.clip(corr,-0.4,0.6)) if np.isfinite(corr) else 0.1
        else: corr=0.1
        per_team={}
        for team in {x['team'] for x in history}:
            vals=[x['pts'] for x in history if x['team']==team]
            per_team[team]=vals
        for _,g in day.iterrows():
            key=(str(g.season),str(g.game_id)); log=log_games.get(key)
            if log is None: continue
            game=log['rows']
            home=game.loc[game.MATCHUP.astype(str).str.contains(r'vs\.',regex=True)]
            away=game.loc[~game.MATCHUP.astype(str).str.contains(r'vs\.',regex=True)]
            if len(home)==1 and len(away)==1: h,a=home.iloc[0],away.iloc[0]
            else:
                # Neutral-site games have no home marker; use stable ordering only for symmetry.
                ordered=game.sort_values('TEAM_ABBREVIATION'); h,a=ordered.iloc[0],ordered.iloc[1]
            ht,at=str(h.TEAM_ABBREVIATION),str(a.TEAM_ABBREVIATION)
            hp=float(g.predicted_home_points); ap=float(g.predicted_away_points)
            hsd=_team_sd(per_team.get(ht,[]),league_sd); asd=_team_sd(per_team.get(at,[]),league_sd)
            rng=np.random.default_rng(stable_seed(f'{g.season}-{g.game_id}-mc-coach-v1'))
            z1=rng.standard_normal(DRAWS); z2=rng.standard_normal(DRAWS)
            zaway=corr*z1+np.sqrt(1-corr*corr)*z2
            hs=np.maximum(np.rint(hp+hsd*z1),0); ass=np.maximum(np.rint(ap+asd*zaway),0)
            ots=rng.random(DRAWS)<np.clip(ot_rate,0.0,0.25)
            hcoach=np.asarray(coach_points_from_outcomes(hs,ass,10.0,10.0,ots),float)
            acoach=np.asarray(coach_points_from_outcomes(ass,hs,10.0,10.0,ots),float)
            for team,opp,actual_pts,opp_pts,actual_ot,expected_mc in [
                (ht,at,float(h.PTS),float(a.PTS),log['overtime'],float(np.mean(hcoach))),
                (at,ht,float(a.PTS),float(h.PTS),log['overtime'],float(np.mean(acoach)))]:
                outcome=actual.loc[actual.season.astype(str).eq(str(g.season)) & actual.game_id.eq(str(g.game_id)) & actual.team.eq(team)]
                if len(outcome)!=1: continue
                records.append({'season':str(g.season),'date':date.date().isoformat(),'game_id':str(g.game_id),
                    'team':team,'opponent':opp,'predicted_team_points':hp if team==ht else ap,
                    'predicted_opponent_points':ap if team==ht else hp,'team_score_sd_prior':hsd if team==ht else asd,
                    'opponent_score_sd_prior':asd if team==ht else hsd,'score_correlation_prior':corr,
                    'overtime_probability_prior':ot_rate,'actual_overtime':bool(actual_ot),
                    'actual_base_coach_pdk':float(outcome.iloc[0].actual_base_coach_pdk),
                    'predicted_coach_pdk_monte_carlo':expected_mc})
        # Only after all forecasts for the date, append that date's final NBA scores to history.
        today=logs.loc[logs.GAME_DATE.eq(date)].copy()
        today=today.drop_duplicates(['GAME_ID','TEAM_ABBREVIATION'])
        for (season,gid),gg in today.groupby(['SEASON','GAME_ID'],sort=False):
            if len(gg)!=2: continue
            gg=gg.sort_values('TEAM_ABBREVIATION')
            rr=[]
            for _,row in gg.iterrows():
                rr.append({'team':str(row.TEAM_ABBREVIATION),'pts':float(row.PTS)})
            for x in rr: history.append(x)
            home=today.loc[today.GAME_ID.eq(gid)&today.MATCHUP.astype(str).str.contains(r'vs\.',regex=True)]
            away=today.loc[today.GAME_ID.eq(gid)&~today.MATCHUP.astype(str).str.contains(r'vs\.',regex=True)]
            if len(home)==1 and len(away)==1: hpts,apts=float(home.iloc[0].PTS),float(away.iloc[0].PTS)
            else: hpts,apts=float(gg.iloc[0].PTS),float(gg.iloc[1].PTS)
            ot=bool(gg.MIN.gt(240).any()) if gg.MIN.notna().any() else False
            game_history.append({'home_pts':hpts,'away_pts':apts,'overtime':ot})
    pred=pd.DataFrame(records)
    if pred.empty: raise RuntimeError('No Monte Carlo predictions were generated.')
    # Attach direct-model and rolling baselines for the same team-game rows.
    dd=direct.loc[direct.method.isin(['model_pregame_team_form','baseline_previous5_base_score','baseline_previous10_base_score']),
                  ['season','game_id','team','predicted_base_coach_pdk','method']].copy()
    dd['game_id']=dd.game_id.astype(str).str.zfill(10)
    dd=dd.pivot_table(index=['season','game_id','team'],columns='method',values='predicted_base_coach_pdk',aggfunc='first').reset_index()
    pred=pred.merge(dd,on=['season','game_id','team'],how='left',validate='one_to_one')
    pred=pred.rename(columns={'model_pregame_team_form':'direct_model_pdk','baseline_previous5_base_score':'baseline_previous5_pdk','baseline_previous10_base_score':'baseline_previous10_pdk'})
    metric_rows=[]
    for season,group in pred.groupby('season'):
        for method,col in [('monte_carlo_team_score_distribution','predicted_coach_pdk_monte_carlo'),('direct_base_score_model','direct_model_pdk'),('baseline_previous5','baseline_previous5_pdk'),('baseline_previous10','baseline_previous10_pdk')]:
            g=group.dropna(subset=['actual_base_coach_pdk',col])
            metric_rows.append({'test_season':season,'method':method,**_metric(g.actual_base_coach_pdk,g[col])})
    for method,col in [('monte_carlo_team_score_distribution','predicted_coach_pdk_monte_carlo'),('direct_base_score_model','direct_model_pdk'),('baseline_previous5','baseline_previous5_pdk'),('baseline_previous10','baseline_previous10_pdk')]:
        g=pred.dropna(subset=['actual_base_coach_pdk',col]); metric_rows.append({'test_season':'pooled_2022-26','method':method,**_metric(g.actual_base_coach_pdk,g[col])})
    metrics=pd.DataFrame(metric_rows)
    pred.to_csv(PRED,index=False); metrics.to_csv(METRICS,index=False)
    audit={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'test_seasons':sorted(TEST_SEASONS),'selected_team_score_half_life_games':15.0,'selection_season':'2024-25 validation','final_holdout_season':'2025-26','input_team_point_predictions':str(POINT_FCST.relative_to(ROOT)),'input_actual_neutral_coach_scores':str(OUTCOMES.relative_to(ROOT)),'draws_per_game':DRAWS,'simulation':'correlated normal team scores using prior-only team score SDs, prior-only score correlation and prior-only overtime frequency; official coach rules applied with coach_cr=opponent_cr=10','rows':len(pred),'unique_games':int(pred.game_id.nunique()),'metrics':metrics.to_dict(orient='records'),'limitations':['Equal coach CR isolates base score and is not exact historical credit-adjusted PDK.','Historical overtime probability and team-score volatility are estimated only from games completed before the target date.','Monte Carlo is a challenger experiment, not a production change.','2025-26 remains a reported holdout; the half-life was selected using 2024-25 only.'],'production_changed':False}
    AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    pivot=metrics.loc[metrics.test_season.eq('pooled_2022-26')].set_index('method')
    lines=['# Dunkest coach score forecast: direct model vs pregame Monte Carlo — V1','','## Method','',f'- Evaluated {pred.game_id.nunique():,} games / {len(pred):,} team-game coach outcomes across 2022/23–2025/26.','- Team-point forecasts use half-life 15, selected on 2024/25 validation; 2025/26 remains the final holdout.','- Monte Carlo uses {0:,} draws per game, team-score SDs and score correlation estimated strictly from prior dates, plus prior-only overtime frequency.'.format(DRAWS),'- Applies the official coach scoring rules to simulated outcomes with equal CR=10 on both sides, isolating the base score.','- Direct model and previous-5/previous-10 baselines are joined on season + NBA game ID + team.','', '## Pooled metrics', '', '| Method | N | MAE | RMSE | Bias |','|---|---:|---:|---:|---:|']
    for method in ['monte_carlo_team_score_distribution','direct_base_score_model','baseline_previous5','baseline_previous10']:
        r=pivot.loc[method]; lines.append(f"| {method} | {int(r['n']):,} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['bias_pred_minus_actual']:+.3f} |")
    lines += ['', '## Interpretation', '', 'This is the key comparison for deciding whether the rule-aware score distribution adds value beyond a direct score model. The result is still a neutral-credit base-score comparison, not exact historical PDK. No production model or config is changed.', '', '## Artifacts','',f'- Predictions: `{PRED.relative_to(ROOT)}`',f'- Metrics: `{METRICS.relative_to(ROOT)}`',f'- Audit JSON: `{AUDIT.relative_to(ROOT)}`','']
    REPORT.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'status':'completed','rows':len(pred),'games':int(pred.game_id.nunique()),'metrics':metrics.loc[metrics.test_season.eq('pooled_2022-26')].to_dict(orient='records'),'outputs':[str(p.relative_to(ROOT)) for p in (PRED,METRICS,AUDIT,REPORT)]},indent=2))
if __name__=='__main__': raise SystemExit(main())
