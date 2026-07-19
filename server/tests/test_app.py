from collections.abc import Iterator
from pathlib import Path

import hexserver.app as app_module
import pytest
from fastapi.testclient import TestClient
from hexserver.store import MapStore

PLAYER = {"cookie": "mapkey=player-key"}
DM = {"cookie": "mapkey=dm-key"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(app_module, "store", MapStore(Path(":memory:")))
    monkeypatch.setattr(app_module, "MAP_KEY", "player-key")
    monkeypatch.setattr(app_module, "DM_KEY", "dm-key")
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture
def open_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(app_module, "store", MapStore(Path(":memory:")))
    monkeypatch.setattr(app_module, "MAP_KEY", "")
    monkeypatch.setattr(app_module, "DM_KEY", "")
    with TestClient(app_module.app) as c:
        yield c


def test_no_key_rejected(client: TestClient) -> None:
    assert client.get("/api/config").status_code == 403


def test_wrong_key_rejected(client: TestClient) -> None:
    r = client.get("/api/config", headers={"cookie": "mapkey=wrong"})
    assert r.status_code == 403


def test_player_key_gives_player_role(client: TestClient) -> None:
    r = client.get("/api/config", headers=PLAYER)
    assert r.status_code == 200
    assert r.json()["role"] == "player"


def test_dm_key_gives_dm_role(client: TestClient) -> None:
    r = client.get("/api/config", headers=DM)
    assert r.status_code == 200
    assert r.json()["role"] == "dm"


def test_query_key_redirects_and_sets_cookie(client: TestClient) -> None:
    r = client.get("/api/config?key=player-key", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "mapkey=player-key" in r.headers["set-cookie"]


def test_no_keys_configured_everyone_is_dm(open_client: TestClient) -> None:
    r = open_client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["role"] == "dm"


def test_ws_rejects_without_key(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect("/ws"),
    ):
        pass
    assert exc.value.code == 4403


def test_player_cannot_clear_all(client: TestClient) -> None:
    app_module.store.set_hex(0, 0, "FOG")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "clear_all"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
    assert app_module.store.count() == 1


def test_dm_can_clear_all(client: TestClient) -> None:
    app_module.store.set_hex(0, 0, "FOG")
    app_module.store.set_hex(1, 0, "FOREST")
    with client.websocket_connect("/ws", headers=DM) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "clear_all"})
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
    assert app_module.store.count() == 1


def test_player_can_set_hex(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "set_hex", "q": 2, "r": 3, "terrain": "FOREST"})
        msg = ws.receive_json()
        assert msg["op"] == "set_hex"
    assert app_module.store.count() == 1


HEXMAP = {
    "hexes": [
        {"q": 0, "r": 0, "terrain": "OCEAN", "icon_name": None},
        {"q": 1, "r": 0, "terrain": "FOREST", "icon_name": "castle"},
    ]
}


def test_import_requires_dm(client: TestClient) -> None:
    r = client.post("/api/map/import", json=HEXMAP, headers=PLAYER)
    assert r.status_code == 403


def test_import_replaces_map(client: TestClient) -> None:
    app_module.store.set_hex(5, 5, "FOG")
    r = client.post("/api/map/import", json=HEXMAP, headers=DM)
    assert r.status_code == 200
    assert r.json()["hexes"] == 2
    snap = app_module.store.snapshot()
    coords = {(h["q"], h["r"]) for h in snap["hexes"]}
    assert coords == {(0, 0), (1, 0)}


def test_import_rejects_malformed(client: TestClient) -> None:
    r = client.post("/api/map/import", json={"nope": 1}, headers=DM)
    assert r.status_code == 400


def test_import_rejects_empty(client: TestClient) -> None:
    r = client.post("/api/map/import", json={"hexes": []}, headers=DM)
    assert r.status_code == 400


def test_import_broadcasts_snapshot(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        r = client.post("/api/map/import", json=HEXMAP, headers=DM)
        assert r.status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert len(msg["hexes"]) == 2
