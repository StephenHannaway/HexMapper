# Hexmapper — Enhancement Handoff

Handoff for a fresh Claude Code session working in `C:\Users\Steph\Projects\Code\Hex Editor`.
Read this whole file before starting. Pick items by priority unless Stephen says otherwise.

**Status 2026-07-21:** **All 27 items are done, merged and deployed.** Batch 1
(items 1-3, 6-9, 13-15, 17-20, 22, 24-27), batch 2 (4 undo, 5 rate limiting, 10
travel measure, 16 last-edited-by, 21 minimap, 23 theme/grid, plus a sidebar
layout redesign), and item 12 (multiple maps) are all live on
https://hexmapper-west-marches.fly.dev. The multiple-maps migration was verified
against a copy of the live prod DB (218 hexes preserved) before deploy; a backup
sits in `backups/` (gitignored). Nothing outstanding on the original backlog —
pick new work with Stephen.

## What this project is

A collaborative online hex map for a D&D West Marches group. Deployed and in use.

- **Live app**: https://hexmapper-west-marches.fly.dev — gated by `HEXMAP_KEY` secret
  (invite link = `/?key=<secret>`, key stored locally at `~/.hexmap-invite-key.txt`).
  Fly app `hexmapper-west-marches`, region `lhr`, one 256MB machine, auto-stop,
  1 GB volume mounted at `/data` holding `map.db` (SQLite). **Deploys never touch the volume.**
- **Server**: FastAPI + WebSocket, `server/src/hexserver/`
  - `app.py` — static serving, REST (`/api/config`, `/api/map`, `/api/map/export`,
    `/api/map/import` [POST, DM-only], `/api/history`), WS hub (`/ws`),
    invite-key gate middleware, dm/player roles, per-op audit logging
  - `store.py` — all map state + SQLite; ops: `set_hex`, `set_icon`, `set_note`,
    `set_party`, `set_explored`, `set_fog`, `remove_hex`, `add_layer`, `clear_all`,
    `log_op`/`history`, import/export of the desktop `.hexmap` JSON format
  - `config.py` — 19 terrains (name→hex colour), 15 icons (name→PNG in `src/hexmapper/assets/`)
  - `tests/` — 47 pytest tests: store logic + full app-level WS/REST coverage
    (TestClient; key gate, roles, broadcasts, import, history, fog, cursors)
- **Client**: `web/index.html` + `web/app.js`. No framework, no build step. Canvas
  renderer (axial hex coords, flat-top), pan/zoom/keyboard nav + pinch zoom, tools
  (pan, paint, icon, notes, move-party, reveal/hide [DM], remove, add-layer,
  centre/fit, export, import [DM], clear-all [DM]), optimistic edits +
  server-authoritative broadcast with version numbers, presence list with colours,
  live cursors, recent-changes feed, hex ping, fog rendering, auto-reconnect with
  snapshot resync + version-gap resync.
- **Sync model**: per-hex last-write-wins; server validates ops, bumps a version,
  broadcasts to all; snapshot on connect/reconnect; client refetches `/api/map` if
  a broadcast version skips ahead. Good enough at party scale.
- **Desktop original**: `src/hexmapper/` (pygame) — unchanged, shares assets and
  `.hexmap` format (its `from_json_dict` ignores unknown keys, so the web format's
  extra fields — `note`, `note_author` — are safe). Don't break it.
- Design spec: `docs/superpowers/specs/2026-07-19-online-collab-hexmap-design.md`.
  Architecture guide: `docs/how-it-works.html` (predates roles/notes/fog — update it
  when convenient). Roads & rivers plan: `docs/superpowers/plans/2026-07-20-roads-and-rivers.md`.

## What's been built (branch `feat/enhancements-batch-1`, PR #1)

- **Roles**: second secret `HEXMAP_DM_KEY` → role dm/player from which key the
  `mapkey` cookie matches. `clear_all`, `set_explored`, `set_fog` and map import are
  DM-only (`DM_OPS` in app.py); DM-only buttons carry class `dm-only` and hide for
  players. With no DM key set everyone is a DM (pre-role behaviour). Visiting an
  invite link now *replaces* a stale cookie, so a player can upgrade via the DM link.
  **Prod prerequisite:** `flyctl secrets set HEXMAP_DM_KEY=<new secret>`.
- **Schema migrations** (run automatically in `MapStore.__init__`, additive ALTERs):
  `note`, `note_author`, `explored INTEGER DEFAULT 1` columns on `hexes`; new tables
  `ops` (audit, capped at 1000 rows) and `meta` (key/value: `party`, `fog`).
- **Notes**: `set_note` op stamped with the sender's hello name; floating panel,
  yellow dot indicator, "last edited by". Round-trips through `.hexmap`.
