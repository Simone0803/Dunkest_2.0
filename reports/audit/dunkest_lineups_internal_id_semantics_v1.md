# Lineups API ID semantics audit — V1

Generated UTC: 2026-10-12T21:10:51.486465+00:00

## Results

- API responses captured: **18** (18 successful)
- Unique Lineups entity IDs: **600**
- IDs numerically overlapping profile catalogue: **335**
- Same-player matches at the same numeric ID: **0**
- Names matching an official profile slug: **474**
- Names without an exact profile-slug match: **126**

## Conclusion

The Lineups API field id is a Lineups entity identifier, not a Dunkest player-profile ID. Numeric overlap with the profile catalogue is not sufficient evidence: this capture has 335 overlapping numeric IDs but 0 same-player matches at those IDs. Do not use Lineups id to query /api/player/games. Resolve historical player-game IDs only from the official profile catalogue or a verified profile URL.

## Safety policy

- No Lineups entity ID is written into the official Dunkest player ID field.
- Names matched to profile slugs are a separate matching dimension.
- Unmatched rookies remain unresolved until a profile ID is published or an explicit official cross-reference is available.

Detailed rows: reports/audit/dunkest_lineups_internal_id_semantics_v1.csv

Reproduce with: PYTHONPATH=src ./.venv/bin/python scripts/audit_dunkest_lineups_internal_id_semantics_v1.py
