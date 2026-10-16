#!/usr/bin/env python3
"""Test whether the best small neural candidate adds value to the full production ensemble.
Outer folds are 2022-23, 2023-24, 2024-25; each fold trains only on prior seasons.
The 2025-26 holdout and 2026-27 prospective test are not used.
"""
from __future__ import annotations
import json, time, warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd, torch
from torch import nn
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from dunkest.config import Settings
import dunkest.models.predictor as predictor
from dunkest.models.multiseason_training import adapt_certified_training_rows, DEFAULT_DATASET
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/audit'; STAMP='dunkest_production_ensemble_torch_mlp_walk_forward_20261016_v1'
CSV=OUT/f'{STAMP}_metrics.csv'; REPORT=OUT/f'{STAMP}.md'; AUDIT=OUT/f'{STAMP}.json'
FOLDS=['2022-23','2023-24','2024-25']; SEED=20261016
class TorchMLPRegressor:
 def __init__(self, hidden=(128,64), dropout=0.0, weight_decay=0.001, lr=0.001, max_epochs=55, patience=8, random_state=SEED):
  self.hidden=hidden; self.dropout=dropout; self.weight_decay=weight_decay; self.lr=lr; self.max_epochs=max_epochs; self.patience=patience; self.random_state=random_state
 def _new(self,n):
  layers=[]; last=n
  for width in self.hidden:
   layers.extend([nn.Linear(last,width),nn.ReLU()])
   if self.dropout>0: layers.append(nn.Dropout(self.dropout))
   last=width
  layers.append(nn.Linear(last,1)); return nn.Sequential(*layers)
 def _fit_epochs(self,x,y,w,epochs,seed):
  torch.manual_seed(seed); np.random.seed(seed); torch.set_num_threads(4)
  model=self._new(x.shape[1]); opt=torch.optim.AdamW(model.parameters(),lr=self.lr,weight_decay=self.weight_decay)
  xt=torch.tensor(x,dtype=torch.float32); yt=torch.tensor(y,dtype=torch.float32); wt=torch.tensor(w,dtype=torch.float32)
  for _ in range(epochs):
   model.train()
   for ix in torch.randperm(len(xt)).split(2048):
    opt.zero_grad(set_to_none=True); p=model(xt[ix]).squeeze(-1); loss=(((p-yt[ix])**2)*wt[ix]).mean(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),5.); opt.step()
  return model
 def fit(self,X,y,sample_weight=None):
  X=np.asarray(X,dtype=np.float32); y=np.asarray(y,dtype=np.float32).reshape(-1)
  w=np.ones(len(y),dtype=np.float32) if sample_weight is None else np.asarray(sample_weight,dtype=np.float32).reshape(-1)
  cut=max(1000,int(len(y)*.85)); cut=min(cut,len(y)-100)
  mean=X[:cut].mean(axis=0); std=X[:cut].std(axis=0); std=np.where(std<1e-8,1.,std)
  ym=float(y[:cut].mean()); ys=float(y[:cut].std()) or 1.
  x=(X[:cut]-mean)/std; yt=(y[:cut]-ym)/ys; xv=(X[cut:]-mean)/std; yv=(y[cut:]-ym)/ys
  torch.manual_seed(self.random_state); np.random.seed(self.random_state); torch.set_num_threads(4)
  model=self._new(x.shape[1]); opt=torch.optim.AdamW(model.parameters(),lr=self.lr,weight_decay=self.weight_decay)
  xt=torch.tensor(x,dtype=torch.float32); ytt=torch.tensor(yt,dtype=torch.float32); wt=torch.tensor(w[:cut],dtype=torch.float32); xvt=torch.tensor(xv,dtype=torch.float32); yvt=torch.tensor(yv,dtype=torch.float32)
  best=float('inf'); best_state=None; best_epoch=1; patience=0
  for epoch in range(self.max_epochs):
   model.train()
   for ix in torch.randperm(len(xt)).split(2048):
    opt.zero_grad(set_to_none=True); p=model(xt[ix]).squeeze(-1); loss=(((p-ytt[ix])**2)*wt[ix]).mean(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),5.); opt.step()
   model.eval()
   with torch.no_grad(): val=float(((model(xvt).squeeze(-1)-yvt)**2).mean().item())
   if val<best-1e-5: best=val; best_state={k:v.detach().clone() for k,v in model.state_dict().items()}; best_epoch=epoch+1; patience=0
   else:
    patience+=1
    if patience>=self.patience: break
  # Refit on all available past rows for the selected epoch count.
  self.x_mean_=X.mean(axis=0); self.x_std_=X.std(axis=0); self.x_std_=np.where(self.x_std_<1e-8,1.,self.x_std_)
  self.y_mean_=float(y.mean()); self.y_std_=float(y.std()) or 1.
  xf=(X-self.x_mean_)/self.x_std_; yf=(y-self.y_mean_)/self.y_std_
  self.model_=self._fit_epochs(xf,yf,w,max(8,best_epoch),self.random_state)
  self.n_iter_=best_epoch
  return self
 def predict(self,X):
  x=(np.asarray(X,dtype=np.float32)-self.x_mean_)/self.x_std_
  self.model_.eval()
  with torch.no_grad(): p=self.model_(torch.tensor(x,dtype=torch.float32)).squeeze(-1).cpu().numpy()
  return p*self.y_std_+self.y_mean_

