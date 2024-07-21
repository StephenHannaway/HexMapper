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

def on_hexagon_double_click(event, gui):
    # Get all items at the clicked point
    items = gui.canvas.find_overlapping(event.x, event.y, event.x, event.y)
    item = gui.canvas.find_withtag("current")
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
    print(f"Offset x: {gui.offset_x}, Offset y: {gui.offset_y}")

def on_resize(event, gui):
    print("New size is: {}x{}".format(event.width, event.height))
    gui.canvas.focus_set()

def on_button_paint(gui):
    print("Painting")
    # Bind pan events to the app
    gui.bind_event("<ButtonPress-1>", lambda event: on_paint_start(event, gui))
    gui.bind_event("<B1-Motion>", lambda event: on_paint_motion(event, gui))
    gui.focus()

def on_button_pan(gui):
    print("Panning")
    # Bind pan events to the app
    gui.bind_event("<ButtonPress-1>", lambda event: on_pan_start(event, gui))
    gui.bind_event("<B1-Motion>", lambda event: on_pan_motion(event, gui))
    gui.focus()

def on_paint_motion(event, gui):
    items = gui.canvas.find_overlapping(event.x, event.y, event.x, event.y)
    for item in items:
        if "hexagon" in gui.canvas.gettags(item):
                # Change the color of the hexagon
                gui.canvas.itemconfig(item, fill=gui.selected_terrain)
    gui.focus() 

def on_paint_start(event, gui):
    gui.focus()
