# gui class for HexMapper
import tkinter as tk
from tkinter import ttk
import sv_ttk
from Utils.Hexagon import Hexagon 
from Utils.ui_setup import create_main_window, setup_grid
from Utils.drawer import draw_hexagon, add_ring, add_img
from constants.mapperConstants import Terrain
class GUI():
    def __init__(self, WIDTH=1000, HEIGHT=900, HEX_SIZE=30, BACKGROUND_COLOR="#1e1e1e", GRID={}):
        self.width = WIDTH
        self.height = HEIGHT
        self.bg_color = BACKGROUND_COLOR
        self.hex_size = HEX_SIZE
        self.grid = GRID
        self.zoom_level = 0
        self.pan_x = 0
        self.pan_y = 0
        self.offset_x = 0
        self.offset_y = 0
        self.selected_color = Terrain.FOG.value

    def create_main_window(self):
        self.root, self.canvas = create_main_window(self)
        sv_ttk.set_theme("dark")

        setup_grid(self.canvas, self.hex_size, self.grid)
    
    def update_root(self):
        self.root.update()

    def bind_event(self, event, command):
        self.canvas.bind(event, command)

    def draw_hexagon(self, q, r):
        hexagon = draw_hexagon(self.canvas, (q, r), self.hex_size, self.selected_color, self.offset_x, self.offset_y, self.zoom_level)
        return hexagon
    
    def draw_hex_ring(self, n):
        hexagon = add_ring(self.grid, self.canvas, self.hex_size, self.selected_color, self.offset_x, self.offset_y, self.zoom_level)
        return hexagon
    
    def draw_image(self):
        hexagon = add_img(self.root, self.canvas, (0,0), 15, offset_x=0, offset_y=0, zoom_level=0)
        return hexagon
    
    def focus(self):
        self.canvas.focus_set()

    def zoom_in(self):
        self.zoom_level += 1
        self.canvas.scale(tk.ALL, self.width / 2, self.height / 2, 1.1, 1.1)

    def zoom_out(self):
        self.zoom_level += -1
        self.canvas.scale(tk.ALL, self.width / 2, self.height / 2, 1/1.1, 1/1.1)

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

