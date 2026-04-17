import json
import logging
import os
from typing import Any

import pygame
import pygame_gui

import hexmapper.config as config
from hexmapper.config import (
    BUTTON_HEIGHT,
    BUTTON_SPACING,
    BUTTON_WIDTH_PERCENT,
    DROPDOWN_HEIGHT,
    FONT_SIZE_PERCENT,
    INITIAL_TERRAIN,
    MIN_BUTTON_WIDTH,
    MIN_FONT_SIZE,
    MIN_UI_WIDTH,
    UI_PADDING,
    UI_WIDTH_PERCENT,
    Terrain,
)
from hexmapper.hex_grid import HexGrid
from hexmapper.viewport import Viewport

logger = logging.getLogger(__name__)


class UIManager:
    def __init__(self, hex_grid: HexGrid, viewport: Viewport) -> None:
        self.hex_grid = hex_grid
        self.viewport = viewport
        self.painting = False
        self.placing_icon = False
        self.removing = False
        self.current_terrain: Terrain = INITIAL_TERRAIN
        self.current_icon: str | None = None
        self.screen_width = viewport.screen_width
        self.screen_height = viewport.screen_height
        self._pending_save_data: dict[str, Any] | None = None
        self.file_dialog_window: Any = None

        self.ui_rect: pygame.Rect
        self.icon_palette_rect: pygame.Rect
        self.font: pygame.font.Font
        self.zoom_in_rect: pygame.Rect
        self.zoom_out_rect: pygame.Rect
        self.add_layer_rect: pygame.Rect
        self.remove_hex_rect: pygame.Rect
        self.clear_all_rect: pygame.Rect
        self.save_rect: pygame.Rect
        self.load_rect: pygame.Rect
        self.terrain_dropdown: Any
        self.icon_dropdown: Any

        self.gui_manager = pygame_gui.UIManager((self.screen_width, self.screen_height))

    def setup_ui_elements(self) -> None:
        if hasattr(self, "terrain_dropdown"):
            self.terrain_dropdown.kill()
        if hasattr(self, "icon_dropdown"):
            self.icon_dropdown.kill()

        ui_width = max(MIN_UI_WIDTH, self.screen_width * UI_WIDTH_PERCENT)
        button_width = max(MIN_BUTTON_WIDTH, ui_width * BUTTON_WIDTH_PERCENT)

        self.font = pygame.font.SysFont(
            "Arial", max(MIN_FONT_SIZE, int(self.screen_height * FONT_SIZE_PERCENT))
        )

        self.ui_rect = pygame.Rect(
            self.screen_width - ui_width - 1,
            0,
            ui_width + 1,
            self.screen_height,
        )
        if self.screen_width < MIN_UI_WIDTH * 9:
            self.ui_rect.x = self.screen_width - ui_width
            self.ui_rect.width = ui_width

        button_x = self.ui_rect.x + (ui_width - button_width) / 2
        self.icon_palette_rect = pygame.Rect(
            button_x, BUTTON_SPACING * 10, button_width, BUTTON_HEIGHT * 3
        )
        self.zoom_in_rect = pygame.Rect(
            button_x, BUTTON_SPACING * 1, button_width, BUTTON_HEIGHT
        )
        self.zoom_out_rect = pygame.Rect(
            button_x, BUTTON_SPACING * 2, button_width, BUTTON_HEIGHT
        )
        self.add_layer_rect = pygame.Rect(
            button_x, BUTTON_SPACING * 3, button_width, BUTTON_HEIGHT
        )
        self.remove_hex_rect = pygame.Rect(
            button_x, BUTTON_SPACING * 4, button_width, BUTTON_HEIGHT
        )
        self.clear_all_rect = pygame.Rect(
            button_x, BUTTON_SPACING * 5, button_width, BUTTON_HEIGHT
        )
        self.save_rect = pygame.Rect(
            button_x, BUTTON_SPACING * 6, button_width, BUTTON_HEIGHT
        )
        self.load_rect = pygame.Rect(
            button_x, BUTTON_SPACING * 7, button_width, BUTTON_HEIGHT
        )

        self.terrain_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=[t.name for t in Terrain],
            starting_option=self.current_terrain.name,
            relative_rect=pygame.Rect(
                button_x, BUTTON_SPACING * 8, button_width, DROPDOWN_HEIGHT
            ),
            manager=self.gui_manager,
        )

        icon_options: list[str | tuple[str, str]] = [
            str(entry["name"]) for entry in config.IMAGES.values()
        ]
        self.icon_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=icon_options,
            starting_option=icon_options[0],
            relative_rect=pygame.Rect(
                button_x, BUTTON_SPACING * 9, button_width, DROPDOWN_HEIGHT
            ),
            manager=self.gui_manager,
        )

        self.gui_manager.set_window_resolution((self.screen_width, self.screen_height))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.VIDEORESIZE:
            self._handle_resize(event)

        try:
            gui_consumed = self.gui_manager.process_events(event)
        except TypeError:
            self.gui_manager.process_events(event)
            gui_consumed = False

        if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            self._handle_dropdown_change(event)
            return
        if event.type == pygame_gui.UI_FILE_DIALOG_PATH_PICKED:
            if hasattr(event, "text") and event.text:
                if self._pending_save_data:
                    self._handle_file_save(event.text)
                else:
                    self._handle_file_load(event.text)
            self.file_dialog_window = None
            return

        if self.file_dialog_window is not None:
            try:
                if not self.file_dialog_window.alive():
                    self.file_dialog_window = None
                elif event.type in (
                    pygame.MOUSEBUTTONDOWN,
                    pygame.MOUSEBUTTONUP,
                    pygame.MOUSEMOTION,
                ):
                    return
            except AttributeError:
                if event.type in (
                    pygame.MOUSEBUTTONDOWN,
                    pygame.MOUSEBUTTONUP,
                    pygame.MOUSEMOTION,
                ):
                    return

        if gui_consumed:
            return

        if event.type in (
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION,
        ):
            if hasattr(
                self, "terrain_dropdown"
            ) and self.terrain_dropdown.rect.collidepoint(event.pos):
                return
            if hasattr(self, "icon_dropdown") and self.icon_dropdown.rect.collidepoint(
                event.pos
            ):
                return

        if event.type == pygame.MOUSEBUTTONDOWN:
            self._handle_mouse_down(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            self._handle_mouse_up(event)
        elif event.type == pygame.KEYDOWN:
            self._handle_key_down(event)
        elif event.type == pygame.MOUSEMOTION:
            self._handle_mouse_motion(event)

    def _handle_file_save(self, file_path: str) -> None:
        if not self._pending_save_data:
            return
        try:
            directory = os.path.dirname(file_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(self._pending_save_data, f, indent=2)
            self._pending_save_data = None
        except OSError as e:
            logger.error("Failed to save map to %s: %s", file_path, e)

    def _handle_file_load(self, file_path: str) -> None:
        try:
            with open(file_path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.error("Invalid map file: %s", file_path)
                return
            self.hex_grid.from_json_dict(data)
            if "viewport" in data:
                vp = data["viewport"]
                self.viewport.scale = vp.get("scale", 1.0)
                self.viewport.offset_x = vp.get("offset_x", 0)
                self.viewport.offset_y = vp.get("offset_y", 0)
        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to load map from %s: %s", file_path, e)

    def _handle_resize(self, event: pygame.event.Event) -> None:
        self.screen_width, self.screen_height = event.size
        self.viewport.update_screen_size(event.size)
        self.setup_ui_elements()

    def _handle_dropdown_change(self, event: pygame.event.Event) -> None:
        if event.ui_element == self.terrain_dropdown:
            self.current_terrain = Terrain[event.text]
            self.placing_icon = False
        elif event.ui_element == self.icon_dropdown:
            self.current_icon = event.text
            self.placing_icon = True

    def _handle_mouse_down(self, event: pygame.event.Event) -> None:
        if event.button == 1:
            on_dropdown = (
                hasattr(self, "terrain_dropdown")
                and self.terrain_dropdown.rect.collidepoint(event.pos)
            ) or (
                hasattr(self, "icon_dropdown")
                and self.icon_dropdown.rect.collidepoint(event.pos)
            )
            if not on_dropdown and self.ui_rect.collidepoint(event.pos):
                self._handle_button_click(event.pos)
            elif not on_dropdown:
                self.painting = True

    def _handle_button_click(self, pos: tuple[int, int]) -> None:
        if self.zoom_in_rect.collidepoint(pos):
            self.viewport.zoom(
                1, (self.viewport.screen_width / 2, self.viewport.screen_height / 2)
            )
        elif self.zoom_out_rect.collidepoint(pos):
            self.viewport.zoom(
                -1, (self.viewport.screen_width / 2, self.viewport.screen_height / 2)
            )
        elif self.add_layer_rect.collidepoint(pos):
            self.hex_grid.add_layer(self.current_terrain)
        elif self.remove_hex_rect.collidepoint(pos):
            self.removing = not self.removing
        elif self.clear_all_rect.collidepoint(pos):
            self._handle_clear_all()
        elif self.save_rect.collidepoint(pos):
            self._handle_save()
        elif self.load_rect.collidepoint(pos):
            self._handle_load()

    def _handle_save(self) -> None:
        save_data: dict[str, Any] = self.hex_grid.to_json_dict()
        save_data["viewport"] = {
            "scale": self.viewport.scale,
            "offset_x": self.viewport.offset_x,
            "offset_y": self.viewport.offset_y,
        }
        self.file_dialog_window = pygame_gui.windows.UIFileDialog(
            rect=pygame.Rect(0, 0, 400, 400),
            manager=self.gui_manager,
            window_title="Save Map",
            initial_file_path="untitled.hexmap",
            allow_existing_files_only=False,
            allow_picking_directories=False,
            allowed_suffixes={"hexmap"},
        )
        self.file_dialog_window.set_blocking(True)
        self._pending_save_data = save_data

    def _handle_load(self) -> None:
        self.file_dialog_window = pygame_gui.windows.UIFileDialog(
            rect=pygame.Rect(0, 0, 400, 400),
            manager=self.gui_manager,
            window_title="Load Map",
            initial_file_path="",
            allow_existing_files_only=True,
            allow_picking_directories=False,
            allowed_suffixes={"hexmap"},
        )
        self.file_dialog_window.set_blocking(True)

    def _handle_clear_all(self) -> None:
        self.hex_grid.clear_all()
        center_x, center_y = self.hex_grid.hex_to_pixel(0, 0)
        self.viewport.offset_x = self.screen_width / 2 - center_x * self.viewport.scale
        self.viewport.offset_y = self.screen_height / 2 - center_y * self.viewport.scale
        self.viewport.scale = 1.0

    def _handle_paint_click(self, pos: tuple[int, int]) -> None:
        self.handle_paint(pos)
        if not (self.placing_icon and self.current_icon):
            world_pos = self.viewport.screen_to_world(pos)
            q, r = self.hex_grid.pixel_to_hex(*world_pos)
            if (q, r) in self.hex_grid.hexes:
                self.hex_grid.hexes[(q, r)].terrain = self.current_terrain
            else:
                self.hex_grid.add_hex(q, r, self.current_terrain)

    def _handle_mouse_up(self, event: pygame.event.Event) -> None:
        if event.button == 1:
            if not self.ui_rect.collidepoint(event.pos) and not self.removing:
                self._handle_paint_click(event.pos)
            self.painting = False

    def _handle_key_down(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_a:
            self.hex_grid.add_layer(self.current_terrain)
        elif event.key == pygame.K_s and (event.mod & pygame.KMOD_CTRL):
            self._handle_save()
        elif event.key == pygame.K_o and (event.mod & pygame.KMOD_CTRL):
            self._handle_load()

    def _handle_mouse_motion(self, event: pygame.event.Event) -> None:
        if (
            self.painting
            and event.buttons[0]
            and not self.ui_rect.collidepoint(event.pos)
        ):
            self.handle_paint(event.pos)

    def draw(self, screen: pygame.Surface) -> None:
        if self.removing and not self.ui_rect.collidepoint(pygame.mouse.get_pos()):
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_NO)
        else:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        pygame.draw.rect(screen, (40, 40, 45), self.ui_rect)

        mouse_pos = pygame.mouse.get_pos()
        self._draw_modern_button(
            screen,
            self.zoom_in_rect,
            "Zoom +",
            self.zoom_in_rect.collidepoint(mouse_pos),
        )
        self._draw_modern_button(
            screen,
            self.zoom_out_rect,
            "Zoom -",
            self.zoom_out_rect.collidepoint(mouse_pos),
        )
        self._draw_modern_button(
            screen,
            self.add_layer_rect,
            "Add Layer",
            self.add_layer_rect.collidepoint(mouse_pos),
        )
        self._draw_modern_button(
            screen,
            self.remove_hex_rect,
            "Stop Removing" if self.removing else "Remove Hex",
            self.remove_hex_rect.collidepoint(mouse_pos),
            active=self.removing,
        )
        self._draw_modern_button(
            screen,
            self.clear_all_rect,
            "Clear All",
            self.clear_all_rect.collidepoint(mouse_pos),
        )
        self._draw_modern_button(
            screen, self.save_rect, "Save", self.save_rect.collidepoint(mouse_pos)
        )
        self._draw_modern_button(
            screen, self.load_rect, "Load", self.load_rect.collidepoint(mouse_pos)
        )

        self.gui_manager.update(pygame.time.get_ticks() / 1000.0)
        self.gui_manager.draw_ui(screen)

    def _draw_modern_button(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        text: str,
        hover: bool = False,
        active: bool = False,
    ) -> None:
        if active:
            color1 = (130, 50, 50) if hover else (110, 40, 40)
            color2 = (110, 40, 40) if hover else (90, 30, 30)
        else:
            color1 = (100, 100, 110) if hover else (80, 80, 90)
            color2 = (80, 80, 90) if hover else (60, 60, 70)
        pygame.draw.rect(screen, color1, rect, border_radius=6)
        pygame.draw.rect(screen, color2, rect.inflate(-4, -4), border_radius=4)

        max_width = rect.width - 2 * UI_PADDING
        current_font = self.font
        text_surf = current_font.render(text, True, (240, 240, 245))

        if text_surf.get_width() > max_width:
            scale_factor = max_width / text_surf.get_width()
            new_size = max(12, int(current_font.get_height() * scale_factor * 0.9))
            current_font = pygame.font.SysFont("Arial", new_size)
            text_surf = current_font.render(text, True, (240, 240, 245))

        screen.blit(text_surf, text_surf.get_rect(center=rect.center))
        pygame.draw.rect(screen, (120, 120, 130, 50), rect, 2, border_radius=6)

    def handle_paint(self, screen_pos: tuple[int, int]) -> None:
        world_pos = self.viewport.screen_to_world(screen_pos)
        q, r = self.hex_grid.pixel_to_hex(*world_pos)
        hex_exists = (q, r) in self.hex_grid.hexes

        if self.removing:
            if hex_exists:
                del self.hex_grid.hexes[(q, r)]
            return

        if self.placing_icon and self.current_icon:
            if not hex_exists:
                return
            cell = self.hex_grid.hexes[(q, r)]
            if cell.icon_name == self.current_icon:
                cell.icon_name = None
                cell._icon_surface = None
            else:
                cell.icon_name = self.current_icon
            return

        if not hex_exists:
            self.hex_grid.add_hex(q, r, self.current_terrain)
        else:
            self.hex_grid.hexes[(q, r)].terrain = self.current_terrain
