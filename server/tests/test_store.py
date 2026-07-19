from pathlib import Path

import pytest
from hexserver.store import MapStore


@pytest.fixture
def store() -> MapStore:
    return MapStore(Path(":memory:"))


def test_add_layer_surrounds_single_hex(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    added = store.add_layer("FOREST")
    assert len(added) == 6
    assert store.count() == 7
    assert all(h["terrain"] == "FOREST" for h in added)


def test_add_layer_only_adds_ring(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    store.add_layer("FOG")
    added = store.add_layer("OCEAN")
    assert len(added) == 12
    assert store.count() == 19
    coords = {(h["q"], h["r"]) for h in added}
    assert (0, 0) not in coords


def test_add_layer_rejects_unknown_terrain(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    with pytest.raises(ValueError, match="unknown terrain"):
        store.add_layer("LAVA_LAND")


def test_set_hex_and_snapshot(store: MapStore) -> None:
    store.set_hex(2, -1, "DESERT")
    snap = store.snapshot()
    assert {
        "q": 2,
        "r": -1,
        "terrain": "DESERT",
        "icon": None,
        "note": None,
        "note_author": None,
    } in snap["hexes"]


def test_remove_hex(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    store.remove_hex(0, 0)
    assert store.count() == 0


def test_set_note_and_snapshot(store: MapStore) -> None:
    store.set_hex(1, 2, "FOREST")
    store.set_note(1, 2, "Session 12: owlbear den", "steph")
    snap = store.snapshot()
    (cell,) = [h for h in snap["hexes"] if h["q"] == 1 and h["r"] == 2]
    assert cell["note"] == "Session 12: owlbear den"
    assert cell["note_author"] == "steph"


def test_set_note_missing_hex_raises(store: MapStore) -> None:
    with pytest.raises(ValueError, match="no hex"):
        store.set_note(9, 9, "ghost note", "steph")


def test_empty_note_clears(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    store.set_note(0, 0, "temp", "steph")
    store.set_note(0, 0, "  ", "steph")
    (cell,) = store.snapshot()["hexes"]
    assert cell["note"] is None
    assert cell["note_author"] is None


def test_repaint_keeps_note(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    store.set_note(0, 0, "keep me", "steph")
    store.set_hex(0, 0, "DESERT")
    (cell,) = store.snapshot()["hexes"]
    assert cell["terrain"] == "DESERT"
    assert cell["note"] == "keep me"


def test_note_roundtrips_through_hexmap(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    store.set_note(0, 0, "roundtrip", "steph")
    data = store.export_hexmap()
    other = MapStore(Path(":memory:"))
    other.import_hexmap(data)
    (cell,) = other.snapshot()["hexes"]
    assert cell["note"] == "roundtrip"
    assert cell["note_author"] == "steph"


def test_migrates_old_db(tmp_path: Path) -> None:
    import sqlite3

    db_file = tmp_path / "old.db"
    con = sqlite3.connect(db_file)
    con.execute(
        "CREATE TABLE hexes (q INTEGER, r INTEGER, terrain TEXT, icon TEXT, "
        "PRIMARY KEY (q, r))"
    )
    con.execute("INSERT INTO hexes VALUES (0, 0, 'FOG', NULL)")
    con.commit()
    con.close()
    store = MapStore(db_file)
    store.set_note(0, 0, "migrated", "steph")
    (cell,) = store.snapshot()["hexes"]
    assert cell["note"] == "migrated"


def test_log_op_and_history(store: MapStore) -> None:
    store.log_op("steph", "set_hex", {"q": 0, "r": 0, "terrain": "FOG"})
    store.log_op("ines", "remove_hex", {"q": 1, "r": 1})
    hist = store.history(10)
    assert len(hist) == 2
    assert hist[0]["player"] == "ines"
    assert hist[0]["op"] == "remove_hex"
    assert hist[0]["detail"] == {"q": 1, "r": 1}
    assert hist[1]["player"] == "steph"
    assert isinstance(hist[0]["ts"], float)


def test_history_limit(store: MapStore) -> None:
    for i in range(5):
        store.log_op("steph", "set_hex", {"q": i, "r": 0, "terrain": "FOG"})
    assert len(store.history(3)) == 3
    assert store.history(3)[0]["detail"]["q"] == 4


def test_ops_table_pruned(store: MapStore) -> None:
    for i in range(1100):
        store.log_op("steph", "set_hex", {"q": i, "r": 0, "terrain": "FOG"})
    row = store.db.execute("SELECT COUNT(*) FROM ops").fetchone()
    assert row[0] <= 1000
    assert store.history(1)[0]["detail"]["q"] == 1099


def test_party_defaults_to_none(store: MapStore) -> None:
    assert store.snapshot()["party"] is None


def test_set_party_and_snapshot(store: MapStore) -> None:
    store.set_party(3, -2)
    assert store.snapshot()["party"] == {"q": 3, "r": -2}
    store.set_party(4, -2)
    assert store.snapshot()["party"] == {"q": 4, "r": -2}
