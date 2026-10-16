#!/usr/bin/env python3
"""Expansive past-only grid search for Dunkest PDK regressors, including PyTorch dropout MLPs.

Selection folds: 2022-23, 2023-24, 2024-25; each fold trains strictly on earlier seasons.
The 2025-26 holdout and 2026-27 prospective outcomes are not used. This is model selection,
not a production promotion. The current production ensemble is retained as a reference.
"""
from __future__ import annotations
import json, math, os, time, warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor, GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPRegressor
from dunkest.config import Settings
from dunkest.models.predictor import FEATURE_COLS
from dunkest.models.multiseason_training import adapt_certified_training_rows, DEFAULT_DATASET
import torch
from torch import nn

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/audit'
STAMP='dunkest_pdk_monte_carlo_search_20261016_v1'
CSV=OUT/f'{STAMP}_fold_metrics.csv'; SUMMARY=OUT/f'{STAMP}_summary.csv'; AUDIT=OUT/f'{STAMP}.json'; REPORT=OUT/f'{STAMP}.md'
METRIC_COLUMNS=['candidate_id','family','config_json','fold_season','n','mae','rmse','bias_pred_minus_actual','mae_actual_ge25','n_actual_ge25','mae_actual_ge30','n_actual_ge30','mae_history_lt5','n_history_lt5','baseline_mae','baseline_rmse','train_rows','test_rows','feature_count','fit_seconds','iterations','epochs','early_stop_val_mse_standardized']
FOLDS=['2022-23','2023-24','2024-25']
SEED=20261016
MAX_EPOCHS=55; PATIENCE=8; BATCH_SIZE=2048

# Deterministic Monte Carlo search: broad distributions, sampled once and persisted in audit.
# 80 candidates: 10 Ridge, 20 HistGradientBoosting, 20 GradientBoosting,
# 10 ExtraTrees, 8 RandomForest and 12 Torch MLP configurations.
CANDIDATES=[]
def add(family, cfg): CANDIDATES.append({'family':family,'cfg':cfg,'id':f'trial-{len(CANDIDATES)+1:03d}__'+family+'__'+'__'.join(f'{k}-{v}' for k,v in cfg.items())})
rng=np.random.default_rng(20261016)
for a in np.exp(rng.uniform(np.log(.01),np.log(100.),10)): add('ridge',{'alpha':round(float(a),7)})
for _ in range(20):
 add('hist_gbr',{'max_leaf_nodes':int(rng.choice([10,15,20,31,40,63])),'learning_rate':round(float(np.exp(rng.uniform(np.log(.015),np.log(.12)))),7),'l2_regularization':round(float(np.exp(rng.uniform(np.log(.01),np.log(30.)))),7),'max_iter':int(rng.choice([150,200,250,300,400])),'min_samples_leaf':int(rng.choice([15,25,40,60]))})
for _ in range(20):
 add('gradient_boosting',{'n_estimators':int(rng.choice([100,150,220,300,400])),'learning_rate':round(float(np.exp(rng.uniform(np.log(.015),np.log(.1)))),7),'max_depth':int(rng.choice([1,2,3,4])),'min_samples_leaf':int(rng.choice([3,5,8,12,20])),'subsample':round(float(rng.uniform(.65,1.)),4)})
for _ in range(10):
 add('extra_trees',{'n_estimators':int(rng.choice([220,300,380])),'max_depth':int(rng.choice([6,8,10])) if rng.random()<.75 else None,'min_samples_leaf':int(rng.choice([2,3,5,8,12])),'max_features':round(float(rng.choice([.5,.7,.85,1.])),2)})
for _ in range(8):
 add('random_forest',{'n_estimators':int(rng.choice([220,300])),'max_depth':int(rng.choice([6,8,10])) if rng.random()<.75 else None,'min_samples_leaf':int(rng.choice([2,4,8,12])),'max_features':round(float(rng.choice([.5,.7,.85,1.])),2),'bootstrap':bool(rng.choice([True,False]))})
for _ in range(12):
 add('torch_dropout_mlp',{'hidden':[(64,32),(128,64),(128,64,32),(256,128,64)][int(rng.integers(0,4))],'dropout':round(float(rng.choice([0.,.1,.2,.3,.4])),2),'weight_decay':round(float(np.exp(rng.uniform(np.log(1e-5),np.log(1e-2)))),8),'lr':round(float(np.exp(rng.uniform(np.log(1e-4),np.log(2e-3)))),8)})

