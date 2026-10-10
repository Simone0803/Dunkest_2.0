# Dati locali e backtest

La directory `data/` è esclusa dal controllo versione: può contenere grandi dataset e cache locali. I backtest storici devono usare dati reali archiviati, non log sintetici e non il listino corrente al posto di quello storico.

## Snapshot richiesti per ogni giornata

Per la stagione Dunkest `SID` e la giornata `GW`, il backtest verifica questi file sotto `data/processed/`:

- `dunkest_fixture_mapping_SID_*.parquet`: mapping NBA–Dunkest con provenienza, timestamp precedente alla partita, mapping verificato e identificativi NBA.
- `player_credits_SID_gwGW.parquet`: rosa, ruoli e CR archiviati prima della giornata.
- `injuries_SID_gwGW.parquet`: snapshot indisponibili con giocatore, squadra, stato e giornata.
- `coach_market_SID_gwGW.parquet`: coach, squadra, CR, avversario, data, NBA game ID e fonte del fixture.
- `dunkest_players_SID_gwGW.parquet`: risultati giocatore con `actual_pdk`, `gameweek_stats_available` e `nba_game_id`.
- `dunkest_coach_results_SID_gwGW.parquet`: risultati coach con `team`, `nba_game_id` e `actual_coach_pdk`.

Sono inoltre necessari log NBA reali per la stagione configurata, conservati o recuperabili tramite la NBA API. I file con nomi diversi non sono automaticamente equivalenti: non rinominare snapshot per far passare i controlli. La readiness del programma verifica colonne e collegamenti tra identità prima di calcolare metriche.

## Preparare ed eseguire

Dalla radice del repository:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
bash ./run-backtest.sh --config config/backtest.example.yaml --from-gw 1 --to-gw 10
```

La configurazione d'esempio usa Dunkest season ID `25` / NBA 2025-26. Usala solo se gli snapshot in `data/processed/` corrispondono a quella stagione. Per una stagione diversa, crea una copia della configurazione e aggiorna almeno `season`, `season_id` e le date NBA.

Se uno o più snapshot mancano, il comando elenca i controlli falliti e termina con codice d'errore, senza presentare metriche di rosa come risultati validi. Gli snapshot prepartita non possono essere ricostruiti fedelmente a posteriori dal listino odierno; raccoglili prima delle giornate future e conserva i risultati ufficiali a giornata conclusa.
