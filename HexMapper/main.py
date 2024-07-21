# main.py
from interface import GUI
from constants.mapperConstants import Terrain
from Utils.Hexagon import Hexagon
from Utils.event_handler_new import (
    on_button_terrain,
    on_button_feature,
    on_hexagon_double_click,
    on_pan_start,
    on_pan_motion,
    on_zoom_in,
    on_zoom_out,
    on_resize,
)

def main():
    app = GUI()
    app.create_main_window()
    app.update_root()

    app.bind_event("<Double-Button-1>", lambda event: on_hexagon_double_click(event, app))

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
