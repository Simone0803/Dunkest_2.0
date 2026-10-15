# Historical Dunkest listone source-recovery check

Date checked: 2026-10-14

## Results

| Season/source | Public page | Observed download target | Recovery decision |
|---|---|---|---|
| 2024/25 playoff listone | https://www.dunkest.com/it/nba/notizie/fantabasket/207782/asta-fantabasket-il-listone-dunkest-playoff-nba | The article's “Scarica listone” link resolves to Google Sheets ID `1k-zD9sws6VZLLdgSNRoUS2_cQ_3N1W6znaJcF-hGSRU`; the opened sheet title is “Listone Dunkest Fantasy NBA 2026/27” | Not historical evidence; do not import as 2024/25 data |
| 2023/24 listone | https://www.dunkest.com/it/nba/notizie/fantabasket/94770/asta-dunkest-kit-stagione-nba | The article's “Scarica listone” link resolves to Google Sheets ID `1hHCsuWocqRZdyX7TFlZEKL8aeDSyMvXN`; public fetch returned HTTP 410 Gone | Historical file not recoverable through this current public link |
| 2025/26 listone page | https://www.dunkest.com/it/nba/notizie/fantabasket/17211/asta-fantabasket-listone-dunkest-nba | The page currently redirects/updates to 2026/27 and its download target is the 2026/27 Google Sheet | Do not treat the page's historic URL as proof of downloaded file season |
| Third-party Scribd copy titled 2024/25 | https://www.scribd.com/document/792314445/Listone-Dunkest-NBA-2024-25 | Page content is a user-uploaded copy; despite its title it includes 2026/27-era names such as Cooper Flagg, Cameron Boozer and AJ Dybantsa, and current-era team assignments | Reject as contaminated/mislabeled historical evidence; do not import |

## Interpretation

This pass recovered no usable historical listone file. It established that old official article links now serve a newer season or are gone, and that a third-party upload with a historical title contains later-season contamination. This is a source-resolution problem, not proof that the historical data never existed.

A read-only filename scan of project files, Documents, Desktop and Downloads found no local spreadsheet named for Dunkest/listone. The similarly named local tar archive contains source-code changes only, not market data. No downloaded spreadsheet was added to `data/raw`; no current-season or contaminated listone was relabelled as historical. Continue recovery through original browser/download backups, archived original URLs, or original file attachments. Any recovered file must retain its exact source URL, retrieval timestamp, file hash, and an explicit season/version check before it can be used as historical market evidence.

## References

- 2024/25 playoff listone page: https://www.dunkest.com/it/nba/notizie/fantabasket/207782/asta-fantabasket-il-listone-dunkest-playoff-nba
- 2023/24 listone page: https://www.dunkest.com/it/nba/notizie/fantabasket/94770/asta-dunkest-kit-stagione-nba
- 2025/26 listone page (now updated to 2026/27): https://www.dunkest.com/it/nba/notizie/fantabasket/17211/asta-fantabasket-listone-dunkest-nba
- Third-party Scribd copy rejected for temporal contamination: https://www.scribd.com/document/792314445/Listone-Dunkest-NBA-2024-25
