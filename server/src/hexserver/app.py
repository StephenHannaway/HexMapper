import asyncio
import itertools
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

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
from hexserver.store import MapStore

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_DIR = Path(os.environ.get("HEXMAP_WEB_DIR", REPO_ROOT / "web"))
ASSETS_DIR = Path(
    os.environ.get("HEXMAP_ASSETS_DIR", REPO_ROOT / "src" / "hexmapper" / "assets")
)
DB_PATH = Path(os.environ.get("HEXMAP_DB", REPO_ROOT / "server" / "map.db"))
SEED_FILE = Path(os.environ.get("HEXMAP_SEED", REPO_ROOT / "map.hexmap2"))
MAP_KEY = os.environ.get("HEXMAP_KEY", "")
DM_KEY = os.environ.get("HEXMAP_DM_KEY", "")

app = FastAPI(title="hexserver")
store = MapStore(DB_PATH, seed_file=SEED_FILE)
lock = asyncio.Lock()


def role_for(cookie: str | None, query_key: str | None) -> str | None:
    # "dm" | "player" | None (rejected). With no DM key configured everyone
    # who passes the gate is a DM, preserving pre-role behaviour.
    candidates = [c for c in (cookie, query_key) if c]
    if DM_KEY and any(secrets.compare_digest(c, DM_KEY) for c in candidates):
        return "dm"
    full_access = "player" if DM_KEY else "dm"
    if not MAP_KEY:
        return full_access
    if any(secrets.compare_digest(c, MAP_KEY) for c in candidates):
        return full_access
    return None


class KeyGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        cookie = request.cookies.get("mapkey")
        query_key = request.query_params.get("key")
        if role_for(cookie, query_key) is None:
            return HTMLResponse(
                "<h1>This map is private</h1><p>Ask your DM for the invite link.</p>",
                status_code=403,
            )
        if query_key and query_key != cookie:
            response: Response = RedirectResponse(request.url.path)
            response.set_cookie(
                "mapkey", query_key, max_age=365 * 24 * 3600, httponly=True
            )
            return response
        return await call_next(request)


app.add_middleware(KeyGateMiddleware)


DEFAULT_MAP_ID = 1


class Hub:
    def __init__(self) -> None:
        self.clients: dict[WebSocket, str] = {}
        self.rooms: dict[WebSocket, int] = {}  # ws -> map_id it is viewing

    def room(self, ws: WebSocket) -> int:
        return self.rooms.get(ws, DEFAULT_MAP_ID)

    async def broadcast(
        self, message: dict[str, Any], map_id: int, exclude: WebSocket | None = None
    ) -> None:
        # only clients viewing this map hear about its edits
        payload = json.dumps(message)
        for ws in list(self.clients):
            if ws is exclude or self.rooms.get(ws) != map_id:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                self.clients.pop(ws, None)
                self.rooms.pop(ws, None)

    async def broadcast_all(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                self.clients.pop(ws, None)
                self.rooms.pop(ws, None)

    def names(self, map_id: int) -> list[str]:
        return sorted(
            n for ws, n in self.clients.items() if self.rooms.get(ws) == map_id
        )


hub = Hub()


@app.get("/api/config")
async def get_config(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "terrains": TERRAINS,
            "icons": [
                {"name": name, "url": f"/assets/{path}"} for name, path in ICONS.items()
            ],
            "role": role_for(
                request.cookies.get("mapkey"), request.query_params.get("key")
            ),
            "feature_costs": {
                "road": {"terrains": ROAD_COSTS, "default": ROAD_DEFAULT},
                "river": {"terrains": RIVER_COSTS, "default": RIVER_DEFAULT},
                "reuse": REUSE_DISCOUNT,
            },
        }
    )


@app.get("/api/map")
async def get_map(map_id: int = DEFAULT_MAP_ID) -> JSONResponse:
    async with lock:
        if not store.map_exists(map_id):
            map_id = DEFAULT_MAP_ID
        return JSONResponse(store.snapshot(map_id))


@app.get("/api/map/export")
async def export_map(map_id: int = DEFAULT_MAP_ID) -> JSONResponse:
    async with lock:
        return JSONResponse(store.export_hexmap(map_id))


