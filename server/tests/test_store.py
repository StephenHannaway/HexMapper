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
    assert {"q": 2, "r": -1, "terrain": "DESERT", "icon": None} in snap["hexes"]


def test_remove_hex(store: MapStore) -> None:
    store.set_hex(0, 0, "FOG")
    store.remove_hex(0, 0)
    assert store.count() == 0
