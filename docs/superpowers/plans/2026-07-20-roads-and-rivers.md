# Dynamic Roads & Rivers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Road and River tools that route a path *intelligently* between clicked
waypoints (terrain-aware A*), persist it as a first-class feature, render it as a
smooth line on the map, and let any hex answer "which roads/rivers cross me?".

**Architecture:** A new `features` table stores each road/river as an ordered list
of hex coordinates. The server owns pathfinding (`pathfind.py`, plain A* over axial
hexes with per-kind terrain cost tables) and is authoritative: the client sends
`add_feature {kind, waypoints}`, the server routes, stores, and broadcasts the full
path. The client mirrors the same A* (cost tables served via `/api/config`) purely
for live preview while placing waypoints. Hex awareness is a lookup
(`store.features_at(q, r)` server-side; a derived `Map` client-side), not a column —
one source of truth, no denormalisation to keep in sync.

**Tech Stack:** Existing stack only — FastAPI/SQLite server (`server/src/hexserver/`),
vanilla-JS canvas client (`web/app.js`). No new dependencies.

## Global Constraints

- `uv run ruff check src tests`, `uv run ruff format --check src tests`, and
  `uv run mypy --strict src/hexserver` must pass from `server/` after every task.
- All server tests live in `server/tests/`; run with `uv run pytest tests` from `server/`.
- Conventional commits (`feat:`, `test:`, `fix:`); commit at the end of every task.
- `.hexmap` export/import must stay loadable by the desktop app — new data goes in a
  *top-level* `features` key, which `hexmapper.hex_grid.from_json_dict` ignores.
- Client stays framework-free; follow existing `app.js` idioms (module-scope state,
  `send()`, `toast()`, `draw()` full-redraw).
- DM_OPS gating is NOT applied to features: any player may build/remove (matches the
  charting-as-you-explore philosophy and every other non-destructive op).
- Feature kinds are exactly `"road"` and `"river"`.
- Work on the existing `feat/enhancements-batch-1` branch unless Stephen says otherwise.

---

### Task 1: Pathfinding module with per-kind cost tables

**Files:**
- Modify: `server/src/hexserver/config.py` (append cost tables at the end)
- Create: `server/src/hexserver/pathfind.py`
- Test: `server/tests/test_pathfind.py`

**Interfaces:**
- Consumes: `NEIGHBOURS` currently in `store.py` — move the constant into
  `pathfind.py` and re-import it from there in `store.py` (single definition).
- Produces:
  - `pathfind.NEIGHBOURS: list[tuple[int, int]]`
  - `pathfind.hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int`
  - `pathfind.a_star(start, goal, cost, max_nodes=4000) -> list[tuple[int, int]]`
    where `cost: Callable[[int, int], float]` is the cost to *enter* a hex;
    returns the path *including both endpoints*; raises `ValueError` if the node
    budget is exhausted.
  - `pathfind.build_cost(kind, terrain_at, occupied) -> Callable[[int, int], float]`
    where `terrain_at: dict[tuple[int, int], str]` and `occupied` is the set of
    hexes already carrying a feature of the same kind (reuse discount).
  - `config.ROAD_COSTS`, `config.RIVER_COSTS: dict[str, float]`,
    `config.ROAD_DEFAULT = 8.0`, `config.RIVER_DEFAULT = 3.0`,
    `config.REUSE_DISCOUNT = 0.25`

- [ ] **Step 1: Append cost tables to `config.py`**

```python
# Feature routing costs: cost to enter a hex of this terrain.
# Roads like flat charted land; rivers like wet lowland and merge toward water.
ROAD_COSTS: dict[str, float] = {
    "CITY": 0.5,
    "GRASSLAND": 1, "PLAINS": 1, "FARM": 1, "FOG": 1.5,
    "BEACH": 1.2, "FOREST": 1.5, "TUNDRA": 1.5, "WASTELAND": 1.5,
    "HILLS": 2, "DESERT": 2, "SNOW": 2,
    "JUNGLE": 3, "MOUNTAIN": 3,
    "SWAMP": 4, "MARSH": 4,
    "VOLCANO": 6,
    "LAKE": 20, "OCEAN": 30,  # bridges/ferries: possible, discouraged
}
ROAD_DEFAULT = 8.0  # unpainted hex — roads prefer charted land

RIVER_COSTS: dict[str, float] = {
    "LAKE": 0.2, "OCEAN": 0.2,
    "SWAMP": 0.5, "MARSH": 0.5,
    "BEACH": 0.8,
    "GRASSLAND": 1, "FARM": 1, "PLAINS": 1, "FOG": 1,
    "FOREST": 1.2, "JUNGLE": 1.2,
    "CITY": 1.5,
    "SNOW": 2, "TUNDRA": 2,
    "HILLS": 2.5, "MOUNTAIN": 3.5,
    "WASTELAND": 4, "DESERT": 5,
    "VOLCANO": 8,
}
RIVER_DEFAULT = 3.0

REUSE_DISCOUNT = 0.25  # entering a hex already carrying the same feature kind
```

