# Ricontrollo DNS fonti Dunkest

**Timestamp controllo:** 2026-10-24 08:14:10 UTC  
**Esito:** DNS generale non funzionante nell'ambiente.

Controllo singolo con `socket.getaddrinfo(..., 443)`:

| Host | Timestamp UTC | Esito |
|---|---|---|
| `fantaking-api.dunkest.com` | 2026-10-24T08:14:10.483484Z | `gaierror [Errno 8] nodename nor servname provided, or not known` |
| `example.com` | 2026-10-24T08:14:10.491200Z | `gaierror [Errno 8] nodename nor servname provided, or not known` |

Poiché fallisce anche il dominio esterno di controllo, questa prova indica un problema DNS generale dell'ambiente, non un errore HTTP specifico dell'API Dunkest. L'endpoint `https://fantaking-api.dunkest.com/api/v1/leagues/1/config` non è stato richiesto: senza risoluzione DNS non è possibile determinarne lo status code. Non sono stati ripetuti tentativi né avviato un forecast.

La nuova evidenza non cambia il blocco operativo: giornata futura, fixture e cutoff restano non verificati. Le fonti ufficiali pubbliche e la loro insufficienza per determinare gli orari dei turni sono documentate nell'audit [dunkest_first_prospective_forecast_block_20261024_v1.md](dunkest_first_prospective_forecast_block_20261024_v1.md). Riprendere l'acquisizione soltanto quando la risoluzione DNS è disponibile e l'API restituisce il calendario ufficiale.
