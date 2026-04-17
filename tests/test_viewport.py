import pytest

from hexmapper.viewport import Viewport


def test_initialization() -> None:
    vp = Viewport((800, 600))
    assert vp.screen_width == 800
    assert vp.screen_height == 600
    assert vp.scale == 1.0
    assert vp.offset_x == 0.0
    assert vp.offset_y == 0.0


def test_pan() -> None:
    vp = Viewport((800, 600))
    vp.pan((10.0, 20.0))
    assert vp.offset_x == 10.0
    assert vp.offset_y == 20.0


def test_screen_to_world_roundtrip() -> None:
    vp = Viewport((800, 600))
    vp.offset_x = 50.0
    vp.offset_y = 30.0
    world = vp.screen_to_world((200.0, 300.0))
    back = vp.world_to_screen(world)
    assert back[0] == pytest.approx(200.0)
    assert back[1] == pytest.approx(300.0)


def test_zoom_clamps_to_min() -> None:
    vp = Viewport((800, 600))
    for _ in range(50):
        vp.zoom(-1, (400.0, 300.0))
    assert vp.scale == pytest.approx(0.2)


def test_zoom_clamps_to_max() -> None:
    vp = Viewport((800, 600))
    for _ in range(50):
        vp.zoom(1, (400.0, 300.0))
    assert vp.scale == pytest.approx(5.0)


def test_update_screen_size() -> None:
    vp = Viewport((800, 600))
    vp.update_screen_size((1600, 1200))
    assert vp.screen_width == 1600
    assert vp.screen_height == 1200
