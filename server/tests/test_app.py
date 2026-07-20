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


def test_query_key_replaces_stale_cookie(client: TestClient) -> None:
    r = client.get(
        "/api/config?key=dm-key",
        headers={"cookie": "mapkey=player-key"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 307)
    assert "mapkey=dm-key" in r.headers["set-cookie"]


def test_set_note_broadcasts_with_author(client: TestClient) -> None:
    app_module.store.set_hex(0, 0, "FOG")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "hello", "name": "steph"})
        assert ws.receive_json()["type"] == "presence"
        ws.send_json({"op": "set_note", "q": 0, "r": 0, "note": "owlbear den"})
        msg = ws.receive_json()
        assert msg["op"] == "set_note"
        assert msg["note"] == "owlbear den"
        assert msg["note_author"] == "steph"


def test_set_note_on_missing_hex_errors(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "set_note", "q": 9, "r": 9, "note": "ghost"})
        assert ws.receive_json()["type"] == "error"


def test_ops_logged_and_served(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "hello", "name": "steph"})
        assert ws.receive_json()["type"] == "presence"
        ws.send_json({"op": "set_hex", "q": 1, "r": 2, "terrain": "FOREST"})
        msg = ws.receive_json()
        assert msg["by"] == "steph"
    entries = client.get("/api/history", headers=PLAYER).json()["ops"]
    assert entries[0]["player"] == "steph"
    assert entries[0]["op"] == "set_hex"
    assert entries[0]["detail"] == {"q": 1, "r": 2, "terrain": "FOREST"}


def test_clear_all_snapshot_tagged(client: TestClient) -> None:
    app_module.store.set_hex(0, 0, "FOG")
    with client.websocket_connect("/ws", headers=DM) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "clear_all"})
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert msg["action"] == "clear_all"


def test_import_is_logged(client: TestClient) -> None:
    assert client.post("/api/map/import", json=HEXMAP, headers=DM).status_code == 200
    entries = client.get("/api/history", headers=DM).json()["ops"]
    assert entries[0]["op"] == "import"


def test_set_party_broadcasts(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "set_party", "q": 2, "r": 2})
        msg = ws.receive_json()
        assert msg["op"] == "set_party"
        assert (msg["q"], msg["r"]) == (2, 2)
    assert app_module.store.snapshot()["party"] == {"q": 2, "r": 2}


def test_ping_is_ephemeral(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        before = app_module.store.version
        ws.send_json({"op": "ping", "q": 5, "r": -3})
        msg = ws.receive_json()
        assert msg["type"] == "ping"
        assert (msg["q"], msg["r"]) == (5, -3)
    assert app_module.store.version == before
    assert app_module.store.history(10) == []


def test_set_explored_is_dm_only(client: TestClient) -> None:
    app_module.store.set_hex(0, 0, "FOG")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "set_explored", "q": 0, "r": 0, "explored": False})
        assert ws.receive_json()["type"] == "error"
    with client.websocket_connect("/ws", headers=DM) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "set_explored", "q": 0, "r": 0, "explored": False})
        msg = ws.receive_json()
        assert msg["op"] == "set_explored"
        assert msg["explored"] is False


def test_set_fog_is_dm_only(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "set_fog", "enabled": True})
        assert ws.receive_json()["type"] == "error"
    with client.websocket_connect("/ws", headers=DM) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "set_fog", "enabled": True})
        msg = ws.receive_json()
        assert msg["op"] == "set_fog"
        assert msg["enabled"] is True
    assert app_module.store.snapshot()["fog"] is True


