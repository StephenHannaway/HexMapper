# hexagon_drawer.py
import math

def draw_hexagon(canvas, hex_tuple, hex_size, fill_color, offset_x=0, offset_y=0, zoom_level=0, outline_color="black"):
    q, r = hex_tuple
    width = canvas.winfo_width()
    height = canvas.winfo_height()
    points = []

    #x_center = 1000 / 2 + 3/2 * hex_size * q + offset_x # width / 2 + 3/2 * hex_size * q 
    #y_center = 900 / 2 + math.sqrt(3) * hex_size * (r + q / 2) + offset_y #height / 2 + math.sqrt(3) * hex_size * (r + q / 2)
    
    x_center = 1000 / 2 + hex_size * (math.sqrt(3) * (q + r / 2)) + offset_x  # Adjust width if needed
    y_center = 900 / 2 + hex_size * (3/2 * r) + offset_y  # Adjust height if needed


    for i in range(6):
        angle = 2 * math.pi * (i / 6) - math.pi / 6 #2 * math.pi * (i / 6)
        x = x_center + hex_size * math.cos(angle)#x_center + hex_size * math.cos(angle)
        y = y_center + hex_size * math.sin(angle)#y_center + hex_size * math.sin(angle)
        points.extend([x, y])
    hexagon = canvas.create_polygon(points, fill=fill_color, outline=outline_color, tags='hexagon')
    handle_zoom(canvas, hexagon, width, height, zoom_level)
    return hexagon

def handle_zoom(canvas, hexagon, width, height, factor):
    if not factor:
        return
    if factor > 0:
        for i in range(factor):
            canvas.scale(hexagon, 1000 / 2, 900 / 2, 1.1, 1.1)

    if factor < 0:
        for i in range(abs(factor)):
            canvas.scale(hexagon, 1000 / 2, 900 / 2, 1/1.1, 1/1.1)

def add_ring_old(n, canvas, hex_size, fill_color, offset_x=0, offset_y=0, zoom_level=0, outline_color="black"):
    results = []
    abs_n = abs(n)
    
    for i in range(-abs_n, abs_n + 1):
        for j in range(-abs_n, abs_n + 1):
            if i + j == abs_n or i + j == -abs_n:
                draw_hexagon(canvas, (i, j), hex_size, fill_color, offset_x, offset_y, zoom_level)


def add_ring(GRID, canvas, hex_size, fill_color, offset_x=0, offset_y=0, zoom_level=0, outline_color="black"):
    directions = [
        (1, 0), (1, -1), (0, -1), 
        (-1, 0), (-1, 1), (0, 1)
    ]
    
    # Collect all the current hexes in the grid
    current_hexes = set(GRID.keys())
    
    # Find outer hexes
    outer_hexes = set()
    for q, r in current_hexes:
        for dq, dr in directions:
            neighbor = (q + dq, r + dr)
            if neighbor not in current_hexes:
                outer_hexes.add(neighbor)

    # Add the outer hexes to the grid
    for q, r in outer_hexes:
        if (q, r) not in GRID:
            GRID[(q, r)] = draw_hexagon(canvas, (q, r), hex_size, fill_color, offset_x, offset_y, zoom_level)

