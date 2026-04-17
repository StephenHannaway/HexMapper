import math

import pygame

import hexmapper.config as config
from hexmapper.hex_grid import HexGrid
from hexmapper.viewport import Viewport


class HexGridRenderer:
    def __init__(self, hex_grid: HexGrid, viewport: Viewport) -> None:
        self.hex_grid = hex_grid
        self.viewport = viewport

    def draw(self, screen: pygame.Surface) -> None:
        world_size = config.HEX_SIZE
        screen_size = world_size * self.viewport.scale

        for (q, r), cell in self.hex_grid.hexes.items():
            world_x, world_y = self.hex_grid.hex_to_pixel(q, r, world_size)
            screen_x, screen_y = self.viewport.world_to_screen((world_x, world_y))

            points = [
                (
                    screen_x + screen_size * math.cos(math.pi / 3 * i),
                    screen_y + screen_size * math.sin(math.pi / 3 * i),
                )
                for i in range(6)
            ]

            pygame.draw.polygon(screen, cell.terrain.color, points)
            pygame.draw.polygon(screen, (50, 50, 50), points, 1)

            if cell.icon_name:
                icon_id = config.NAME_TO_KEY[cell.icon_name]
                if not cell._icon_surface:
                    cell._icon_surface = config.IMAGES[icon_id]["surface"]  # type: ignore[assignment]
                if cell._icon_surface:
                    icon_size = int(screen_size * 1.3)
                    if cell._icon_surface.get_width() != icon_size:
                        cell._icon_surface = pygame.transform.smoothscale(
                            config.IMAGES[icon_id]["surface"],  # type: ignore[arg-type]
                            (icon_size, icon_size),
                        )
                    screen.blit(
                        cell._icon_surface,
                        cell._icon_surface.get_rect(center=(screen_x, screen_y)),
                    )
