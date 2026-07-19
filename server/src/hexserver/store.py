import json
import sqlite3
from pathlib import Path
from typing import Any

from hexserver.config import TERRAINS

NEIGHBOURS = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]


class MapStore:
    def __init__(self, db_path: Path, seed_file: Path | None = None) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS hexes ("
            "q INTEGER, r INTEGER, terrain TEXT, icon TEXT, PRIMARY KEY (q, r))"
        )
        self.version = 0
        if seed_file is not None and self.count() == 0 and seed_file.exists():
            self.import_hexmap(json.loads(seed_file.read_text()))

    def count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM hexes").fetchone()
        return int(row[0])

    def snapshot(self) -> dict[str, Any]:
        rows = self.db.execute("SELECT q, r, terrain, icon FROM hexes").fetchall()
        return {
            "version": self.version,
            "hexes": [
                {"q": q, "r": r, "terrain": terrain, "icon": icon}
                for q, r, terrain, icon in rows
            ],
        }

    def set_hex(self, q: int, r: int, terrain: str) -> None:
        if terrain not in TERRAINS:
            raise ValueError(f"unknown terrain {terrain!r}")
        self.db.execute(
            "INSERT INTO hexes (q, r, terrain, icon) VALUES (?, ?, ?, NULL) "
            "ON CONFLICT (q, r) DO UPDATE SET terrain = excluded.terrain",
            (q, r, terrain),
        )
        self.db.commit()
        self.version += 1

    def set_icon(self, q: int, r: int, icon: str | None) -> None:
        cur = self.db.execute(
            "UPDATE hexes SET icon = ? WHERE q = ? AND r = ?", (icon, q, r)
        )
        self.db.commit()
        if cur.rowcount:
            self.version += 1

    def remove_hex(self, q: int, r: int) -> None:
        self.db.execute("DELETE FROM hexes WHERE q = ? AND r = ?", (q, r))
        self.db.commit()
        self.version += 1

    def add_layer(self, terrain: str) -> list[dict[str, Any]]:
        if terrain not in TERRAINS:
            raise ValueError(f"unknown terrain {terrain!r}")
        existing = {
            (q, r) for q, r in self.db.execute("SELECT q, r FROM hexes").fetchall()
        }
        added: list[dict[str, Any]] = []
        for q, r in existing:
            for dq, dr in NEIGHBOURS:
                nq, nr = q + dq, r + dr
                if (nq, nr) not in existing:
                    existing.add((nq, nr))
                    added.append({"q": nq, "r": nr, "terrain": terrain, "icon": None})
        self.db.executemany(
            "INSERT INTO hexes (q, r, terrain, icon) VALUES (?, ?, ?, NULL)",
            [(h["q"], h["r"], h["terrain"]) for h in added],
        )
        self.db.commit()
        self.version += 1
        return added

    def clear_all(self) -> None:
        self.db.execute("DELETE FROM hexes")
        self.db.execute(
            "INSERT INTO hexes (q, r, terrain, icon) VALUES (0, 0, 'FOG', NULL)"
        )
        self.db.commit()
        self.version += 1

    def import_hexmap(self, data: dict[str, Any]) -> None:
        self.db.execute("DELETE FROM hexes")
        self.db.executemany(
            "INSERT OR REPLACE INTO hexes (q, r, terrain, icon) VALUES (?, ?, ?, ?)",
            [
                (h["q"], h["r"], h["terrain"], h.get("icon_name"))
                for h in data.get("hexes", [])
                if h["terrain"] in TERRAINS
            ],
        )
        self.db.commit()
        self.version += 1

    def export_hexmap(self) -> dict[str, Any]:
        rows = self.db.execute("SELECT q, r, terrain, icon FROM hexes").fetchall()
        return {
            "hexes": [
                {"q": q, "r": r, "terrain": terrain, "icon_name": icon}
                for q, r, terrain, icon in rows
            ]
        }