- **History**: every mutating op logged `(ts, player, op, detail)`; `GET /api/history`;
  broadcasts carry `by`; sidebar feed coalesces consecutive paints. Groundwork for
  undo (item 4) and per-hex attribution (item 16).
- **Fog-of-war**: `set_fog` toggle + `set_explored` per hex (Reveal/hide tool).
  Players render unexplored hexes as blank fog (icons/notes suppressed, note reads
  blocked); DM sees them dimmed. Painting always marks a hex explored. Off by default.
- **Party marker**: `set_party` (anyone), gold ring, stored in `meta`.
- **Ping**: double-click → ephemeral `ping` broadcast (no version/log), 3 pulses.
- **Live cursors**: throttled `cursor` op, handled *before* the lock, broadcast
  excludes sender (`hub.broadcast(..., exclude=ws)`), keyed by connection `cid`;
  coloured outline + name tag, 6s expiry.
- **Presence polish**: name→hue colours, duplicate names collapse to ×N, join/leave
  toasts, online count in the tab title.
- **UX**: icon thumbnail grid; pinch-zoom/two-finger pan (`pointers` map in app.js;
  needs a real phone test); hotkeys P/B/I/N/M/R + C fit + `?` help overlay + Esc.
- **CI**: `server-check` / `server-test` jobs. **Must** `uv sync --all-packages --dev`
  at the repo root (a member-dir `uv sync --dev` misses the root dev group — this
  broke CI once already).
- **Resync**: client refetches the snapshot when `msg.version > state.version + 1`.

## Workflow (non-negotiable, from CLAUDE.md)

- `uv` for Python, `ruff` + `mypy --strict` + `pytest` must pass; pre-commit hooks run.
- Conventional commits. Feature branches for larger work; squash-merge PRs.
- Run locally: `cd server && uv run uvicorn hexserver.app:app --app-dir src --port 8321`
  (no key gate locally; throwaway local DB `server/map.db`, gitignored). To exercise
  roles locally: `HEXMAP_KEY=x HEXMAP_DM_KEY=y uv run uvicorn ...`.
- Tests/checks from `server/`: `uv run pytest tests`, `uv run ruff check src tests`,
  `uv run mypy --strict src/hexserver`.
- Deploy (Docker Desktop must be running): `~/.fly/bin/flyctl deploy --local-only --ha=false`.
- Verify changes in a real browser before claiming done. Don't deploy without asking
  unless Stephen already asked for the change to go live.
- **Never** commit or print the invite key into shared docs/artifacts.

## The backlog

Priorities: **P1** = highest value / do first · P2 = next · P3 = nice-to-have.
Sizes: S (<1h), M (half day), L (day+). ✓ = done on `feat/enhancements-batch-1`.

### Roles & safety

1. ✓ **DM role via second key.**
2. ✓ **Map import/restore endpoint.**
3. ✓ **Edit history / audit log.**
4. ✓ **Undo.** DM-only. Each mutating store method captures an inverse onto a
   capped 100-entry `undo` table; the `undo` op pops and applies it, then
   broadcasts a snapshot. Undo button (disabled via snapshot `can_undo`) + Ctrl+Z.
5. ✓ **Rate limiting.** Token-bucket per WS connection (`RateLimiter`, 40 burst,
   25/s). A dropped non-cursor op replies `{error, resync:true}` so the client
   refetches the snapshot and can't diverge from a silently-dropped edit.

### West Marches gameplay

6. ✓ **Hex notes.**
7. ✓ **Named place labels.** Per-hex `label` column (auto-migrated), `set_label` op,
   set via a "Place name" field in the notes panel; drawn as outlined text under the
   hex centre, hidden below ~11px hex size and on fogged player hexes. Rides `.hexmap`.
8. ✓ **Party position marker.**
9. ✓ **Fog-of-war mode.**
10. ✓ **Travel measure tool.** Measure tool (T): click start then end → hex
    distance + days at a configurable `hexes/day`; a client travel A* routes the
    highlighted path and roads discount it ("N via roads"). Pure client feature.
11. *(superseded — see items 26/27, planned in
    `docs/superpowers/plans/2026-07-20-roads-and-rivers.md`)*
12. **P3 · L — Multiple maps.** Region maps / dungeon maps with a switcher; maps
    table + map_id on hexes + per-map WS rooms. The design spec already sketches this. (`server/`, `web/`)

### Collaboration feel

13. ✓ **Live cursors.**
14. ✓ **Hex ping.**
15. ✓ **Presence polish.**
16. ✓ **"Last edited by" on hover.** Per-hex `edited_by` column stamped on
    paint/icon/note/label, surfaced in the snapshot, broadcasts and `.hexmap`
    export; shown in the sidebar coordinate readout on hover (fog-aware).

### UX & rendering