- [ ] **Step 2: Write the failing tests**

```python
# server/tests/test_pathfind.py
import pytest
from hexserver.pathfind import a_star, build_cost, hex_distance


def flat_cost(q: int, r: int) -> float:
    return 1.0


def test_hex_distance() -> None:
    assert hex_distance((0, 0), (0, 0)) == 0
    assert hex_distance((0, 0), (3, 0)) == 3
    assert hex_distance((0, 0), (2, -1)) == 2
    assert hex_distance((-1, -1), (1, 1)) == 4


def test_a_star_straight_line_on_flat_ground() -> None:
    path = a_star((0, 0), (4, 0), flat_cost)
    assert path[0] == (0, 0)
    assert path[-1] == (4, 0)
    assert len(path) == 5  # optimal on uniform cost


def test_a_star_routes_around_expensive_terrain() -> None:
    # wall of cost-100 hexes at q=2 except a gap at r=3
    def cost(q: int, r: int) -> float:
        if q == 2 and r != 3:
            return 100.0
        return 1.0

    path = a_star((0, 0), (4, 0), cost)
    assert (2, 3) in path  # took the gap
    assert all(not (q == 2 and r != 3) for q, r in path)


def test_a_star_start_equals_goal() -> None:
    assert a_star((5, 5), (5, 5), flat_cost) == [(5, 5)]


def test_a_star_gives_up_on_budget() -> None:
    with pytest.raises(ValueError, match="no route"):
        a_star((0, 0), (500, 500), flat_cost, max_nodes=50)


def test_build_cost_road_prefers_charted_flat_land() -> None:
    terrain = {(1, 0): "GRASSLAND", (2, 0): "MOUNTAIN"}
    cost = build_cost("road", terrain, occupied=set())
    assert cost(1, 0) == 1
    assert cost(2, 0) == 3
    assert cost(9, 9) == 8.0  # unpainted default


def test_build_cost_reuse_discount() -> None:
    terrain = {(1, 0): "GRASSLAND"}
    cost = build_cost("road", terrain, occupied={(1, 0)})
    assert cost(1, 0) == pytest.approx(0.25)


def test_build_cost_river_profile() -> None:
    terrain = {(0, 1): "SWAMP", (0, 2): "DESERT"}
    cost = build_cost("river", terrain, occupied=set())
    assert cost(0, 1) == 0.5
    assert cost(0, 2) == 5
    assert cost(9, 9) == 3.0


def test_build_cost_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown feature kind"):
        build_cost("canal", {}, set())
```

- [ ] **Step 3: Run tests to verify they fail**

Run (from `server/`): `uv run pytest tests/test_pathfind.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'hexserver.pathfind'`

- [ ] **Step 4: Implement `pathfind.py`**

```python
# server/src/hexserver/pathfind.py
import heapq
from collections.abc import Callable

from hexserver.config import (
    REUSE_DISCOUNT,
    RIVER_COSTS,
    RIVER_DEFAULT,
    ROAD_COSTS,
    ROAD_DEFAULT,
)

NEIGHBOURS = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]

Hex = tuple[int, int]


def hex_distance(a: Hex, b: Hex) -> int:
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def build_cost(
    kind: str, terrain_at: dict[Hex, str], occupied: set[Hex]
) -> Callable[[int, int], float]:
    if kind == "road":
        table, default = ROAD_COSTS, ROAD_DEFAULT
    elif kind == "river":
        table, default = RIVER_COSTS, RIVER_DEFAULT
    else:
        raise ValueError(f"unknown feature kind {kind!r}")

    def cost(q: int, r: int) -> float:
        base = table.get(terrain_at.get((q, r), ""), default)
        if (q, r) in occupied:
            return base * REUSE_DISCOUNT
        return base

    return cost


def a_star(
    start: Hex,
    goal: Hex,
    cost: Callable[[int, int], float],
    max_nodes: int = 4000,
) -> list[Hex]:
    if start == goal:
        return [start]
    open_heap: list[tuple[float, int, Hex]] = [(0.0, 0, start)]
    g_score: dict[Hex, float] = {start: 0.0}
    came_from: dict[Hex, Hex] = {}
    counter = 0  # heap tiebreaker
    explored = 0
    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path
        explored += 1
        if explored > max_nodes:
            break
        for dq, dr in NEIGHBOURS:
            nxt = (current[0] + dq, current[1] + dr)
            tentative = g_score[current] + cost(*nxt)
            if tentative < g_score.get(nxt, float("inf")):
                g_score[nxt] = tentative
                came_from[nxt] = current
                counter += 1
                f = tentative + hex_distance(nxt, goal)
                heapq.heappush(open_heap, (f, counter, nxt))
    raise ValueError("no route found (budget exhausted)")
```

