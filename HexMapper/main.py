# main.py
from HexMapper.interface import GUI
from HexMapper.constants.mapperConstants import Terrain
from HexMapper.Utils.Hexagon import Hexagon
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

def initialize_grid(gui):
    # Function to initialize and draw the hexagon grid
    axial_range = 5  # Example axial range for the grid
    for q in range(-axial_range, axial_range + 1):
        for r in range(-axial_range, axial_range + 1):
            if -q - r >= -axial_range and -q - r <= axial_range:
                #canvas_location = draw_hexagon(canvas, (q, r), hex_size, width, height, Terrain.FOG.value)
                gui.GRID[(q, r)] = Hexagon(q, r, gui.HEX_SIZE, Terrain.FOG, None, gui.canvas)

def main():
    app = GUI(1000, 900, 15, "#1e1e1e", {})
    app.create_main_window()
    button_configs = {
        "FARM": lambda: on_button_click(Terrain.FARM.value, app),
        "MOUNTAIN": lambda: on_button_click(Terrain.MOUNTAIN.value, app),
        "FOREST": lambda: on_button_click(Terrain.FOREST.value, app),
        "LAKE": lambda: on_button_click(Terrain.LAKE.value, app),
        "DESERT": lambda: on_button_click(Terrain.DESERT.value, app),
        "FOG": lambda: on_button_click(Terrain.FOG.value, app),
        "CITY": lambda: on_button_click(Terrain.CITY.value, app),
        "SWAMP": lambda: on_button_click(Terrain.SWAMP.value, app),  # New button
        "New Hex": lambda: on_button_hex(app),  # New button
    }
    app.add_buttons(button_configs)
    app.update_root()
    initialize_grid(app)

    app.bind_event("<Double-Button-1>", lambda event: on_hexagon_double_click(app))

    # Bind pan events to the app
    app.bind_event("<ButtonPress-1>", lambda event: on_pan_start(event, app))
    app.bind_event("<B1-Motion>", lambda event: on_pan_motion(event, app))

    # zoom in and out bindings
    app.bind_event("i", lambda event: on_zoom_in(app)) 
    app.bind_event("o", lambda event: on_zoom_out(app))

    app.bind_event("<Configure>", lambda event: on_resize(event, app))
    app.root.mainloop()

if __name__ == '__main__':
    main()
