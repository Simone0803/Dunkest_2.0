# Consolidamento validazione Dunkest — 2026-10-16

## Esito

La validazione tecnica e gli esperimenti autorizzati sono stati completati. Non è emersa evidenza sufficiente per cambiare il modello di produzione o dichiarare validato un backtest fantasy storico. Sono stati aggiunti gli script sperimentali, i risultati macchina/leggibili e questo rapporto; non sono stati modificati pesi, configurazioni di produzione, dati sorgente o bundle prospettico.

Branch di lavoro: `codex/claude-audit-hardening-20261015` (base iniziale `928592e`, allineata al remote). Gli artefatti elencati in questo rapporto sono stati prodotti nel workspace durante la validazione.

## Perimetro dei dati e del tempo

- Le etichette ufficiali Dunkest PDK certificate per apprendimento coprono il 2020/21–2024/25: 93.766 righe nel dataset V3. Le righe 2018/19 e 2019/20 hanno tutte `gameValidForDunkest=False` (26.094 e 22.384 righe); possono contribuire come storia NBA verificata, non come target Dunkest certificati.
- Il dataset V3 complessivo include anche il 2025/26 (112.178 righe). Questa stagione era già stata analizzata in precedenti esperimenti: non è un holdout finale incontaminato a livello di progetto. I nuovi confronti walk-forward e le ricerche di iperparametri dichiarano `holdout_2025_26_used=false`; il report one-shot del 2025/26, riportato separatamente qui sotto, era una valutazione già eseguita e non è stato riutilizzato per selezionare candidati.
- Il 2026/27 prospettico è rimasto escluso dagli esperimenti. Il bundle GW1 resta congelato fino al 2026-10-23 12:00 UTC.
- L’audit temporale preesistente rileva shift delle rolling features, storie filtrate strettamente prima della data target, preprocessing stimato nel fold di training e nessuna duplicazione player/date nel dataset V3. La ricerca Monte Carlo e l’espansione hanno usato i fold 2022/23, 2023/24 e 2024/25; ogni fold addestra solo su stagioni precedenti e usa split di early stopping appartenenti al passato del fold.
- Rimane una differenza di provenienza: i target sono PDK ufficiali, mentre alcune feature di storia PDK sono ricostruite da boxscore. L’ablation del 13 ottobre ha misurato una variazione MAE macro-stagione di -0,0031 con IC bootstrap clusterizzato per data al 95% [-0,0079; 0,0014], compatibile con nessuna differenza. Non c’è base per sostituire la fonte delle feature.

## Ricerche di modelli

Tutte le metriche aggregate qui sotto sono descrittive sui tre fold di selezione (57.682 predizioni aggregate), non una stima inferenziale dell’effetto. Le molte configurazioni confrontate sugli stessi fold aumentano il rischio di selezione; non è stata calcolata una correzione per confronti multipli o un intervallo paired per la selezione. `bias` è predizione meno valore effettivo.

| Esperimento | Configurazioni / fit | Risultato principale | Uso holdout/prospettico |
|---|---:|---|---|
| Grid PDK estesa con dropout | 51 / 153 | Miglior candidato: MLP (128,64), dropout 0, weight decay .001, LR .001; MAE 7,5482, RMSE 9,8241, bias -0,1234, MAE effettivi ≥25: 12,0717 e ≥30: 14,0255. Il baseline ensemble sugli stessi fold: MAE 7,5524, RMSE 9,8209, bias -0,1447, code 12,2119 / 14,1967. | Esclusi entrambi |
| Espansione iperparametri | 104 / 312 | Miglior MLP: MAE 7,5482, RMSE 9,8241, bias -0,1234, code 12,0717 / 14,0255. L’RMSE è lievemente peggiore del baseline; candidati alternativi scambiano MAE e metriche di coda. | Esclusi entrambi |
| Ricerca Monte Carlo deterministica, seed 20261016 | 80 / 240 | 80 configurazioni uniche. Migliore MAE aggregata: trial 078 MLP (128,64,32), dropout 0; MAE 7,5557, RMSE 9,8165, bias -0,0617, code 12,0710 / 14,0163. | Esclusi entrambi |
| Ensemble di produzione + MLP Torch | 3 modelli/fold | Report preesistente: MAE 7,5456, RMSE 9,8034, bias -0,0520; codice di promozione impostato a `false`. | Esclusi entrambi |
| Confronto iperparametri produzione | Report preesistente | GBR regolarizzato vicino alla produzione; effetti misti fra metriche. Raccomandazione del report: mantenere la produzione. | — |