def metrics(y,p,history):
 y=np.asarray(y,float); p=np.asarray(p,float); e=p-y
 out={'n':int(len(y)),'mae':float(mean_absolute_error(y,p)),'rmse':float(np.sqrt(mean_squared_error(y,p))),'bias_pred_minus_actual':float(np.mean(e))}
 for threshold in (25,30):
  m=y>=threshold; out[f'mae_actual_ge{threshold}']=float(np.mean(np.abs(e[m]))) if m.any() else np.nan; out[f'n_actual_ge{threshold}']=int(m.sum())
 m=history<5; out['mae_history_lt5']=float(np.mean(np.abs(e[m]))) if m.any() else np.nan; out['n_history_lt5']=int(m.sum())
 return out

def build_model(c, seed):
 f=c['family']; p=c['cfg']
 if f=='ridge': return make_pipeline(StandardScaler(),Ridge(alpha=p['alpha']))
 if f=='hist_gbr': return HistGradientBoostingRegressor(**p,random_state=seed,early_stopping=False)
 if f=='random_forest': return RandomForestRegressor(**p,random_state=seed,n_jobs=3)
 if f=='extra_trees': return ExtraTreesRegressor(**p,random_state=seed,n_jobs=3)
 if f=='gradient_boosting': return GradientBoostingRegressor(**p,random_state=seed)
 if f=='sklearn_mlp': return make_pipeline(StandardScaler(),MLPRegressor(**p,random_state=seed,early_stopping=True,n_iter_no_change=12,validation_fraction=.15))
 raise ValueError(f)

class DropoutMLP(nn.Module):
 def __init__(self,n_features,hidden,dropout):
  super().__init__(); layers=[]; last=n_features
  for width in hidden:
   layers += [nn.Linear(last,width),nn.ReLU()]
   if dropout>0: layers.append(nn.Dropout(dropout))
   last=width
  layers.append(nn.Linear(last,1)); self.net=nn.Sequential(*layers)
 def forward(self,x): return self.net(x).squeeze(-1)

def fit_torch(cfg,Xtr,ytr,wtr,Xval,yval,seed):
 torch.manual_seed(seed); np.random.seed(seed); torch.set_num_threads(4)
 # Standardization parameters are fitted only on the training slice.
 mean=Xtr.mean(axis=0); std=Xtr.std(axis=0); std=np.where(std<1e-8,1.0,std)
 x=(Xtr-mean)/std; xv=(Xval-mean)/std
 ym=float(ytr.mean()); ys=float(ytr.std()) or 1.0; yt=(ytr-ym)/ys; yv=(yval-ym)/ys
 device=torch.device('cpu'); model=DropoutMLP(x.shape[1],tuple(cfg['hidden']),float(cfg['dropout'])).to(device)
 opt=torch.optim.AdamW(model.parameters(),lr=float(cfg['lr']),weight_decay=float(cfg['weight_decay']))
 xt=torch.tensor(x,dtype=torch.float32); ytt=torch.tensor(yt,dtype=torch.float32); wt=torch.tensor(wtr,dtype=torch.float32)
 xvt=torch.tensor(xv,dtype=torch.float32); yvt=torch.tensor(yv,dtype=torch.float32)
 best=float('inf'); best_state=None; patience=0
 for epoch in range(MAX_EPOCHS):
  model.train(); order=torch.randperm(len(xt))
  for ix in order.split(BATCH_SIZE):
   opt.zero_grad(set_to_none=True); pred=model(xt[ix]); loss=(((pred-ytt[ix])**2)*wt[ix]).mean(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),5.0); opt.step()
  model.eval()
  with torch.no_grad(): val=float(torch.mean((model(xvt)-yvt)**2).item())
  if val < best-1e-5:
   best=val; best_state={k:v.detach().clone() for k,v in model.state_dict().items()}; patience=0
  else:
   patience+=1
   if patience>=PATIENCE: break
 if best_state is not None: model.load_state_dict(best_state)
 model.eval()
 with torch.no_grad(): pred=model(torch.tensor((Xval-mean)/std,dtype=torch.float32)).cpu().numpy()*ys+ym
 return pred,epoch+1,float(best)

