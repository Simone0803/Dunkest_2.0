# Audit della catena temporale e delle fixture Dunkest

Data audit: 2026-10-07. Questa mappa descrive lo stato del codice prima delle correzioni della pipeline fixture. `NBA_WEEK_NUMBER` indica il campo `weekNumber` fornito da NBA ScheduleLeagueV2; non è un identificativo Dunkest.

## 1. Mappa NBA schedule → Dunkest GW/Turno

| Punto | Funzione/file | Input | Trasformazione/output | Rischio |
|---|---|---|---|---|
| Fonte NBA | `collector.fetch_future_schedule` — `src/dunkest/data/nba/collector.py:239-269` | ScheduleLeagueV2 `gameId`, `gameDate`, squadre casa/trasferta, `weekNumber`, stato | Normalizza in `GAME_ID`, `GAME_DATE`, `HOME_TEAM`, `AWAY_TEAM`, `GAME_STATUS`, `WEEK_NUMBER`; scarta `WEEK_NUMBER <= 0` | Conserva correttamente un numero NBA, ma il nome e gli usi downstream lo fanno sembrare una giornata fantasy. Non contiene Dunkest GW/Turno o validità fantasy. |
| Feature matchup giocatore | `build_feature_matrix` → `_attach_next_game_schedule` — `src/dunkest/features/builder.py:486-504, 610-645` | Schedule NBA + `target_gameweek` | Filtra `WEEK_NUMBER == target_gameweek`; costruisce righe squadra-avversaria; per team ordina per data e sceglie la prima partita dopo `last_game`; scrive `OPPONENT`, `is_home`, `rest_days`, `is_b2b`, forma vs avversario e contesto difensivo | È il mapping diretto errato NBA week → Dunkest giornata. Se una squadra ha più gare nella NBA week, sceglie cronologicamente la prima, anche se Dunkest ha marcato valida un'altra gara. Inoltre il feature row non conserva `GAME_ID`/data del fixture assegnato. |
| Training ordinario | `run_train` — `src/dunkest/pipeline/train.py:46-69` | `get_future_schedule` e `settings.target_gameweek` | Passa lo schedule NBA al feature builder con il numero Dunkest configurato | Propaga la conflazione nella previsione live; nessuna tabella fixture Dunkest viene letta. |
| Season opener | `run_season_opener` — `src/dunkest/pipeline/season_opener.py:120-152` | NBA future schedule, mercato Lineups e team overrides | Costruisce features G1 con la stessa schedule NBA e `target_gameweek=1` | Stesso mapping ambiguo in G1. Il mercato opener non conserva game ID/validità fantasy. |
| Selezione matchup coach (data access) | `get_coach_data` — `src/dunkest/data/access.py:702-822` | NBA schedule + `gw`; lista coach/CR | Filtra `WEEK_NUMBER == gw`; crea una riga per squadra e partita; salva `giornata=gw`, `gameweek=gw` | Più partite NBA per squadra generano più righe; il campo `giornata` viene assegnato al numero NBA senza prova che corrisponda a Dunkest. Cache coach può quindi perpetuare l'associazione errata. |
| Selezione matchup coach (modello) | `_next_game_context` — `src/dunkest/models/coach.py:340-405` | NBA schedule e opzionale opponent/date dal coach market | Filtra `WEEK_NUMBER == gameweek`; inizializza il matchup per team con il primo in ordine cronologico; se il mercato indica l'avversario usa un match team/opponent e preferisce la data esatta, ma se la data non combacia sceglie comunque la prima riga | Fallback al primo matchup NBA anche quando non esiste una corrispondenza univoca. Opponent/date espliciti mitigano soltanto quando sono corretti e coincidono con schedule. |
| Cutoff walk-forward | `run_walk_forward_backtest` — `src/dunkest/backtest/walk_forward.py:178-232` | NBA schedule e intervallo `from_gw..to_gw` | Filtra `WEEK_NUMBER == gw`, usa la data minima come cutoff e definisce train/outcome della Giornata Dunkest con quello stesso `gw` | Cutoff temporale può essere troppo anticipato o riferirsi a gare non eleggibili. Le statistiche Dunkest scaricate per GW sono poi confrontate con un training cut scelto tramite numero NBA, quindi backtest non temporalmente ancorato alla vera Giornata. |
| CLI / scraper Lineups | `__main__.py:29-30, 134-155`; `lineups_browser.py:220-283, 810-917, 959-1008` | `--giornata` passato come `gameweek` allo scraper; intestazioni UI “TURNO N” | `_fixtures_from_accessibility_nodes` interpreta il parametro come numero di TURNO. Lo scraper scansiona tutte le fixture mostrate, ma distingue `target_fixture_labels` solo per il turno scelto; salva CSV mercato e status con colonna `gameweek`, senza fixture rows o game ID | Il CLI chiama l'argomento Giornata ma lo scraper lo confronta con TURNO. Sono concetti diversi. I fixture label di target non vengono archiviati; il `gameweek` del CSV non prova se rappresenti Giornata o Turno. |
| Stats Dunkest ufficiali | `fetch_week_rounds`, `fetch_dunkest_gameweek_players` — `src/dunkest/data/dunkest/client.py:23-90` | API Dunkest `season_id`, `week_number`, `rounds` | Recupera gli identificativi `rounds` per una settimana Dunkest e le statistiche aggregate per `weeks=[gameweek]`; il risultato riceve `gameweek` | È una fonte Dunkest (non NBA), ma il codice non collega round/player PDK a un NBA `GAME_ID`, data/ora e validità della singola partita. `rounds` è usato per stats e non salvato come fixture mapping. |
| Statistiche coach Dunkest | `fetch_coach_cr_table` — `client.py:111-124` | Dunkest `weeks=[gameweek]` | Fetch coach stats/prezzi | Non restituisce la relazione coach fixture ↔ NBA game ID nella pipeline locale. |
| Target player-game | `build_direct_pdk_target`, `build_stat_targets` — `src/dunkest/targets/pdk_targets.py:8-16`; `_rolling_features` — `features/builder.py:177-217` | NBA player logs con `GAME_ID`, `GAME_DATE`, matchup e box score | Target PDK/minuti; il feature builder mantiene player/data/box-score target ma non `GAME_ID` nell'output delle features | Le osservazioni storiche possono essere identificate nel raw log da game ID, ma tale identity viene persa nel feature frame. Il target NBA player-game non è identificato come partita fantasy valida. |
| Team schedule storico | `collector.fetch_schedule` — `collector.py:224-237` | LeagueGameFinder | Estrae righe casa NBA e `GAME_ID` | È schedule NBA, nessuna giornata/turno/validità Dunkest. |
| Artifacts | `_input_paths`, `save_run_artifacts` — `src/dunkest/report/artifacts.py:65-85, 127+` | Parquet player/team logs, NBA schedule, Dunkest market snapshots | Fingerprinta schedule e snapshot; le predizioni finali contengono team/opponent ma non fixture identity/turno/validità | Provenance dei file non equivale a provenance del mapping. Gli artifact non permettono di ricostruire quale NBA game abbia prodotto la prediction/target. |