La griglia estesa e l’espansione ritrovano sostanzialmente lo stesso piccolo MLP. La ricerca Monte Carlo non mostra un vantaggio netto e ripetibile su MAE, RMSE e code. Il report one-shot già presente sul 2025/26 confrontava produzione (MAE 7,5544; RMSE 9,8249; bias -0,1137; code 12,0267 / 14,0951) con ensemble+MLP (7,5402; 9,8130; -0,1405; 12,0377 / 14,0839). L’errore nei punteggi alti ≥25 peggiorava leggermente; la regola di promozione predefinita era falsa. Poiché il progetto aveva già osservato quella stagione, questi numeri non rendono il holdout incontaminato.

### Calibrazione

Le tre ricerche di calibrazione hanno prodotto 150 righe (affine), 33 (ensemble) e 183 (gated), complete sui tre fold, con configurazioni uniche e metriche finite; tutte escludono holdout e prospettivo. Nessun metodo ha migliorato insieme errore complessivo, RMSE, bias e punteggi alti.

- Affine: nessuna correzione MAE 7,5761, RMSE 9,8780, bias -0,4223, errori ≥25/≥30 12,4927/14,5176. Il metodo affine gated riportato: MAE 7,5773, RMSE 9,8735, bias -0,3304, code 12,3596/14,3018.
- Ensemble calibration: `band_mean` porta bias a -0,0356 e gli errori ≥25/≥30 a 12,0985/14,0102, ma aumenta MAE a 7,6074; non è un miglioramento complessivo.
- Gated high-score: nessuna correzione MAE 7,5761, RMSE 9,8780, bias -0,4223; `gated_global` ha MAE 7,5763, RMSE 9,8755, bias -0,3826 e code 12,4341/14,4232. Variazioni piccole, senza vantaggio congiunto.

Conclusione sulle predizioni individuali: lasciare invariati ensemble e calibrazione di produzione. I miglioramenti puntuali sono troppo piccoli e misti per sostenere promozione o significatività.

## Coorti di produzione

Il report OOS esistente del modello di produzione aggrega tre fold cronologici. Valori aggregati: tutti i giocatori n=57.682, MAE 7,5573, RMSE 9,8230, bias -0,1067; rookie n=4.147, MAE 6,2433, bias -0,407; storia ≤5 partite n=1.454, MAE 5,2446, bias +0,058; cambio squadra n=555, MAE 7,1731, bias +1,6858; punteggio effettivo ≥25 n=13.104, MAE 12,1893, bias -11,1911; ≥30 n=8.794, MAE 14,1810, bias -13,6477. Nei punteggi alti rimane sottostima sostanziale. Non sono disponibili CSV OOS con etichette/coorti di ruolo affidabili point-in-time; non sono quindi riportate statistiche per ruolo inventate o ricostruite ex post.

## Validità del backtest fantasy

Non si può certificare un confronto storico completo di lineup Dunkest con le evidenze disponibili.

