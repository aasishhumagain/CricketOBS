# CricketOBS — Phase 1

A Windows-friendly, local score-only broadcast starter. The scorer enters each
delivery manually. No real match feed, footage,
logos, music, API keys, or YouTube credentials are included.

## Quick launch on Windows

1. Install Python **3.11 or newer** from python.org; select **Add python.exe to PATH**.
   Python 3.12 is the tested version. Open a new terminal after installation.
2. Extract the ZIP to a writable folder (do not run inside the ZIP).
3. Double-click `setup.bat`. Internet access is needed to install dependencies.
   Wait for “Setup complete”.
4. Double-click `run.bat` and leave its window open.
5. Open **http://127.0.0.1:8000/** in your browser.
6. Set both team names and overs per innings, then choose **New match / apply setup**.
   Click the outcome button for each delivery. **Undo last ball** restores the
   previous score, even across an innings change.
7. Stop the server with **Ctrl+C** in its window.

Equivalent PowerShell commands from the extracted project folder:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Activation is unnecessary; these commands work without changing PowerShell's
execution policy. If `venv` creates Python but fails at `ensurepip`, and your main
Python has pip 22.3 or newer, use this fallback (also supported by setup.bat):

```powershell
python -m pip --python .venv install -r requirements.txt
```

If Python is missing, repair its installation and PATH. If downloads fail, check
the internet/proxy and rerun setup. If port 8000 is occupied, stop the other server
or use `--port 8001` and change every dashboard/overlay URL accordingly.

## Add the overlay in OBS

1. Start CricketOBS first. In OBS create a scene, then add a **Browser** source.
2. Leave “Local file” unchecked. Set URL to
   **http://127.0.0.1:8000/overlay**.
3. Set **Width 1920**, **Height 1080**, and FPS **30**. The scorebar has a
   transparent background so the gameplay remains visible behind it; match your
   OBS canvas to 1920×1080.
4. Fit the source to the canvas if needed. Keep the lower scorebar inside the safe area.
5. Enter a delivery in the dashboard and confirm the score updates in OBS.

OBS handles encoding and YouTube streaming. Connect your own channel in OBS,
check its stream settings and preview, and start a private/unlisted test stream
yourself. This starter does not create streams, start OBS, or transmit to YouTube.
No OBS installation or channel access is needed to preview locally.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Manual smoke check:

- Visit http://127.0.0.1:8000/health — expect `status: ok`, `mode: manual`.
- Open dashboard and overlay together. Both should show CONNECTED.
- Click a run or extra: both views change; wides and no-balls do not use a legal ball.
- Undo restores the preceding score. New match applies team names and over limit.
- Refresh the overlay: it immediately receives the current shared state.
- Stop the server: the overlay displays OFFLINE and warns the score may be stale.
  Restart: it reconnects automatically to a new paused match.
- Let a match finish: the second innings has a target and the result appears.

Automated coverage includes strike changes, six-ball overs, all-out innings,
extras, free hits, successful chases, defended totals, ties, deterministic seeds,
The dashboard sends manual outcomes to two or more live WebSocket viewers.

## Structure and API

- `app/engine.py`: cricket innings and serializable score state.
- `app/main.py`: FastAPI lifecycle, manual HTTP controls, roster API, and WebSockets.
- `app/database.py`: SQLite roster storage and idempotent initial seeding.
- `app/npl_2026_rosters.json`: NPL Season 3 team/player seed data and source metadata.
- `app/static/`: original HTML/CSS/JavaScript dashboard and 1920×1080 overlay.
- `data/cricketobs.sqlite3`: generated local database; player edits persist here.
- `tests/`: engine and HTTP/WebSocket tests.
- `requirements.txt`: pinned direct dependencies; `requirements-lock.txt`: full
  tested environment snapshot for reproducible installation.