- [ ] **Step 5: Point `store.py` at the shared constant**

In `server/src/hexserver/store.py`, delete the line
`NEIGHBOURS = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]`
and add to the imports:

```python
from hexserver.pathfind import NEIGHBOURS
```

- [ ] **Step 6: Run tests + checks**

Run: `uv run pytest tests -q` — Expected: all pass (existing 47 + 9 new).
Run: `uv run ruff check src tests && uv run ruff format src tests && uv run mypy --strict src/hexserver` — Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add server/ && git commit -m "feat: hex A* pathfinding with road/river cost profiles"
```

---

### Task 2: Feature storage — CRUD, hex awareness, snapshot, export/import

**Files:**
- Modify: `server/src/hexserver/store.py`
- Test: `server/tests/test_store.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces (all on `MapStore`):
  - `add_feature(kind: str, path: list[tuple[int, int]], created_by: str) -> dict[str, Any]`
    → `{"id": int, "kind": str, "path": [[q, r], ...], "created_by": str}`; bumps `version`.
  - `remove_feature(feature_id: int) -> None` — raises `ValueError` if missing; bumps `version`.
  - `features() -> list[dict[str, Any]]` — same dict shape as `add_feature` returns.
  - `features_at(q: int, r: int) -> list[int]` — ids of features whose path crosses that hex.
  - `snapshot()` gains a `"features"` key (list as above).
  - `export_hexmap()` gains a top-level `"features"` key; `import_hexmap` restores it
    (tolerates files without one).
  - `terrain_map() -> dict[tuple[int, int], str]` — for the app layer's cost builder.

- [ ] **Step 1: Write the failing tests (append to `server/tests/test_store.py`)**

```python
def test_add_feature_and_snapshot(store: MapStore) -> None:
    f = store.add_feature("road", [(0, 0), (1, 0), (2, 0)], "steph")
    assert f["kind"] == "road"
    assert f["path"] == [[0, 0], [1, 0], [2, 0]]
    assert f["created_by"] == "steph"
    snap = store.snapshot()
    assert snap["features"] == [f]


def test_features_at(store: MapStore) -> None:
    a = store.add_feature("road", [(0, 0), (1, 0)], "steph")
    b = store.add_feature("river", [(1, 0), (1, 1)], "ines")
    assert store.features_at(1, 0) == [a["id"], b["id"]]
    assert store.features_at(0, 0) == [a["id"]]
    assert store.features_at(9, 9) == []


def test_remove_feature(store: MapStore) -> None:
    f = store.add_feature("road", [(0, 0), (1, 0)], "steph")
    v = store.version
    store.remove_feature(f["id"])
    assert store.features() == []
    assert store.version == v + 1
    with pytest.raises(ValueError, match="no feature"):
        store.remove_feature(f["id"])


def test_add_feature_rejects_bad_kind(store: MapStore) -> None:
    with pytest.raises(ValueError, match="unknown feature kind"):
        store.add_feature("canal", [(0, 0), (1, 0)], "steph")


def test_features_roundtrip_hexmap(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    store.add_feature("river", [(0, 0), (0, 1)], "steph")
    data = store.export_hexmap()
    other = MapStore(Path(":memory:"))
    other.import_hexmap(data)
    (f,) = other.features()
    assert f["kind"] == "river"
    assert f["path"] == [[0, 0], [0, 1]]


def test_import_without_features_key(store: MapStore) -> None:
    store.import_hexmap({"hexes": [{"q": 0, "r": 0, "terrain": "FOG"}]})
    assert store.features() == []


def test_terrain_map(store: MapStore) -> None:
    store.set_hex(2, -1, "DESERT")
    assert store.terrain_map() == {(2, -1): "DESERT"}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_store.py -q` — Expected: new tests FAIL with
`AttributeError: 'MapStore' object has no attribute 'add_feature'`.

- [ ] **Step 3: Implement in `store.py`**

In `__init__`, after the `meta` table creation:

```python
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS features ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "kind TEXT, path TEXT, created_by TEXT, ts REAL)"
        )
```

