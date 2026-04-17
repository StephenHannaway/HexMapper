import pygame

import hexmapper.config as config
from hexmapper.hex_grid import HexGrid
from hexmapper.hex_grid_renderer import HexGridRenderer
from hexmapper.ui import UIManager
from hexmapper.viewport import Viewport


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((1152, 768), pygame.RESIZABLE)
    pygame.display.set_caption("Hex Editor")
    clock = pygame.time.Clock()

    config.init_images()

    viewport = Viewport(screen.get_size())
    viewport.offset_x = (screen.get_width() - 1024) / 2
    viewport.offset_y = (screen.get_height() - 768) / 2

    hex_grid = HexGrid()
    hex_renderer = HexGridRenderer(hex_grid, viewport)

    ui_manager = UIManager(hex_grid, viewport)
    ui_manager.setup_ui_elements()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEMOTION and event.buttons[1]:
                viewport.pan(event.rel)

            ui_manager.handle_event(event)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    viewport.pan((-10 / viewport.scale, 0))
                elif event.key == pygame.K_RIGHT:
                    viewport.pan((10 / viewport.scale, 0))
                elif event.key == pygame.K_UP:
                    viewport.pan((0, -10 / viewport.scale))
                elif event.key == pygame.K_DOWN:
                    viewport.pan((0, 10 / viewport.scale))
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS):
                    viewport.zoom(1, (screen.get_width() / 2, screen.get_height() / 2))
                elif event.key == pygame.K_MINUS:
                    viewport.zoom(-1, (screen.get_width() / 2, screen.get_height() / 2))

        pan_speed = 10 / viewport.scale
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            viewport.pan((-pan_speed, 0))
        if keys[pygame.K_RIGHT]:
            viewport.pan((pan_speed, 0))
        if keys[pygame.K_UP]:
            viewport.pan((0, -pan_speed))
        if keys[pygame.K_DOWN]:
            viewport.pan((0, pan_speed))

        screen.fill((30, 30, 30))
        hex_renderer.draw(screen)
        ui_manager.draw(screen)
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
