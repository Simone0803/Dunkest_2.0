# Historical Dunkest endpoint discovery (v1)

- Checked the public game configuration, league configuration, schedule-list routes, schedule-item routes, and a small set of plausible historical-season routes.
- `GET /api/v1/games/1/config`: HTTP 200; exposes current game configuration and a league list, not a historical schedule archive.
- `GET /api/v1/leagues/1/config`: HTTP 200; exposes current-season config, but historical query parameters previously tested do not select old seasons.
- `GET /api/v1/schedules`: HTTP 401 `UNAUTHENTICATED`; schedule collection is not publicly listable without authentication.
- `GET /api/v1/schedules/1`: HTTP 405 (GET unsupported); `/schedules/{id}/matchdays` and guessed league/competition/season routes return 404.
- Public site `/js/main.js` did not expose the historical calendar routes in the inspected source.
- OpenAPI/docs URLs tried returned 404; these probes do not prove no supported authenticated endpoint exists.

## Conclusion

The exact schedule-item endpoint is usable for known schedule and matchday IDs, but a public endpoint to enumerate historical schedules was not found. The unauthenticated search plus coarse ID survey did not recover regular-season calendars for 2018/19–2021/22. Do not bypass authentication, infer IDs from stats season IDs, or substitute reconstructed proxies for official PDK targets.

## Safeguards

Read-only requests only. No account credentials, raw datasets, target values, model, temporal split, or backtest changed.
