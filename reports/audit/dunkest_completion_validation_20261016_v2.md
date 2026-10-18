# Validazione completamento Dunkest — 2026-10-16, V2

## Problema affrontato

La modalità `training_target=auto` poteva selezionare il target proxy sia quando la colonna ufficiale era sotto la soglia di 1.000 valori finiti, sia quando era assente. Entrambi i casi rendevano possibile un cambio implicito della provenienza del target.

Ora `auto` seleziona solo `target_pdk_official`: se la colonna manca o contiene meno di 1.000 valori finiti, il training si interrompe con un errore. Il messaggio indica `training_target='target_pdk'` come scelta esplicita per il proxy. Con almeno 1.000 etichette ufficiali, `auto` continua a selezionare `target_pdk_official`.

Il percorso standard GW1 è stato verificato tramite configurazione e codice: `config/season_opener.yaml` imposta `training_target: target_pdk_official` e `opening_multiseason_training: true`; `run_train` chiama il trainer multistagione, che passa `target_column="target_pdk_official"` a `train_models`. Il trainer non è stato eseguito integralmente. Non sono state cambiate feature, pesi, iperparametri, configurazione, dati né snapshot prospettici. Non sono stati prodotti risultati OOS.

## File modificati

- `src/dunkest/models/predictor.py` — errore esplicito quando la colonna ufficiale manca o è sotto soglia.
- `tests/test_official_pdk_labels.py` — regressioni per target ufficiale sufficiente, insufficiente, assente in modalità `auto` e proxy esplicito.
- `reports/audit/dunkest_completion_validation_20261016_v2.md` — questo riepilogo.

## Verifiche

- `PYTHONPATH=src .venv/bin/pytest -q tests/test_official_pdk_labels.py tests/test_official_pdk_training_target_integration.py tests/test_multiseason_training.py tests/test_config_options.py` — **27 passed**.
- `git diff --check` — superato.

## Evidenze quantitative e limiti

- Soglia automatica: **1.000** target ufficiali finiti.
- L’audit preesistente registra **18.412** target ufficiali finiti nel sottoinsieme abbinato 2025/26; questa modifica non ricalcola metriche.
- I test sintetici verificano che `auto` rifiuti 99 etichette ufficiali su 100 e che rifiuti anche l’assenza della colonna; il test sul target sufficiente verifica la soglia di 1.000. Il proxy esplicito continua a risolvere `target_pdk`.
- Non è stata eseguita l’intera suite né `run_train` end-to-end; i test coprono resolver, configurazione e adapter multistagione. Nessuna nuova validazione OOS o di lineup è stata effettuata.
- Il test prospettico GW1 2026/27 è rimasto isolato e invariato fino al lock indicato nel report V1.

## Blocchi residui

Restano validi i blocchi del report V1: mancano outcome ufficiali completi e snapshot pre-lock autentici per certificare il backtest fantasy storico; le feature storiche PDK proxy e i target ufficiali conservano una differenza di provenienza già misurata senza vantaggio conclusivo nel cambio di feature.

## Prossimo passo consigliato

Quando serve il proxy, impostare esplicitamente `training_target='target_pdk'`; il percorso standard GW1 resta configurato e cablato sul target ufficiale.
