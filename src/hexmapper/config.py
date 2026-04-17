import logging
import os
from enum import Enum
from pathlib import Path

import pygame
from pygame import image

_ASSETS_DIR = Path(__file__).parent / "assets"

logger = logging.getLogger(__name__)

HEX_SIZE = 20
WORLD_OFFSET_X = 512
WORLD_OFFSET_Y = 384
DEFAULT_SCALE = 1.0

UI_WIDTH_PERCENT = 0.1
MIN_UI_WIDTH = 128
BUTTON_WIDTH_PERCENT = 0.7
MIN_BUTTON_WIDTH = 88
BUTTON_HEIGHT = 40
BUTTON_SPACING = 60
DROPDOWN_HEIGHT = 30
UI_PADDING = 8
FONT_SIZE_PERCENT = 0.02
MIN_FONT_SIZE = 16


class Terrain(Enum):
    FARM = "#98FB98"
    MOUNTAIN = "#829696"
    FOREST = "#00b200"
    LAKE = "#0077ff"
    DESERT = "#ffd232"
    FOG = "#e0e0e0"
    CITY = "#000000"
    SWAMP = "#2e8b57"
    SNOW = "#ffffff"
    JUNGLE = "#228b22"
    VOLCANO = "#ff4500"
    BEACH = "#f5deb3"
    OCEAN = "#000080"
    GRASSLAND = "#7cfc00"
    HILLS = "#808080"
    TUNDRA = "#708090"
    WASTELAND = "#8b4513"
    MARSH = "#556b2f"
    PLAINS = "#ff7f50"

    @property
    def color(self) -> tuple[int, int, int]:
        h = self.value
        return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


IMAGES: dict[str, dict[str, object]] = {}
NAME_TO_KEY: dict[str, str] = {}

_IMAGE_DEFINITIONS: dict[str, dict[str, str]] = {
    "akaford": {"name": "Akaford", "path": "akaford.png"},
    "animal_skull": {"name": "Animal Skull", "path": "animal-skull.png"},
    "bridge": {"name": "Bridge", "path": "bridge.png"},
    "camp": {"name": "Camp", "path": "camp.png"},
    "cave": {"name": "Cave", "path": "cave.png"},
    "holy_oak": {"name": "Holy Oak", "path": "holy-oak.png"},
    "mine": {"name": "Mine", "path": "mine.png"},
    "pillar": {"name": "Pillar", "path": "pillar.png"},
    "pyramid": {"name": "Pyramid", "path": "pyramid.png"},
    "ruin": {"name": "Ruin", "path": "ruin.png"},
    "swords_emblem": {"name": "Swords Emblem", "path": "swords-emblem.png"},
    "temple": {"name": "Temple", "path": "temple.png"},
    "tower": {"name": "Tower", "path": "tower.png"},
    "village": {"name": "Village", "path": "village.png"},
    "wall": {"name": "Wall", "path": "wall.png"},
}


def _create_placeholder_surface(name: str) -> pygame.Surface:
    surface = pygame.Surface((64, 64), pygame.SRCALPHA)
    surface.fill((255, 200, 200))
    pygame.draw.rect(surface, (255, 255, 255), surface.get_rect(), 2)
    pygame.draw.line(surface, (255, 255, 255), (8, 8), (56, 56), 3)
    pygame.draw.line(surface, (255, 255, 255), (56, 8), (8, 56), 3)
    font = pygame.font.SysFont("Arial", 12)
    text = name[:8] + "..." if len(name) > 8 else name
    text_surf = font.render(text, True, (100, 0, 0))
    surface.blit(text_surf, text_surf.get_rect(center=(32, 32)))
    return surface


def init_images() -> None:
    global IMAGES, NAME_TO_KEY

    IMAGES = {}
    for key, defn in _IMAGE_DEFINITIONS.items():
        path = _ASSETS_DIR / defn["path"]
        try:
            surface = image.load(os.fspath(path)).convert_alpha()
            IMAGES[key] = {"name": defn["name"], "surface": surface, "path": str(path)}
        except (FileNotFoundError, pygame.error) as e:
            logger.warning("Could not load %s: %s — using placeholder", path, e)
            IMAGES[key] = {
                "name": defn["name"],
                "surface": _create_placeholder_surface(defn["name"]),
                "path": str(path),
                "is_placeholder": True,
            }

    NAME_TO_KEY = {str(data["name"]): key for key, data in IMAGES.items()}


INITIAL_HEX_Q = 0
INITIAL_HEX_R = 0
INITIAL_TERRAIN = Terrain.FOG
