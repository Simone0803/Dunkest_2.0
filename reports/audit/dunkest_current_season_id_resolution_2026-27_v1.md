# Dunkest 2026–27 Player ID Resolution Audit

- Generated (UTC): 2026-10-12T18:30:32.544780+00:00
- Market: `data/processed/player_credits_26_gw1.parquet`
- Catalogue: `data/raw/dunkest_player_games_history_v1/player_catalog_current.json`
- Network requests: none; this is a local identity-resolution audit only.

## Summary

- Unique market names: **566**
- Resolved unique player IDs: **493** (87.1%)
- Explicit, reviewed aliases: **5**
- Unmatched names: **71**
- Ambiguous names: **2**

## Explicit aliases applied

| Market name | Catalogue ID | Catalogue name |
|---|---:|---|
| Ron Holland II | 2470 | Holland II Ronald;Ronald Holland Ii |
| Kenyon Martin Jr | 740 | Kj Martin;Martin KJ |
| Nah'shon Hyland | 959 | Bones Hyland;Hyland Bones |
| Alex Sarr | 2449 | Alexandre Sarr;Sarr Alexandre |
| Carlton Carrington | 2460 | Bub Carrington;Carrington Bub |

## Ambiguous identities left unresolved

| Market name | Candidate IDs | Candidate names |
|---|---|---|
| Dru Smith | 1007;1085 | Dru Smith;Smith Dru |
| Jaylin Williams | 1115;2406 | Jaylin Williams;Williams Jaylin |

## Unmatched names left unresolved

No fuzzy match was applied; these names remain excluded from ID-based collection until the official catalogue or an explicit alias can support the mapping.

- Henri Veesaar
- Kingston Flemings
- Zuby Ejiofor
- Joshua Jefferson
- Kylan Boswell
- Michael Ajayi
- Mikel Brown Jr.
- Tyler Bilodeau
- Chris Cenac Jr.
- Dillon Mitchell
- Milos Uzan
- Christian Anderson
- Hannes Steinbach
- Caleb Wilson
- Dailyn Swain
- Tobe Awaka
- Ernest Udeh Jr.
- Meleek Thomas
- Morez Johnson
- Sergio De Larrea
- Tobias Lawal
- Vsevolod Ishchenko
- Alpha Diallo
- Trevon Brazile
- Ebuka Okorie
- Elijah Harkless
- Ugonna Onyenso
- Lajae Jones
- Yaxel Lendeborg
- Bruce Thornton
- Quadir Copeland
- Braden Smith
- Baba Miller
- Keaton Wagler
- Nick Martinelli
- Ak Okereke
- Arthur Kaluma
- Cameron Carr
- Cameron Boozer
- Karim Lopez
- Ryan Conwell
- Tre Donaldson
- Bogoljub Markovic
- Brayden Burries
- Malique Lewis
- Nate Ament
- Isaiah Evans
- Trey Kaufman-renn
- Jaron Pierre Jr
- Jack Kayil
- Tyler Nickel
- Aday Mara
- Bennett Stirtz
- Otega Oweh
- Izaiyah Nelson
- Duke Miles
- Labaron Philon
- Koa Peat
- Alex Karaban
- Darius Acuff Jr
- Emanuel Sharp
- Ja'kobi Gillespie
- Jayden Quaintance
- Maliq Brown
- Tarris Reed Jr
- Allen Graves
- Jaden Bradley
- Nate Bittle
- Darryn Peterson
- Aj Dybantsa
- Felix Okpara

## Policy

- An alias is accepted only when its exact target slug resolves to one unique numeric catalogue ID.
- Duplicate IDs/names remain ambiguous; no guess is made.
- This audit does not alter the market, raw API checkpoints, historical datasets, or frozen prediction runs.
