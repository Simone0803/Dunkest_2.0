# Diagnostica degli errori PDK sui punteggi elevati

**Data analisi:** 2026-10-26
**Ambito:** ricalcolo descrittivo da previsioni e outcome già archiviati, più appaiamento a feature storiche pre-target. Nessun training, scraping, forecast, tuning o modifica a modelli/configurazioni/dati è stato eseguito.

## Sintesi

Il confronto salvato riguarda un modello RF sperimentale game-level, non il predictor runtime collegato alle rose. Sulle stesse 18.412 osservazioni RF migliora il MAE complessivo di 0,211 PDK rispetto alla media last-10, ma sui 2.712 outcome ufficiali ≥30 peggiora il MAE di 0,493 e il RMSE di 0,287. La differenza è robusta nel bootstrap appaiato per data.

La diagnosi per **PDK previsto** chiarisce il fenomeno: nella fascia RF prevista ≥30, la media prevista è 34,52 e la media osservata 34,48; nelle fasce 30–35 e ≥35 la calibrazione media RF è quasi neutra. Quindi i dati non supportano un rialzo globale delle previsioni alte. La criticità più evidente è che il RF emette meno previsioni ≥30 e intercetta meno dei risultati che supereranno 30: recall 29,2% contro 33,9% di last-10. Molti outcome ≥30 sono collocati sotto 30 dalla previsione, e il gruppo definito a posteriori dal risultato ha errori elevati per entrambi i metodi.

I risultati mostrano anche che gli outcome ≥30 hanno mediamente più minuti e PDK per minuto dei cinque precedenti, ma **non è disponibile una previsione RF dei minuti né una previsione esplicita del rate**. Non si può quindi assegnare causalmente l’errore a minuti o produzione.

## 1. Artefatti e validità del confronto

| Ruolo | Artefatto | Verifica |
|---|---|---|
| Previsione RF e baseline | [`dunkest_pdk_holdout_2025-26_predictions_v1.csv`](../../data/processed/dunkest_pdk_holdout_2025-26_predictions_v1.csv) | 18.412 righe; colonne `prediction_random_forest`, `prediction_baseline_prev10`, `target_pdk`; nessuna previsione/target nulla. |
| Protocollo e provenienza | [`dunkest_pdk_holdout_2025-26_audit_v1.json`](../../data/processed/dunkest_pdk_holdout_2025-26_audit_v1.json) | RF allenato su 93.766 righe 2020/21–2024/25; test fisso 2025/26 di 18.412 righe; nessuna sovrapposizione di stagioni; zero righe di storia NBA con data uguale o successiva al target. L'audit registra i campi outcome vietati tra i controlli leakage. |
| Feature pre-target | [`dunkest_pdk_game_training_2020-26_v3.parquet`](../../data/processed/dunkest_pdk_game_training_2020-26_v3.parquet) | Appaiato al file previsioni con `(season_id, gameId, dunkest_player_id)`: 18.412/18.412, chiavi univoche in entrambi. Contiene feature passate, incluse partite storiche, lag PDK/NBA e medie recenti dei minuti/statistiche. |
| PDK ufficiale e minuti outcome | [`official_dunkest_vs_nba_matched_2025-26.parquet`](../../data/processed/official_dunkest_vs_nba_matched_2025-26.parquet) | Dopo filtro `gameValidForDunkest=True`, appaiamento univoco su ID giocatore Dunkest e game ID Dunkest: 18.412/18.412; `target_pdk` coincide con `pdk_official` in tutte le righe (differenza massima 0). Il collegamento NBA sottostante è verificato dal dataset tramite nome/data/avversario. |

Le previsioni salvate non sono state rigenerate. Il file CSV non contiene l'intero vettore feature per riga; il feature table e l'audit del holdout sono stati usati per controllare identità, disponibilità e protocollo. Questo è un holdout storico online one-step-ahead per stagione, non una previsione della stagione intera pre-opening, e il report originale dichiara che il RF non è integrato nel predictor operativo.

SHA-256 degli input principali:

