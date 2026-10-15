# Validazione del calendario ufficiale Dunkest rispetto all’archivio locale

## Scopo
Verificare se il flag ufficiale `gameValidForDunkest` presente nell’archivio locale è coerente con il campo `is_valid` dei team restituiti dal calendario ufficiale Dunkest.

## Fonte e metodo
- Endpoint ufficiale in sola lettura: `GET /api/v1/schedules/{schedule_id}/matchdays/{matchday_id}`.
- `schedule_id=1`: matchday con partite dal 18 ottobre 2022 al 9 aprile 2023, identificato come stagione NBA 2022/23.
- `schedule_id=8`: matchday con partite dal 24 ottobre 2023 al 12 aprile 2024, identificato come stagione NBA 2023/24.
- Archivio locale letto senza modificarlo: `data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet`.
- Matching: data di inizio API convertita in `America/New_York` + squadra di casa + squadra ospite, confrontata con data e avversario nel dataset locale.
- Il confronto del flag è effettuato a livello di team-game, aggregando i record giocatore e segnalando eventuali flag locali discordanti.

## Risultati

| Stagione | Schedule ID | Matchday API | Partite API | Partite con entrambe le squadre abbinate localmente | Lati squadra con flag confrontabile | Flag concordi |
|---|---:|---:|---:|---:|---:|---:|
| 2022/23 | 1 | 65 | 1041 | 1040 | 2080 | 2080/2080 |
| 2023/24 | 8 | 63 | 1014 | 1014 | 2028 | 2027/2028 |

Complessivamente, il confronto ha trovato **2055 partite** nell’API. Per **2054 partite lato casa** e **2054 lato trasferta** è stata trovata la corrispondenza data/squadre nell’archivio. Sui **4108 lati squadra** effettivamente confrontabili, **4107** flag coincidono (**99.976%**).

## Eccezioni da non nascondere
- Una partita API del 1 febbraio 2023, Detroit–Washington, non trova una corrispondenza locale tramite data e coppia di squadre.
- Una discordanza del flag: Boston–Cleveland del 12 dicembre 2023. L’API riporta `home_valid=true` e `away_valid=false`, mentre l’archivio locale riporta `gameValidForDunkest=false` per entrambe le squadre. Va verificata prima di usare questi campi come equivalenti perfetti.

## Conclusione operativa
La forte concordanza è una prova indipendente che l’endpoint del calendario contiene informazione utile per validare la semantica del flag. **Non basta però per sovrascrivere il flag locale o ricostruire automaticamente i target PDK**: restano almeno un caso discordante e una partita senza match locale. Inoltre, questo test copre solo le stagioni 2022/23 e 2023/24 e non dimostra la disponibilità del calendario storico per tutte le annate 2018–2025.

## Integrità
Sono stati creati solo report di audit. Nessun dataset raw, target PDK, modello, split temporale o backtest è stato modificato.
