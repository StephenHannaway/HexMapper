# event_handlers.py
from constants.mapperConstants import Terrain, Feature
from Utils.drawer import draw_hexagon
import tkinter as tk

selected_terrain = Terrain.FOG.value
pan_data = {"x": 0, "y": 0}

def on_button_terrain(gui, color):
    gui.selected_terrain = color
    gui.focus()

def on_button_feature(gui, feature):
    #gui.draw_hex_ring(6)
    gui.selected_feature = feature
    gui.selected_terrain = None
    gui.focus()

def on_hexagon_double_click(gui):
    item = gui.canvas.find_withtag("current")
    print(item)
    if item:
        if gui.selected_terrain:
            gui.canvas.itemconfig(item, fill=gui.selected_terrain)
        else:
            hex_tuple = gui.map[item[0]]
            gui.draw_image(hex_tuple, gui.selected_feature)

def on_zoom_in(gui):
    print("Zooming in")
    gui.zoom_in()

def on_zoom_out(gui):
    print("Zooming out")
    gui.zoom_out()

def on_pan_start(event, gui):
    # Record the initial position
    gui.pan_x = event.x
    gui.pan_y = event.y

def on_pan_motion(event, gui):
    # Calculate how much the mouse has moved
    delta_x = event.x - gui.pan_x 
    delta_y = event.y - gui.pan_y

    # Move the canvas content the same distance
    gui.canvas.move(tk.ALL, delta_x, delta_y)

    # Update the pan data
    gui.pan_x  = event.x
    gui.pan_y = event.y
    gui.offset_x += delta_x
    gui.offset_y += delta_y

def on_resize(event, gui):
    print("New size is: {}x{}".format(event.width, event.height))
    gui.canvas.focus_set()

