from enum import Enum

class Feature(Enum):
    RIVER = "River"
    ROAD = "Road"
    VILLAGE = r"HexMapper\assets\village.png"
    CITY = r"HexMapper\assets\akaford.png"
    WALL = r"HexMapper\assets\wall.png"
    BRIDGE = r"HexMapper\assets\bridge.png"
    TOWER = r"HexMapper\assets\tower.png"
    CAVE = r"HexMapper\assets\cave.png"
    MINE = r"HexMapper\assets\mine.png"
    RUINS = r"HexMapper\assets\ruin.png"
    TEMPLE = r"HexMapper\assets\temple.png"
    CAMP = r"HexMapper\assets\camp.png"


class Terrain(Enum):
    FARM = "#98FB98"
    MOUNTAIN = "#829696"
    FOREST = "#00b200"
    LAKE = "#0077ff"
    DESERT = "#ffd232"
    FOG = "#e0e0e0"#"#c0c0c0"
    CITY = "#000000"
    SWAMP = "#2e8b57"
    SNOW = "#ffffff"
    JUNGLE = "#228b22"
    VOLCANO = "#ff4500"
    BEACH = "#f5deb3"
    OCEAN = "#000080"
    GRASSLAND = "#7cfc00"
    HILLS = "#808080"
    TUNDRA = "#708090"
    WASTELAND = "#8b4513"
    MARSH = "#556b2f"
    PLAINS = "#ff7f50"