17. ✓ **Touch support.** (Implemented; still wants a real-phone sanity check.)
18. ✓ **Visual icon picker.**
19. ✓ **Keyboard shortcuts + help overlay.**
20. ✓ **PNG export.** "Export PNG" renders the whole map to an offscreen canvas sized
    to the hex bounds and downloads `world-map.png`. `draw()` targets a swappable
    `ctx`; ephemeral overlays skipped via an `exporting` flag; player exports respect
    fog (fogged hexes render blank as on screen). (`web/app.js`)
21. ✓ **Minimap.** Bottom-right overview rendered from hex data at low res with a
    live viewport rectangle and party dot; click to recentre. Toggle in Display.
22. ✓ **Hex coordinate readout + jump.** Sidebar shows `q,r` under the cursor; a
    "go to q,r" box recentres the view on a typed hex. (`web/app.js`)
23. ✓ **Theme & grid options.** Light-background toggle, grid on/off + strength,
    minimap toggle, travel rate — all in a Display section, saved to localStorage
    under `hexPrefs`.

### Engineering & ops

24. ✓ **CI for the server + web.** (Deploy-on-main still optional — ask Stephen first.)
25. ✓ **Client resync hardening + tests.**

### New: dynamic roads & rivers

Full implementation plan with code: `docs/superpowers/plans/2026-07-20-roads-and-rivers.md`.
Shared infrastructure (features table, A* pathfinding, feature rendering) built once,
then two thin tool variants.

26. ✓ **Dynamic road building.** Road tool (O): click waypoints, dashed live A*
    preview, Enter/double-click builds, Esc cancels, Shift-click removes. Server
    routes authoritatively (`pathfind.py`, cost tables in `config.py`, served to the
    client via `/api/config.feature_costs`); `features` table; awareness via
    `store.features_at(q, r)` / client `featureIdsAt(q, r)`.
27. ✓ **Dynamic river building.** Same skeleton, river cost profile, wide blue
    rendering beneath roads; both fog-aware (players see lines break at unexplored
    hexes) and both round-trip through `.hexmap`.

## Item 12 as built (multiple maps)

- `maps` table (default `World Map`, id 1); `map_id` column on
  hexes/features/meta/ops/undo. Migration in `MapStore._migrate` rebuilds the
  old single-map `hexes`/`meta` tables to carry `map_id` and adopts all existing
  rows under map 1 — backward compatible and non-destructive.
- Per-map version counters (`store.versions[map_id]`) so a client only resyncs
  when its own map changes. WebSocket **rooms**: `hub.rooms[ws]` tracks the map a
  connection is viewing; edits/cursors/pings/presence broadcast only within that
  room. Ops carry no client-supplied `map_id` — the server uses the connection's
  room (authoritative).
- New ops: `switch_map`, and DM-only `create_map`/`rename_map`/`delete_map`
  (handled in `handle_map_admin`, not `apply_op`). Deleting a map bounces its
  viewers back to the World Map.
- Client: Maps section (switcher + DM new/rename/delete). Export/import/resync/
  history all carry `?map_id=`.

## Ideas beyond the original backlog

Nothing on the 27-item list remains. Natural follow-ups if the group asks:
per-map fog defaults, a "duplicate map" action, drag-reorder of the map list,
or dungeon-scale tooling (smaller hexes / square grid option).

## Gotchas learned the hard way

- PowerShell 5.1 on this machine: no `&&`, no `RandomNumberGenerator::Fill`;
  the Bash tool exists for POSIX syntax.
- The canvas is inside a flex row — keep `min-width: 0` on it or the backing-store
  resize loop pushes the sidebar off screen.
- `BaseHTTPMiddleware` does not cover WebSockets — the key gate is checked
  separately in `ws_endpoint`; keep it that way for any new WS routes.
- Iterating a set while mutating it broke `add_layer` once (RuntimeError kills the
  WS silently). The WS handler now logs + survives unexpected op errors — preserve that.
- `uv` made this repo a workspace (`server` is a member); run server commands from
  `server/` with the shared root venv. **In CI, sync with
  `uv sync --all-packages --dev` from the repo root** — `uv sync --dev` inside
  `server/` installs only the member's deps and the dev tools vanish.
- Chrome caches `/app.js` hard during local dev — hard-reload (Ctrl+Shift+R) after
  edits or you will debug a stale module (this cost 30 minutes once).
- An edit sent before the first WS snapshot used to suppress fit-to-view; guarded by
  `state.hadSnapshot` now — don't regress it.
- Every tool button needs BOTH: an entry in `setTool`'s id list AND an
  `onclick = () => setTool(...)` binding (forgetting the second shipped once).
- `gh` CLI and `jq` are not installed; use the GitHub API via
  `git credential fill` + `uv run python` (never print the token).
