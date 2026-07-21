"""Convert a Text Mapper (gnomeyland) map into the hexmapper .hexmap format.

Source coords are XXYY (column, row), flat-top hexes, even columns shifted
down (verified against the mountain-chain adjacency in map2.txt). Akaford
(2377) is anchored at q=0,r=0.

By default a cleanup pass also runs: disconnected border scaffolding is
dropped, the canal starburst becomes one river plus settlement roads with a
Bridge at the crossing, and the canvas edge gets a terrain transition ring.
Pass --raw for the faithful conversion.

Usage: uv run python scripts/convert_textmapper.py map2.txt map2.hexmap [--raw]
"""

import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any

ANCHOR_COL, ANCHOR_ROW = 23, 77

BACKGROUNDS = {
    "ocean": "OCEAN",
    "water": "LAKE",
    "sand": "BEACH",
    "soil": "FARM",
    "green": "GRASSLAND",
    "light-green": "GRASSLAND",
    "dark-green": "FOREST",
    "light-grey": "HILLS",
    "rock": "MOUNTAIN",
    "empty": "FOG",
}
OVERLAY_TERRAINS = {
    "forest": "FOREST",
    "forest-mountains": "MOUNTAIN",
    "forest-hill": "HILLS",
    "mountain": "MOUNTAIN",
    "mountains": "MOUNTAIN",
    "fields": "FARM",
    "city": "CITY",
    "large-lake": "LAKE",
}
ICONS = {
    "village": "Village",
    "tower": "Tower",
    "shrine": "Temple",
    "chaos": "Cave",
    "city": "Akaford",
}
FEATURE_KINDS = {
    "canal": "river",
    "river": "river",
    "trail": "road",
    "trailn": "road",
}

NEIGHBOURS = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]

# --- cleanup pass (map2-specific) -------------------------------------------
# The source map sketched distant borders as disconnected scaffolding: two
# full-height ocean columns (01/66), a lone ocean hex, and a tail of blank
# hexes that only existed to carry one canal. The canal starburst from Akaford
# is replaced with one through-flowing river plus roads between settlements.

CANVAS = range(13, 34), range(67, 88)  # cols, rows of the blank working canvas

CLEAN_FEATURES = [
    ("river", "2381-2377-2374-2372-1867"),
    ("river", "2775-2774-2873-2872"),
    ("road", "2377-2476-2475-2576-2675-2775-2774"),
    ("road", "2377-2476-2475-2576-2676-2677-2778-2878"),
    ("road", "2774-2672"),
    ("road", "2774-2874"),
    ("road", "2377-2077-1884"),
]

TRANSITIONS = {
    "MOUNTAIN": "HILLS",
    "CITY": "GRASSLAND",
    "LAKE": "GRASSLAND",
    "FARM": "GRASSLAND",
}


def drop_in_cleanup(col: int, row: int, terrain: str) -> bool:
    if col <= 2 or col >= 66:  # ocean border columns + their shore hexes
        return True
    if (col, row) == (5, 55):  # lone stray ocean hex
        return True
    return terrain == "FOG" and row >= 88  # canal-carrier tail off the canvas


