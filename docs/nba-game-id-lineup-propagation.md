# Propagazione di `nba_game_id` nelle formazioni

## Causa

Nel percorso di forecast live il contesto fixture verificato (avversario, turno e
`nba_game_id`) veniva aggiunto al forecast grezzo usato per il forecast coach.
Il frame eleggibile passato a `run_optimize`, invece, proveniva da
`forecast.eligible` senza quel contesto. L'ottimizzatore conserva le colonne dei
giocatori selezionati e `save_run_artifacts` copia `nba_game_id` da
`solution.players`; quindi il campo arrivava già nullo al serializer. Il
`lineups.parquet` GW2 del 23 ottobre 2026 conferma il sintomo: avversario e
turno sono valorizzati per i 30 record, ma `nba_game_id` è nullo in tutti.

## Correzione e comportamento

Il contesto delle fixture verificate viene applicato al frame eleggibile prima
dell'ottimizzazione, usando la squadra per recuperare congiuntamente avversario,
turno e ID partita. Le fixture non verificate non forniscono contesto; una
fixture verificata ed eleggibile senza ID, duplicata o con una squadra assegnata
a più partite genera un errore esplicito. La serializzazione mantiene gli ID
dei giocatori e l'ID matchup del coach; gli slot dinamici per turno restano
indipendenti dall'identità della partita.

Il replay degli artefatti GW2 è diagnostico: non certifica un forecast pre-lock.
Il run è stato generato alle 16:03 UTC del 23 ottobre 2026; gli snapshot
archiviati riportano acquisizioni alle 13:04, 13:08 e 16:02 UTC. La sola
presenza di questi timestamp non dimostra che tutti gli input precedessero il
cutoff della Giornata. Non vengono ricostruiti snapshot né validate
retroattivamente previsioni pre-cutoff.
