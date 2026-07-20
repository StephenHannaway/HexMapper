import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from hexserver.config import TERRAINS
from hexserver.pathfind import NEIGHBOURS as NEIGHBOURS  # re-export

FEATURE_KINDS = ("road", "river")


class MapStore:
    def __init__(self, db_path: Path, seed_file: Path | None = None) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS hexes ("
            "q INTEGER, r INTEGER, terrain TEXT, icon TEXT, "
            "note TEXT, note_author TEXT, explored INTEGER DEFAULT 1, "
            "label TEXT, PRIMARY KEY (q, r))"
        )
        cols = {row[1] for row in self.db.execute("PRAGMA table_info(hexes)")}
        if "note" not in cols:
            self.db.execute("ALTER TABLE hexes ADD COLUMN note TEXT")
            self.db.execute("ALTER TABLE hexes ADD COLUMN note_author TEXT")
            self.db.commit()
        if "explored" not in cols:
            self.db.execute("ALTER TABLE hexes ADD COLUMN explored INTEGER DEFAULT 1")
            self.db.commit()
        if "label" not in cols:
            self.db.execute("ALTER TABLE hexes ADD COLUMN label TEXT")
            self.db.commit()
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS ops ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts REAL, player TEXT, op TEXT, detail TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS features ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "kind TEXT, path TEXT, created_by TEXT, ts REAL)"
        )
        self.version = 0
        if seed_file is not None and self.count() == 0 and seed_file.exists():
            self.import_hexmap(json.loads(seed_file.read_text()))

    def count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM hexes").fetchone()
        return int(row[0])

    def snapshot(self) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT q, r, terrain, icon, note, note_author, explored, label FROM hexes"
        ).fetchall()
        return {
            "version": self.version,
            "party": self.party(),
            "fog": self.fog_enabled(),
            "features": self.features(),
            "hexes": [
                {
                    "q": q,
                    "r": r,
                    "terrain": terrain,
                    "icon": icon,
                    "note": note,
                    "note_author": note_author,
                    "explored": explored,
                    "label": label,
                }
                for q, r, terrain, icon, note, note_author, explored, label in rows
            ],
        }

    def set_hex(self, q: int, r: int, terrain: str) -> None:
        if terrain not in TERRAINS:
            raise ValueError(f"unknown terrain {terrain!r}")
        self.db.execute(
            "INSERT INTO hexes (q, r, terrain, icon) VALUES (?, ?, ?, NULL) "
            "ON CONFLICT (q, r) DO UPDATE SET terrain = excluded.terrain, explored = 1",
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

    def set_note(self, q: int, r: int, note: str, author: str) -> dict[str, Any]:
        text = note.strip() or None
        cur = self.db.execute(
            "UPDATE hexes SET note = ?, note_author = ? WHERE q = ? AND r = ?",
            (text, author if text else None, q, r),
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no hex at {q},{r}")
        self.version += 1
        return {"note": text, "note_author": author if text else None}

    def set_label(self, q: int, r: int, label: str) -> str | None:
        text = label.strip() or None
        cur = self.db.execute(
            "UPDATE hexes SET label = ? WHERE q = ? AND r = ?", (text, q, r)
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no hex at {q},{r}")
        self.version += 1
        return text

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
        for q, r in list(existing):
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
        self.db.execute("DELETE FROM features")
        self.db.execute(
            "INSERT INTO hexes (q, r, terrain, icon) VALUES (0, 0, 'FOG', NULL)"
        )
        self.db.commit()
        self.version += 1

    def set_explored(self, q: int, r: int, explored: bool) -> None:
        cur = self.db.execute(
            "UPDATE hexes SET explored = ? WHERE q = ? AND r = ?",
            (1 if explored else 0, q, r),
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no hex at {q},{r}")
        self.version += 1

    def fog_enabled(self) -> bool:
        row = self.db.execute("SELECT value FROM meta WHERE key = 'fog'").fetchone()
        return row is not None and row[0] == "1"

    def set_fog(self, enabled: bool) -> None:
        self.db.execute(
            "INSERT INTO meta (key, value) VALUES ('fog', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            ("1" if enabled else "0",),
        )
        self.db.commit()
        self.version += 1

    def add_feature(
        self, kind: str, path: list[tuple[int, int]], created_by: str
    ) -> dict[str, Any]:
        if kind not in FEATURE_KINDS:
            raise ValueError(f"unknown feature kind {kind!r}")
        cur = self.db.execute(
            "INSERT INTO features (kind, path, created_by, ts) VALUES (?, ?, ?, ?)",
            (kind, json.dumps([[q, r] for q, r in path]), created_by, time.time()),
        )
        self.db.commit()
        self.version += 1
        return {
            "id": cur.lastrowid,
            "kind": kind,
            "path": [[q, r] for q, r in path],
            "created_by": created_by,
        }

    def remove_feature(self, feature_id: int) -> None:
        cur = self.db.execute("DELETE FROM features WHERE id = ?", (feature_id,))
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no feature {feature_id}")
        self.version += 1

    def features(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, kind, path, created_by FROM features ORDER BY id"
        ).fetchall()
        return [
            {"id": i, "kind": k, "path": json.loads(p), "created_by": c}
            for i, k, p, c in rows
        ]

    def features_at(self, q: int, r: int) -> list[int]:
        return [f["id"] for f in self.features() if [q, r] in f["path"]]

    def terrain_map(self) -> dict[tuple[int, int], str]:
        rows = self.db.execute("SELECT q, r, terrain FROM hexes").fetchall()
        return {(q, r): t for q, r, t in rows}

    def party(self) -> dict[str, Any] | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = 'party'").fetchone()
        if row is None:
            return None
        loaded: dict[str, Any] = json.loads(row[0])
        return loaded

    def set_party(self, q: int, r: int) -> None:
        self.db.execute(
            "INSERT INTO meta (key, value) VALUES ('party', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (json.dumps({"q": q, "r": r}),),
        )
        self.db.commit()
        self.version += 1

    def log_op(self, player: str, op: str, detail: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO ops (ts, player, op, detail) VALUES (?, ?, ?, ?)",
            (time.time(), player, op, json.dumps(detail)),
        )
        self.db.execute("DELETE FROM ops WHERE id <= (SELECT MAX(id) FROM ops) - 1000")
        self.db.commit()

    def history(self, limit: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT ts, player, op, detail FROM ops ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"ts": ts, "player": player, "op": op, "detail": json.loads(detail)}
            for ts, player, op, detail in rows
        ]

    def import_hexmap(self, data: dict[str, Any]) -> None:
        self.db.execute("DELETE FROM hexes")
        self.db.executemany(
            "INSERT OR REPLACE INTO hexes "
            "(q, r, terrain, icon, note, note_author, label) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    h["q"],
                    h["r"],
                    h["terrain"],
                    h.get("icon_name"),
                    h.get("note"),
                    h.get("note_author"),
                    h.get("label"),
                )
                for h in data.get("hexes", [])
                if h["terrain"] in TERRAINS
            ],
        )
        self.db.execute("DELETE FROM features")
        for f in data.get("features", []):
            if f.get("kind") in FEATURE_KINDS and isinstance(f.get("path"), list):
                self.db.execute(
                    "INSERT INTO features (kind, path, created_by, ts) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        f["kind"],
                        json.dumps(f["path"]),
                        f.get("created_by"),
                        time.time(),
                    ),
                )
        self.db.commit()
        self.version += 1

    def export_hexmap(self) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT q, r, terrain, icon, note, note_author, label FROM hexes"
        ).fetchall()
        # note/label fields and the features key are extras the desktop app ignores
        return {
            "features": self.features(),
            "hexes": [
                {
                    "q": q,
                    "r": r,
                    "terrain": terrain,
                    "icon_name": icon,
                    "note": note,
                    "note_author": note_author,
                    "label": label,
                }
                for q, r, terrain, icon, note, note_author, label in rows
            ],
        }