@app.get("/api/history")
async def get_history(limit: int = 50, map_id: int = DEFAULT_MAP_ID) -> JSONResponse:
    async with lock:
        return JSONResponse({"ops": store.history(min(limit, 200), map_id)})


@app.post("/api/map/import")
async def import_map(request: Request, map_id: int = DEFAULT_MAP_ID) -> JSONResponse:
    role = role_for(request.cookies.get("mapkey"), request.query_params.get("key"))
    if role != "dm":
        return JSONResponse({"detail": "Only the DM can import a map"}, status_code=403)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"detail": "not valid JSON"}, status_code=400)
    hexes = data.get("hexes") if isinstance(data, dict) else None
    if not isinstance(hexes, list) or not hexes:
        return JSONResponse(
            {"detail": "not a .hexmap file (no hexes)"}, status_code=400
        )
    async with lock:
        if not store.map_exists(map_id):
            map_id = DEFAULT_MAP_ID
        store.import_hexmap(data, map_id)
        store.log_op("the DM", "import", {"hexes": len(hexes)}, map_id)
        snap = store.snapshot(map_id)
    await hub.broadcast(
        {"type": "snapshot", "action": "import", "by": "the DM", **snap}, map_id
    )
    return JSONResponse({"ok": True, "hexes": len(snap["hexes"])})


MAP_ADMIN_OPS = {"create_map", "rename_map", "delete_map"}


async def handle_map_admin(ws: WebSocket, op: str, msg: dict[str, Any]) -> None:
    async with lock:
        if op == "create_map":
            new = store.create_map(str(msg.get("name") or "New Map"))
            maps = store.maps()
        elif op == "rename_map":
            store.rename_map(int(msg["map_id"]), str(msg.get("name") or "Map"))
            maps = store.maps()
        else:  # delete_map
            target = int(msg["map_id"])
            store.delete_map(target)
            maps = store.maps()
    await hub.broadcast_all({"type": "maps", "maps": maps})
    if op == "create_map":
        # move the creator straight into the new map
        await switch_to(ws, int(new["id"]))
    elif op == "delete_map":
        # anyone viewing the deleted map falls back to the default map
        stranded = [w for w in hub.clients if hub.rooms.get(w) == int(msg["map_id"])]
        for w in stranded:
            await switch_to(w, DEFAULT_MAP_ID, action="map_deleted")


