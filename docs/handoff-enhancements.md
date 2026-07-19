# Hexmapper — Enhancement Handoff

Handoff for a fresh Claude Code session working in `C:\Users\Steph\Projects\Code\Hex Editor`.
Read this whole file before starting. Pick items by priority unless Stephen says otherwise.

## What this project is

A collaborative online hex map for a D&D West Marches group. Deployed and in use.

- **Live app**: https://hexmapper-west-marches.fly.dev — gated by `HEXMAP_KEY` secret
  (invite link = `/?key=<secret>`, key stored locally at `~/.hexmap-invite-key.txt`).
  Fly app `hexmapper-west-marches`, region `lhr`, one 256MB machine, auto-stop,
  1 GB volume mounted at `/data` holding `map.db` (SQLite). **Deploys never touch the volume.**
- **Server**: FastAPI + WebSocket, `server/src/hexserver/`
  - `app.py` — static serving, REST (`/api/config`, `/api/map`, `/api/map/export`),
    WS hub (`/ws`), invite-key gate middleware
  - `store.py` — all map state + SQLite; ops: `set_hex`, `set_icon`, `remove_hex`,
    `add_layer`, `clear_all`, import/export of the desktop `.hexmap` JSON format
  - `config.py` — 19 terrains (name→hex colour), 15 icons (name→PNG in `src/hexmapper/assets/`)
  - `tests/` — pytest for store logic
- **Client**: `web/index.html` + `web/app.js`. No framework, no build step. Canvas
  renderer (axial hex coords, flat-top), pan/zoom/keyboard nav, tools (pan, paint,
  icon, remove, add-layer, centre/fit, export, clear-all with two-click confirm),
  optimistic edits + server-authoritative broadcast with version numbers, presence
  list, auto-reconnect with snapshot resync.
- **Sync model**: per-hex last-write-wins; server validates ops, bumps a version,
  broadcasts to all; snapshot on connect/reconnect. Good enough at party scale.
- **Desktop original**: `src/hexmapper/` (pygame) — unchanged, shares assets and
  `.hexmap` format. Don't break it.
- Design spec: `docs/superpowers/specs/2026-07-19-online-collab-hexmap-design.md`.
  Architecture guide: `docs/how-it-works.html`.

## Workflow (non-negotiable, from CLAUDE.md)

- `uv` for Python, `ruff` + `mypy --strict` + `pytest` must pass; pre-commit hooks run.
- Conventional commits. Feature branches for larger work; squash-merge PRs.
- Run locally: `cd server && uv run uvicorn hexserver.app:app --app-dir src --port 8321`
  (no key gate locally; throwaway local DB `server/map.db`, gitignored).
- Tests/checks from `server/`: `uv run pytest tests`, `uv run ruff check src tests`,
  `uv run mypy --strict src/hexserver`.
- Deploy (Docker Desktop must be running): `~/.fly/bin/flyctl deploy --local-only --ha=false`.
- Verify changes in a real browser before claiming done. Don't deploy without asking
  unless Stephen already asked for the change to go live.
- **Never** commit or print the invite key into shared docs/artifacts.

## The 25 enhancements

Priorities: **P1** = highest value / do first · P2 = next · P3 = nice-to-have.
Sizes: S (<1h), M (half day), L (day+). Each item lists the main files it touches.

### Roles & safety

1. **P1 · M — DM role via second key.** Add `HEXMAP_DM_KEY` secret; gate destructive
   ops (`clear_all`, future import) server-side by role derived from which key the
   cookie matches. Hide/disable DM-only buttons for players. (`app.py`, `web/app.js`, `index.html`)
2. **P1 · M — Map import/restore endpoint.** `POST /api/map/import` accepting a
   `.hexmap` JSON upload, DM-only; UI button next to Export. Closes the
   backup-restore loop (export already exists; `store.import_hexmap` already exists). (`app.py`, `web/`)
3. **P2 · M — Edit history / audit log.** Append `(ts, player, op)` to an `ops` table;
   "recent changes" panel in the sidebar; groundwork for undo. (`store.py`, `app.py`, `web/`)
4. **P2 · L — Undo.** Global undo of the last N ops from the ops log (DM-only), or
   per-hex "revert to previous". Requires item 3. (`store.py`, `app.py`, `web/`)
5. **P3 · S — Rate limiting.** Cap ops/second per connection to stop a stuck client
   or griefer from flooding. (`app.py`)

### West Marches gameplay

