# Audit autonomo: ottimizzatore, allenatori e plusvalenza — 2026-10-14 V1

## Ambito e criteri

Ispezione del codice di produzione, test e audit walk-forward già presenti. Non sono stati inventati snapshot storici pre-lock, non sono state usate etichette retroattive come se fossero input pre-lock e non è stato modificato il holdout GW1 2026/27, congelato fino al 2026-10-23 12:00 UTC.

## 1. Ottimizzatore delle rose

### Già presente nel codice

- MILP con vincoli di budget, ruoli, numero di giocatori, massimo di tre elementi della stessa squadra NBA includendo l'allenatore, slot e capitano.
- Gestione dinamica dei turni Dunkest quando sono disponibili turni fixture-linked, per modellare le sostituzioni dopo le partite.
- Controllo indipendente della soluzione dopo il solver.
- Malus trasferimenti incluso nell'obiettivo quando esiste una rosa corrente.
- Obiettivo expected_value e variante risk_adjusted; la seconda penalizza lo spread P90-P10 tramite risk_lambda.
- Vincolo conservativo: giocatori con dubbio di partecipazione (p_play < 1) non entrano nella rosa.
- Plusvalenza inclusa come valore futuro approssimato tramite prezzo ombra del credito, stimato con differenza finita aumentando il budget di un CR.
- Generazione di tre rose distinte, con controlli su allenatori e capitani ripetuti.

### Lacune importanti

1. **Manca un confronto certificato fra optimizer e baseline sullo stesso universo.** Gli audit di rose storiche hanno copertura incompleta e non dispongono di tutti gli snapshot pre-lock. Quindi non dimostrano che il MILP migliori il punteggio realizzato rispetto a migliori PDK/CR, ranking per ruolo o greedy.
2. **Il costo opportunità per giocatore ora è calcolabile in modalità audit, ma non è ancora integrato nel report standard.** Ho aggiunto uno script controfattuale che esclude ogni giocatore della rosa di rango 1 e riottimizza sotto gli stessi vincoli, tenendo fisso il prezzo ombra del CR. Una semplice differenza fra due PDK individuali non sarebbe un sostituto corretto: ruoli, moltiplicatori, crediti, allenatore e limite per squadra interagiscono.
3. **Il rischio è una preferenza configurabile, non ancora una politica certificata.** La penalità lambda × (P90-P10) è una funzione obiettivo euristica; non è una misura di rischio di portafoglio calibrata su risultati di rose complete. La configurazione opener usa risk_adjusted, lambda 0.10: scelta prudenziale, non dimostrazione di rendimento superiore.
4. **La distribuzione della rosa è approssimata.** Gli spread individuali sono aggregati usando una correlazione comune fissa; non è ancora una distribuzione congiunta appresa da shock di partita/squadra validati.

### Evidenza storica disponibile

Il backtest sequenziale dei malus (2022/23–2024/25) confronta coefficienti 0, 2.5 e 5, ma usa un universo osservato incompleto, crediti coach fissi a 10, risultati coach neutral-credit e zero per alcune righe mancanti. Sulle 409 giornate abbinate, il coefficiente 2.5 supera 0 di circa 2.66 punti netti medi (IC bootstrap 95% circa [0.04, 5.31]), mentre 2.5 contro 5 è circa +0.32 (IC [−2.42, 3.01]). Questi risultati sono proxy esplorativi, non sufficienti per modificare il malus di produzione.

### Diagnostica controfattuale su una rosa prevista

Eseguito scripts/audit_dunkest_player_opportunity_costs_v1.py sul run 20261014T175113Z_7c1f0803, usando la configurazione season_opener. Tutti i 10 controfattuali sono stati risolti con stato Optimal. La rosa di riferimento è la prima proposta (coach Micah Nori, 243.30 PDK netti previsti).

- Mediana del gap nell'obiettivo risk-adjusted: **0.107 PDK-equivalent**.
- Mediana della differenza nel punteggio netto atteso non penalizzato dal rischio: **0.081 PDK**.
- I gap maggiori nell'obiettivo sono Ty Jerome (3.571 PDK-equivalent; differenza netta attesa 3.039) e Lauri Markkanen (1.174; 0.832).
- Per alcuni giocatori, la rosa controfattuale ha PDK attesi maggiori ma obiettivo risk-adjusted peggiore: il costo dipende quindi anche dall'incertezza, non solo dalla media.

Questa diagnostica misura il costo opportunità **secondo il modello e il mercato salvato**, non punti realizzati. Serve a capire quali scelte sono fragili o sostituibili, ma non dimostra che una sostituzione avrebbe reso di più nella partita reale.