def to_axial(col: int, row: int) -> tuple[int, int]:
    q = col - ANCHOR_COL
    r = row - ANCHOR_ROW - (q // 2)
    return q, r


def hex_line(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    n = max(
        abs(a[0] - b[0]),
        abs(a[1] - b[1]),
        abs(a[0] + a[1] - b[0] - b[1]),
    )
    if n == 0:
        return [a]
    out: list[tuple[int, int]] = []
    for i in range(n + 1):
        t = i / n
        q = a[0] + (b[0] - a[0]) * t
        r = a[1] + (b[1] - a[1]) * t
        s = -q - r
        qr, rr, sr = round(q), round(r), round(s)
        dq, dr, ds = abs(qr - q), abs(rr - r), abs(sr - s)
        if dq > dr and dq > ds:
            qr = -rr - sr
        elif dr > ds:
            rr = -qr - sr
        out.append((int(qr), int(rr)))
    return out


def expand_path(waypoints: list[tuple[int, int]]) -> list[tuple[int, int]]:
    path: list[tuple[int, int]] = []
    for a, b in itertools.pairwise(waypoints):
        for cell in hex_line(a, b):
            if not path or path[-1] != cell:
                path.append(cell)
    return path


def parse_waypoints(spec: str) -> list[tuple[int, int]]:
    return [to_axial(int(c[:2]), int(c[2:])) for c in spec.split("-")]


def convert(text: str, cleanup: bool = True) -> dict[str, Any]:
    hexes: dict[tuple[int, int], dict[str, Any]] = {}
    features: list[dict[str, Any]] = []
    lake_paths: list[list[tuple[int, int]]] = []
    canvas_fog: set[tuple[int, int]] = set()

    for raw in text.splitlines():
        line = raw.strip().rstrip(".")
        m = re.match(r"^(\d{4}(?:-\d{4})+)\s+(\S+)$", line)
        if m:
            kind = m.group(2)
            if kind == "large-lake":
                lake_paths.append(parse_waypoints(m.group(1)))
            elif kind in FEATURE_KINDS and not cleanup:
                features.append(
                    {
                        "kind": FEATURE_KINDS[kind],
                        "path": [
                            [q, r] for q, r in expand_path(parse_waypoints(m.group(1)))
                        ],
                        "created_by": "import",
                    }
                )
            continue

        m = re.match(r"^(\d{4})\s+(.*)$", line)
        if not m:
            continue
        col, row = int(m.group(1)[:2]), int(m.group(1)[2:])
        rest = m.group(2)
        label_m = re.search(r'"([^"]*)"', rest)
        label = label_m.group(1) if label_m else None
        words = re.sub(r'"[^"]*"', "", rest).split()

        terrain = "FOG"
        for w in words:
            if w in BACKGROUNDS:
                terrain = BACKGROUNDS[w]
        for w in words:
            if w in OVERLAY_TERRAINS:
                terrain = OVERLAY_TERRAINS[w]
        icon = None
        for w in words:
            if w in ICONS:
                icon = ICONS[w]

        if cleanup and drop_in_cleanup(col, row, terrain):
            continue
        q, r = to_axial(col, row)
        if terrain == "FOG" and col in CANVAS[0] and row in CANVAS[1]:
            canvas_fog.add((q, r))
        hexes[(q, r)] = {
            "q": q,
            "r": r,
            "terrain": terrain,
            "icon_name": icon,
            "label": label,
        }

    # large-lake polygons: paint the outline hexes, then any hex fully
    # surrounded by lake becomes lake too
    lake = {cell for path in lake_paths for cell in path}
    for q, r in list(hexes):
        if (q, r) not in lake and all(
            (q + dq, r + dr) in lake for dq, dr in NEIGHBOURS
        ):
            lake.add((q, r))
    for q, r in lake:
        entry = hexes.setdefault(
            (q, r),
            {"q": q, "r": r, "terrain": "LAKE", "icon_name": None, "label": None},
        )
        entry["terrain"] = "LAKE"

    # citywalls ellipses around Akaford: nearest approximation is a ring of
    # Wall icons on the six neighbouring hexes
    if (0, 0) in hexes and hexes[(0, 0)]["icon_name"] == "Akaford":
        for dq, dr in NEIGHBOURS:
            ring = hexes.get((dq, dr))
            if ring is not None and ring["icon_name"] is None:
                ring["icon_name"] = "Wall"

    if cleanup:
        for kind, spec in CLEAN_FEATURES:
            features.append(
                {
                    "kind": kind,
                    "path": [[q, r] for q, r in expand_path(parse_waypoints(spec))],
                    "created_by": "import",
                }
            )

        # soften the settled blob's edge: canvas hexes bordering painted
        # terrain pick up their most common neighbour, downgraded a step
        snapshot = {k: str(h["terrain"]) for k, h in hexes.items()}
        for q, r in canvas_fog:
            near = [
                snapshot[(q + dq, r + dr)]
                for dq, dr in NEIGHBOURS
                if snapshot.get((q + dq, r + dr), "FOG") != "FOG"
            ]
            if near:
                pick = max(sorted(set(near)), key=near.count)
                hexes[(q, r)]["terrain"] = TRANSITIONS.get(pick, pick)

        river_cells = {
            (p[0], p[1]) for f in features if f["kind"] == "river" for p in f["path"]
        }
        for f in features:
            if f["kind"] != "road":
                continue
            for p in f["path"]:
                crossing = hexes.get((p[0], p[1]))
                if (
                    crossing is not None
                    and (p[0], p[1]) in river_cells
                    and crossing["terrain"] != "CITY"
                    and crossing["icon_name"] is None
                ):
                    crossing["icon_name"] = "Bridge"

    ordered = [hexes[k] for k in sorted(hexes)]
    return {"features": features, "hexes": ordered}


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--raw"]
    src, dst = Path(args[0]), Path(args[1])
    data = convert(src.read_text(encoding="utf-8"), cleanup="--raw" not in sys.argv)
    dst.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    n_hex = len(data["hexes"])
    n_feat = len(data["features"])
    print(f"{n_hex} hexes, {n_feat} features -> {dst}")


if __name__ == "__main__":
    main()