- L’audit di readiness della stagione corrente trova GW1 2026/27 non pronto: esistono mapping fixture, roster/crediti, snapshot infortuni con timestamp e coach legati alle fixture; mancano risultati player e coach collegati. Non calcolare metriche aggiungendo stati prepartita o risultati mancanti.
- Nell’audit di autenticità, 39 archivi hanno hash validi, 31 precedono il primo giorno di fixture conosciuto, ma nessun bundle contiene i metadati di recupero della fonte; otto archivi iniziali non hanno data della prima fixture. L’esecuzione G1 del 14 ottobre è stata rifiutata perché congelata circa 133 ore prima del primo tip-off, oltre la finestra di 36 ore.
- Il backtest storico proxy rigoroso copre 409 round key, ma solo 3 round hanno outcome osservati per tutti i dieci giocatori di entrambe le strategie. Lineup complete: 17/409 modello e 9/409 baseline. Delta medio -6,225 punti, IC bootstrap round 95% [-56,515; 27,655]. Candidate universe, prezzi/ruoli ritardati, prezzi coach storici e malus trasferimenti non sono ricostruibili completamente. È un proxy sparso, non un backtest certificato.
- La ricostruzione PDK da boxscore è esplicitamente un’approssimazione delle regole; il feed ufficiale Dunkest resta fonte autorevole. Il scoring di lineup e coach contiene test per moltiplicatori, capitano/sesto, panchina, malus e casi fail-closed, ma i test non sostituiscono risultati storici verificati.

Per una futura valutazione: acquisire prima del lock snapshot con timestamp, fonte, hash e crediti di roster/giocatori, disponibilità e coach; conservarli entro 36 ore dal lock; verificare mapping round/fixture; poi acquisire risultati ufficiali player/coach e stato storico dei trasferimenti/malus. Non ricostruire snapshot pre-lock a posteriori.

## Verifiche eseguite

- `./.venv/bin/python -m compileall -q src scripts tests`: completato.
- `PYTHONPATH=src .venv/bin/pytest -q`: 613 passed, 1 warning in 10,28 s. L’unico warning è joblib su macOS che non rileva i core fisici e usa il fallback ai core logici.
- `PYTHONPATH=src .venv/bin/python -m pip check`: nessuna dipendenza rotta.
- `git diff --check`: superato prima dello staging; verificare anche la versione staged durante la pubblicazione.
- Script di ricerca completati: griglia estesa 153/153, espansione 312/312, Monte Carlo 240/240 fit. Gli artefatti JSON attestano holdout e prospettico esclusi. La ricerca Monte Carlo ha 80 righe per ciascun fold, 240 coppie candidate/fold uniche e metriche principali finite.

## Riproducibilità e artefatti

Eseguire dalla root del repository con l’ambiente virtuale attivo e `PYTHONPATH=src`:

```bash
PYTHONPATH=src .venv/bin/python scripts/grid_search_dunkest_pdk_hyperparameter_expansion_20261016_v1.py
PYTHONPATH=src .venv/bin/python scripts/grid_search_dunkest_pdk_monte_carlo_search_20261016_v1.py
PYTHONPATH=src .venv/bin/python scripts/experiment_dunkest_affine_score_calibration_walk_forward_20261016_v1.py
PYTHONPATH=src .venv/bin/python scripts/experiment_dunkest_ensemble_score_calibration_walk_forward_20261016_v1.py
PYTHONPATH=src .venv/bin/python scripts/experiment_dunkest_high_score_gated_calibration_walk_forward_20261016_v1.py
```

Ogni esperimento scrive report Markdown, JSON e CSV in `reports/audit/`. Per griglia estesa, ensemble+MLP, calibrazione, integrità temporale e backtest proxy, consultare gli omonimi report datati nella stessa directory. I CSV/JSON sono la fonte dei conteggi e delle metriche; il presente documento ne sintetizza risultati e limiti.

## Decisione

Consolidare gli artefatti sperimentali e preservare la produzione attuale. Nessun nuovo modello o calibratore è promosso. Nessun risultato di lineup viene presentato come backtest storico certificato. Prima di una decisione fantasy servono snapshot pre-lock autentici, risultati Dunkest player/coach completi e stato storico di crediti e trasferimenti.
