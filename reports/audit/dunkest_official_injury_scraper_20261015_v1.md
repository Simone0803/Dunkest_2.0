# Verifica scraping infortuni Fantasy Dunkest — 2026-10-15

## Implementazione

- Fonte: https://fantasy.dunkest.com/1/injuries
- Metodo: Playwright/Chromium con lo stesso profilo persistente e bootstrap di accessibilità Flutter usati da Lineups.
- Endpoint strutturato intercettato: `/api/v1/leagues/1/injuries`.
- Il parser legge `data.players`, nome completo, abbreviazione squadra, descrizione, motivo e data.
- Non viene più usato il fallback alla pagina HTML legacy. Se l'API non risponde con uno schema valido o non fornisce righe leggibili, la cattura fallisce in modo esplicito.
- I refresh forzati non riutilizzano in silenzio uno snapshot vecchio se la cattura ufficiale fallisce.
- La corrispondenza per nome completo è stata resa più conservativa: un nome completo non può escludere un altro giocatore soltanto perché condivide il cognome; sono mantenuti i match esatti e quelli con iniziale coerente.

## Verifica live in sola acquisizione

- Risposta endpoint: HTTP 200.
- Record infortuni: **124**.
- Squadre presenti nella lista: **28**.
- Stati: **104 GAME TIME DECISION**, **20 OUT**.
- Mercato Lineups confrontato: **563 giocatori**.
- OUT ufficiali associati al mercato: **20/20**; il filtro hard-out rimuove esattamente 20 giocatori.
- Esempi confermati dalla fonte ufficiale: Shaedon Sharpe (POR), Jordan Miller (LAC), Brandon Ingram (LAC).

Lo snapshot globale `data/processed/injuries.parquet` è stato aggiornato con la fonte ufficiale e metadati riferiti alla Giornata 1. Non sono state rigenerate le previsioni, le rose o gli artefatti pre-match della G1.

## Test

Suite completa: **423 passed**. Compilazione Python e `git diff --check` superati.
