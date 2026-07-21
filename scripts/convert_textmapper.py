"""Convert a Text Mapper (gnomeyland) map into the hexmapper .hexmap format.

Source coords are XXYY (column, row), flat-top hexes, even columns shifted
down (verified against the mountain-chain adjacency in map2.txt). Akaford
(2377) is anchored at q=0,r=0.

Usage: uv run python scripts/convert_textmapper.py map2.txt map2.hexmap
"""

import itertools
import json
import re
import sys
from pathlib import Path

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


def convert(text: str) -> dict[str, object]:
    hexes: dict[tuple[int, int], dict[str, object]] = {}
    features: list[dict[str, object]] = []
    lake_paths: list[list[tuple[int, int]]] = []

    for raw in text.splitlines():
        line = raw.strip().rstrip(".")
        m = re.match(r"^(\d{4}(?:-\d{4})+)\s+(\S+)$", line)
        if m:
            waypoints = [
                to_axial(int(c[:2]), int(c[2:])) for c in m.group(1).split("-")
            ]
            kind = m.group(2)
            if kind == "large-lake":
                lake_paths.append(waypoints)
            elif kind in FEATURE_KINDS:
                path: list[tuple[int, int]] = []
                for a, b in itertools.pairwise(waypoints):
                    for cell in hex_line(a, b):
                        if not path or path[-1] != cell:
                            path.append(cell)
                features.append(
                    {
                        "kind": FEATURE_KINDS[kind],
                        "path": [[q, r] for q, r in path],
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

        q, r = to_axial(col, row)
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

    ordered = [hexes[k] for k in sorted(hexes)]
    return {"features": features, "hexes": ordered}


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    data = convert(src.read_text(encoding="utf-8"))
    dst.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    n_hex = len(data["hexes"])  # type: ignore[arg-type]
    n_feat = len(data["features"])  # type: ignore[arg-type]
    print(f"{n_hex} hexes, {n_feat} features -> {dst}")


if __name__ == "__main__":
    main()