def test_cursor_broadcast_excludes_sender(client: TestClient) -> None:
    with (
        client.websocket_connect("/ws", headers=PLAYER) as ws1,
        client.websocket_connect("/ws", headers=PLAYER) as ws2,
    ):
        assert ws1.receive_json()["type"] == "snapshot"
        assert ws2.receive_json()["type"] == "snapshot"
        ws1.send_json({"op": "hello", "name": "steph"})
        assert ws1.receive_json()["type"] == "presence"
        assert ws2.receive_json()["type"] == "presence"
        before = app_module.store.version
        ws1.send_json({"op": "cursor", "q": 3, "r": 4})
        msg = ws2.receive_json()
        assert msg["type"] == "cursor"
        assert (msg["q"], msg["r"], msg["by"]) == (3, 4, "steph")
        assert "cid" in msg
        # the sender gets no echo: next thing ws1 sees is the ping, not a cursor
        ws1.send_json({"op": "ping", "q": 0, "r": 0})
        assert ws1.receive_json()["type"] == "ping"
    assert app_module.store.version == before
    assert app_module.store.history(10) == []


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
        ws.send_json(
            {"op": "add_feature", "kind": "canal", "waypoints": [[0, 0], [1, 0]]}
        )
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


def test_feature_ops_are_logged(client: TestClient) -> None:
    app_module.store.set_hex(0, 0, "GRASSLAND")
    app_module.store.set_hex(1, 0, "GRASSLAND")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json(
            {"op": "add_feature", "kind": "road", "waypoints": [[0, 0], [1, 0]]}
        )
        assert ws.receive_json()["op"] == "add_feature"
    entries = client.get("/api/history", headers=PLAYER).json()["ops"]
    assert entries[0]["op"] == "add_feature"
    assert entries[0]["detail"]["kind"] == "road"


def test_set_label_broadcasts(client: TestClient) -> None:
    app_module.store.set_hex(0, 0, "CITY")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "set_label", "q": 0, "r": 0, "label": "Akaford"})
        msg = ws.receive_json()
        assert msg["op"] == "set_label"
        assert msg["label"] == "Akaford"
    assert app_module.store.snapshot()["hexes"][0]["label"] == "Akaford"


def test_player_cannot_undo(client: TestClient) -> None:
    app_module.store.set_hex(0, 0, "FOREST")
    app_module.store.set_hex(0, 0, "DESERT", "someone")
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "undo"})
        assert ws.receive_json()["type"] == "error"
    assert app_module.store.snapshot()["hexes"][0]["terrain"] == "DESERT"


def test_dm_undo_reverts_last_edit(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=DM) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "set_hex", "q": 0, "r": 0, "terrain": "FOREST"})
        assert ws.receive_json()["op"] == "set_hex"
        ws.send_json({"op": "set_hex", "q": 0, "r": 0, "terrain": "DESERT"})
        assert ws.receive_json()["op"] == "set_hex"
        ws.send_json({"op": "undo"})
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert msg["action"] == "undo"
    assert app_module.store.snapshot()["hexes"][0]["terrain"] == "FOREST"


def test_snapshot_reports_can_undo(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=DM) as ws:
        assert ws.receive_json()["can_undo"] is False
        ws.send_json({"op": "set_hex", "q": 0, "r": 0, "terrain": "FOREST"})
        assert ws.receive_json()["op"] == "set_hex"
    assert app_module.store.can_undo() is True


def test_edited_by_in_broadcast(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=PLAYER) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        ws.send_json({"op": "hello", "name": "Mara"})
        assert ws.receive_json()["type"] == "presence"
        ws.send_json({"op": "set_hex", "q": 4, "r": 4, "terrain": "FOREST"})
        msg = ws.receive_json()
        assert msg["edited_by"] == "Mara"


def test_rate_limit_drops_flood_and_asks_resync(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers=DM) as ws:
        assert ws.receive_json()["type"] == "snapshot"
        saw_resync = False
        for i in range(app_module.RATE_BURST + 20):
            ws.send_json({"op": "set_hex", "q": i, "r": 0, "terrain": "FOREST"})
            msg = ws.receive_json()
            if msg["type"] == "error" and msg.get("resync"):
                saw_resync = True
                break
        assert saw_resync