### Prossima implementazione necessaria

- Costruire un harness di confronto che alimenti MILP e baseline con identici giocatori eleggibili, crediti, coach, indisponibilità e regole.
- Integrare il costo opportunità controfattuale nel report delle rose come diagnostica opzionale, mantenendolo fuori dal percorso standard finché il costo computazionale e la stabilità del solver non sono valutati. Lo script audit esistente produce già i gap per la rosa di rango 1.
- Valutare ogni strategia su punteggio netto realizzato, trasferimenti, tasso di rose fattibili, coverage e differenze paired per giornata; non soltanto sulla previsione.
- Non promuovere risk_lambda senza un confronto temporale out-of-sample di rose complete.

## 2. Allenatori e probabilità di vittoria

### Già presente nel codice

- Separazione fra punteggio base coach e moltiplicatore dipendente dalla differenza di CR.
- Regole di punteggio coach implementate in src/dunkest/rules/coach.py, con test di sensibilità dei coefficienti.
- Forecast coach Monte Carlo a partire da punti attesi delle squadre, volatilità, correlazione e probabilità di overtime.
- Fallback esplicito quando non c'è un matchup verificato: la pipeline non dovrebbe promuovere una proiezione prior-only a matchup valido.
- Probabilità di vittoria normalizzate per la stessa partita, così le due probabilità sono complementari.
- Calibrazione Platt e proxy di forza roster non promossi: negli audit hanno peggiorato Brier score e log loss.

### Problema corretto durante questa ispezione

In src/dunkest/models/coach.py, il simulatore precedente poteva assegnare il flag overtime a un campione con un margine simulato qualsiasi, indipendentemente dal pareggio regolamentare. Il punteggio coach applicava quindi il bonus/malus speciale OT a partite che non erano state rese coerenti con un overtime.

Il simulatore ora:
- marca overtime secondo il prior empirico o quando il campione è in parità;
- per i campioni OT porta il punteggio regolamentare a una parità, conserva approssimativamente il totale e risolve l'OT con un punto, mantenendo il vincitore campionato quando già determinato;
- restituisce punteggi finali non in parità e flag OT coerenti.

Questa è un'approssimazione esplicita, non una simulazione dettagliata dei punti segnati in un overtime. Ho rigenerato il walk-forward V4 importando direttamente il simulatore del codice di produzione, poi ho eseguito un bootstrap paired a cluster di partita (10.000 repliche):
- 4.920 partite / 9.840 team-game outcomes, stagioni 2022/23–2025/26.
- MAE Monte Carlo: 15.202; modello diretto: 16.073; baseline previous-10: 16.596.
- Differenza MAE Monte Carlo − diretto: −0.871, IC bootstrap 95% [−1.000, −0.740].
- Differenza MAE Monte Carlo − previous-10: −1.394, IC [−1.531, −1.260].
- Bias Monte Carlo +0.135, quindi lievemente positivo; l'RMSE (17.461) è leggermente migliore del modello diretto (17.934).

L'approccio rule-aware resta promettente per il punteggio base a CR neutrale, ma non certifica i punti coach price-adjusted né il rendimento di una rosa completa. Il report V4 e il bootstrap V3 sono separati dai precedenti e non sovrascrivono artefatti versionati.

### Evidenza e limiti

- Il report Monte Carlo coach V4 (che riusa il simulatore di produzione corretto) riporta MAE pooled 15.202 contro 16.073 del modello diretto e 16.596 del baseline previous-10; il bootstrap paired V3 ha intervalli sotto zero per entrambi i confronti. Il report usa punteggi coach a CR neutrale: non certifica il punteggio storico price-adjusted.
- Mancano coppie storiche pre-lock di CR coach avversari per calcolare e validare esattamente il coefficiente storico.
- La calibrazione Platt ha leggermente peggiorato Brier e log loss nel validation 2024/25 e nel test 2025/26; non va attivata sulla base del solo miglioramento dell'accuracy.
- Il proxy di forza roster ha peggiorato Brier/log loss nel validation complessivo; resta non promosso.

### Audit aggiornato e prossime verifiche

