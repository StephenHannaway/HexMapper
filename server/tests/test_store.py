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
    store.set_hex(2, -1, "DESERT", "steph")
    snap = store.snapshot()
    assert {
        "q": 2,
        "r": -1,
        "terrain": "DESERT",
        "icon": None,
        "note": None,
        "note_author": None,
        "explored": 1,
        "label": None,
        "edited_by": "steph",
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


def test_clear_party(store: MapStore) -> None:
    store.set_party(1, 1)
    store.clear_party()
    assert store.snapshot()["party"] is None


def test_undo_clear_party_restores(store: MapStore) -> None:
    store.set_party(2, 5)
    store.clear_party()
    store.undo()
    assert store.snapshot()["party"] == {"q": 2, "r": 5}


def test_clear_all_removes_party(store: MapStore) -> None:
    store.set_party(1, 1)
    store.clear_all()
    assert store.snapshot()["party"] is None


def test_undo_clear_all_restores_party(store: MapStore) -> None:
    store.set_party(2, -3)
    store.clear_all()
    store.undo()
    assert store.snapshot()["party"] == {"q": 2, "r": -3}


def test_hexes_default_explored(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    (cell,) = store.snapshot()["hexes"]
    assert cell["explored"] == 1


def test_set_explored_toggles(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    store.set_explored(0, 0, False)
    assert store.snapshot()["hexes"][0]["explored"] == 0
    store.set_explored(0, 0, True)
    assert store.snapshot()["hexes"][0]["explored"] == 1


def test_repaint_marks_explored(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    store.set_explored(0, 0, False)
    store.set_hex(0, 0, "DESERT")
    assert store.snapshot()["hexes"][0]["explored"] == 1


def test_fog_flag_persists(store: MapStore) -> None:
    assert store.snapshot()["fog"] is False
    store.set_fog(True)
    assert store.snapshot()["fog"] is True
    store.set_fog(False)
    assert store.snapshot()["fog"] is False


def test_explored_migration_defaults_true(tmp_path: Path) -> None:
    import sqlite3

    db_file = tmp_path / "old.db"
    con = sqlite3.connect(db_file)
    con.execute(
        "CREATE TABLE hexes (q INTEGER, r INTEGER, terrain TEXT, icon TEXT, "
        "note TEXT, note_author TEXT, PRIMARY KEY (q, r))"
    )
    con.execute("INSERT INTO hexes VALUES (0, 0, 'FOG', NULL, NULL, NULL)")
    con.commit()
    con.close()
    store = MapStore(db_file)
    assert store.snapshot()["hexes"][0]["explored"] == 1


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
    v = store.version_of(1)
    store.remove_feature(f["id"])
    assert store.features() == []
    assert store.version_of(1) == v + 1
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


def test_clear_all_removes_features(store: MapStore) -> None:
    store.add_feature("road", [(0, 0), (1, 0)], "steph")
    store.clear_all()
    assert store.features() == []


def test_terrain_map(store: MapStore) -> None:
    store.set_hex(2, -1, "DESERT")
    assert store.terrain_map() == {(2, -1): "DESERT"}


def test_set_label_and_snapshot(store: MapStore) -> None:
    store.set_hex(1, 1, "CITY")
    store.set_label(1, 1, "Akaford")
    (cell,) = store.snapshot()["hexes"]
    assert cell["label"] == "Akaford"


def test_empty_label_clears(store: MapStore) -> None:
    store.set_hex(0, 0, "CITY")
    store.set_label(0, 0, "Akaford")
    store.set_label(0, 0, "  ")
    assert store.snapshot()["hexes"][0]["label"] is None


def test_label_missing_hex_raises(store: MapStore) -> None:
    with pytest.raises(ValueError, match="no hex"):
        store.set_label(9, 9, "Nowhere")


def test_label_roundtrips_hexmap(store: MapStore) -> None:
    store.set_hex(0, 0, "CITY")
    store.set_label(0, 0, "Akaford")
    other = MapStore(Path(":memory:"))
    other.import_hexmap(store.export_hexmap())
    assert other.snapshot()["hexes"][0]["label"] == "Akaford"


def test_label_migration(tmp_path: Path) -> None:
    import sqlite3

    db_file = tmp_path / "old.db"
    con = sqlite3.connect(db_file)
    con.execute(
        "CREATE TABLE hexes (q INTEGER, r INTEGER, terrain TEXT, icon TEXT, "
        "note TEXT, note_author TEXT, explored INTEGER DEFAULT 1, "
        "PRIMARY KEY (q, r))"
    )
    con.execute("INSERT INTO hexes VALUES (0, 0, 'FOG', NULL, NULL, NULL, 1)")
    con.commit()
    con.close()
    store = MapStore(db_file)
    store.set_label(0, 0, "migrated")
    assert store.snapshot()["hexes"][0]["label"] == "migrated"


def test_multimap_migration_preserves_production_data(tmp_path: Path) -> None:
    """A batch-2 single-map DB (edited_by, no map_id) migrates to map 1 intact."""
    import sqlite3

    db_file = tmp_path / "prod.db"
    con = sqlite3.connect(db_file)
    con.execute(
        "CREATE TABLE hexes (q INTEGER, r INTEGER, terrain TEXT, icon TEXT, "
        "note TEXT, note_author TEXT, explored INTEGER DEFAULT 1, label TEXT, "
        "edited_by TEXT, PRIMARY KEY (q, r))"
    )
    con.execute(
        "INSERT INTO hexes VALUES (0, 0, 'CITY', 'Temple', 'seat of power', "
        "'steph', 1, 'Akaford', 'steph')"
    )
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta VALUES ('party', '{\"q\": 0, \"r\": 0}')")
    con.execute("INSERT INTO meta VALUES ('fog', '1')")
    con.execute(
        "CREATE TABLE features (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, "
        "path TEXT, created_by TEXT, ts REAL)"
    )
    con.execute(
        "INSERT INTO features (kind, path, created_by, ts) "
        "VALUES ('road', '[[0,0],[1,0]]', 'steph', 0)"
    )
    con.commit()
    con.close()

    store = MapStore(db_file)
    assert store.maps() == [{"id": 1, "name": "World Map"}]
    snap = store.snapshot(1)
    hexes = {(h["q"], h["r"]): h for h in snap["hexes"]}
    assert hexes[(0, 0)]["terrain"] == "CITY"
    assert hexes[(0, 0)]["icon"] == "Temple"
    assert hexes[(0, 0)]["label"] == "Akaford"
    assert hexes[(0, 0)]["edited_by"] == "steph"
    assert snap["party"] == {"q": 0, "r": 0}
    assert snap["fog"] is True
    assert snap["features"][0]["kind"] == "road"
    # a second map is fully independent of the migrated one
    m = store.create_map("Dungeon")
    assert store.count(m["id"]) == 1
    assert store.count(1) == 1


def _hex(store: MapStore, q: int, r: int) -> dict[str, object] | None:
    for h in store.snapshot()["hexes"]:
        if h["q"] == q and h["r"] == r:
            return h
    return None


def test_edited_by_stamped(store: MapStore) -> None:
    store.set_hex(0, 0, "FOREST", "alice")
    assert _hex(store, 0, 0)["edited_by"] == "alice"  # type: ignore[index]
    store.set_icon(0, 0, "Tower", "bob")
    assert _hex(store, 0, 0)["edited_by"] == "bob"  # type: ignore[index]


def test_undo_paint_restores_previous_terrain(store: MapStore) -> None:
    store.set_hex(0, 0, "FOREST", "alice")
    store.set_hex(0, 0, "DESERT", "bob")
    assert store.can_undo()
    label = store.undo()
    assert label is not None
    assert _hex(store, 0, 0)["terrain"] == "FOREST"  # type: ignore[index]


def test_undo_paint_of_new_hex_removes_it(store: MapStore) -> None:
    store.set_hex(3, 3, "FOREST", "alice")
    store.undo()
    assert _hex(store, 3, 3) is None


def test_undo_remove_hex_restores_it(store: MapStore) -> None:
    store.set_hex(1, 1, "LAKE", "alice")
    store.set_note(1, 1, "kraken", "alice")
    store.remove_hex(1, 1, "bob")
    store.undo()
    restored = _hex(store, 1, 1)
    assert restored is not None
    assert restored["terrain"] == "LAKE"
    assert restored["note"] == "kraken"


def test_undo_feature_removes_it(store: MapStore) -> None:
    store.set_hex(0, 0, "GRASSLAND")
    store.set_hex(1, 0, "GRASSLAND")
    f = store.add_feature("road", [(0, 0), (1, 0)], "alice")
    assert len(store.features()) == 1
    store.undo()
    assert store.features() == []
    assert f["id"] is not None


def test_undo_clear_all_restores_map(store: MapStore) -> None:
    store.set_hex(0, 0, "FOREST", "alice")
    store.set_hex(1, 0, "DESERT", "alice")
    store.clear_all("bob")
    assert store.count() == 1  # the seeded FOG hex
    store.undo()
    assert _hex(store, 0, 0)["terrain"] == "FOREST"  # type: ignore[index]
    assert _hex(store, 1, 0)["terrain"] == "DESERT"  # type: ignore[index]


def test_undo_empty_returns_none(store: MapStore) -> None:
    assert store.undo() is None
    assert not store.can_undo()


def test_undo_is_lifo(store: MapStore) -> None:
    store.set_hex(0, 0, "FOREST", "a")
    store.set_hex(0, 0, "DESERT", "a")
    store.set_hex(0, 0, "LAKE", "a")
    store.undo()
    assert _hex(store, 0, 0)["terrain"] == "DESERT"  # type: ignore[index]
    store.undo()
    assert _hex(store, 0, 0)["terrain"] == "FOREST"  # type: ignore[index]
    store.undo()
    assert _hex(store, 0, 0) is None


def test_undo_stack_capped_at_100(store: MapStore) -> None:
    for i in range(130):
        store.set_hex(0, 0, "FOREST" if i % 2 else "DESERT", "a")
    rows = store.db.execute("SELECT COUNT(*) FROM undo").fetchone()[0]
    assert rows <= 100


# --- multiple maps (item 12) ---


def test_default_map_exists(store: MapStore) -> None:
    maps = store.maps()
    assert maps == [{"id": 1, "name": "World Map"}]


def test_create_map_seeds_a_blank_hex(store: MapStore) -> None:
    m = store.create_map("Dungeon of Doom")
    assert m["id"] == 2
    assert store.count(2) == 1
    assert store.maps() == [
        {"id": 1, "name": "World Map"},
        {"id": 2, "name": "Dungeon of Doom"},
    ]


def test_maps_are_isolated(store: MapStore) -> None:
    store.set_hex(0, 0, "FOREST", "a", map_id=1)
    m = store.create_map("Cave")
    store.set_hex(0, 0, "LAKE", "b", map_id=m["id"])
    assert _hex_on(store, 1, 0, 0)["terrain"] == "FOREST"  # type: ignore[index]
    assert _hex_on(store, 2, 0, 0)["terrain"] == "LAKE"  # type: ignore[index]
    # painting map 2 must not touch map 1's hex
    assert store.count(1) == 1


def test_per_map_versions_independent(store: MapStore) -> None:
    store.create_map("B")
    store.set_hex(0, 0, "FOREST", "a", map_id=1)
    store.set_hex(0, 0, "FOREST", "a", map_id=1)
    v1, v2 = store.version_of(1), store.version_of(2)
    assert v1 == 2
    assert v2 == 0


def test_per_map_undo_isolated(store: MapStore) -> None:
    store.create_map("B")
    store.set_hex(0, 0, "FOREST", "a", map_id=1)
    assert store.can_undo(1)
    assert not store.can_undo(2)
    # undoing map 2 (empty stack) does nothing to map 1
    assert store.undo(2) is None
    assert _hex_on(store, 1, 0, 0)["terrain"] == "FOREST"  # type: ignore[index]


def test_per_map_party_and_fog(store: MapStore) -> None:
    store.create_map("B")
    store.set_party(3, 3, "a", map_id=1)
    store.set_fog(True, "a", map_id=2)
    assert store.party(1) == {"q": 3, "r": 3}
    assert store.party(2) is None
    assert store.fog_enabled(2) is True
    assert store.fog_enabled(1) is False


def test_delete_map_removes_its_data(store: MapStore) -> None:
    m = store.create_map("Temp")
    store.set_hex(0, 0, "FOREST", "a", map_id=m["id"])
    store.delete_map(m["id"])
    assert not store.map_exists(m["id"])
    assert (
        store.db.execute(
            "SELECT COUNT(*) FROM hexes WHERE map_id = ?", (m["id"],)
        ).fetchone()[0]
        == 0
    )


def test_cannot_delete_default_map(store: MapStore) -> None:
    with pytest.raises(ValueError, match="default map"):
        store.delete_map(1)


def test_rename_map(store: MapStore) -> None:
    m = store.create_map("Old")
    store.rename_map(m["id"], "New Name")
    assert {"id": m["id"], "name": "New Name"} in store.maps()


def _hex_on(store: MapStore, map_id: int, q: int, r: int) -> dict[str, object] | None:
    for h in store.snapshot(map_id)["hexes"]:
        if h["q"] == q and h["r"] == r:
            return h
    return None