### Altri usi semantici

- `Settings.target_gameweek` (`src/dunkest/config.py:18, 113`) è un intero usato per Dunkest GW in API/mercato, ma riutilizzato come `WEEK_NUMBER` NBA nei punti sopra.
- `access.py:52-428`, `models/capital_gain.py:24-51`, `backtest/metrics.py:35-73` e `pipeline/ablation.py` usano `gameweek` per dati/metriche Dunkest (o snapshot etichettati GW); non sono di per sé un mapping NBA, ma ereditano etichette senza fixture identity.
- I test coach usano `WEEK_NUMBER=1` come sinonimo della partita/GW campione (`tests/test_coach_prior_projection.py:85-320`); passano anche una prova con più gare e mercato opponent/date, ma non verificano la validità Dunkest.
- `tests/test_upcoming_schedule.py` verifica normalizzazione NBA schedule e che venga scelta la prossima gara, non che essa sia quella fantasy valida.
- `docs/data_sources.md` documenta l'API Dunkest `week/rounds` e l'NBA API come sorgenti separate; non esiste documentazione né schema locale di una tabella bridge.

La ricerca completa è stata eseguita con `rg -n -i "WEEK_NUMBER|week number|gameweek|giornata|turno|fixture|matchup|opponent|schedule" src tests docs README.md config reports/audit`. Le occorrenze di schedule/opponent non tutte effettuano un'associazione GW; quelle che ne effettuano una sono isolate nella tabella sopra.

## 2. Identità stabile proposta

Non usare ordinali cronologici come identità. L'identità canonica di una partita NBA è `(nba_season, nba_game_id)`; validare che game ID sia non vuoto e univoco per stagione. Squadra/giocatore devono essere collegati attraverso quella identity.

Schema normalizzato proposto per il bridge:

