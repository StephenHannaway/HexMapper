# Online Collaborative Hexmap — Design

Date: 2026-07-19
Status: draft, awaiting review

## Goal

Turn the desktop pygame hex editor into an online tool a D&D West Marches group
can use to collaboratively build a shared world hexmap. All party members can
view and edit the same map from a browser, live.

## Current state

Desktop pygame app. Map model: `dict[(q, r) -> HexCell(q, r, terrain, icon_name)]`
with axial coordinates, 19-value `Terrain` enum (hex colours), 15 PNG icons,
JSON save format (`.hexmap`). Two existing maps: `map.hexmap1`, `map.hexmap2`.

## Approaches considered

1. **Web app rewrite: TypeScript/Canvas frontend + FastAPI WebSocket backend** —
   recommended. The map model is ~100 lines of logic; porting hex math to TS is
   trivial. Backend stays Python (primary stack). Browser access means zero
   install for players, works on phones at the table.
2. **pygbag (pygame → WebAssembly)** — reuses existing rendering code, but
   pygame-gui support in wasm is unreliable, a sync backend is still required,
   and the result is a canvas-in-iframe with poor mobile UX. Code reuse is
   smaller than it looks; rejected.
3. **Keep desktop app, add a sync server** — every player must install Python +
   the app. Fails the "available to all party members online" requirement;
   rejected.

## Architecture (approach 1)

Monorepo, this repository:

```
Hex Editor/
├── src/hexmapper/        # existing desktop app (kept, untouched)
├── server/               # FastAPI backend (uv, src layout: src/hexserver/)
├── web/                  # Vite + TypeScript frontend (no framework)
└── docs/superpowers/specs/
```

Single deployable unit: FastAPI serves the built static frontend, a small REST
API, and a WebSocket endpoint. SQLite for persistence. One Docker container on
Fly.io or Railway with a persistent volume.

### Backend (`server/`, Python 3.12, FastAPI)

- **State**: server-authoritative in-memory map per map-id, backed by SQLite.
  Tables: `maps(id, name, invite_token, dm_token)`,
  `hexes(map_id, q, r, terrain, icon)`, `sessions(token, map_id, display_name, role)`.
- **REST**:
  - `POST /api/maps` — create map (returns DM link + invite link)
  - `GET /api/maps/{id}` — full snapshot `{version, hexes: [...]}`
  - `POST /api/maps/{id}/import` — upload existing `.hexmap` JSON (DM only)
  - `GET /api/maps/{id}/export` — download `.hexmap` (backup / desktop interop)
- **WebSocket** `/ws/{map_id}`: client sends edit ops, server validates,
  applies, persists, and broadcasts to all connected clients with a
  monotonically increasing `version`. Ops mirror the desktop tools:
  - `set_hex {q, r, terrain}` (paint; creates or recolours)
  - `set_icon {q, r, icon | null}`
  - `remove_hex {q, r}`
  - `add_layer {terrain}` (server computes ring, broadcasts resulting hexes)
  - `clear_all` (DM only)
  - presence: join/leave notices with display names
- **Conflict model**: per-hex last-write-wins. Edits are single-cell and
  idempotent; no CRDT/OT needed at party scale (< 20 users). On reconnect the
  client requests a snapshot and resubscribes.
- **Auth**: no accounts. DM creates a map and shares the invite link (token in
  URL). First visit prompts for a display name, stored in a cookie session.
  The DM link carries the `dm` role; destructive ops (`clear_all`, import) are
  DM-only.
- **Quality gates**: uv, ruff, mypy --strict, pytest (op application, layer
  ring logic, auth/role checks, snapshot/replay), justfile recipes, CI job.

### Frontend (`web/`, Vite + vanilla TypeScript)

- Canvas renderer: port of `hex_grid.py` math (hex_to_pixel, pixel_to_hex,
  round_hex) and `hex_grid_renderer.py` drawing (flat-top hexes, terrain fill,
  1px outline, icon blit). Icons are the same PNGs served as static assets.
- Viewport: pan (drag / arrow keys), zoom to cursor (wheel / buttons),
  touch support (pinch zoom, drag pan) so it works on tablets at the table.
- Tools sidebar mirroring the desktop UI: terrain picker, icon picker,
  remove mode, add-layer, export; DM extras (clear all, import).
- Presence strip: who's online.
- Sync client: applies local edits optimistically, sends op over WS, reconciles
  from broadcast versions; full resync on reconnect.
- Tests: vitest for the hex math port (mirror `tests/test_hex_grid.py`).

### Data flow

1. Player opens invite link → REST snapshot → canvas renders map.
2. Player paints a hex → optimistic local update → `set_hex` over WS.
3. Server validates role/op, writes SQLite, bumps version, broadcasts.
4. All clients (including sender) apply the authoritative op by version;
   out-of-order or missed versions trigger a snapshot refetch.

### Error handling

- WS drop → exponential backoff reconnect → snapshot resync (versions make
  this cheap and safe).
- Invalid ops (bad terrain name, non-DM `clear_all`) → rejected with an error
  frame; client reverts the optimistic change.
- SQLite writes serialized behind an asyncio lock (single-writer is ample at
  this scale).

## Out of scope (possible later phases)

- Fog-of-war reveal mechanics beyond the existing FOG terrain default.
- Hex notes/annotations, edit history/undo, multiple maps per group UI,
  live cursors.

## Implementation phases

1. **Server core**: scaffold `server/` (uv, FastAPI), map state + SQLite,
   snapshot REST, `.hexmap` import/export. Tests for op application.
2. **Frontend render**: scaffold `web/` (Vite/TS), hex math port + canvas
   renderer + viewport, loading a snapshot read-only.
3. **Editing + realtime**: WS protocol both ends, all edit ops, optimistic
   updates, reconnect/resync, presence.
4. **Auth + roles**: map creation flow, invite/DM links, display names,
   DM-only ops.
5. **Deploy**: Dockerfile (build web, serve via FastAPI), Fly.io/Railway with
   volume, CI extended to server + web checks, import `map.hexmap1`.