- Walk-forward score e probabilità sono stati rigenerati usando il simulatore OT condiviso col codice di produzione. L'audit probabilistico V2 mantiene lo split temporale: training fino al 2023/24, validation 2024/25 e holdout 2025/26.
- V2: validation Brier 0.209904 e log loss 0.606907; Platt peggiora entrambi (0.209965 e 0.607094). Sul holdout 2025/26, raw Brier 0.206585 e log loss 0.601396; Platt peggiora entrambi (0.206693 e 0.601526). Quindi la calibrazione Platt resta non promossa anche con il simulatore aggiornato.
- Continuare a monitorare reliability per fascia, MAE del margine e copertura matchup verificati; valutare eventuali alternative solo sul validation temporale e una volta fissate prima del holdout.
- Validare i moltiplicatori ufficiali con input CR pre-lock autentici quando saranno disponibili. Fino ad allora, tenere separate le metriche neutral-credit e gli scenari ipotetici.
- Mantenere disattivati Platt e roster-strength adjustment finché non migliorano le metriche probabilistiche out-of-sample.

## 3. Plusvalenza e strategia multi-giornata

### Già presente nel codice

- Modello di variazione CR con validazione expanding-origin per stagione/giornata.
- Esclusione delle stagioni con meno di 28 squadre NBA rilevate nel campione.
- Estimatore adattivo per fascia di CR, correzione di bias per fascia stimata soltanto da residui OOF precedenti e distribuzione empirica dei residui in unità CR.
- Probabilità di guadagno/perdita, quantili P10/P90 e indicatori di supporto del modello.
- Conversione PDK→ΔCR effettuata prima di aggiungere residui CR, evitando di sommare quantità con unità diverse.
- Il valore di budget futuro nel MILP è stimato dal valore marginale di un CR nello specifico mercato.

### Evidenza disponibile e caveat

L'audit di calibrazione plusvalenza riporta MAE walk-forward intorno a 0.068–0.069 CR contro circa 0.178–0.179 CR per il baseline della media della finestra di training. Il campione filtrato resta limitato e la probabilità di guadagno mostra ottimismo residuo di circa 3.3 punti percentuali nell'audit conversion-only, che non include l'errore della previsione PDK.

La valorizzazione nel MILP è **a un solo passo**: prezzo ombra del CR × ΔCR atteso. Non è ancora un'ottimizzazione dinamica su più giornate e non simula in modo completo cambi di ruolo, perdita di minuti, infortuni, variazioni di prezzo e costi futuri di trasferimento.

Il backtest sequenziale dei trasferimenti non può certificare una strategia multi-giornata: il roster riportato è quello della strategia simulata, non quello storico reale; il pool di candidati copre circa il 60% del mercato osservato; alcune righe target mancanti sono trattate come zero; mancano CR coach storici e snapshot pre-lock completi.

### Prossima implementazione necessaria

- Modellare una distribuzione di ΔCR per giocatore e propagare l'incertezza attraverso più giornate.
- Confrontare una politica PDK-immediati con una politica PDK+valore futuro, applicando gli stessi costi e vincoli a entrambe.
- Simulare scenari di rischio con dati disponibili al momento della decisione; non attribuire probabilità a cambi ruolo/infortuni senza supporto storico.
- Validare le decisioni di trasferimento in walk-forward e riportare punti netti cumulati, CR finale, trasferimenti, malus, volatilità e drawdown.
- Non aumentare il peso della plusvalenza finché la strategia multi-giornata non supera baseline semplici su dati temporali indipendenti.

## Verifiche eseguite in questo passaggio

- Aggiunto tests/test_coach_simulation.py per verificare coerenza del flag overtime, margini finali non nulli e determinismo.
- Test mirati coach: **24 passed**.
- Suite completa: **385 passed** con -W error::DeprecationWarning.
- git diff --check: passato.
- Compilazione Python dei file modificati: passata.
- Audit walk-forward coach V4 completato: 4.920 partite, MAE 15.202; bootstrap paired 10.000 repliche completato.
- Audit probabilità coach V2 completato con simulatore condiviso: Platt peggiora Brier e log loss in validation e holdout, quindi non promosso.
- Audit controfattuale costo opportunità: 10/10 solve ottimali sulla rosa rank 1 del run 20261014T175113Z_7c1f0803.
- Nessun commit o push.

## Stato complessivo e ordine di lavoro

1. Non cambiare i coefficienti di produzione basandosi sui backtest proxy attuali.
2. Ampliare la validazione coach su più stagioni e su dati pre-lock autentici di CR, quando disponibili.
3. Costruire il confronto MILP-vs-baseline con identico universo/vincoli e integrare la diagnostica controfattuale nel report delle rose.
4. Estendere la valutazione plusvalenza da previsione ΔCR a policy multi-giornata, mantenendo un holdout temporale.
5. Certificare l'intero ciclo soltanto quando rose, crediti, indisponibilità, coach ed esiti realizzati sono collegati da evidenza temporale verificabile.

Il holdout GW1 2026/27 resta congelato fino al 2026-10-23 12:00 UTC. Nessun risultato della GW1 è stato usato per tuning.
