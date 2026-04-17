import math
from dataclasses import dataclass
from typing import Any

import pygame

from hexmapper.config import (
    HEX_SIZE,
    INITIAL_HEX_Q,
    INITIAL_HEX_R,
    INITIAL_TERRAIN,
    WORLD_OFFSET_X,
    WORLD_OFFSET_Y,
    Terrain,
)


@dataclass
class HexCell:
    q: int
    r: int
    terrain: Terrain
    icon_name: str | None = None
    _icon_surface: pygame.Surface | None = None


class HexGrid:
    def __init__(self) -> None:
        self.hexes: dict[tuple[int, int], HexCell] = {}
        self.add_hex(INITIAL_HEX_Q, INITIAL_HEX_R, INITIAL_TERRAIN)

    def add_hex(self, q: int, r: int, terrain: Terrain) -> None:
        self.hexes[(q, r)] = HexCell(q=q, r=r, terrain=terrain)

    def add_layer(self, terrain: Terrain) -> list[tuple[int, int]]:
        new_hexes: list[tuple[int, int]] = []
        for q, r in list(self.hexes.keys()):
            for dq, dr in [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]:
                new_q, new_r = q + dq, r + dr
                if (new_q, new_r) not in self.hexes:
                    self.add_hex(new_q, new_r, terrain)
                    new_hexes.append((new_q, new_r))
        return new_hexes

    def clear_all(self) -> None:
        self.hexes = {}
        self.add_hex(INITIAL_HEX_Q, INITIAL_HEX_R, INITIAL_TERRAIN)

    def hex_to_pixel(
        self, q: int, r: int, size: float = HEX_SIZE
    ) -> tuple[float, float]:
        x = size * (3 / 2 * q)
        y = size * (math.sqrt(3) * (r + q / 2))
        return (x + WORLD_OFFSET_X, y + WORLD_OFFSET_Y)

    def pixel_to_hex(
        self, x: float, y: float, size: float = HEX_SIZE
    ) -> tuple[int, int]:
        x -= WORLD_OFFSET_X
        y -= WORLD_OFFSET_Y
        q = (2 / 3 * x) / size
        r = (-1 / 3 * x + math.sqrt(3) / 3 * y) / size
        return self.round_hex(q, r)

    def round_hex(self, q: float, r: float) -> tuple[int, int]:
        s = -q - r
        q_rnd, r_rnd, s_rnd = round(q), round(r), round(s)

        q_diff = abs(q_rnd - q)
        r_diff = abs(r_rnd - r)
        s_diff = abs(s_rnd - s)

        if q_diff > r_diff and q_diff > s_diff:
            q_rnd = -r_rnd - s_rnd
        elif r_diff > s_diff:
            r_rnd = -q_rnd - s_rnd

        return (int(q_rnd), int(r_rnd))

    def to_json_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "hexes": [
                {
                    "q": cell.q,
                    "r": cell.r,
                    "terrain": cell.terrain.name,
                    "icon_name": cell.icon_name,
                }
                for cell in self.hexes.values()
            ]
        }

    def from_json_dict(self, data: dict[str, Any]) -> None:
        self.hexes.clear()
        for hex_data in data.get("hexes", []):
            q: int = hex_data["q"]
            r: int = hex_data["r"]
            terrain = Terrain[hex_data["terrain"]]
            icon_name: str | None = hex_data.get("icon_name")
            self.hexes[(q, r)] = HexCell(q=q, r=r, terrain=terrain, icon_name=icon_name)
