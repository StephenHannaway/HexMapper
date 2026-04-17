from hexmapper.config import Terrain
from hexmapper.hex_grid import HexGrid


def test_initial_state() -> None:
    grid = HexGrid()
    assert (0, 0) in grid.hexes
    assert len(grid.hexes) == 1


def test_add_hex() -> None:
    grid = HexGrid()
    grid.add_hex(1, 0, Terrain.FOREST)
    assert (1, 0) in grid.hexes
    assert grid.hexes[(1, 0)].terrain == Terrain.FOREST


def test_add_layer_expands_grid() -> None:
    grid = HexGrid()
    added = grid.add_layer(Terrain.MOUNTAIN)
    assert len(added) == 6
    assert len(grid.hexes) == 7


def test_clear_all_resets_to_single_hex() -> None:
    grid = HexGrid()
    grid.add_layer(Terrain.FOREST)
    grid.clear_all()
    assert len(grid.hexes) == 1
    assert (0, 0) in grid.hexes


def test_round_trip_json() -> None:
    grid = HexGrid()
    grid.add_layer(Terrain.LAKE)
    grid.hexes[(0, 0)].icon_name = "tower"
    data = grid.to_json_dict()
    grid2 = HexGrid()
    grid2.from_json_dict(data)
    assert len(grid2.hexes) == len(grid.hexes)
    assert grid2.hexes[(0, 0)].terrain == Terrain.FOG
    assert grid2.hexes[(0, 0)].icon_name == "tower"


def test_round_hex_center() -> None:
    grid = HexGrid()
    assert grid.round_hex(0.1, 0.1) == (0, 0)
    assert grid.round_hex(0.9, 0.0) == (1, 0)


def test_terrain_color() -> None:
    r, g, b = Terrain.FARM.color
    assert (r, g, b) == (0x98, 0xFB, 0x98)
