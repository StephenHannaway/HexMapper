from HexMapper.constants.mapperConstants import Terrain, Feature 
from HexMapper.Utils.drawer import draw_hexagon

class Hexagon:

    def __init__(self, q, r, hex_size=30, terrain=Terrain.FOG, feature=None, canvas=None):
        self.q = q
        self.r = r
        self.hex_size = hex_size
        self.terrain = terrain
        self.feature = feature
        self.canvas = canvas
        self.canvas_id = None
        if self.canvas:
            self.canvas_id = draw_hexagon(self.canvas, (self.q, self.r), self.hex_size, self.terrain.value)
        
        
