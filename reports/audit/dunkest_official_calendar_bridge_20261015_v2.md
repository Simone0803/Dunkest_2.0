# Official Dunkest API calendar bridge audit — GW1

- Official API endpoint: `https://fantaking-api.dunkest.com/api/v1/schedules/57/matchdays/1858`
- Schedule ID / matchday ID: `57` / `1858`
- Official matches: **16**
- Unique NBA GAME_ID links: **16 / 16**
- Turns: `{'1': 3, '2': 11, '3': 2}`
- Eligible team sides: **30**; unknown sides: **0**
- Raw payload SHA-256: `e4381a148ba4e5986d7752e683b2284eb196c6fca44f27056503b0431943d5a9`
- Mapping CSV SHA-256: `fa8186e88ae1c07741b448cc6f726e1291b6405f26490eb34f06c5de418cb0c8`

The official API supplies Giornata, Turno and per-team `is_valid`. The NBA schedule supplies only NBA GAME_ID identity.

This is an audit-only artifact. No production mapping, market snapshot, model, target or prediction was written.
