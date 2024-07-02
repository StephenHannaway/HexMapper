# ui_setup.py
import tkinter as tk
from tkinter import ttk

def create_main_window(width, height, bg_color):
    root = tk.Tk()
    root.title('Hexagon Grid Drawer')
    canvas = tk.Canvas(root, width=width, height=height, bg=bg_color)
    canvas.grid(row=0, column=0, rowspan=8)
    # After creating the canvas, make it focusable
    canvas.configure(takefocus=1)
    # Set focus to the canvas so it can receive keyboard events
    canvas.focus_set()
    return root, canvas

def add_buttons(root, button_configs):
    buttons = {}
    for i, (text, command) in enumerate(button_configs.items()):
        button = ttk.Button(root, text=text, command=command)
        button.grid(row=i, column=1)
        buttons[text] = button
    return buttons