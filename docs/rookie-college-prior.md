# Rookie college prior

The prediction pipeline reads `data/rookie_college.csv`. It expects one row per player and college season.

- Historical players need `nba_pdk_per_min`: their average Dunkest PDK per minute in their first NBA regular season, reconstructed with the same PDK rules used by this project.
- Current draft class players leave `nba_pdk_per_min` blank. Their college row is scored by a Ridge model trained on the historical rows.
- The calibration requires at least 40 labelled rookies spanning at least four draft classes. It is evaluated with expanding temporal folds: each held-out draft class is predicted using earlier classes only, and imputation and scaling are refit inside each fold. If the college model does not beat the training-fold rookie NBA-rate median, the college signal is disabled. Otherwise its starting blend weight scales with the out-of-sample MAE gain, up to 20%, and fades as NBA games accumulate. With insufficient history or no measurable gain, the pipeline keeps its conservative current NBA role and credit prior.

The input columns are listed in the CSV header. Statistics are per game; `minutes_per_game` is minutes per appearance. `pace` is the college team's possessions per 40 minutes. `conference_strength` should be a numeric, season-adjusted conference or team rating where larger values mean stronger competition. `draft_pick` is the overall pick number. Leave unavailable inputs blank.

The feature builder creates a Dunkest-like college rate, adjusts it for team pace, and also uses per-40 box-score rates, usage, starts, competition strength, age, draft position, and games played. Historical rookie outcomes calibrate the translation to NBA PDK per minute; college production is never treated as an NBA rate directly.

The college estimate never exceeds 20% of the rate blend. Its starting weight is calibrated from temporal out-of-sample MAE and then decays as NBA appearances accumulate. The prediction report shows the model MAE beside the rookie-rate baseline MAE and the effective blend weight. Current NBA lineup and rotation competition continue to determine expected minutes.

## Build and refresh the data

The repository includes `scripts/build_rookie_college_data.py`, which fills this CSV from real season records:

```bash
./.venv/bin/python scripts/build_rookie_college_data.py
```

By default, it uses draft classes 2014–2025 for calibration and adds the latest specified incoming draft class (default 2026). Each draft class is paired with the NCAA season ending in that draft year (the 2025–26 college season for the 2026 draft). The NCAA records come from [Bart Torvik's player season export](https://barttorvik.com/getadvstats.php?year=2026&csv=1) and [team results](https://barttorvik.com/2026_team_results.csv): box-score averages, role, age, team pace, adjusted ratings, and strength of schedule. Draft order comes from NBA Stats DraftHistory. Rookie outcomes come from each player's NBA regular-season game logs in their first season; PDK/min is reconstructed using this project's Dunkest scoring function. The current draft class has no NBA outcome yet, so only its target column is blank by design.

The collector stores downloaded source files under `data/raw/rookie_prior/` and reuses them on the next run. To replace cached files, delete that folder before rerunning. It refuses to overwrite the final CSV if fewer than 40 NBA-labelled college players across four draft classes were matched. Rows that could not be matched to a D1 player-season export are omitted; the command reports matched counts by draft year.

Example options:

```bash
./.venv/bin/python scripts/build_rookie_college_data.py --from-draft-year 2010 --current-draft-year 2026
```

The NCAA source's `starts` field is not present in the season export and remains blank; the model treats it as unavailable. All other required box-score, age, pace, and schedule-strength inputs are checked before publishing the CSV.