6. **P1 · L — Hex notes.** Click a hex in a "notes" tool to read/write freeform text
   ("Session 12: owlbear den"). New `notes` column; note indicator dot on hexes;
   panel shows note + last editor. The single highest-value feature for the group. (`store.py`, `app.py`, `web/`)
7. **P2 · M — Named place labels.** Text labels rendered on/under hexes at readable
   zoom levels (e.g. "Akaford"). Store as per-hex `label`; declutter by hiding when
   zoomed far out. (`store.py`, `app.py`, `web/app.js`)
8. **P2 · S — Party position marker.** One special movable token everyone sees;
   "move party here" via context/tool. Broadcast like any op; store in a `meta` table. (`store.py`, `app.py`, `web/`)
9. **P2 · M — Fog-of-war mode.** Player view renders unexplored hexes as blank/fog
   regardless of terrain; DM sees all; DM "reveal" tool flips an `explored` flag.
   Depends on item 1 for roles. (`store.py`, `app.py`, `web/app.js`)
10. **P3 · M — Travel measure tool.** Click two hexes → hex distance + path
    highlight + configurable "days at N hexes/day". Pure client feature (axial
    distance is trivial). (`web/app.js`)
11. **P3 · M — Rivers & roads.** Edge features drawn along hex borders (river between
    two hexes, road through). New data shape: per-edge records. Design carefully to
    stay compatible with `.hexmap`. (`store.py`, `app.py`, `web/app.js`)
12. **P3 · L — Multiple maps.** Region maps / dungeon maps with a switcher; maps
    table + map_id on hexes + per-map WS rooms. The design spec already sketches this. (`server/`, `web/`)

### Collaboration feel

13. **P2 · S — Live cursors.** Broadcast hovered hex per player (throttled);
    render soft highlights + name tags in other tabs. Ephemeral — no persistence. (`app.py`, `web/app.js`)
14. **P2 · S — Hex ping.** Double-click flashes a hex for everyone (find the party,
    "look here"). Ephemeral broadcast op. (`app.py`, `web/app.js`)
15. **P2 · S — Presence polish.** Stable per-player colours, dedupe repeated names,
    join/leave toasts, count in the tab title. (`app.py`, `web/`)
16. **P3 · S — "Last edited by" on hover.** Tooltip showing who last touched a hex
    (needs item 3's log or a per-hex `edited_by` column). (`store.py`, `web/app.js`)

### UX & rendering

17. **P1 · M — Touch support.** Single-finger pan (in pan tool), two-finger
    pinch-zoom, larger touch targets; test on a phone — players will open this at
    the table. Pointer events are already in place, so this is incremental. (`web/app.js`, `index.html`)
18. **P1 · S — Visual icon picker.** Replace the `<select>` with a thumbnail grid
    (icons are already served as PNGs). Big usability win, tiny effort. (`web/index.html`, `web/app.js`)
19. **P2 · S — Keyboard shortcuts for tools.** P/B/I/R/E-style keys + a "?" overlay
    listing all controls; extend the existing hint line. (`web/app.js`, `index.html`)
20. **P2 · M — PNG export.** Render the full map to an offscreen canvas and download
    as PNG for Discord sharing. (`web/app.js`)
21. **P2 · M — Minimap.** Small overview in a corner with a viewport rectangle;
    click to jump. Render cheaply from hex data at low res. (`web/app.js`)
22. **P3 · S — Hex coordinate readout + jump.** Show `q,r` under the cursor; a "go to
    coordinate" box. Helps players reference locations in session notes. (`web/app.js`)
23. **P3 · M — Theme & grid options.** Light map background option, grid line
    toggle/strength, saved per player in localStorage. (`web/index.html`, `web/app.js`)

### Engineering & ops

24. **P1 · S — CI for the server + web.** Extend `.github/workflows/ci.yml` to run
    server pytest/ruff/mypy (the existing CI only covers the desktop app). Optional:
    deploy-on-main with a `FLY_API_TOKEN` repo secret — ask Stephen first. (`.github/`, maybe `justfile`)
25. **P2 · M — Client resync hardening + tests.** Detect version gaps in broadcasts
    and refetch the snapshot; add server WS tests with FastAPI's TestClient
    (connect, op, broadcast, reject-invalid, key gate). (`web/app.js`, `server/tests/`)

## Suggested first batch

`1 → 2 → 18 → 17 → 24 → 6` — after that, ask Stephen what the group is feeling the
lack of. Items 3, 9, 12 are the big structural ones; do them on feature branches.

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
  `server/` with the shared root venv.
