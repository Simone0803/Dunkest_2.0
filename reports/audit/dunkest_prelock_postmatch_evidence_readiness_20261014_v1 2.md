# Dunkest — pre-lock e post-match evidence readiness
Data audit: 2026-10-14

## Intervento eseguito

È stato corretto il revisore indipendente dell'archivio pre-lock. Prima della modifica, la decisione ricalcolata rechecked_pre_lock_eligible dipendeva solo dalla freschezza dei file e ignorava la validazione semantica delle fixture. Ora l'idoneità richiede simultaneamente:
- hash del bundle coerenti con il manifest;
- record nel registro immutabile coerente con l'hash del manifest;
- tutti gli snapshot richiesti freschi;
- fixture mapping verificato, univoco, con hash del payload e timestamp di acquisizione validi, prima del run e entro la finestra ammessa rispetto al kickoff.

Aggiunto test di regressione: fixture duplicate con snapshot freschi non possono più superare il revisore.

## Esito dell'audit sul run GW1 disponibile

Run: 20261014T103438Z_034cc8bc

- Integrità dei file archiviati: **valida**.
- Stato di certificazione memorizzato: **incomplete_evidence**.
- Fixture mapping: **non valido per uso pre-lock**.
- Timestamp di acquisizione del mapping: 2026-10-12 08:53:22 UTC.
- Età del mapping al run: circa 49,7 ore, oltre la soglia di 36 ore.
- Run rispetto al primo kickoff (20 ottobre 2026, 00:00 UTC): circa 133,4 ore prima, fuori dalla finestra pre-lock.
- Idoneità ricalcolata: **false**.

L'archivio rimane intatto; la revisione è un artefatto separato e non riscrive manifest o registro.

Report di revisione: reports/audit/prelock_review_20261014T103438Z_034cc8bc_v2.json

## Stato post-match

Non esistono ancora risultati realizzati per GW1 2026/27: il primo kickoff è il 20 ottobre 2026 e l'ultimo fixture mappato è il 22 ottobre. L'evaluation corrente resta not_ready. Non è un errore del modello; la raccolta va eseguita solo dopo la conclusione delle partite e il cutoff di sicurezza definito dalla pipeline.

Non sono stati aggiunti risultati sintetici, non sono stati assegnati zero a punteggi mancanti e non sono stati ricostruiti snapshot storici post hoc.

## Prossima finestra operativa

Con una finestra massima di 36 ore, il primo istante teorico per il preflight è **2026-10-18 12:00 UTC**. Prima di produrre un run da conservare come evidenza, lo script deve:
1. acquisire nuovamente il calendario Lineups e confermare le fixture eleggibili;
2. aggiornare e verificare timestamp/hash del mapping e degli snapshot di mercato, crediti, coach e disponibilità;
3. produrre la previsione solo se il mapping è fresco e verificato;
4. archiviare il run in modalità immutabile e controllare pre_lock_eligible;
5. dopo la fine di GW1, raccogliere PDK ufficiali e risultati coach collegati alle fixture e verificare copertura prima di calcolare metriche.

Se lo scraping produce una fixture mapping vecchia o non verificata, il run non è certificabile. Non va aggirato il gate usando un mapping precedente.

## Test e vincoli

- Test mirati pre-lock/post-match: 37 superati.
- Suite completa: **390 test superati** (-W error::DeprecationWarning).
- Nessuna modifica ai pesi o ai parametri di produzione.
- Holdout GW1 2026/27 congelato fino al **2026-10-23 12:00 UTC**.
- Nessun commit o push eseguito.
