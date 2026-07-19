import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from hexserver.config import ICONS, TERRAINS
from hexserver.store import MapStore

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_DIR = REPO_ROOT / "web"
ASSETS_DIR = REPO_ROOT / "src" / "hexmapper" / "assets"
DB_PATH = REPO_ROOT / "server" / "map.db"
SEED_FILE = REPO_ROOT / "map.hexmap2"

app = FastAPI(title="hexserver")
store = MapStore(DB_PATH, seed_file=SEED_FILE)
lock = asyncio.Lock()


class Hub:
    def __init__(self) -> None:
        self.clients: dict[WebSocket, str] = {}

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                self.clients.pop(ws, None)

    def names(self) -> list[str]:
        return sorted(self.clients.values())


hub = Hub()


@app.get("/api/config")
async def get_config() -> JSONResponse:
    return JSONResponse(
        {
            "terrains": TERRAINS,
            "icons": [
                {"name": name, "url": f"/assets/{path}"} for name, path in ICONS.items()
            ],
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


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    hub.clients[ws] = "anonymous"
    try:
        async with lock:
            await ws.send_text(json.dumps({"type": "snapshot", **store.snapshot()}))
        while True:
            msg = json.loads(await ws.receive_text())
            op = msg.get("op")
            async with lock:
                try:
                    out = apply_op(op, msg)
                except Exception as e:
                    logger.exception("op failed: %s", msg)
                    await ws.send_text(json.dumps({"type": "error", "detail": str(e)}))
                    continue
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


def apply_op(op: str | None, msg: dict[str, Any]) -> dict[str, Any] | None:
    if op == "hello":
        return None
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
        return {"type": "snapshot", **store.snapshot()}
    raise ValueError(f"unknown op {op!r}")


app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