| Campo | Significato |
|---|---|
| `nba_season`, `nba_game_id` | Identity NBA stabile, composta da stagione e game ID ufficiale |
| `game_start_utc`, `game_date_local` | Timestamp timezone-aware e data locale ufficiale |
| `home_team_id`, `home_team_code`, `away_team_id`, `away_team_code` | Lati della partita; ID e codice fonte |
| `dunkest_season_id` | Season ID Dunkest |
| `dunkest_matchday_id` / `dunkest_matchday_number` | Identity e label della Giornata Dunkest, nullable finché non provate |
| `dunkest_turn_id` / `dunkest_turn_number` | Identity e label del Turno dentro la giornata, nullable finché non provate |
| `fantasy_eligible` | Boolean nullable: `true`, `false`, o `unknown`; non convertire unknown in false |
| `eligibility_reason` | valido, non valido, riposo/media, rinvio, non mappato, ecc. |
| `source`, `source_url_or_endpoint`, `source_retrieved_at_utc` | Provenienza e tempo di osservazione |
| `source_revision` / `raw_payload_sha256` | Versione/hash del mapping ufficiale catturato |
| `mapping_observed_at_utc`, `prediction_cutoff_utc` | Validità temporale: il mapping usato deve essere conoscibile entro il cutoff |

Identity del fatto player-game: `(nba_season, nba_game_id, player_id)`; usare player name solo come label. Il PDK raw per partita è POST_MATCH; il PDK ufficiale aggregato della Giornata è un target fantasy separato e non prova da solo il game ID quando la squadra ha più gare.

## 3. Fonti trovate e copertura locale

**Disponibili:**

- NBA ScheduleLeagueV2 cache: 1.200 righe 2026/27 con `GAME_ID`, `GAME_DATE`, home/away, stato e NBA `WEEK_NUMBER`.
- NBA player logs 2025/26: 24.424 righe con `GAME_ID`, `GAME_DATE`, `PLAYER_ID`, team, matchup, minuti/box score e PDK ricostruito.
- NBA team logs 2025/26: 2.460 righe con game ID/date/team/box score.
- Dunkest API client: `week/rounds` e stats `mode=dunkest` per `weeks` e `rounds`; PLUS history ha `player`, CR, PDK, minuti, stagione e `gameweek`, ma non NBA game ID/date/turno.
- Lineups scraper legge label tipo `20/10 BOS @ DET`, separa fixture del `TURNO` selezionato e visita le fixture. Non persiste label, game id, eligibility o il contesto gerarchico in una tabella fixture.
- Coach snapshot GW1 locale ha 30 righe con team/opponent/date, ma è prodotto da `get_coach_data` sul NBA `WEEK_NUMBER`; non è fonte indipendente che dimostri validità Dunkest.

**Mancanti:**

- Tabella ufficiale e versionata `NBA game ID ↔ Dunkest giornata ↔ turno ↔ validità` per stagione corrente e storica.
- Raw response/payload ufficiale Dunkest che certifichi la validità per team/fixture; l'API `week/rounds` usata localmente restituisce round label, non la bridge identity salvata.
- Turno distinto da Giornata nel CSV di scraping/CLI; la colonna corrente `gameweek` non risolve tale distinzione.
- Game ID nel feature/inference artifact e nel join tra NBA player-game e PDK effettivo Dunkest.
- Snapshot pre-GW storici per roster/CR/infortuni/coach, più score realizzati coach e status ufficiale delle partite rinviate.

## 4. Campione player-game: cosa si può verificare oggi

È possibile ispezionare una riga NBA player-game nel raw log, ma non completare in modo attendibile le colonne fantasy:

| Campo richiesto | Fonte/campo locale | Stato |
|---|---|---|
| Player/team | `player_game_logs_2025-26`: `PLAYER_NAME`, `TEAM_ABBREVIATION` | Disponibile nel raw log |
| `game_id`, datetime NBA | `GAME_ID`, `GAME_DATE` | Disponibili nel raw log, persi nel feature frame |
| Opponent/home-away | `MATCHUP`/`OPPONENT` | Disponibile e verificabile nel raw log NBA |
| Dunkest GW/Turno/validity | Nessuna colonna o bridge archiviata | **Non disponibile** |
| Minuti/actual NBA-game PDK | `MIN`, `PDK` | Disponibile nel raw NBA log (PDK ricostruito) |
| Actual Dunkest player-week PDK | Dunkest API per GW, aggregato per player | Target separato; non joinabile univocamente al game ID |
| Predicted PDK per quella game identity | prediction artifact corrente per player, senza `GAME_ID`/data fixture | **Non disponibile** come osservazione player-game predetta |

Di conseguenza non esiste oggi un campione valido che possa mostrare contemporaneamente player, NBA game ID, Dunkest GW/Turno valido, actual Dunkest PDK e prediction della stessa partita. Stampare un record con GW/Turno dedotto da NBA week sembrerebbe completo ma sarebbe non verificato. Il report di implementazione deve mantenere questi campi `UNKNOWN` e la readiness FAIL finché il bridge ufficiale non esiste.