def main():
 settings=Settings.from_yaml(); source=pd.read_parquet(settings.data_path/DEFAULT_DATASET)
 # Keep historical adapter's certification/cutoff checks; never append the 2025/26 holdout.
 minute_path=settings.data_path/'processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'
 minute_labels=None
 if minute_path.exists(): minute_labels=pd.read_parquet(minute_path,columns=['nba_GAME_ID','nba_PLAYER_ID','nba_MIN','nba_match_status'])
 rows=adapt_certified_training_rows(source,minutes_labels=minute_labels)
 if rows['season_label'].astype(str).isin(['2025-26']).any(): raise RuntimeError('Holdout leakage: 2025-26 rows entered certified adapter.')
 if CSV.exists():
  done=pd.read_csv(CSV)
  completed=set(zip(done['candidate_id'].astype(str),done['fold_season'].astype(str)))
 else: done=pd.DataFrame(); completed=set()
 records=[]; started=time.time(); nfinite=0
 # Feature schema is shared with production; medians are fit on past-only training data per fold.
 cols=[c for c in FEATURE_COLS if c in rows.columns and pd.to_numeric(rows[c],errors='coerce').replace([np.inf,-np.inf],np.nan).notna().any()]
 for fold in FOLDS:
  train=rows.loc[rows.season_label.astype(str)<fold].copy(); test=rows.loc[rows.season_label.astype(str).eq(fold)].copy()
  if train.empty or test.empty: raise RuntimeError(f'Empty temporal fold {fold}: train={len(train)} test={len(test)}')
  med=pd.DataFrame({c:pd.to_numeric(train[c],errors='coerce') for c in cols}).replace([np.inf,-np.inf],np.nan).median().fillna(0.)
  Xtr=pd.DataFrame({c:pd.to_numeric(train[c],errors='coerce') for c in cols}).replace([np.inf,-np.inf],np.nan).fillna(med).fillna(0.).to_numpy(np.float32)
  Xte=pd.DataFrame({c:pd.to_numeric(test[c],errors='coerce') for c in cols}).replace([np.inf,-np.inf],np.nan).fillna(med).fillna(0.).to_numpy(np.float32)
  ytr=pd.to_numeric(train.target_pdk_official,errors='coerce').to_numpy(float); yte=pd.to_numeric(test.target_pdk_official,errors='coerce').to_numpy(float)
  wtr=pd.to_numeric(train['_training_sample_weight'],errors='coerce').fillna(1.).to_numpy(float)
  history=pd.to_numeric(test.history_games_before_target,errors='coerce').fillna(0).to_numpy(float)
  # baseline uses only past-derived previous-10 PDK feature; fallback is past-train median.
  base=pd.to_numeric(test.prev10_pdk_mean,errors='coerce').to_numpy(float); base=np.where(np.isfinite(base),base,float(np.median(ytr)))
  baseline=metrics(yte,base,history)
  print(f'FOLD {fold}: train={len(train):,}, test={len(test):,}, features={len(cols)} baseline_mae={baseline["mae"]:.5f}',flush=True)
  for i,c in enumerate(CANDIDATES,1):
   key=(c['id'],fold)
   if key in completed: continue
   t0=time.time(); extra={}
   if c['family']=='torch_dropout_mlp':
    # Use the latest 15% of training dates for early stopping, never the evaluation season.
    dates=pd.to_datetime(train.GAME_DATE,errors='coerce'); ud=np.sort(dates.dropna().unique())
    cut=ud[max(1,int(len(ud)*.85))] if len(ud)>5 else ud[-1]
    a=dates<cut; b=dates>=cut
    if int(a.sum())<1000 or int(b.sum())<100: a=pd.Series(np.arange(len(train))<int(len(train)*.85),index=train.index); b=~a
    pred,epochs,val_loss=fit_torch(c['cfg'],Xtr[a.to_numpy()],ytr[a.to_numpy()],wtr[a.to_numpy()],Xtr[b.to_numpy()],ytr[b.to_numpy()],SEED+FOLDS.index(fold))
    # Refit best epoch count on all past rows with same hyperparameters; no evaluation-season labels.
    torch.manual_seed(SEED+FOLDS.index(fold)); np.random.seed(SEED+FOLDS.index(fold)); torch.set_num_threads(4)
    mean=Xtr.mean(axis=0); std=np.where(Xtr.std(axis=0)<1e-8,1.,Xtr.std(axis=0)); x=(Xtr-mean)/std; xt=torch.tensor(x,dtype=torch.float32)
    ym=float(ytr.mean()); ys=float(ytr.std()) or 1.; yt=torch.tensor((ytr-ym)/ys,dtype=torch.float32); wt=torch.tensor(wtr,dtype=torch.float32)
    model=DropoutMLP(Xtr.shape[1],tuple(c['cfg']['hidden']),float(c['cfg']['dropout']))
    opt=torch.optim.AdamW(model.parameters(),lr=float(c['cfg']['lr']),weight_decay=float(c['cfg']['weight_decay']))
    for ep in range(max(8,epochs)):
     model.train(); order=torch.randperm(len(xt))
     for ix in order.split(BATCH_SIZE):
      opt.zero_grad(set_to_none=True); pr=model(xt[ix]); loss=(((pr-yt[ix])**2)*wt[ix]).mean(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),5.); opt.step()
    model.eval()
    with torch.no_grad(): p=model(torch.tensor((Xte-mean)/std,dtype=torch.float32)).numpy()*ys+ym
    extra={'epochs':int(epochs),'early_stop_val_mse_standardized':float(val_loss)}
   else:
    model=build_model(c,SEED+FOLDS.index(fold))
    fit_kwargs={}
    final_est=model.steps[-1][1] if hasattr(model,'steps') else model
    if 'sample_weight' in final_est.fit.__code__.co_varnames: fit_kwargs['sample_weight']=wtr
    with warnings.catch_warnings():
     warnings.simplefilter('ignore'); model.fit(Xtr,ytr,**fit_kwargs); p=model.predict(Xte)
    if c['family']=='sklearn_mlp': extra={'iterations':int(final_est.n_iter_)}
   result={'candidate_id':c['id'],'family':c['family'],'config_json':json.dumps(c['cfg'],sort_keys=True),'fold_season':fold,**metrics(yte,p,history),'baseline_mae':baseline['mae'],'baseline_rmse':baseline['rmse'],'train_rows':len(train),'test_rows':len(test),'feature_count':len(cols),'fit_seconds':round(time.time()-t0,2),**extra}
   records.append(result); completed.add(key)
   pd.DataFrame([result]).reindex(columns=METRIC_COLUMNS).to_csv(CSV,mode='a',header=not CSV.exists(),index=False)
   print(f'  [{i:02d}/{len(CANDIDATES)}] {c["id"]} MAE={result["mae"]:.5f} RMSE={result["rmse"]:.5f} bias={result["bias_pred_minus_actual"]:.4f} ({result["fit_seconds"]:.1f}s)',flush=True)
 # Summarize all completed candidates from persisted CSV, enabling safe resume.
 allm=pd.read_csv(CSV)
 def summarize(g):
  return pd.Series({'folds':g.fold_season.nunique(),'n':int(g.n.sum()),'weighted_mae':np.average(g.mae,weights=g.n),'weighted_rmse':np.sqrt(np.average(g.rmse**2,weights=g.n)),'weighted_bias':np.average(g.bias_pred_minus_actual,weights=g.n),'mae_ge25':np.average(g.mae_actual_ge25,weights=g.n_actual_ge25),'mae_ge30':np.average(g.mae_actual_ge30,weights=g.n_actual_ge30),'mae_history_lt5':np.average(g.mae_history_lt5,weights=g.n_history_lt5),'median_fit_seconds':np.median(g.fit_seconds)})
 summary=allm.groupby(['candidate_id','family','config_json'],dropna=False).apply(summarize,include_groups=False).reset_index().sort_values(['weighted_mae','weighted_rmse'])
 summary.to_csv(SUMMARY,index=False)
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'source_dataset':str((settings.data_path/DEFAULT_DATASET).relative_to(ROOT)),'label':'certified official Dunkest PDK','selection_folds':FOLDS,'holdout_2025_26_used':False,'prospective_2026_27_used':False,'candidate_count':len(CANDIDATES),'fold_fit_count':len(allm),'features':cols,'protocol':'Each fold trains only on strictly earlier season rows. Imputation and scaling are fit on training rows only. Neural early stopping uses only a tail split of the past training seasons. 2025-26 holdout is excluded.','torch_version':torch.__version__,'max_epochs':MAX_EPOCHS,'patience':PATIENCE,'top_20':summary.head(20).to_dict('records'),'completed':len(allm),'expected':len(CANDIDATES)*len(FOLDS)}
 AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
 report=['# Extensive Dunkest PDK grid search with dropout','','Generated UTC: '+audit['created_utc'],'', '## Protocol','',audit['protocol'],f"\nCandidates: {len(CANDIDATES)}; temporal fold fits expected: {len(CANDIDATES)*len(FOLDS)}; completed: {len(allm)}. Features: {len(cols)}. PyTorch: {torch.__version__}.",'','## Top 20 pooled candidates','',summary.head(20).to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Per-fold details','',allm.sort_values(['candidate_id','fold_season']).to_string(index=False),'','## Interpretation','','Rank by pooled MAE, then RMSE; check bias, high-score and low-history cohorts and consistency by season before selecting a winner. This is a model-selection comparison, not proof of lineup-level gains. The 2025/26 holdout and 2026/27 prospective test remain unused. Production code is not modified by this script.','']
 REPORT.write_text('\n'.join(report),encoding='utf-8')
 print('\nTOP 20\n'+summary.head(20).to_string(index=False),flush=True)
 print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
 print(f'ELAPSED_MIN={(time.time()-started)/60:.1f}',flush=True)
if __name__=='__main__': main()
