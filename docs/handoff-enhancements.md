# Hexmapper — Enhancement Handoff

Handoff for a fresh Claude Code session working in `C:\Users\Steph\Projects\Code\Hex Editor`.
Read this whole file before starting. Pick items by priority unless Stephen says otherwise.

**Status 2026-07-20:** 14 of the original 25 items are done (plus fixes) on branch
`feat/enhancements-batch-1`, draft PR #1 — not yet merged or deployed. The done work
is summarised under "What's been built" and each finished item below is marked ✓.

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
4. **P2 · L — Undo.** Global undo of the last N ops from the ops log (DM-only), or
   per-hex "revert to previous". The ops log (item 3) exists; `detail` currently
   records the *new* state only — undo needs prior-state capture added to `log_op`
   call sites, or a rework to log before/after. (`store.py`, `app.py`, `web/`)
5. **P3 · S — Rate limiting.** Cap ops/second per connection to stop a stuck client
   or griefer from flooding. Live cursors make this slightly more pressing. (`app.py`)

### West Marches gameplay

6. ✓ **Hex notes.**
7. **P2 · M — Named place labels.** Text labels rendered on/under hexes at readable
   zoom levels (e.g. "Akaford"). Store as per-hex `label`; declutter by hiding when
   zoomed far out. (`store.py`, `app.py`, `web/app.js`)
8. ✓ **Party position marker.**
9. ✓ **Fog-of-war mode.**
10. **P3 · M — Travel measure tool.** Click two hexes → hex distance + path
    highlight + configurable "days at N hexes/day". Pure client feature. Once
    items 26/27 land, roads should reduce travel cost. (`web/app.js`)
11. *(superseded — see items 26/27, planned in
    `docs/superpowers/plans/2026-07-20-roads-and-rivers.md`)*
12. **P3 · L — Multiple maps.** Region maps / dungeon maps with a switcher; maps
    table + map_id on hexes + per-map WS rooms. The design spec already sketches this. (`server/`, `web/`)

### Collaboration feel

13. ✓ **Live cursors.**
14. ✓ **Hex ping.**
15. ✓ **Presence polish.**
16. **P3 · S — "Last edited by" on hover.** Tooltip showing who last touched a hex.
    Cheapest route now: per-hex `edited_by` column updated in `set_hex`/`set_icon`,
    surfaced in snapshot; the ops log alone can't answer historical hexes cheaply.
    (`store.py`, `web/app.js`)

### UX & rendering

17. ✓ **Touch support.** (Implemented; still wants a real-phone sanity check.)
18. ✓ **Visual icon picker.**
19. ✓ **Keyboard shortcuts + help overlay.**
20. **P2 · M — PNG export.** Render the full map to an offscreen canvas and download
    as PNG for Discord sharing. Respect fog for player exports. (`web/app.js`)
21. **P2 · M — Minimap.** Small overview in a corner with a viewport rectangle;
    click to jump. Render cheaply from hex data at low res. (`web/app.js`)
22. **P3 · S — Hex coordinate readout + jump.** Show `q,r` under the cursor; a "go to
    coordinate" box. The cursor-op plumbing already computes the hovered hex. (`web/app.js`)
23. **P3 · M — Theme & grid options.** Light map background option, grid line
    toggle/strength, saved per player in localStorage. (`web/index.html`, `web/app.js`)

### Engineering & ops

24. ✓ **CI for the server + web.** (Deploy-on-main still optional — ask Stephen first.)
25. ✓ **Client resync hardening + tests.**

### New: dynamic roads & rivers

Full implementation plan with code: `docs/superpowers/plans/2026-07-20-roads-and-rivers.md`.
Shared infrastructure (features table, A* pathfinding, feature rendering) built once,
then two thin tool variants.

26. **P1 · L — Dynamic road building.** Road tool: click waypoints; the road is
    routed *intelligently* between them (A* over terrain costs — roads prefer flat
    charted land, reuse existing roads, avoid water/mountains); live preview while
    placing; hexes know which roads cross them (`features_at(q, r)`).
    (`store.py`, `pathfind.py` [new], `app.py`, `web/app.js`, `web/index.html`)
27. **P1 · L — Dynamic river building.** Same tool skeleton, river cost profile
    (rivers hug low/wet terrain, merge with existing rivers, run to lakes/ocean),
    distinct rendering (wide blue under roads). (same files as 26)

## Suggested next batch

`26 → 27` (one plan, do together) → then ask Stephen — 20 (PNG export) and 7 (labels)
are the likely next picks; 4 (undo) when a quiet day allows.

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
