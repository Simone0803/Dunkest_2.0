# Dunkest cutoff evidence and certification v1

## Source and semantics

The existing Dunkest/Fantaking public API client uses these official endpoints:

- `GET https://fantaking-api.dunkest.com/api/v1/leagues/1/config`
- `GET https://fantaking-api.dunkest.com/api/v1/schedules/{schedule_id}/matchdays/{matchday_id}`

The responses identify the active schedule and matchday, matchday number, turn number, Dunkest match ID, and each Dunkest match's `started_at` value. The API does not provide a field explicitly named as a lock/cutoff. The cutoff is therefore classified as **official-rule-derived**, not as an explicit API lock timestamp.

Dunkest's official [calendar guide](https://www.dunkest.com/it/notizie/fantabasket/8774/calendario-dunkest-cosa-sono-giornata-turni) states that a Turn begins one minute before the first match of that day. The run-time acquisition groups official match starts by Dunkest Turn and derives that Turn's boundary as `min(match.started_at) - 1 minute`. The official [2026/27 matchday checklist](https://www.dunkest.com/it/nba/notizie/fantabasket/19903/check-list-giornata-cosa-fare-quando) confirms that team management operations close when the Turn starts. Both rule URLs are retained in the evidence.

## Evidence retained

For each prediction run, `dunkest_cutoff_evidence.json` stores the decoded config and matchday payloads, endpoint URLs, acquisition timestamps, the official rule URL, UTC normalization policy, per-turn cutoff values, fixture-to-match links, and canonical JSON SHA-256 hashes. `manifest.json` records the evidence file hash and distinguishes `certified` from `uncertified` overall pre-lock status.

The archive validator independently checks the evidence file hash, both payload hashes, derived cutoff hash, gameweek identity, turn-specific candidate cutoffs, fixture link uniqueness, and timing. Missing timezone offsets, mismatched gameweeks/turns/matches, payload tampering, missing timestamps, late source acquisition, or run/input times at or after the first-turn cutoff fail certification.

## Limits

The API does not expose an explicit lock field. Certification relies on the official published Turn rule and the official calendar's timezone-bearing `started_at` values. It does not infer a cutoff from an NBA tipoff alone. If the calendar response omits a time offset, changes schema, cannot be linked uniquely to the verified fixture mapping, or is unavailable, the run remains `uncertified`.

No historical snapshot is rewritten or recertified. No real forecast was run during this change, so the implementation has not yet certified a live run. The endpoint and rule source must be reachable and mutually consistent at a future prediction capture.