async def switch_to(ws: WebSocket, map_id: int, action: str | None = None) -> None:
    old = hub.room(ws)
    async with lock:
        if not store.map_exists(map_id):
            map_id = DEFAULT_MAP_ID
        snap = store.snapshot(map_id)
    hub.rooms[ws] = map_id
    payload = {"type": "snapshot", **snap}
    if action:
        payload["action"] = action
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:
        hub.clients.pop(ws, None)
        hub.rooms.pop(ws, None)
        return
    if old != map_id:
        await hub.broadcast({"type": "presence", "users": hub.names(old)}, old)
    await hub.broadcast({"type": "presence", "users": hub.names(map_id)}, map_id)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    role = role_for(ws.cookies.get("mapkey"), ws.query_params.get("key"))
    if role is None:
        await ws.close(code=4403)
        return
    await ws.accept()
    hub.clients[ws] = "anonymous"
    hub.rooms[ws] = DEFAULT_MAP_ID
    limiter = RateLimiter(RATE_BURST, RATE_PER_SEC)
    try:
        async with lock:
            await ws.send_text(
                json.dumps({"type": "snapshot", **store.snapshot(DEFAULT_MAP_ID)})
            )
        while True:
            msg = json.loads(await ws.receive_text())
            op = msg.get("op")
            author = hub.clients.get(ws, "anonymous")
            room = hub.room(ws)
            if not limiter.allow():
                if op != "cursor":
                    # tell the client to resnapshot so a dropped edit can't diverge
                    await ws.send_text(
                        json.dumps(
                            {"type": "error", "detail": "Slow down", "resync": True}
                        )
                    )
                continue
            if op == "cursor":
                # ephemeral hover position: no lock, no version, no log
                try:
                    cq, cr = int(msg["q"]), int(msg["r"])
                except Exception:
                    continue
                await hub.broadcast(
                    {"type": "cursor", "q": cq, "r": cr, "by": author, "cid": id(ws)},
                    room,
                    exclude=ws,
                )
                continue
            if op == "hello":
                hub.clients[ws] = str(msg.get("name") or "anonymous")[:32]
                await hub.broadcast(
                    {"type": "presence", "users": hub.names(room)}, room
                )
                continue
            if op == "switch_map":
                await switch_to(ws, int(msg.get("map_id", DEFAULT_MAP_ID)))
                continue
            if op in MAP_ADMIN_OPS:
                if role != "dm":
                    await ws.send_text(
                        json.dumps(
                            {"type": "error", "detail": "Only the DM can manage maps"}
                        )
                    )
                    continue
                try:
                    await handle_map_admin(ws, op, msg)
                except Exception as e:
                    logger.exception("map admin failed: %s", msg)
                    await ws.send_text(json.dumps({"type": "error", "detail": str(e)}))
                continue
            async with lock:
                try:
                    out = apply_op(op, msg, role, author, room)
                except Exception as e:
                    logger.exception("op failed: %s", msg)
                    await ws.send_text(json.dumps({"type": "error", "detail": str(e)}))
                    continue
                if out is not None and out.get("type") != "ping":
                    out["by"] = author
                    store.log_op(
                        author,
                        str(op),
                        {
                            k: msg[k]
                            for k in (
                                "q",
                                "r",
                                "terrain",
                                "icon",
                                "explored",
                                "enabled",
                                "kind",
                                "id",
                                "label",
                                "clear",
                            )
                            if k in msg
                        },
                        room,
                    )
            if out is not None:
                await hub.broadcast(out, room)
    except WebSocketDisconnect:
        pass
    finally:
        room = hub.room(ws)
        hub.clients.pop(ws, None)
        hub.rooms.pop(ws, None)
        await hub.broadcast({"type": "presence", "users": hub.names(room)}, room)


DM_OPS = {"clear_all", "set_explored", "set_fog", "undo"}

# Per-connection flood guard: allow a short burst, then a steady rate.
RATE_BURST = 40
RATE_PER_SEC = 25.0


class RateLimiter:
    def __init__(self, burst: int, per_sec: float) -> None:
        self.capacity = float(burst)
        self.per_sec = per_sec
        self.tokens = float(burst)
        self.updated = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(
            self.capacity, self.tokens + (now - self.updated) * self.per_sec
        )
        self.updated = now
        if self.tokens < 1.0:
            return False
        self.tokens -= 1.0
        return True


def plan_feature_path(
    kind: str, waypoints: list[tuple[int, int]], map_id: int
) -> list[tuple[int, int]]:
    if not 2 <= len(waypoints) <= 12:
        raise ValueError("need 2-12 waypoints")
    terrain = store.terrain_map(map_id)
    occupied = {
        (int(q), int(r))
        for f in store.features(map_id)
        if f["kind"] == kind
        for q, r in f["path"]
    }
    cost = build_cost(kind, terrain, occupied)
    path: list[tuple[int, int]] = []
    for a, b in itertools.pairwise(waypoints):
        leg = a_star(a, b, cost)
        path.extend(leg if not path else leg[1:])  # dedupe joints
    if len(path) > 300:
        raise ValueError("path too long (max 300 hexes)")
    return path