## 5. Contratto temporale PRE_MATCH / POST_MATCH

| Classe | Esempi | Uso consentito |
|---|---|---|
| PRE_MATCH | fixture e mapping acquisiti entro il cutoff; CR/roster snapshot; injury report con timestamp; storico player/team solo con data precedente al game start; coach snapshot | Feature/predizione della partita target |
| POST_MATCH | risultato, minuti, box score, PDK effettivo, PLUS realizzata, stato finale NBA | Target/evaluation soltanto; vietato in feature inference |
| UNKNOWN | availability o mapping senza timestamp/fonte, status vecchio o fixture non mappata | Non usare come certezza; rende readiness incompleta |

Ogni feature row deve portare `nba_game_id`, `game_start_utc`, `prediction_cutoff_utc`, `dunkest_matchday_id`, `dunkest_turn_id`, `fantasy_eligible` e provenance del mapping. Un controllo deve rifiutare feature post-match e qualsiasi dato con `available_at > prediction_cutoff_utc`. Le feature storiche rolling possono essere ammesse solo con sorgenti di game log `< game_start_utc`.

## 6. Backtest readiness e snapshot

Un GW è end-to-end ready solo se i componenti obbligatori passano: fixture mapping univoco/versionato; pre-match roster e prezzi; status injury; coach e CR; fonti/timestamp pre-cutoff; actual player/coach outcomes e mapping realizzato; lineup/prediction archiviate prima del match. `BACKTEST_READY=false` deve bloccare metriche lineup aggregate e riportare un report di copertura per campo.

Archiviazione proposta, immutabile per run e Giornata:

```text
data/archive/<nba_season>/dunkest_gw_<n>/<snapshot_id>/
  manifest.json
  nba_schedule.parquet
  dunkest_fixture_bridge.parquet
  player_market.parquet
  injuries.parquet
  coach_market.parquet
  predictions.parquet
  lineups.parquet
  post_match_player_results.parquet       # scritto a giornata conclusa
  post_match_coach_results.parquet        # scritto a giornata conclusa
  readiness.json
```

Manifest: source/endpoint, fetched-at UTC, coverage, raw+normalized hash, schema version, transformations, model/source fingerprint, config hash, seed, Git commit/explicit unavailable reason e optimizer parameters. Non sovrascrivere snapshot: nuove acquisizioni creano revisioni collegate; correggere mapping crea nuova revisione e mantiene la precedente.

## 7. Test richiesti per la correzione

1. Fixture `(season, game_id)` non vuota e unica; duplicati identity rifiutati.
2. Join player→fixture su team e game ID, mai solo su team/data ordinale; team/opponent e home/away verificati dall'identity.
3. Un team con più partite nella stessa NBA week è ammesso; solo il bridge ufficiale determina GW/Turno/eligibility.
4. Dunkest GW che contiene un sottoinsieme delle partite NBA è ammessa; fixture non mappata resta unknown.
5. Permutare ordine cronologico/input schedule non cambia GW/Turno/validity.
6. Fonte mapping disponibile dopo prediction cutoff non può essere usata per quella prediction.
7. Un giocatore non viene associato a fixture prima del timestamp di conoscibilità del mapping o con team/avversario incompatibili.
8. Home/away deriva da `home_team_id`/`away_team_id`, non da ordering della lista.
9. Colonne POST_MATCH e identificativi target (`actual_pdk`, `PLUS`, box score della gara target, risultato) non entrano nelle feature PRE_MATCH; fail esplicito all'ingresso nel training/inference feature list.
10. Fixture multiple e doppie partite NBA nella stessa finestra dimostrano che `NBA_WEEK_NUMBER -> Dunkest GW` non è una funzione valida; regressione attuale deve fallire il test finché si rimuove l'assunzione.
11. Readiness status separato per mapping, roster, CR, injuries, coach, pre-match timestamp e risultati; se un requisito è FAIL/UNKNOWN, `BACKTEST_READY=false` e le metriche lineup non vengono emesse.

## 8. Metriche

Nomi richiesti nei report: `player_game_pdk_mae` (unità PDK/player NBA game, stagione/split espliciti), `dunkest_gameweek_player_pdk_mae` (PDK/player Dunkest GW), `capital_gain_delta_cr_mae` (CR/player/GW), e `official_plus_sign_accuracy` (segno della PLUS realizzata, campione e fonte espliciti). Ogni metrica documenta target source, unità, copertura, split, cutoff e baseline; vietato chiamare genericamente una misura `MAE` senza il target.
