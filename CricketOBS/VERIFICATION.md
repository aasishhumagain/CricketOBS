# Phase 1 verification

Verified on Windows with Python 3.12.10 on 2026-11-01.

- `python -m pytest -q`: **8 passed** in 3.82 seconds.
- 100 seeded complete matches reconcile batter runs plus extras and legal balls.
- HTTP pages, controls, validation, two WebSocket subscribers, reset, automatic
  simulation and pause passed integration tests.
- `node --check app/static/live.js`: passed.
- Actual Uvicorn service started on 127.0.0.1:8000; browser overlay received its
  initial state and displayed CONNECTED, fictional teams, score and simulation labels.
- Browser screenshot inspection covered the visible portion of the fixed canvas;
  full-frame OBS rendering and YouTube transmission require the user's OBS check.

One non-failing dependency deprecation warning comes from Starlette's TestClient
using an AnyIO alias. Tests require a normal Windows process environment; the
restricted execution runner stalled async tests, which passed outside it.

No live cricket provider, OBS application, or YouTube account was used or tested.