New methods (place after `set_fog`); `FEATURE_KINDS = ("road", "river")` as a
module-level constant next to `NEIGHBOURS` import:

```python
    def add_feature(
        self, kind: str, path: list[tuple[int, int]], created_by: str
    ) -> dict[str, Any]:
        if kind not in FEATURE_KINDS:
            raise ValueError(f"unknown feature kind {kind!r}")
        cur = self.db.execute(
            "INSERT INTO features (kind, path, created_by, ts) VALUES (?, ?, ?, ?)",
            (kind, json.dumps([[q, r] for q, r in path]), created_by, time.time()),
        )
        self.db.commit()
        self.version += 1
        return {
            "id": cur.lastrowid,
            "kind": kind,
            "path": [[q, r] for q, r in path],
            "created_by": created_by,
        }

    def remove_feature(self, feature_id: int) -> None:
        cur = self.db.execute("DELETE FROM features WHERE id = ?", (feature_id,))
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no feature {feature_id}")
        self.version += 1

    def features(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, kind, path, created_by FROM features ORDER BY id"
        ).fetchall()
        return [
            {"id": i, "kind": k, "path": json.loads(p), "created_by": c}
            for i, k, p, c in rows
        ]

    def features_at(self, q: int, r: int) -> list[int]:
        return [
            f["id"] for f in self.features() if [q, r] in f["path"]
        ]

    def terrain_map(self) -> dict[tuple[int, int], str]:
        rows = self.db.execute("SELECT q, r, terrain FROM hexes").fetchall()
        return {(q, r): t for q, r, t in rows}
```

Wire into existing methods:
- `snapshot()`: add `"features": self.features(),` beside `"party"`/`"fog"`.
- `export_hexmap()`: add `"features": self.features(),` as a top-level key.
- `import_hexmap()`: after the hexes insert, add:

```python
        self.db.execute("DELETE FROM features")
        for f in data.get("features", []):
            if f.get("kind") in FEATURE_KINDS and isinstance(f.get("path"), list):
                self.db.execute(
                    "INSERT INTO features (kind, path, created_by, ts) "
                    "VALUES (?, ?, ?, ?)",
                    (f["kind"], json.dumps(f["path"]), f.get("created_by"), time.time()),
                )
```

Also `clear_all()`: add `self.db.execute("DELETE FROM features")` before the commit.

- [ ] **Step 4: Fix the two exact-shape snapshot tests**

`test_set_hex_and_snapshot` and friends assert full snapshot dicts — they compare
`snap["hexes"]` entries only, so no change needed there; but any test asserting the
full snapshot dict must gain `"features": []`. Run the suite and patch the ones that
fail (expected: `test_party_defaults_to_none`-style tests are keyed access, fine).

- [ ] **Step 5: Run tests + checks**

Run: `uv run pytest tests -q` — Expected: all pass.
Run: ruff + mypy as in Task 1 — Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add server/ && git commit -m "feat: features table — roads/rivers CRUD, hex awareness, hexmap round-trip"
```

---

### Task 3: WS ops `add_feature` / `remove_feature` with server-side routing

**Files:**
- Modify: `server/src/hexserver/app.py`
- Test: `server/tests/test_app.py` (append)

**Interfaces:**
- Consumes: `store.add_feature/remove_feature/features/terrain_map` (Task 2),
  `pathfind.a_star/build_cost` (Task 1).
- Produces:
  - WS in: `{"op": "add_feature", "kind": "road"|"river", "waypoints": [[q, r], ...]}`
    (2–12 waypoints; total routed path capped at 300 hexes).
  - WS out: `{"type": "op", "op": "add_feature", "version": n, "feature": {...}, "by": name}`.
  - WS in: `{"op": "remove_feature", "id": int}` →
    out `{"type": "op", "op": "remove_feature", "version": n, "id": int, "by": name}`.
  - `/api/config` gains `"feature_costs"`:
    `{"road": {"terrains": {...}, "default": 8.0}, "river": {...}, "reuse": 0.25}`.
  - Audit log detail for `add_feature`: `{"kind": ..., "hexes": len(path)}` —
    add `"kind"` and `"hexes"` handling to the log call (see Step 3).

- [ ] **Step 1: Write the failing tests (append to `server/tests/test_app.py`)**

```python
def test_add_feature_routes_between_waypoints(client: TestClient) -> None:
    for q in range(5):
        app_module.store.set_hex(q, 0, "GRASSLAND")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json(
            {"op": "add_feature", "kind": "road", "waypoints": [[0, 0], [4, 0]]}
        )
        msg = ws.receive_json()
        assert msg["op"] == "add_feature"
        f = msg["feature"]
        assert f["kind"] == "road"
        assert f["path"][0] == [0, 0]
        assert f["path"][-1] == [4, 0]
        assert len(f["path"]) == 5  # straight over uniform grassland
    assert app_module.store.features_at(2, 0) == [f["id"]]