- CSV previsioni: `bd0919ca06306bba83991c28e78c949605c06f92a68fedbf875b7085162ba817`
- audit JSON: `fd2d7995fe1742efd7b84cf085196bae237b86aa8de34f6b1c636298dedf8a55`
- feature Parquet: `9f1cae2490822bc3617f96e35463473787fbfec016236f27a5c586f0cd9c72e5`
- join outcome NBA Dunkest: `d85586050858d722bd886c3ab116adba869920cb5dd4a4a26bfc2b1305715227`

## 2. Metriche complessive e bootstrap

Bias = `previsione − PDK ufficiale`; differenza = RF meno last-10. Bootstrap appaiato a cluster per `game_date`, 5.000 ricampionamenti di date con reinserimento, seed `20261026`. Le righe della stessa data restano nello stesso cluster.

| Campione | n | RF MAE | Last-10 MAE | Δ MAE (IC 95%) | RF RMSE | Last-10 RMSE | Δ RMSE (IC 95%) | RF bias | Last-10 bias | Δ bias (IC 95%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Tutte le osservazioni | 18.412 | 7,577 | 7,789 | **-0,211** [-0,244; -0,177] | 9,856 | 10,154 | **-0,298** [-0,334; -0,261] | -0,172 | -0,048 | -0,125 [-0,190; -0,071] |
| PDK effettivo ≥30 | 2.712 | 14,265 | 13,771 | **+0,493** [+0,404; +0,582] | 16,751 | 16,463 | **+0,287** [+0,189; +0,385] | -13,861 | -12,944 | -0,917 [-1,009; -0,824] |
| RF previsto ≥30 | 1.297 | 10,537 | 10,825 | **-0,288** [-0,448; -0,133] | 13,359 | 13,734 | **-0,375** [-0,547; -0,202] | +0,027 | +2,270 | -2,243 [-2,352; -2,128] |
| Last-10 previsto ≥30 | 1.588 | 10,413 | 10,683 | **-0,270** [-0,413; -0,135] | 13,155 | 13,512 | **-0,357** [-0,500; -0,208] | +0,171 | +2,519 | -2,349 [-2,449; -2,249] |

I gruppi “PDK effettivo ≥30” sono retrospettivi. I due gruppi previsti sono selezionati prima di osservare il target rispetto al rispettivo metodo; all'interno di ogni riga entrambi i metodi sono valutati sulle medesime osservazioni selezionate. Il bootstrap è per data, non per giocatore indipendente.

## 3. Calibrazione per fasce di PDK previsto

Bias in tabella = media prevista meno media osservata. Le fasce sono definite separatamente dai valori previsti di ciascun metodo, quindi rispondono a una domanda ex ante. `Share outcome ≥30` è invece una frequenza osservata all'interno della fascia.

| Metodo | PDK previsto | n | Media prevista | Media PDK osservato | Bias | MAE | RMSE | Quota outcome ≥30 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RF | <10 | 4.826 | 6,649 | 6,683 | -0,034 | 5,448 | 7,232 | 1,3% |
| RF | 10–<20 | 8.386 | 14,545 | 14,872 | -0,327 | 7,528 | 9,577 | 7,9% |
| RF | 20–<25 | 2.363 | 22,383 | 22,725 | -0,342 | 9,121 | 11,514 | 24,5% |
| RF | 25–<30 | 1.540 | 27,494 | 27,167 | +0,327 | 9,660 | 12,018 | 39,8% |
| RF | 30–<35 | 953 | 31,846 | 32,055 | -0,209 | 9,921 | 12,632 | 57,2% |
| RF | ≥35 | 344 | 41,808 | 41,129 | +0,679 | 12,244 | 15,193 | 71,8% |
| Last-10 | <10 | 5.296 | 5,893 | 7,557 | -1,664 | 5,801 | 8,001 | 1,8% |
| Last-10 | 10–<20 | 7.470 | 14,677 | 14,655 | +0,022 | 7,729 | 9,778 | 8,1% |
| Last-10 | 20–<25 | 2.446 | 22,328 | 21,610 | +0,718 | 9,083 | 11,395 | 21,1% |
| Last-10 | 25–<30 | 1.612 | 27,333 | 26,088 | +1,244 | 9,779 | 12,139 | 35,9% |
| Last-10 | 30–<35 | 930 | 32,194 | 30,600 | +1,593 | 10,024 | 12,637 | 51,9% |
| Last-10 | ≥35 | 658 | 40,817 | 36,989 | +3,828 | 11,614 | 14,660 | 66,3% |

La fascia RF ≥30, combinando le ultime due righe RF, ha previsione media 34,49 e osservato medio 34,46 (bias +0,03 circa). RF non mostra una sottostima media condizionata alla propria fascia prevista alta. Last-10 sovrastima invece progressivamente nelle fasce previste ≥25.

### Riconoscimento della coda effettiva

| Regola retrospettiva / soglia di previsione | Outcome ≥30 | Previsioni nella fascia | Veri positivi | Precisione | Recall degli outcome ≥30 | Outcome ≥30 mancati |
|---|---:|---:|---:|---:|---:|---:|
| RF previsto ≥30 | 2.712 | 1.297 | 792 | 61,1% | 29,2% | 1.920 |
| Last-10 previsto ≥30 | 2.712 | 1.588 | 919 | 57,9% | 33,9% | 1.793 |

Il RF individua meno opportunità di punteggio alto: la sua precisione sopra soglia è maggiore, ma la copertura degli outcome ≥30 è inferiore. Dei 2.712 outcome ≥30, 72,6% non raggiunge la soglia prevista RF ≥30; per last-10 la quota è 66,1%. La tabella per fasce mostra che questo non equivale a una cattiva calibrazione media delle previsioni RF già alte.

## 4. Distribuzione e sottostime grandi

Definisco sottostima come `osservato − previsto ≥ soglia`.

| Campione | Metodo | Sottostima ≥10 PDK | ≥20 PDK | ≥30 PDK | Mediana errore previsto−osservato | P90 errore assoluto | P95 | P99 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Tutto | RF | 2.819 (15,3%) | 671 (3,6%) | 122 (0,7%) | +1,062 | 16,012 | 19,721 | 28,612 |
| Tutto | Last-10 | 2.822 (15,3%) | 697 (3,8%) | 130 (0,7%) | +0,887 | 16,545 | 20,409 | 29,318 |
| Effettivo ≥30 | RF | 1.770 (65,3%) | 640 (23,6%) | 122 (4,5%) | — | — | — | — |
| Effettivo ≥30 | Last-10 | 1.654 (61,0%) | 637 (23,5%) | 130 (4,8%) | — | — | — | — |

Sottogruppi di coda più estrema:

| PDK effettivo | n | RF MAE / bias | Last-10 MAE / bias |
|---|---:|---:|---:|
| ≥40 | 988 | 19,664 / -19,403 | 18,657 / -18,151 |
| ≥50 | 288 | 24,636 / -24,527 | 23,079 / -22,676 |
| ≥60 | 91 | 30,134 / -30,134 | 28,112 / -28,057 |

## 5. Minuti, titolarità, ruolo e storico

### Minuti

Il CSV delle previsioni non contiene minuti attesi dal modello, probabilità di presenza o PDK condizionale. Il feature table ha `prev5_nba_min_mean`, cioè una statistica storica disponibile pre-target, non una previsione operativa di minuti. Come baseline diagnostica di minutaggio, confrontando questa media con i minuti ufficiali:

| Campione | n con media prev5 | MAE minuti | RMSE minuti | Bias `prev5−effettivi` | Zeri ufficiali nei minuti |
|---|---:|---:|---:|---:|---:|
| Baseline minuti = media NBA ultime 5 | 18.348 | 5,025 | 6,595 | +0,586 | 101 nel sottoinsieme |

Nel join completo sono presenti 106 righe con zero minuti ufficiali; restano outcome PDK ufficiali. I minuti zero sono esclusi dal calcolo PDK/min, non trasformati in dati mancanti né eliminati dalle metriche PDK.

| Minuti effettivi | n | PDK effettivo medio | PDK/min medio, solo minuti >0 | Media minuti prev5 | RF MAE / bias | Last-10 MAE / bias |
|---|---:|---:|---:|---:|---:|---:|
| <10 | 2.467 | 2,181 | 0,512 | — | 5,332 / +4,681 | 5,350 / +4,327 |
| 10–<20 | 4.265 | 8,806 | 0,571 | — | 6,201 / +2,416 | 6,439 / +2,263 |
| 20–<30 | 6.537 | 17,100 | 0,688 | — | 7,717 / -0,549 | 8,037 / -0,404 |
| ≥30 | 5.143 | 27,704 | 0,811 | — | 9,620 / -4,168 | 9,762 / -3,610 |

Gli outcome effettivi ≥30 hanno minuti medi 32,76 contro 30,41 minuti medi delle ultime cinque partite (delta +2,35). Hanno inoltre PDK/min medio 1,225 contro rate storico descrittivo `prev5_pdk_mean / prev5_nba_min_mean` pari a 0,860. Il campione con minuti positivi e rate storico disponibile è 18.222; nella coda effettiva ≥30 è 2.711.

Per la differenza di minutaggio `minuti effettivi − media prev5`, le righe con incremento ≥5 minuti sono 3.178; l'incremento medio è +8,98 minuti e il residuo RF medio `PDK osservato−RF` è +7,36. Con minuti entro ±5 dalla media prev5 (10.952 righe), il residuo RF medio è +0,52. Con calo ≥5 minuti (4.092 righe), il residuo medio RF è -6,21. Queste sono coorti definite usando i minuti outcome, quindi sono diagnostiche retrospettive, non feature/previsioni.

**Limite di attribuzione:** minuti effettivi e rate PDK effettivo sono entrambi associati alla coda; il PDK/min contiene matematicamente il target PDK nel numeratore. Non è una decomposizione causale e non prova che il modello sbagli per rate più che per minuti. Senza minuti previsti e componenti PDK/min previste non posso separare le fonti dell'errore.

### Titolarità e ruolo

`starter` è presente nell'outcome ufficiale, non nella previsione: perciò lo uso soltanto come stratificazione ex post. Il ruolo/posizione del giocatore non è una feature disponibile nel holdout: `opponentTeamPosition` indica `home`/`visitor` (9.225/9.187 righe), non il ruolo Dunkest. Non è stato sostituito con il ruolo attuale.

| Stato starter osservato dopo la partita | n | RF MAE / RMSE / bias | Last-10 MAE / RMSE / bias |
|---|---:|---:|---:|
| Non starter | 9.444 | 6,287 / 8,049 / +0,926 | 6,498 / 8,409 / +0,682 |
| Starter | 8.968 | 8,936 / 11,456 / -1,329 | 9,148 / 11,714 / -0,817 |

Degli outcome ≥30, 2.435/2.712 (89,8%) risultano starter nel box score. Anche questa informazione è osservata dopo la gara e non può essere interpretata come previsione della titolarità.

### Quantità di storico pre-target

| Partite Dunkest valide precedenti (`history_games_before_target`) | n | RF MAE / RMSE / bias | Last-10 MAE / RMSE / bias | Outcome ≥30 |
|---|---:|---:|---:|---:|
| 0 | 90 | 4,692 / 7,045 / -1,331 | 9,202 / 10,056 / +7,158 | 1 |
| 1–3 | 265 | 5,266 / 7,200 / +0,229 | 5,538 / 8,059 / -0,841 | 6 |
| 4–10 | 556 | 5,653 / 7,954 / -0,028 | 5,908 / 8,446 / -1,062 | 21 |
| >10 | 17.501 | 7,688 / 9,958 / -0,177 | 7,875 / 10,232 / -0,041 | 2.684 |

La coda effettiva non è concentrata nei giocatori con pochissime osservazioni Dunkest: 2.684 dei 2.712 casi ≥30 hanno più di 10 partite precedenti. Le celle low-history hanno campioni piccoli e una sola, sei e 21 etichette di coda rispettivamente; non supportano un intervento sui rookie.

## 6. Cause: evidenza e ipotesi

### Supportato dai dati

1. **Gli errori alti sono reali e peggiori per RF nel sottoinsieme retrospettivo PDK≥30.** Il bootstrap per data esclude zero per le differenze MAE e RMSE; RF ha bias più negativo.
2. **Il problema è soprattutto la copertura degli outcome alti, non una sottostima uniforme nelle fasce previste alte.** RF ha recall inferiore alla soglia 30, ma le sue fasce previste ≥30 sono calibrate in media. Last-10 invece sovrastima nelle fasce previste ≥25.
3. **Gli outcome alti sono associati a più minuti e a PDK/min più alto rispetto alla storia recente.** I minuti effettivi aumentano in media di 2,35 sui tail ≥30; il rate osservato supera il rate storico derivato dai lag. Si osservano errori PDK RF più positivi nei gruppi con salto di minuti.
4. **Gli eventi alti non sono un problema limitato ai rookie/low-history.** La maggior parte assoluta dei tail ha oltre 10 partite Dunkest precedenti.

### Non dimostrato / ipotesi

- Non è dimostrato che l'RF sia “compresso” sistematicamente nella fascia che esso stesso predice come alta: le medie di quelle fasce non lo mostrano. È invece compatibile con una minore propensione a emettere previsioni ≥30 e con sorprese non identificate prima della gara.
- Non è dimostrato che il driver dominante sia il minutaggio o la produzione statistica per minuto. Il modello non archivia minuti previsti, probabilità di giocare, rate previsto o contributi statistici previsti.
- Cambi di ruolo, infortuni, disponibilità dei compagni e rotazione non sono rappresentati nel holdout con stati storici point-in-time sufficienti a questa diagnosi.
- I risultati non sono una verifica del modello di produzione, della correzione DvP, dei coach o delle rose: il modello testato è l'artefatto RF storico.

## 7. Tre interventi potenziali, ordinati per evidenza e fattibilità

1. **Non applicare una calibrazione positiva globale né un moltiplicatore alle previsioni alte sulla base di questo risultato.** Evidenza alta e costo nullo: RF previsto ≥30 è mediamente calibrato, mentre last-10 sovrastima nelle fasce ≥25; una correzione globale rischia di peggiorare fasce già corrette. Nessuna modifica al modello è proposta.
2. **Archiviare per un futuro campione prospettico i minuti/probabilità di presenza previsti e le componenti PDK previste (rate o statistiche e minuto condizionale).** Evidenza alta del gap informativo: esiste solo la media storica minuti e il risultato osservato; non esiste il minutaggio RF previsto. Questo è il prerequisito per distinguere errore opportunità/minuti da errore di produzione.
3. **Dopo aver raccolto tali componenti, valutare sul solo development walk-forward un challenger orientato alla copertura della coda o a output distribuzionali, con metriche sia per previsione ex ante sia per outcome ≥30.** Evidenza media: il RF ha recall alti inferiore, ma le fasce alte condizionate sono già ben calibrate. I pesi/parametri non vanno scelti su questo holdout 2025/26 né sulla GW1 prospettica congelata; serve un periodo finale nuovo e separato.

## 8. Prossima analisi a maggior valore informativo

La singola analisi successiva più utile è una **decomposizione appaiata dei residui del predictor operativo su nuovi forecast pre-lock archiviati**, collegando per ciascun giocatore `P(presenza)`, minuti previsti condizionati alla presenza, rate/PDK condizionale, PDK finale e outcome ufficiale. Va confrontata per fasce definite ex ante e per gruppo outcome ≥30, mantenendo i medesimi giocatori/giornate e bootstrap per data. È l'unico passaggio che può stabilire quantitativamente se la coda alta viene persa per minuti, disponibilità o produzione, senza usare il modello RF sperimentale come surrogato della produzione.

## 9. Riproducibilità e modifiche

Analisi eseguita con `.venv/bin/python` e pandas/NumPy sui quattro artefatti indicati, join univoci a cardinalità uno-a-uno, controlli di uguaglianza del target e metriche calcolate sulle stesse righe. Bootstrap per data: 5.000 ricampionamenti, seed fisso `20261026`. Le fasce sono chiuse a sinistra/aperta a destra (`[a,b)`), ad eccezione dell'ultima fascia aperta superiore. PDK/min esclude solo righe con minuti effettivi pari a zero o rate storico indisponibile; le metriche PDK includono tutte le 18.412 osservazioni.

I comandi eseguiti sono stati letture locali (`git status --short`, `git diff --stat`, `PYTHONPATH=src .venv/bin/python` con script inline di controllo/metriche/bootstrap, `sha256` sugli artefatti). Nessun test software è stato eseguito perché non è stato modificato codice. Nessuna modifica locale preesistente è stata toccata; l'unico nuovo file è questo report.
