TERRAINS: dict[str, str] = {
    "FARM": "#98FB98",
    "MOUNTAIN": "#829696",
    "FOREST": "#00b200",
    "LAKE": "#0077ff",
    "DESERT": "#ffd232",
    "FOG": "#e0e0e0",
    "CITY": "#000000",
    "SWAMP": "#2e8b57",
    "SNOW": "#ffffff",
    "JUNGLE": "#228b22",
    "VOLCANO": "#ff4500",
    "BEACH": "#f5deb3",
    "OCEAN": "#000080",
    "GRASSLAND": "#7cfc00",
    "HILLS": "#808080",
    "TUNDRA": "#708090",
    "WASTELAND": "#8b4513",
    "MARSH": "#556b2f",
    "PLAINS": "#ff7f50",
}

# Feature routing costs: cost to enter a hex of this terrain.
# Roads like flat charted land; rivers like wet lowland and merge toward water.
ROAD_COSTS: dict[str, float] = {
    "CITY": 0.5,
    "GRASSLAND": 1,
    "PLAINS": 1,
    "FARM": 1,
    "BEACH": 1.2,
    "FOG": 1.5,
    "FOREST": 1.5,
    "TUNDRA": 1.5,
    "WASTELAND": 1.5,
    "HILLS": 2,
    "DESERT": 2,
    "SNOW": 2,
    "JUNGLE": 3,
    "MOUNTAIN": 3,
    "SWAMP": 4,
    "MARSH": 4,
    "VOLCANO": 6,
    "LAKE": 20,  # bridges/ferries: possible, discouraged
    "OCEAN": 30,
}
ROAD_DEFAULT = 8.0  # unpainted hex — roads prefer charted land

RIVER_COSTS: dict[str, float] = {
    "LAKE": 0.2,
    "OCEAN": 0.2,
    "SWAMP": 0.5,
    "MARSH": 0.5,
    "BEACH": 0.8,
    "GRASSLAND": 1,
    "FARM": 1,
    "PLAINS": 1,
    "FOG": 1,
    "FOREST": 1.2,
    "JUNGLE": 1.2,
    "CITY": 1.5,
    "SNOW": 2,
    "TUNDRA": 2,
    "HILLS": 2.5,
    "MOUNTAIN": 3.5,
    "WASTELAND": 4,
    "DESERT": 5,
    "VOLCANO": 8,
}
RIVER_DEFAULT = 3.0

REUSE_DISCOUNT = 0.25  # entering a hex already carrying the same feature kind

ICONS: dict[str, str] = {
    "Akaford": "akaford.png",
    "Animal Skull": "animal-skull.png",
    "Bridge": "bridge.png",
    "Camp": "camp.png",
    "Cave": "cave.png",
    "Holy Oak": "holy-oak.png",
    "Mine": "mine.png",
    "Pillar": "pillar.png",
    "Pyramid": "pyramid.png",
    "Ruin": "ruin.png",
    "Swords Emblem": "swords-emblem.png",
    "Temple": "temple.png",
    "Tower": "tower.png",
    "Village": "village.png",
    "Wall": "wall.png",
}