`GET /api/state` returns the shared match snapshot. `GET /health` checks service
availability. `WS /ws` sends the initial snapshot, changes, and a 10-second
heartbeat snapshot. Slow viewers receive the latest state without an unbounded
queue. The frontend reconnects with backoff. `POST /api/control` accepts JSON:

```json
{"action":"delivery","outcome":"4"}
```

Actions: `delivery` (`0`,`1`,`2`,`3`,`4`,`6`,`W`,`Wd`,`Nb`), `undo`, and `reset`
(`team_a`, `team_b`, `overs`). Explore schemas at http://127.0.0.1:8000/docs.
`GET /api/roster` returns the eight NPL 2026 Season 3 teams and their saved squads.
`POST /api/roster/{team_slug}/players` adds a player, and
`DELETE /api/roster/{team_slug}/players/{player_id}` removes one. Roster changes
are stored in `data/cricketobs.sqlite3` and survive server restarts; the database
is seeded on first startup from `app/npl_2026_rosters.json`. The imported player
list, team logos, and portraits are attributed to NPLT20League.com in the roster
page and seed file. The site identifies itself as independent and not affiliated
with the official NPL. Match score state remains in memory and resets when the
server restarts.

## Scoring rules and limits

Two 20-over innings, 11 batters per side, six legal deliveries per over, strike
rotation on odd runs and over ends, boundaries, caught wickets, wides and no-balls,
one-run extras and a free hit after no-ball. Wide/no-ball events do not count as
legal deliveries; this simplified generator assigns no bat runs on those events.
A free hit survives another illegal delivery and suppresses the next legal
caught wicket. All wickets are caught: run-outs and other dismissal types are
not generated. The chase ends on reaching the target; innings end at 10 wickets
or the over limit. Ties stand without a super over.

Manual scoring is not a full laws engine. No bowling figures, byes, leg-byes, penalties, reviews, rain/DLS,
abandonments, substitutions, or tournament rules. Innings transitions are
immediate. The final striker indicator is hidden after completion.

Run **one server worker**, on loopback only, for a trusted local operator.
No authentication, persistence, or multi-worker synchronization is provided.
Browser commands with a mismatched Origin are rejected; this is not an
internet-facing administration service. The overlay has no external frontend
library or font dependency; NPL team logos and player portraits are loaded from
NPLT20League.com and require an internet connection.

## Future licensed API integration

Manual scoring is the only implemented source. A future provider adapter should
normalize an authorized feed into the same snapshot schema, replacing the scorer's
delivery controls. Keep API credentials server-side; account for provider
rate limits, corrections, innings identifiers, duplicates, out-of-order updates,
and stale-feed indicators. Add contract tests and persistence before live use.


WebSocket implementation reference:
[FastAPI official documentation](https://fastapi.tiangolo.com/advanced/websockets/).

## Studio and OBS scene controls

Keep OBS pointed at the same /overlay URL. The On-air overlay buttons on every
studio page switch that shared output between Live score, Countdown, Teams,
Squads, Playing XI, Toss and hidden graphics. The dashboard preview shows the
same output as OBS. Scene choices and match data are shared through WebSockets.

Select teams on Match info, save eleven players per side on Playing XI before
scoring, and record the result on Toss. Saved XI names and available portraits
appear in the scorebar and team sheets. Use dashboard outcome buttons for scoring;
Start timer counts down once per second; Pause holds the remaining time. Scoring stays manual. Full-screen scenes use the
saved stream title and background. Live score retains a transparent background.
Match settings, XI, toss and scene choices reset when the server restarts;
roster edits remain stored in SQLite.

Frontend renderer checks: node --test tests/test_overlay.cjs

Additional overlay scenes include Match summary (scores, rates, extras and recent
balls), Innings break (chase target), and Match result. Result shows a waiting
message until the match finishes. The visual style selector applies Classic
(red/navy), Midnight (cyan/navy), or Minimal (white/green) to live score and
full-screen graphics. Classic uses the configured scene background; Midnight and
Minimal provide their own coordinated backgrounds. Neither scenes nor styles
start the timer or change match scores.
