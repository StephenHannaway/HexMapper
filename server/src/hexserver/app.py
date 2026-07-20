import asyncio
import itertools
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
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


class Hub:
    def __init__(self) -> None:
        self.clients: dict[WebSocket, str] = {}

    async def broadcast(
        self, message: dict[str, Any], exclude: WebSocket | None = None
    ) -> None:
        payload = json.dumps(message)
        for ws in list(self.clients):
            if ws is exclude:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                self.clients.pop(ws, None)

    def names(self) -> list[str]:
        return sorted(self.clients.values())


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
async def get_map() -> JSONResponse:
    async with lock:
        return JSONResponse(store.snapshot())


@app.get("/api/map/export")
async def export_map() -> JSONResponse:
    async with lock:
        return JSONResponse(store.export_hexmap())


@app.get("/api/history")
async def get_history(limit: int = 50) -> JSONResponse:
    async with lock:
        return JSONResponse({"ops": store.history(min(limit, 200))})


@app.post("/api/map/import")
async def import_map(request: Request) -> JSONResponse:
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
        store.import_hexmap(data)
        store.log_op("the DM", "import", {"hexes": len(hexes)})
        snap = store.snapshot()
    await hub.broadcast(
        {"type": "snapshot", "action": "import", "by": "the DM", **snap}
    )
    return JSONResponse({"ok": True, "hexes": len(snap["hexes"])})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    role = role_for(ws.cookies.get("mapkey"), ws.query_params.get("key"))
    if role is None:
        await ws.close(code=4403)
        return
    await ws.accept()
    hub.clients[ws] = "anonymous"
    try:
        async with lock:
            await ws.send_text(json.dumps({"type": "snapshot", **store.snapshot()}))
        while True:
            msg = json.loads(await ws.receive_text())
            op = msg.get("op")
            author = hub.clients.get(ws, "anonymous")
            if op == "cursor":
                # ephemeral hover position: no lock, no version, no log
                try:
                    cq, cr = int(msg["q"]), int(msg["r"])
                except Exception:
                    continue
                await hub.broadcast(
                    {"type": "cursor", "q": cq, "r": cr, "by": author, "cid": id(ws)},
                    exclude=ws,
                )
                continue
            async with lock:
                try:
                    out = apply_op(op, msg, role, author)
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
                            )
                            if k in msg
                        },
                    )
            if op == "hello":
                hub.clients[ws] = str(msg.get("name") or "anonymous")[:32]
                await hub.broadcast({"type": "presence", "users": hub.names()})
            elif out is not None:
                await hub.broadcast(out)
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.pop(ws, None)
        await hub.broadcast({"type": "presence", "users": hub.names()})


DM_OPS = {"clear_all", "set_explored", "set_fog"}


def plan_feature_path(
    kind: str, waypoints: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    if not 2 <= len(waypoints) <= 12:
        raise ValueError("need 2-12 waypoints")
    terrain = store.terrain_map()
    occupied = {
        (int(q), int(r))
        for f in store.features()
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
    op: str | None, msg: dict[str, Any], role: str, author: str
) -> dict[str, Any] | None:
    if op in DM_OPS and role != "dm":
        raise PermissionError("Only the DM can do that")
    if op == "hello":
        return None
    if op == "ping":
        return {"type": "ping", "q": int(msg["q"]), "r": int(msg["r"]), "by": author}
    if op == "set_hex":
        q, r, terrain = int(msg["q"]), int(msg["r"]), str(msg["terrain"])
        store.set_hex(q, r, terrain)
        return {
            "type": "op",
            "op": "set_hex",
            "version": store.version,
            "q": q,
            "r": r,
            "terrain": terrain,
        }
    if op == "set_icon":
        q, r = int(msg["q"]), int(msg["r"])
        icon = msg.get("icon")
        store.set_icon(q, r, icon)
        return {
            "type": "op",
            "op": "set_icon",
            "version": store.version,
            "q": q,
            "r": r,
            "icon": icon,
        }
    if op == "remove_hex":
        q, r = int(msg["q"]), int(msg["r"])
        store.remove_hex(q, r)
        return {
            "type": "op",
            "op": "remove_hex",
            "version": store.version,
            "q": q,
            "r": r,
        }
    if op == "set_note":
        q, r = int(msg["q"]), int(msg["r"])
        note = str(msg.get("note") or "")[:2000]
        result = store.set_note(q, r, note, author)
        return {
            "type": "op",
            "op": "set_note",
            "version": store.version,
            "q": q,
            "r": r,
            **result,
        }
    if op == "set_explored":
        q, r = int(msg["q"]), int(msg["r"])
        explored = bool(msg["explored"])
        store.set_explored(q, r, explored)
        return {
            "type": "op",
            "op": "set_explored",
            "version": store.version,
            "q": q,
            "r": r,
            "explored": explored,
        }
    if op == "set_fog":
        enabled = bool(msg["enabled"])
        store.set_fog(enabled)
        return {
            "type": "op",
            "op": "set_fog",
            "version": store.version,
            "enabled": enabled,
        }
    if op == "set_label":
        q, r = int(msg["q"]), int(msg["r"])
        label = store.set_label(q, r, str(msg.get("label") or "")[:40])
        return {
            "type": "op",
            "op": "set_label",
            "version": store.version,
            "q": q,
            "r": r,
            "label": label,
        }
    if op == "set_party":
        q, r = int(msg["q"]), int(msg["r"])
        store.set_party(q, r)
        return {
            "type": "op",
            "op": "set_party",
            "version": store.version,
            "q": q,
            "r": r,
        }
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
    if op == "add_layer":
        added = store.add_layer(str(msg["terrain"]))
        return {
            "type": "op",
            "op": "apply_hexes",
            "version": store.version,
            "hexes": added,
        }
    if op == "clear_all":
        store.clear_all()
        return {"type": "snapshot", "action": "clear_all", **store.snapshot()}
    raise ValueError(f"unknown op {op!r}")


app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
