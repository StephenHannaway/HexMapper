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
        if "edited_by" not in cols:
            self.db.execute("ALTER TABLE hexes ADD COLUMN edited_by TEXT")
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
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS undo ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts REAL, player TEXT, label TEXT, inverse TEXT)"
        )
        self.version = 0
        if seed_file is not None and self.count() == 0 and seed_file.exists():
            self.import_hexmap(json.loads(seed_file.read_text()))

    def count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM hexes").fetchone()
        return int(row[0])

    _HEX_COLS = "q, r, terrain, icon, note, note_author, explored, label, edited_by"

    def _hex_row(self, q: int, r: int) -> dict[str, Any] | None:
        row = self.db.execute(
            f"SELECT {self._HEX_COLS} FROM hexes WHERE q = ? AND r = ?", (q, r)
        ).fetchone()
        if row is None:
            return None
        keys = [c.strip() for c in self._HEX_COLS.split(",")]
        return dict(zip(keys, row, strict=True))

    def _restore_hex(self, row: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO hexes "
            "(q, r, terrain, icon, note, note_author, explored, label, edited_by) "
            "VALUES (:q, :r, :terrain, :icon, :note, :note_author, :explored, "
            ":label, :edited_by)",
            row,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "party": self.party(),
            "fog": self.fog_enabled(),
            "features": self.features(),
            "can_undo": self.can_undo(),
            "hexes": self._all_hex_rows(),
        }

    def set_hex(self, q: int, r: int, terrain: str, author: str = "someone") -> None:
        if terrain not in TERRAINS:
            raise ValueError(f"unknown terrain {terrain!r}")
        prior = self._hex_row(q, r)
        self.db.execute(
            "INSERT INTO hexes (q, r, terrain, icon, edited_by) "
            "VALUES (?, ?, ?, NULL, ?) "
            "ON CONFLICT (q, r) DO UPDATE SET terrain = excluded.terrain, "
            "explored = 1, edited_by = excluded.edited_by",
            (q, r, terrain, author),
        )
        self.db.commit()
        self._push_undo(
            author,
            f"paint {q},{r}",
            {"kind": "hex_row", "row": prior}
            if prior
            else {"kind": "del_hex", "q": q, "r": r},
        )
        self.version += 1

    def set_icon(
        self, q: int, r: int, icon: str | None, author: str = "someone"
    ) -> None:
        prior = self._hex_row(q, r)
        cur = self.db.execute(
            "UPDATE hexes SET icon = ?, edited_by = ? WHERE q = ? AND r = ?",
            (icon, author, q, r),
        )
        self.db.commit()
        if cur.rowcount:
            self._push_undo(
                author,
                f"icon {q},{r}",
                {
                    "kind": "set_icon",
                    "q": q,
                    "r": r,
                    "icon": prior["icon"] if prior else None,
                    "edited_by": prior["edited_by"] if prior else None,
                },
            )
            self.version += 1

    def set_note(self, q: int, r: int, note: str, author: str) -> dict[str, Any]:
        text = note.strip() or None
        prior = self._hex_row(q, r)
        cur = self.db.execute(
            "UPDATE hexes SET note = ?, note_author = ?, edited_by = ? "
            "WHERE q = ? AND r = ?",
            (text, author if text else None, author, q, r),
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no hex at {q},{r}")
        if prior is not None:
            self._push_undo(
                author,
                f"note {q},{r}",
                {
                    "kind": "set_note",
                    "q": q,
                    "r": r,
                    "note": prior["note"],
                    "note_author": prior["note_author"],
                    "edited_by": prior["edited_by"],
                },
            )
        self.version += 1
        return {"note": text, "note_author": author if text else None}

    def set_label(
        self, q: int, r: int, label: str, author: str = "someone"
    ) -> str | None:
        text = label.strip() or None
        prior = self._hex_row(q, r)
        cur = self.db.execute(
            "UPDATE hexes SET label = ?, edited_by = ? WHERE q = ? AND r = ?",
            (text, author, q, r),
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no hex at {q},{r}")
        if prior is not None:
            self._push_undo(
                author,
                f"label {q},{r}",
                {
                    "kind": "set_label",
                    "q": q,
                    "r": r,
                    "label": prior["label"],
                    "edited_by": prior["edited_by"],
                },
            )
        self.version += 1
        return text

    def remove_hex(self, q: int, r: int, author: str = "someone") -> None:
        prior = self._hex_row(q, r)
        self.db.execute("DELETE FROM hexes WHERE q = ? AND r = ?", (q, r))
        self.db.commit()
        if prior is not None:
            self._push_undo(
                author, f"remove {q},{r}", {"kind": "hex_row", "row": prior}
            )
        self.version += 1

    def add_layer(self, terrain: str, author: str = "someone") -> list[dict[str, Any]]:
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
        self._push_undo(
            author,
            "add ring",
            {"kind": "del_hexes", "coords": [[h["q"], h["r"]] for h in added]},
        )
        self.version += 1
        return added

    def clear_all(self, author: str = "someone") -> None:
        before = {"hexes": self._all_hex_rows(), "features": self.features()}
        self.db.execute("DELETE FROM hexes")
        self.db.execute("DELETE FROM features")
        self.db.execute(
            "INSERT INTO hexes (q, r, terrain, icon) VALUES (0, 0, 'FOG', NULL)"
        )
        self.db.commit()
        self._push_undo(author, "clear map", {"kind": "restore_all", "data": before})
        self.version += 1

    def _all_hex_rows(self) -> list[dict[str, Any]]:
        rows = self.db.execute(f"SELECT {self._HEX_COLS} FROM hexes").fetchall()
        keys = [c.strip() for c in self._HEX_COLS.split(",")]
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def set_explored(
        self, q: int, r: int, explored: bool, author: str = "someone"
    ) -> None:
        prior = self._hex_row(q, r)
        cur = self.db.execute(
            "UPDATE hexes SET explored = ? WHERE q = ? AND r = ?",
            (1 if explored else 0, q, r),
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no hex at {q},{r}")
        if prior is not None:
            self._push_undo(
                author,
                f"reveal {q},{r}",
                {"kind": "set_explored", "q": q, "r": r, "explored": prior["explored"]},
            )
        self.version += 1

    def fog_enabled(self) -> bool:
        row = self.db.execute("SELECT value FROM meta WHERE key = 'fog'").fetchone()
        return row is not None and row[0] == "1"

    def set_fog(self, enabled: bool, author: str = "someone") -> None:
        prior = self.fog_enabled()
        self.db.execute(
            "INSERT INTO meta (key, value) VALUES ('fog', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            ("1" if enabled else "0",),
        )
        self.db.commit()
        self._push_undo(author, "toggle fog", {"kind": "set_fog", "enabled": prior})
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
        self._push_undo(
            created_by, f"build {kind}", {"kind": "del_feature", "id": cur.lastrowid}
        )
        self.version += 1
        return {
            "id": cur.lastrowid,
            "kind": kind,
            "path": [[q, r] for q, r in path],
            "created_by": created_by,
        }

    def remove_feature(self, feature_id: int, author: str = "someone") -> None:
        row = self.db.execute(
            "SELECT kind, path, created_by FROM features WHERE id = ?", (feature_id,)
        ).fetchone()
        cur = self.db.execute("DELETE FROM features WHERE id = ?", (feature_id,))
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no feature {feature_id}")
        self._push_undo(
            author,
            "remove path",
            {
                "kind": "add_feature",
                "feature_kind": row[0],
                "path": json.loads(row[1]),
                "created_by": row[2],
            },
        )
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

    def set_party(self, q: int, r: int, author: str = "someone") -> None:
        prior = self.party()
        self.db.execute(
            "INSERT INTO meta (key, value) VALUES ('party', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (json.dumps({"q": q, "r": r}),),
        )
        self.db.commit()
        self._push_undo(author, "move party", {"kind": "set_party", "party": prior})
        self.version += 1

    # --- undo (DM-only, single global stack, capped) ---

    def _push_undo(self, player: str, label: str, inverse: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO undo (ts, player, label, inverse) VALUES (?, ?, ?, ?)",
            (time.time(), player, label, json.dumps(inverse)),
        )
        self.db.execute("DELETE FROM undo WHERE id <= (SELECT MAX(id) FROM undo) - 100")
        self.db.commit()

    def can_undo(self) -> bool:
        return self.db.execute("SELECT 1 FROM undo LIMIT 1").fetchone() is not None

    def undo(self) -> str | None:
        row = self.db.execute(
            "SELECT id, label, inverse FROM undo ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        undo_id, label, inverse = row
        self.db.execute("DELETE FROM undo WHERE id = ?", (undo_id,))
        self._apply_inverse(json.loads(inverse))
        self.db.commit()
        self.version += 1
        return str(label)

    def _apply_inverse(self, inv: dict[str, Any]) -> None:
        kind = inv["kind"]
        if kind == "del_hex":
            self.db.execute(
                "DELETE FROM hexes WHERE q = ? AND r = ?", (inv["q"], inv["r"])
            )
        elif kind == "hex_row":
            self._restore_hex(inv["row"])
        elif kind == "set_icon":
            self.db.execute(
                "UPDATE hexes SET icon = ?, edited_by = ? WHERE q = ? AND r = ?",
                (inv["icon"], inv["edited_by"], inv["q"], inv["r"]),
            )
        elif kind == "set_note":
            self.db.execute(
                "UPDATE hexes SET note = ?, note_author = ?, edited_by = ? "
                "WHERE q = ? AND r = ?",
                (inv["note"], inv["note_author"], inv["edited_by"], inv["q"], inv["r"]),
            )
        elif kind == "set_label":
            self.db.execute(
                "UPDATE hexes SET label = ?, edited_by = ? WHERE q = ? AND r = ?",
                (inv["label"], inv["edited_by"], inv["q"], inv["r"]),
            )
        elif kind == "set_explored":
            self.db.execute(
                "UPDATE hexes SET explored = ? WHERE q = ? AND r = ?",
                (inv["explored"], inv["q"], inv["r"]),
            )
        elif kind == "set_party":
            if inv["party"] is None:
                self.db.execute("DELETE FROM meta WHERE key = 'party'")
            else:
                self.db.execute(
                    "INSERT INTO meta (key, value) VALUES ('party', ?) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                    (json.dumps(inv["party"]),),
                )
        elif kind == "set_fog":
            self.db.execute(
                "INSERT INTO meta (key, value) VALUES ('fog', ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                ("1" if inv["enabled"] else "0",),
            )
        elif kind == "del_feature":
            self.db.execute("DELETE FROM features WHERE id = ?", (inv["id"],))
        elif kind == "add_feature":
            self.db.execute(
                "INSERT INTO features (kind, path, created_by, ts) VALUES (?, ?, ?, ?)",
                (
                    inv["feature_kind"],
                    json.dumps(inv["path"]),
                    inv["created_by"],
                    time.time(),
                ),
            )
        elif kind == "del_hexes":
            self.db.executemany(
                "DELETE FROM hexes WHERE q = ? AND r = ?",
                [(q, r) for q, r in inv["coords"]],
            )
        elif kind == "restore_all":
            self.db.execute("DELETE FROM hexes")
            self.db.execute("DELETE FROM features")
            for row_ in inv["data"]["hexes"]:
                self._restore_hex(row_)
            for f in inv["data"]["features"]:
                self.db.execute(
                    "INSERT INTO features (kind, path, created_by, ts) "
                    "VALUES (?, ?, ?, ?)",
                    (f["kind"], json.dumps(f["path"]), f["created_by"], time.time()),
                )

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
        self.db.execute("DELETE FROM undo")  # prior undo history no longer applies
        self.db.executemany(
            "INSERT OR REPLACE INTO hexes "
            "(q, r, terrain, icon, note, note_author, label, edited_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    h["q"],
                    h["r"],
                    h["terrain"],
                    h.get("icon_name"),
                    h.get("note"),
                    h.get("note_author"),
                    h.get("label"),
                    h.get("edited_by"),
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
            "SELECT q, r, terrain, icon, note, note_author, label, edited_by FROM hexes"
        ).fetchall()
        # note/label/edited_by and the features key are extras the desktop ignores
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
                    "edited_by": edited_by,
                }
                for q, r, terrain, icon, note, note_author, label, edited_by in rows
            ],
        }
