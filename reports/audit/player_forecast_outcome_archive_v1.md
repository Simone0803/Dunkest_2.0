# Archivio temporale forecast/esiti giocatore — V1

## Perimetro

Il percorso estende l'archivio del run e il collector post-partita già esistenti. Non modifica il predictor, il blending, i prior o l'optimizer.

## Dato congelato prima del risultato

Ogni run conserva `player_forecast_snapshot.parquet` accanto a `predictions.parquet` e alle lineup. La tabella include una riga per candidato/player-fixture del forecast grezzo, compresi gli esclusi dalla rosa ottimizzabile; conserva identità canonica, team/avversario, turno, ID NBA e Dunkest quando presenti, ruolo/tag, status, CR, minuti/PDK previsti, probabilità di partecipazione, timestamp di disponibilità e versione del codice. Il manifest lega la tabella al suo hash, al fingerprint degli input, al timestamp del forecast e al cutoff dichiarato.

Il run viene certificato solo se il cutoff Dunkest esatto è fornito, verificato e accompagnato da provenienza con SHA-256, gli input timestampati precedono il forecast, le fixture sono verificate e forecast e completamento del run precedono il lock. Il repository non acquisisce attualmente un timestamp ufficiale del lock Dunkest: in assenza di tale fonte il run resta archiviabile come diagnostico, ma non viene certificato pre-lock. L'orario di inizio della prima fixture non viene usato come sostituto del lock.

L'archiviatore pre-lock include la tabella candidata nel bundle hashato e nel registry. Il collector post-partita rifiuta bundle non registrati, alterati, incompleti o privi della prova del cutoff esatto; non ricostruisce snapshot mancanti.

## Riconciliazione degli esiti

Il collector produce una riga per ogni candidato congelato e conserva separatamente:

- `actual_minutes` da una riga NBA giocatore/partita esplicita; `MIN=0` è zero verificato e il testo DNP/Inactive lo marca anche come DNP documentato;
- `outcome_missing` quando manca una riga di esito: l'assenza dai log non è convertita in zero;
- `outcome_ambiguous` quando identità, squadra o righe NBA confliggono; `fixture_unverified` quando non c'è una fixture verificata;
- `actual_pdk_official` soltanto da PDK Dunkest valido e riconciliato; `actual_pdk_nba_proxy` resta una colonna distinta e non viene usato come target ufficiale.

Gli esiti ufficiali PDK sono associati tramite identità giocatore canonica, team/avversario, data e fixture verificata univoca. Le righe non collegate o conflittuali restano mancanti/ambigue. La raccolta può essere parziale solo in modalità esplicita; il report dichiara copertura e numerosità per target e le metriche usano esclusivamente coppie previste/effettive finite.

## Limiti dati attuali

Il feed NBA non garantisce righe DNP o zero-minuti per tutti i candidati. Senza riga esplicita o record ufficiale DNP, il risultato rimane mancante anche per un giocatore presente nel roster pre-lock. Il feed ufficiale Dunkest può inoltre non avere ancora il PDK individuale per tutti i turni. Di conseguenza una raccolta parziale produce diagnostica con copertura, non una misura completa del roster.

Nessun risultato GW1/GW2 esistente viene retrodatato o usato per certificare una nuova previsione. L'infrastruttura e i test coprono il prossimo run valido; non attestano una nuova certificazione live.
