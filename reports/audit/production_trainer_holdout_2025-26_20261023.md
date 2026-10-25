# Trainer di produzione — holdout walk-forward 2025-26

Generato UTC: 2026-10-23 14:41  
Branch: `codex/claude-audit-hardening-20261015`

## Metodo

Ho caricato `data/processed/dunkest_pdk_game_training_2020-26_v3.parquet` e usato `adapt_certified_training_rows(include_2025_26=True)`, che filtra le righe su PDK Dunkest ufficiale valido. Il trainer effettivo `train_models` è stato adattato separatamente sulle stagioni 2020-21–2024-25 (93.766 righe); la stagione 2025-26 è rimasta fuori dall’addestramento e ha fornito il test (18.412 righe). Le feature per ogni partita di test sono walk-forward: le gare precedenti della stagione possono alimentare i lag delle partite successive, mai il contrario. Nessun parametro o peso è stato modificato.

## Metriche sul test 2025-26

| Modello | N | MAE | RMSE | Bias predetto − osservato | R² |
|---|---:|---:|---:|---:|---:|
| Ensemble di produzione | 18.412 | 7,5149 | 9,7659 | −0,0126 | 0,4320 |
| Baseline media ultime 10 gare | 18.412 | 7,7886 | 10,1539 | −0,0479 | 0,3859 |

La baseline usa la media delle ultime 10 etichette PDK disponibili prima della partita; quando non ne ha usa la mediana dei target di training. L’ensemble riduce MAE del 3,5% e RMSE del 3,8% rispetto a questa baseline; la baseline ha un bias aggregato leggermente più vicino a zero. Sulle 440 righe con meno di 5 gare precedenti, MAE è 5,2182 per l’ensemble e 6,2323 per la baseline.

## Calibrazione descrittiva

Nei dieci decili di previsione, la differenza media predetto meno osservato varia da −0,419 a +0,417 PDK. I decili contengono circa 1.841 righe ciascuno. È una verifica di affidabilità media sul singolo holdout; non misura la copertura di intervalli P10/P90 indipendenti.

## Limiti

- Questa è una valutazione individuale walk-forward con target ufficiali reali, non una simulazione di una squadra fissata prima dell’inizio stagione.
- Non valida le acquisizioni live di roster, crediti, infortuni, matchup e coach; non convalida le formazioni né il loro punteggio realizzato.
- Il risultato non sblocca il backtest lineup 2018-19–2025-26, per il quale mancano snapshot pre-lock e archivi risultato verificati.
- Le stagioni 2018-19 e 2019-20 restano escluse dai target perché `gameValidForDunkest` è falso per tutte le righe; nessuna riga è stata riclassificata retroattivamente.

Artefatti: [previsioni holdout](/Users/simone/Documents/Dunkest/reports/audit/production_trainer_holdout_2025-26_20261023_predictions.csv), [audit JSON](/Users/simone/Documents/Dunkest/reports/audit/production_trainer_holdout_2025-26_20261023.json). Il JSON registra stagioni e numerosità di training/test, pesi appresi dal fold, metriche mensili e decili di calibrazione.
