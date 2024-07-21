# ui_setup.py
import tkinter as tk
from tkinter import ttk
from Utils.Hexagon import Hexagon
from constants.mapperConstants import Terrain, Feature
from Utils.event_handler_new import (
    on_button_terrain,
    on_button_feature,
    on_hexagon_double_click,
    on_pan_start,
    on_pan_motion,
    on_zoom_in,
    on_zoom_out,
    on_resize,
    on_button_paint,
    on_button_pan
)

def create_main_window(gui):
    root = tk.Tk()
    root.title('Hexagon Grid Drawer')
    # Create a canvas
    canvas = tk.Canvas(root, width=gui.width, height=gui.height, bg=gui.bg_color)
    canvas.grid(row=0, column=0, rowspan=20)

    # Labels to differentiate sections
    mode_label = ttk.Label(root, text="Controls", font=("Arial", 20, "bold"))
    mode_label.grid(row=0, column=1, padx=10, pady=5, sticky="nsew")

    mode_label = ttk.Label(root, text="Mode", font=("Arial", 12, "bold"))
    mode_label.grid(row=1, column=1, padx=10, pady=5, sticky="W")

    zoom_label = ttk.Label(root, text="Scale & Zoom", font=("Arial", 12, "bold"))
    zoom_label.grid(row=3, column=1, padx=10, pady=5, sticky="W")

    terrain_label = ttk.Label(root, text="Terrain", font=("Arial", 12, "bold"))
    terrain_label.grid(row=6, column=1, padx=10, pady=5, sticky="W")

    features_label = ttk.Label(root, text="Features", font=("Arial", 12, "bold"))
    features_label.grid(row=11, column=1, padx=10, pady=5, sticky="W")

    # Painting and Panning Buttons
    paint_button = ttk.Button(root, text="Paint", command=lambda: on_button_paint(gui))
    pan_button = ttk.Button(root, text="Pan", command=lambda: on_button_pan(gui))

    paint_button.grid(row=2, column=1, padx=10, pady=5, sticky="W")
    pan_button.grid(row=2, column=2, padx=10, pady=5, sticky="W")

    # Zoom Level Slider
    scale_slider = ttk.Scale(root, from_=1, to_=60, orient='horizontal', command=print("Slider changed"))
    scale_slider.set(5)
    scale_slider.grid(row=4, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")

    zoom_in_button = ttk.Button(root, text="Zoom in", command=lambda: on_zoom_in(gui))
    zoom_out_button = ttk.Button(root, text="Zoom out", command=lambda: on_zoom_out(gui))

    zoom_in_button.grid(row=5, column=1, padx=10, pady=5, sticky="W")
    zoom_out_button.grid(row=5, column=2, padx=10, pady=5, sticky="W")

    # Terrain Buttons
    farm_button = ttk.Button(root, text="Farm", command=lambda: on_button_terrain(gui, Terrain.FARM.value))
    mountain_button = ttk.Button(root, text="Mountain", command=lambda: on_button_terrain(gui, Terrain.MOUNTAIN.value))
    forest_button = ttk.Button(root, text="Forest", command=lambda: on_button_terrain(gui, Terrain.FOREST.value))
    lake_button = ttk.Button(root, text="Lake", command=lambda: on_button_terrain(gui, Terrain.LAKE.value))
    desert_button = ttk.Button(root, text="Desert", command=lambda: on_button_terrain(gui, Terrain.DESERT.value))
    fog_button = ttk.Button(root, text="Fog", command=lambda: on_button_terrain(gui, Terrain.FOG.value))
    city_button = ttk.Button(root, text="City", command=lambda: on_button_terrain(gui, Terrain.CITY.value))
    swamp_button = ttk.Button(root, text="Swamp", command=lambda: on_button_terrain(gui, Terrain.SWAMP.value))

    farm_button.grid(row=7, column=1, padx=10, pady=5, sticky="W")
    mountain_button.grid(row=7, column=2, padx=10, pady=5, sticky="W")
    forest_button.grid(row=8, column=1, padx=10, pady=5, sticky="W")
    lake_button.grid(row=8, column=2, padx=10, pady=5, sticky="W")
    desert_button.grid(row=9, column=1, padx=10, pady=5, sticky="W")
    fog_button.grid(row=9, column=2, padx=10, pady=5, sticky="W")
    city_button.grid(row=10, column=1, padx=10, pady=5, sticky="W")
    swamp_button.grid(row=10, column=2, padx=10, pady=5, sticky="W")

    # Feature Buttons
    city_button = ttk.Button(root, text="City", command=lambda: on_button_feature(gui, Feature.CITY.value))
    village_button = ttk.Button(root, text="Village", command=lambda: on_button_feature(gui, Feature.VILLAGE.value))
    wall_button = ttk.Button(root, text="Wall", command=lambda: on_button_feature(gui, Feature.WALL.value))
    bridge_button = ttk.Button(root, text="Bridge", command=lambda: on_button_feature(gui, Feature.BRIDGE.value))
    tower_button = ttk.Button(root, text="Tower", command=lambda: on_button_feature(gui, Feature.TOWER.value))
    bridge_button = ttk.Button(root, text="Bridge", command=lambda: on_button_feature(gui, Feature.BRIDGE.value))
    cave_button = ttk.Button(root, text="Cave", command=lambda: on_button_feature(gui, Feature.CAVE.value))
    mine_button = ttk.Button(root, text="Mine", command=lambda: on_button_feature(gui, Feature.MINE.value))
    ruins_button = ttk.Button(root, text="Ruins", command=lambda: on_button_feature(gui, Feature.RUINS.value))
    temple_button = ttk.Button(root, text="Temple", command=lambda: on_button_feature(gui, Feature.TEMPLE.value))
    camp_button = ttk.Button(root, text="Camp", command=lambda: on_button_feature(gui, Feature.CAMP.value))

    city_button.grid(row=12, column=1, padx=10, pady=5, sticky="W")
    village_button.grid(row=12, column=2, padx=10, pady=5, sticky="W")
    wall_button.grid(row=13, column=1, padx=10, pady=5, sticky="W")
    bridge_button.grid(row=13, column=2, padx=10, pady=5, sticky="W")
    tower_button.grid(row=14, column=1, padx=10, pady=5, sticky="W")
    cave_button.grid(row=14, column=2, padx=10, pady=5, sticky="W")
    mine_button.grid(row=15, column=1, padx=10, pady=5, sticky="W")
    ruins_button.grid(row=15, column=2, padx=10, pady=5, sticky="W")
    temple_button.grid(row=16, column=1, padx=10, pady=5, sticky="W")
    camp_button.grid(row=16, column=2, padx=10, pady=5, sticky="W")

    # After creating the canvas, make it focusable
    canvas.configure(takefocus=1)
    # Set focus to the canvas so it can receive keyboard events
    canvas.focus_set()
    return root, canvas

def setup_grid(canvas, HEX_SIZE, grid, map, axial_range = 5):
    # Function to initialize and draw the hexagon grid
      # Example axial range for the grid
    for q in range(-axial_range, axial_range + 1):
        for r in range(-axial_range, axial_range + 1):
            if -q - r >= -axial_range and -q - r <= axial_range:
                #canvas_location = draw_hexagon(canvas, (q, r), hex_size, width, height, Terrain.FOG.value)
                hex = Hexagon(q, r, HEX_SIZE, Terrain.FOG, None, canvas)
                grid[(q, r)] = hex
                map[hex.canvas_id] = (q, r)
