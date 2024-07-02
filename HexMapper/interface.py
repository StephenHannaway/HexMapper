# gui class for HexMapper
import tkinter as tk
from tkinter import ttk
import sv_ttk
from HexMapper.Utils.Hexagon import Hexagon 
from HexMapper.Utils.ui_setup import create_main_window, add_buttons
from HexMapper.Utils.drawer import draw_hexagon, add_ring
from HexMapper.constants.mapperConstants import Terrain
from HexMapper.Utils.event_handler_new import (
    on_button_click,
    on_button_hex,
    on_hexagon_double_click,
    on_pan_start,
    on_pan_motion,
    on_zoom_in,
    on_zoom_out,
    on_resize,
)

class GUI():
    def __init__(self, WIDTH, HEIGHT, HEX_SIZE, BACKGROUND_COLOR, GRID):
        self.WIDTH = WIDTH
        self.HEIGHT = HEIGHT
        self.BACKGROUND_COLOR = BACKGROUND_COLOR
        self.HEX_SIZE = HEX_SIZE
        self.GRID = GRID
        self.zoom_level = 0
        self.pan_x = 0
        self.pan_y = 0
        self.offset_x = 0
        self.offset_y = 0
        self.selected_color = Terrain.FOG.value

    def create_main_window(self):
        self.root, self.canvas = create_main_window(self.WIDTH, self.HEIGHT, self.BACKGROUND_COLOR)
        sv_ttk.set_theme("dark")
    
    def update_root(self):
        self.root.update()

    def add_buttons(self, button_configs):
        buttons = {}
        for i, (text, command) in enumerate(button_configs.items()):
            button = ttk.Button(self.root, text=text, command=command)
            button.grid(row=i, column=1)
            buttons[text] = button
        return buttons

    def initialize_grid(self):
        # Function to initialize and draw the hexagon grid
        axial_range = 5  # Example axial range for the grid
        for q in range(-axial_range, axial_range + 1):
            for r in range(-axial_range, axial_range + 1):
                if -q - r >= -axial_range and -q - r <= axial_range:
                    #canvas_location = draw_hexagon(canvas, (q, r), hex_size, width, height, Terrain.FOG.value)
                    self.GRID[(q, r)] = Hexagon(q, r, self.HEX_SIZE, Terrain.FOG, None, self.canvas)

    def bind_event(self, event, command):
        self.canvas.bind(event, command)

    def draw_hexagon(self, q, r):
        hexagon = draw_hexagon(self.canvas, (q, r), self.HEX_SIZE, self.selected_color, self.offset_x, self.offset_y, self.zoom_level)
        return hexagon
    
    def draw_hex_ring(self, n):
        hexagon = add_ring(n, self.canvas, self.HEX_SIZE, self.selected_color, self.offset_x, self.offset_y, self.zoom_level)
        return hexagon
    
    def focus(self):
        self.canvas.focus_set()

    def zoom_in(self):
        self.zoom_level += 1
        self.canvas.scale(tk.ALL, self.WIDTH / 2, self.HEIGHT / 2, 1.1, 1.1)

    def zoom_out(self):
        self.zoom_level += -1
        self.canvas.scale(tk.ALL, self.WIDTH / 2, self.HEIGHT / 2, 1/1.1, 1/1.1)

    def on_button_click(color, canvas):
        pass

    def on_button_hex(canvas):
        pass

    def on_hexagon_double_click(event, canvas):
        pass

    def on_zoom_in(event, canvas, WIDTH, HEIGHT):
        pass

    def on_zoom_out(event, canvas, WIDTH, HEIGHT):
        pass

    def pan_start(event):
        # Record the initial position
        pass

    def on_pan_motion(event, canvas):
        # Calculate how much the mouse has moved
        # Move the canvas content the same distance
        # Update the pan data
        pass

    def on_resize(event, canvas):
        pass

