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