def test_add_feature_avoids_water(client: TestClient) -> None:
    # grassland corridor around a lake at (2, 0)
    for q in range(5):
        for r in (-1, 0, 1):
            app_module.store.set_hex(q, r, "GRASSLAND")
    app_module.store.set_hex(2, 0, "LAKE")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json(
            {"op": "add_feature", "kind": "road", "waypoints": [[0, 0], [4, 0]]}
        )
        path = ws.receive_json()["feature"]["path"]
    assert [2, 0] not in path


def test_add_feature_validates(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "add_feature", "kind": "canal", "waypoints": [[0, 0], [1, 0]]})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"op": "add_feature", "kind": "road", "waypoints": [[0, 0]]})
        assert ws.receive_json()["type"] == "error"


def test_remove_feature_broadcasts(client: TestClient) -> None:
    f = app_module.store.add_feature("river", [(0, 0), (0, 1)], "steph")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "remove_feature", "id": f["id"]})
        msg = ws.receive_json()
        assert msg["op"] == "remove_feature"
        assert msg["id"] == f["id"]
    assert app_module.store.features() == []


def test_config_serves_feature_costs(client: TestClient) -> None:
    cfg = client.get("/api/config", headers=PLAYER).json()
    assert cfg["feature_costs"]["road"]["terrains"]["MOUNTAIN"] == 3
    assert cfg["feature_costs"]["river"]["default"] == 3.0
    assert cfg["feature_costs"]["reuse"] == 0.25
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_app.py -q` — Expected: new tests FAIL
(`error` messages: `unknown op 'add_feature'`; config KeyError).

- [ ] **Step 3: Implement in `app.py`**

Imports:

```python
from hexserver.config import (
    ICONS,
    REUSE_DISCOUNT,
    RIVER_COSTS,
    RIVER_DEFAULT,
    ROAD_COSTS,
    ROAD_DEFAULT,
    TERRAINS,
)
from hexserver.pathfind import a_star, build_cost
```

Routing helper (place above `apply_op`):

```python
def plan_feature_path(kind: str, waypoints: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not 2 <= len(waypoints) <= 12:
        raise ValueError("need 2-12 waypoints")
    terrain = store.terrain_map()
    occupied = {
        (q, r)
        for f in store.features()
        if f["kind"] == kind
        for q, r in f["path"]
    }
    cost = build_cost(kind, terrain, occupied)
    path: list[tuple[int, int]] = []
    for a, b in zip(waypoints, waypoints[1:], strict=False):
        leg = a_star(a, b, cost)
        path.extend(leg if not path else leg[1:])  # dedupe joints
    if len(path) > 300:
        raise ValueError("path too long (max 300 hexes)")
    return path
```

`apply_op` branches (before `if op == "add_layer"`):

```python
    if op == "add_feature":
        kind = str(msg["kind"])
        waypoints = [(int(q), int(r)) for q, r in msg["waypoints"]]
        routed = plan_feature_path(kind, waypoints)
        feature = store.add_feature(kind, routed, author)
        return {
            "type": "op",
            "op": "add_feature",
            "version": store.version,
            "feature": feature,
        }
    if op == "remove_feature":
        fid = int(msg["id"])
        store.remove_feature(fid)
        return {
            "type": "op",
            "op": "remove_feature",
            "version": store.version,
            "id": fid,
        }
```

Audit detail: extend the `log_op` key tuple in `ws_endpoint` from
`("q", "r", "terrain", "icon", "explored", "enabled")` to
`("q", "r", "terrain", "icon", "explored", "enabled", "kind", "id")`.

`/api/config`: add to the JSON dict:

```python
            "feature_costs": {
                "road": {"terrains": ROAD_COSTS, "default": ROAD_DEFAULT},
                "river": {"terrains": RIVER_COSTS, "default": RIVER_DEFAULT},
                "reuse": REUSE_DISCOUNT,
            },
```

- [ ] **Step 4: Run tests + checks**

Run: `uv run pytest tests -q` — Expected: all pass.
Run: ruff + mypy — Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add server/ && git commit -m "feat: add_feature/remove_feature ops with server-side A* routing"
```

---

### Task 4: Client — render features and track them in state

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: snapshot `features` list; `add_feature`/`remove_feature` op broadcasts (Task 3).
- Produces:
  - `state.features: Map<int, feature>` and `featureIdsAt(q, r) -> int[]`
    (the client-side hex awareness used by Task 5's removal + future tooltips).
  - `drawFeatures()` called from `draw()` after the hex loop, before cursors:
    rivers first (wide, blue `#4a90d9`), roads on top (brown `#8b6b3d` with a
    darker `#00000055` casing), lines through hex centres smoothed with
    quadratic curves through segment midpoints.

- [ ] **Step 1: State + sync plumbing**

Add `features: new Map(),` to the `state` object. In the snapshot branch (both in
`ws.onmessage` and `resync()`):

```js
      state.features.clear();
      (msg.features || []).forEach((f) => state.features.set(f.id, f));
```

In the op chain:

```js
      } else if (msg.op === "add_feature") {
        state.features.set(msg.feature.id, msg.feature);
      } else if (msg.op === "remove_feature") {
        state.features.delete(msg.id);
```

Awareness helper (near `key()`):

```js
function featureIdsAt(q, r) {
  const ids = [];
  for (const f of state.features.values()) {
    if (f.path.some(([pq, pr]) => pq === q && pr === r)) ids.push(f.id);
  }
  return ids;
}
```

- [ ] **Step 2: Rendering**

Add after the hex loop in `draw()` (before the cursors block):

```js
  drawFeaturePaths("river");
  drawFeaturePaths("road");
```

And the function (near `traceHex`):

```js
const FEATURE_STYLE = {
  river: { stroke: "#4a90d9", width: 0.3, casing: null },
  road: { stroke: "#8b6b3d", width: 0.18, casing: "#00000055" },
};

function drawFeaturePaths(kind) {
  const size = HEX_SIZE * state.scale;
  const style = FEATURE_STYLE[kind];
  for (const f of state.features.values()) {
    if (f.kind !== kind) continue;
    const pts = f.path.map(([q, r]) => {
      const [wx, wy] = hexToPixel(q, r);
      return [wx * state.scale + state.offsetX, wy * state.scale + state.offsetY];
    });
    if (pts.length < 2) continue;
    tracePolyline(pts);
    if (style.casing) {
      ctx.strokeStyle = style.casing;
      ctx.lineWidth = size * (style.width + 0.1);
      ctx.lineCap = ctx.lineJoin = "round";
      ctx.stroke();
    }
    tracePolyline(pts);
    ctx.strokeStyle = style.stroke;
    ctx.lineWidth = Math.max(1.5, size * style.width);
    ctx.lineCap = ctx.lineJoin = "round";
    ctx.stroke();
  }
}

function tracePolyline(pts) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = (pts[i][0] + pts[i + 1][0]) / 2;
    const my = (pts[i][1] + pts[i + 1][1]) / 2;
    ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
  }
  ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
}
```

- [ ] **Step 3: Verify in the browser**

Start the server (`uv run uvicorn hexserver.app:app --app-dir src --port 8321` from
`server/`), paint a strip of hexes, then in the devtools console inject a feature via
a raw WS message — or simpler, run Task 5 first and verify both together. Minimum
check now: `python -c` a row into the DB or use TestClient; confirm a blue and a
brown smooth line render, roads above rivers, and `featureIdsAt` returns ids.
Hard-reload (Ctrl+Shift+R) — Chrome caches app.js.

- [ ] **Step 4: Commit**

```bash
git add web/ && git commit -m "feat: render road/river features as smoothed polylines"
```

---

### Task 5: Client — Road/River tools with live A* preview, finish/cancel, removal

**Files:**
- Modify: `web/app.js`, `web/index.html`

**Interfaces:**
- Consumes: `cfg.feature_costs` (Task 3), `state.features`/`featureIdsAt` (Task 4).
- Produces:
  - Tools `"road"` and `"river"` (buttons `roadBtn`, `riverBtn`; hotkeys **O**/**V**).
  - `state.draft = null | {kind, waypoints: [[q,r],...], preview: [[q,r],...]}`.
  - Click = add waypoint · move = live preview · **Enter**/double-click = build
    (sends `add_feature`) · **Esc** = cancel · **Shift+click** on a feature hex =
    `remove_feature`.
  - `jsAStar(start, goal, kind)` — client mirror of the server router for preview only.

- [ ] **Step 1: index.html**

Buttons after `partyBtn`:

```html
    <button id="roadBtn">Road</button>
    <button id="riverBtn">River</button>
```

Help overlay rows (before the Esc row):

```html
    <div class="helpRow"><kbd>O</kbd><kbd>V</kbd><span>road / river: click waypoints, Enter to build, Shift-click removes</span></div>
```

- [ ] **Step 2: app.js — cost tables + preview A***

After `init()` fetches config, store `state.featureCosts = cfg.feature_costs;`.
Add near `pathfind`-style helpers:

```js
function hexDist(aq, ar, bq, br) {
  const dq = aq - bq, dr = ar - br;
  return (Math.abs(dq) + Math.abs(dr) + Math.abs(dq + dr)) / 2;
}

function featureCost(kind, q, r) {
  const cfg = state.featureCosts[kind];
  const cell = state.hexes.get(key(q, r));
  let base = cell ? (cfg.terrains[cell.terrain] ?? cfg.default) : cfg.default;
  for (const f of state.features.values()) {
    if (f.kind === kind && f.path.some(([pq, pr]) => pq === q && pr === r)) {
      base *= state.featureCosts.reuse;
      break;
    }
  }
  return base;
}

const AXIAL_DIRS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];

function jsAStar(start, goal, kind, maxNodes = 3000) {
  if (start[0] === goal[0] && start[1] === goal[1]) return [start];
  const g = new Map([[key(...start), 0]]);
  const came = new Map();
  let open = [[hexDist(...start, ...goal), start]];
  let explored = 0;
  while (open.length) {
    open.sort((a, b) => a[0] - b[0]);
    const [, cur] = open.shift();
    if (cur[0] === goal[0] && cur[1] === goal[1]) {
      const path = [cur];
      let k = key(...cur);
      while (came.has(k)) {
        path.unshift(came.get(k));
        k = key(...came.get(k));
      }
      return path;
    }
    if (++explored > maxNodes) break;
    const gCur = g.get(key(...cur));
    for (const [dq, dr] of AXIAL_DIRS) {
      const nxt = [cur[0] + dq, cur[1] + dr];
      const t = gCur + featureCost(kind, nxt[0], nxt[1]);
      const nk = key(...nxt);
      if (t < (g.get(nk) ?? Infinity)) {
        g.set(nk, t);
        came.set(nk, cur);
        open.push([t + hexDist(...nxt, ...goal), nxt]);
      }
    }
  }
  return null; // no preview — server may still succeed/fail authoritatively
}
```

- [ ] **Step 3: app.js — draft interaction**

State: `draft: null,` in the state object. In `editAt`, add branches before
`remove`:

```js
  } else if (state.tool === "road" || state.tool === "river") {
    if (e.shiftKey) {   // editAt must accept the event: change signature to editAt(clientX, clientY, e)
      const ids = featureIdsAt(q, r);
      if (ids.length) send({ op: "remove_feature", id: ids[ids.length - 1] });
      return;
    }
    if (!state.draft || state.draft.kind !== state.tool) {
      state.draft = { kind: state.tool, waypoints: [], preview: [] };
    }
    state.draft.waypoints.push([q, r]);
    toast(`Waypoint ${state.draft.waypoints.length} — Enter builds, Esc cancels`);
```

(Adjust `editAt` calls to pass the originating event so `e.shiftKey` is visible;
the existing pointerup already has it.)

Preview on hover — in the pointermove handler where `sendCursor(hq, hr)` is called:

```js
  if (state.draft && state.draft.waypoints.length) {
    const last = state.draft.waypoints[state.draft.waypoints.length - 1];
    state.draft.preview = jsAStar(last, [hq, hr], state.draft.kind) || [];
    draw();
  }
```

Draft rendering — in `draw()` after `drawFeaturePaths("road")`:

```js
  if (state.draft && state.draft.waypoints.length) {
    const committed = [];
    for (let i = 0; i < state.draft.waypoints.length - 1; i++) {
      const leg = jsAStar(state.draft.waypoints[i], state.draft.waypoints[i + 1], state.draft.kind) || [];
      committed.push(...(committed.length ? leg.slice(1) : leg));
    }
    const full = committed.concat(state.draft.preview.slice(committed.length ? 1 : 0));
    if (full.length > 1) {
      const pts = full.map(([q, r]) => {
        const [wx, wy] = hexToPixel(q, r);
        return [wx * state.scale + state.offsetX, wy * state.scale + state.offsetY];
      });
      ctx.globalAlpha = 0.5;
      tracePolyline(pts);
      ctx.strokeStyle = FEATURE_STYLE[state.draft.kind].stroke;
      ctx.lineWidth = Math.max(1.5, HEX_SIZE * state.scale * FEATURE_STYLE[state.draft.kind].width);
      ctx.lineCap = ctx.lineJoin = "round";
      ctx.setLineDash([6, 6]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
    }
  }
```

Finish/cancel — keydown handler additions (before `isTyping()` return):

```js
  if (e.key === "Enter" && state.draft && state.draft.waypoints.length >= 2) {
    send({ op: "add_feature", kind: state.draft.kind, waypoints: state.draft.waypoints });
    state.draft = null;
    draw();
    return;
  }
```

Extend the existing Escape chain: if `state.draft` → `state.draft = null; draw(); return;`
(before the notePanel check). Double-click: in the `dblclick` listener, if
`state.draft && state.draft.waypoints.length >= 2` do the same send-and-clear
*instead of* the ping. Tool switching (`setTool`) clears `state.draft`.

Buttons/keys: add `["roadBtn", "road"], ["riverBtn", "river"]` to `setTool`'s list,
`document.getElementById("roadBtn").onclick = () => setTool("road");` (and river),
and `o: "road", v: "river"` in `TOOL_KEYS`. **Remember the gotcha: both the list
entry AND the onclick binding.**

- [ ] **Step 4: Verify in the browser (hard-reload!)**

Two tabs. In tab 1: pick Road, click two points a dozen hexes apart across mixed
terrain — dashed preview follows the cursor and bends around mountains/lakes; Enter
builds it; the solid road appears in *both* tabs; history feed shows
"built a road". Rivers: same with V, blue, drawn beneath roads at crossings.
Shift+click on the road removes it in both tabs. Esc mid-draft cancels. Ping still
works when no draft is active.

- [ ] **Step 5: Commit**

```bash
git add web/ && git commit -m "feat: road/river tools — waypoint clicks, live A* preview, shift-click removal"
```

---

### Task 6: Fog interaction, history text, final polish

**Files:**
- Modify: `web/app.js`
- Test: `server/tests/test_app.py` (append, one test)

**Interfaces:**
- Consumes: everything above.
- Produces: fog-respecting rendering; history feed entries for features.

- [ ] **Step 1: History text**

In `opText`:

```js
    case "add_feature": return `built a ${d.kind || "path"}`;
    case "remove_feature": return `removed a road/river`;
```

- [ ] **Step 2: Fog filtering in `drawFeaturePaths`**

Players shouldn't see roads/rivers crossing unexplored land. Inside the per-feature
loop, when `state.fog && state.role !== "dm"`, split the path into runs of hexes
whose cell exists and is explored, and render each run separately:

```js
    let runs = [f.path];
    if (state.fog && state.role !== "dm") {
      runs = [];
      let cur = [];
      for (const [q, r] of f.path) {
        const cell = state.hexes.get(key(q, r));
        if (cell && cell.explored) cur.push([q, r]);
        else if (cur.length) { runs.push(cur); cur = []; }
      }
      if (cur.length) runs.push(cur);
    }
```

…then map/trace each run of length ≥ 2 instead of `f.path` directly.

- [ ] **Step 3: One server regression test**

```python
def test_feature_ops_are_logged(client: TestClient) -> None:
    app_module.store.set_hex(0, 0, "GRASSLAND")
    app_module.store.set_hex(1, 0, "GRASSLAND")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "add_feature", "kind": "road", "waypoints": [[0, 0], [1, 0]]})
        assert ws.receive_json()["op"] == "add_feature"
    entries = client.get("/api/history", headers=PLAYER).json()["ops"]
    assert entries[0]["op"] == "add_feature"
    assert entries[0]["detail"]["kind"] == "road"
```

- [ ] **Step 4: Full check suite + browser pass**

Run from `server/`: `uv run pytest tests -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy --strict src/hexserver`.
Browser: with fog on, hide hexes under a road as DM, confirm the player view breaks
the road line at the fog boundary while the DM sees it whole.

- [ ] **Step 5: Commit + update docs + PR**

```bash
git add -A && git commit -m "feat: fog-aware feature rendering, feature history entries"
```

Mark items 26/27 ✓ in `docs/handoff-enhancements.md`, push, and update the PR body.

---

## Design notes & accepted trade-offs

- **Server-authoritative routing** means preview and final path can differ slightly
  if the map changed mid-draft — acceptable; the broadcast path is what everyone sees.
- **`features_at` scans all features** (no index table). At party scale (tens of
  features, ≤300 hexes each) this is microseconds. Revisit only if it shows up.
- **Removing a hex does not edit features crossing it** — a road over a deleted hex
  keeps its path (LWW philosophy). The fog-run renderer already handles gaps
  gracefully; a future "trim dangling features" pass is easy if it annoys anyone.
- **Rivers use the same centre-line model as roads** (not edge-following). It reads
  well at map scale, keeps one code path, and matches "hexes aware of the river".
  Edge-following rivers were the old item 11 idea; consciously dropped.
- **No elevation model** — "downhill flow" is approximated by the river cost table
  (wet/low terrains cheap, ridges dear, water bodies nearly free so rivers run to them).
