class Viewport:
    def __init__(self, screen_size: tuple[int, int]) -> None:
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.scale = 1.0
        self.screen_width, self.screen_height = screen_size
        self.base_width, self.base_height = screen_size
        self.aspect_ratio = screen_size[0] / screen_size[1]

    def update_screen_size(self, new_size: tuple[int, int]) -> None:
        self.screen_width, self.screen_height = new_size
        self.scale *= min(new_size[0] / self.base_width, new_size[1] / self.base_height)
        self.base_width, self.base_height = new_size

    def screen_to_world(self, screen_pos: tuple[float, float]) -> tuple[float, float]:
        x, y = screen_pos
        return ((x - self.offset_x) / self.scale, (y - self.offset_y) / self.scale)

    def world_to_screen(self, world_pos: tuple[float, float]) -> tuple[float, float]:
        x, y = world_pos
        return (x * self.scale + self.offset_x, y * self.scale + self.offset_y)

    def pan(self, rel: tuple[float, float]) -> None:
        self.offset_x += rel[0]
        self.offset_y += rel[1]

    def zoom(self, amount: int, mouse_pos: tuple[float, float]) -> None:
        new_scale = max(0.2, min(5.0, self.scale * (1.1**amount)))
        self.offset_x = mouse_pos[0] - (mouse_pos[0] - self.offset_x) * (
            new_scale / self.scale
        )
        self.offset_y = mouse_pos[1] - (mouse_pos[1] - self.offset_y) * (
            new_scale / self.scale
        )
        self.scale = new_scale