def apply_op(
    op: str | None, msg: dict[str, Any], role: str, author: str, map_id: int
) -> dict[str, Any] | None:
    if op in DM_OPS and role != "dm":
        raise PermissionError("Only the DM can do that")
    v = store.version_of
    if op == "hello":
        return None
    if op == "ping":
        return {"type": "ping", "q": int(msg["q"]), "r": int(msg["r"]), "by": author}
    if op == "set_hex":
        q, r, terrain = int(msg["q"]), int(msg["r"]), str(msg["terrain"])
        store.set_hex(q, r, terrain, author, map_id)
        return {
            "type": "op",
            "op": "set_hex",
            "version": v(map_id),
            "q": q,
            "r": r,
            "terrain": terrain,
            "edited_by": author,
        }
    if op == "set_icon":
        q, r = int(msg["q"]), int(msg["r"])
        icon = msg.get("icon")
        store.set_icon(q, r, icon, author, map_id)
        return {
            "type": "op",
            "op": "set_icon",
            "version": v(map_id),
            "q": q,
            "r": r,
            "icon": icon,
            "edited_by": author,
        }
    if op == "remove_hex":
        q, r = int(msg["q"]), int(msg["r"])
        store.remove_hex(q, r, author, map_id)
        return {
            "type": "op",
            "op": "remove_hex",
            "version": v(map_id),
            "q": q,
            "r": r,
        }
    if op == "set_note":
        q, r = int(msg["q"]), int(msg["r"])
        note = str(msg.get("note") or "")[:2000]
        result = store.set_note(q, r, note, author, map_id)
        return {
            "type": "op",
            "op": "set_note",
            "version": v(map_id),
            "q": q,
            "r": r,
            "edited_by": author,
            **result,
        }
    if op == "set_explored":
        q, r = int(msg["q"]), int(msg["r"])
        explored = bool(msg["explored"])
        store.set_explored(q, r, explored, author, map_id)
        return {
            "type": "op",
            "op": "set_explored",
            "version": v(map_id),
            "q": q,
            "r": r,
            "explored": explored,
        }
    if op == "set_fog":
        enabled = bool(msg["enabled"])
        store.set_fog(enabled, author, map_id)
        return {
            "type": "op",
            "op": "set_fog",
            "version": v(map_id),
            "enabled": enabled,
        }
    if op == "set_label":
        q, r = int(msg["q"]), int(msg["r"])
        label = store.set_label(q, r, str(msg.get("label") or "")[:40], author, map_id)
        return {
            "type": "op",
            "op": "set_label",
            "version": v(map_id),
            "q": q,
            "r": r,
            "label": label,
            "edited_by": author,
        }
    if op == "set_party":
        if msg.get("clear"):
            store.clear_party(author, map_id)
            return {
                "type": "op",
                "op": "set_party",
                "version": v(map_id),
                "clear": True,
            }
        q, r = int(msg["q"]), int(msg["r"])
        store.set_party(q, r, author, map_id)
        return {
            "type": "op",
            "op": "set_party",
            "version": v(map_id),
            "q": q,
            "r": r,
        }
    if op == "add_feature":
        kind = str(msg["kind"])
        waypoints = [(int(q), int(r)) for q, r in msg["waypoints"]]
        routed = plan_feature_path(kind, waypoints, map_id)
        feature = store.add_feature(kind, routed, author, map_id)
        return {
            "type": "op",
            "op": "add_feature",
            "version": v(map_id),
            "feature": feature,
        }
    if op == "remove_feature":
        fid = int(msg["id"])
        store.remove_feature(fid, author, map_id)
        return {
            "type": "op",
            "op": "remove_feature",
            "version": v(map_id),
            "id": fid,
        }
    if op == "add_layer":
        added = store.add_layer(str(msg["terrain"]), author, map_id)
        return {
            "type": "op",
            "op": "apply_hexes",
            "version": v(map_id),
            "hexes": added,
        }
    if op == "clear_all":
        store.clear_all(author, map_id)
        return {"type": "snapshot", "action": "clear_all", **store.snapshot(map_id)}
    if op == "undo":
        label = store.undo(map_id)
        if label is None:
            raise ValueError("nothing to undo")
        return {
            "type": "snapshot",
            "action": "undo",
            "undo_label": label,
            **store.snapshot(map_id),
        }
    raise ValueError(f"unknown op {op!r}")


app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/")
async def index() -> HTMLResponse:
    # Version the app.js URL by its mtime so a deploy is never masked by a
    # browser-cached copy of the old module.
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    version = str(int((WEB_DIR / "app.js").stat().st_mtime))
    html = html.replace("/app.js", f"/app.js?v={version}")
    # never cache the shell itself, so the versioned app.js URL always reaches
    # the browser and a deploy can't be masked by a cached index.html
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
