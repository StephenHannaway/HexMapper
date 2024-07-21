# hexagon_drawer.py
import math
from PIL import Image, ImageTk
from PIL import Image, ImageTk
from constants.mapperConstants import Feature

def draw_hexagon(canvas, hex_tuple, hex_size, fill_color, offset_x=0, offset_y=0, zoom_factor=1, outline_color="black"):
    q, r = hex_tuple
    points = []

    # Apply zoom factor to hex size
    zoomed_hex_size = hex_size * zoom_factor

    # Calculate center position
    x_center = 1000 / 2 + zoomed_hex_size * (math.sqrt(3) * (q + r / 2)) + offset_x
    y_center = 900 / 2 + zoomed_hex_size * (3/2 * r) + offset_y

    # Calculate points of the hexagon
    for i in range(6):
        angle = 2 * math.pi * (i / 6) - math.pi / 6
        x = x_center + zoomed_hex_size * math.cos(angle)
        y = y_center + zoomed_hex_size * math.sin(angle)
        points.extend([x, y])

    # Draw hexagon
    hexagon = canvas.create_polygon(points, fill=fill_color, outline=outline_color, tags='hexagon')

    return hexagon


def add_ring(GRID, canvas, hex_size, fill_color, offset_x=0, offset_y=0, zoom_factor=1, outline_color="black"):
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
            GRID[(q, r)] = draw_hexagon(canvas, (q, r), hex_size, fill_color, offset_x, offset_y, zoom_factor)


def add_img(root, canvas, hex_tuple, image_path, hex_size, offset_x=0, offset_y=0, zoom_factor=1):
    q, r = hex_tuple
    
    # Apply zoom factor to hex size
    zoom_size = hex_size * zoom_factor

    # Calculate center position
    x_center = (1000 / 2 + zoom_size * (math.sqrt(3) * (q + r / 2))) + offset_x
    y_center = (900 / 2 + zoom_size * (3/2 * r)) + offset_y

    # Open and resize the image using PIL
    image = Image.open(image_path)
    resized_image = image.resize((int(zoom_size), int(zoom_size)), Image.Resampling.LANCZOS)
    root.img = img = ImageTk.PhotoImage(resized_image)
    
    # Add image to the canvas
    asset = canvas.create_image(x_center, y_center, anchor='center', image=img, tags='img')

    return (asset, img, image_path)

def scale_images(canvas, items_list, hex_size, zoom_factor):
    new_items_list = []
    img_refs = []

    for item, img, image_path in items_list:
        # Access the PIL image from the ImageTk.PhotoImage object
        pil_img = img._PhotoImage__photo
        
        # Apply zoom factor to hex size
        zoom_size = hex_size * zoom_factor

        # Calculate new size based on zoom factor
        new_width = int(zoom_size)
        new_height = int(zoom_size)

        # Open and resize the image using PIL
        image = Image.open(image_path)
        resized_image = image.resize((int(zoom_size), int(zoom_size)), Image.Resampling.LANCZOS)
        new_img = ImageTk.PhotoImage(resized_image)

        # Update the canvas item with the new image
        canvas.itemconfig(item, image=new_img)
        
        # Keep a reference to the image object
        img_refs.append(new_img)

        # Append the new item and image to the new list
        new_items_list.append((item, new_img, image_path))
    
    # Store references in canvas object to prevent garbage collection
    canvas.img_refs = img_refs
    
    return new_items_list