def score(y,p,history):
 y=np.asarray(y,float); p=np.asarray(p,float); e=p-y; out={'n':len(y),'mae':float(mean_absolute_error(y,p)),'rmse':float(np.sqrt(mean_squared_error(y,p))),'bias_pred_minus_actual':float(e.mean())}
 for t in (25,30):
  m=y>=t; out[f'mae_actual_ge{t}']=float(np.abs(e[m]).mean()) if m.any() else float('nan'); out[f'n_actual_ge{t}']=int(m.sum())
 m=np.asarray(history)<5; out['mae_history_lt5']=float(np.abs(e[m]).mean()) if m.any() else float('nan'); out['n_history_lt5']=int(m.sum()); return out

def main():
 for p in (CSV,REPORT,AUDIT):
  if p.exists(): raise SystemExit(f'Refusing to overwrite {p}')
 settings=Settings.from_yaml(); source=pd.read_parquet(settings.data_path/DEFAULT_DATASET)
 mp=settings.data_path/'processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet'; labels=None
 if mp.exists(): labels=pd.read_parquet(mp,columns=['nba_GAME_ID','nba_PLAYER_ID','nba_MIN','nba_match_status'])
 rows=adapt_certified_training_rows(source,minutes_labels=labels); original=predictor._model_zoo; records=[]
 def zoo(s):
  return {'ridge':Ridge(alpha=3.,random_state=s.random_state),'rf':RandomForestRegressor(n_estimators=200,max_depth=6,random_state=s.random_state,n_jobs=3),'gbr':GradientBoostingRegressor(random_state=s.random_state),'torch_mlp':TorchMLPRegressor(hidden=(128,64),dropout=0.0,weight_decay=0.001,lr=0.001,random_state=s.random_state)}
 try:
  predictor._model_zoo=zoo
  for fold in FOLDS:
   train=rows.loc[rows.season_label.astype(str)<fold].copy(); test=rows.loc[rows.season_label.astype(str).eq(fold)].copy(); t0=time.time()
   models,_=predictor.train_models(settings,train,target_column='target_pdk_official',sample_weight=train['_training_sample_weight'])
   p=predictor._ensemble_predict(models,test); y=test.target_pdk_official.to_numpy(float); h=pd.to_numeric(test.history_games_before_target,errors='coerce').fillna(0).to_numpy(float)
   m=score(y,p,h); records.append({'fold_season':fold,**m,'train_rows':len(train),'test_rows':len(test),'fit_seconds':round(time.time()-t0,1),'model_weights':json.dumps(models.get('_weights',{}),sort_keys=True),'torch_mlp_epochs':getattr(models.get('torch_mlp'),'n_iter_',None)})
   print(f"{fold}: MAE={m['mae']:.5f} RMSE={m['rmse']:.5f} bias={m['bias_pred_minus_actual']:.4f} high25={m['mae_actual_ge25']:.4f} ({records[-1]['fit_seconds']}s)",flush=True)
 finally: predictor._model_zoo=original
 out=pd.DataFrame(records); out.to_csv(CSV,index=False)
 base=pd.read_csv(OUT/'dunkest_production_trainer_walk_forward_20261015_v3_metrics.csv'); base=base[base.candidate.eq('production_ensemble')]
 pooled={'n':int(out.n.sum()),'mae':float(np.average(out.mae,weights=out.n)),'rmse':float(np.sqrt(np.average(out.rmse**2,weights=out.n))),'bias':float(np.average(out.bias_pred_minus_actual,weights=out.n)),'mae_ge25':float(np.average(out.mae_actual_ge25,weights=out.n_actual_ge25)),'mae_ge30':float(np.average(out.mae_actual_ge30,weights=out.n_actual_ge30))}
 prod={'n':int(base.n.sum()),'mae':float(np.average(base.mae,weights=base.n)),'rmse':float(np.sqrt(np.average(base.rmse**2,weights=base.n))),'bias':float(np.average(base.bias_pred_minus_actual,weights=base.n)),'mae_ge25':float(np.average(base.mae_actual_ge25,weights=base.n_actual_ge25)),'mae_ge30':float(np.average(base.mae_actual_ge30,weights=base.n_actual_ge30))}
 audit={'created_utc':datetime.now(timezone.utc).isoformat(),'folds':FOLDS,'holdout_2025_26_used':False,'prospective_2026_27_used':False,'model_zoo':'production Ridge + RF + GBR + Torch MLP (128,64), dropout 0.0, weight_decay 0.001','fold_metrics':records,'ensemble_pooled':pooled,'production_reference_pooled':prod,'promote':bool(pooled['mae']<prod['mae']-0.01 and pooled['rmse']<=prod['rmse']+0.01),'production_code_changed':False}
 AUDIT.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
 report=['# Production ensemble + small Torch MLP walk-forward','','Generated UTC: '+audit['created_utc'],'','## Protocol','','Same certified production adapter and three past-only folds. The best standalone neural candidate from the 51-model grid was added as a fourth component; production ensemble weights are re-learned from past-only OOF predictions. No 2025/26 holdout or 2026/27 prospective outcome was used.','','## Pooled comparison','',pd.DataFrame([{'model':'current production ensemble',**prod},{'model':'production ensemble + Torch MLP',**pooled}]).to_string(index=False,float_format=lambda x:f'{x:.5f}'),'','## Fold metrics','',out.to_string(index=False),'','## Decision','','The candidate is not automatically promoted. It should replace the production ensemble only if the gains are material, stable by season, and not purchased with worse tail error or bias.','']
 REPORT.write_text('\n'.join(report),encoding='utf-8'); print('\nPOOLED',json.dumps({'production':prod,'candidate':pooled,'promote':audit['promote']},indent=2),flush=True); print('REPORT='+str(REPORT.relative_to(ROOT)),flush=True)
if __name__=='__main__': main()
