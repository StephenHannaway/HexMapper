import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from hexserver.config import TERRAINS
from hexserver.pathfind import NEIGHBOURS as NEIGHBOURS  # re-export

FEATURE_KINDS = ("road", "river")
DEFAULT_MAP_ID = 1
DEFAULT_MAP_NAME = "World Map"


class MapStore:
    """SQLite-backed store for one or more hex maps.

    Every map is identified by ``map_id``; rows in ``hexes``/``features``/
    ``meta``/``ops``/``undo`` carry a ``map_id`` column. A version counter is
    kept per map (in memory) so clients only resync when *their* map changes.
    """

    def __init__(self, db_path: Path, seed_file: Path | None = None) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._migrate()
        self.versions: dict[int, int] = defaultdict(int)
        if (
            seed_file is not None
            and self.count(DEFAULT_MAP_ID) == 0
            and seed_file.exists()
        ):
            self.import_hexmap(json.loads(seed_file.read_text()), DEFAULT_MAP_ID)

    # --- schema / migration -------------------------------------------------

    def _migrate(self) -> None:
        db = self.db
        db.execute(
            "CREATE TABLE IF NOT EXISTS maps ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, ts REAL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS hexes ("
            "q INTEGER, r INTEGER, terrain TEXT, icon TEXT, "
            "note TEXT, note_author TEXT, explored INTEGER DEFAULT 1, "
            "label TEXT, PRIMARY KEY (q, r))"
        )
        hex_cols = {row[1] for row in db.execute("PRAGMA table_info(hexes)")}
        # additive single-map columns (pre-multimap migrations)
        for col, ddl in (
            ("note", "note TEXT"),
            ("note_author", "note_author TEXT"),
            ("explored", "explored INTEGER DEFAULT 1"),
            ("label", "label TEXT"),
            ("edited_by", "edited_by TEXT"),
        ):
            if col not in hex_cols:
                db.execute(f"ALTER TABLE hexes ADD COLUMN {ddl}")
        db.commit()
        db.execute(
            "CREATE TABLE IF NOT EXISTS ops ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts REAL, player TEXT, op TEXT, detail TEXT)"
        )
        db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS features ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "kind TEXT, path TEXT, created_by TEXT, ts REAL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS undo ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts REAL, player TEXT, label TEXT, inverse TEXT)"
        )
        db.commit()

        # multi-map migration: rebuild hexes/meta to carry map_id, add it to
        # features/ops/undo, and materialise the default map. Existing rows all
        # belong to the default map (id 1).
        hex_cols = {row[1] for row in db.execute("PRAGMA table_info(hexes)")}
        if "map_id" not in hex_cols:
            db.execute(
                "CREATE TABLE hexes_new ("
                "map_id INTEGER DEFAULT 1, q INTEGER, r INTEGER, terrain TEXT, "
                "icon TEXT, note TEXT, note_author TEXT, explored INTEGER DEFAULT 1, "
                "label TEXT, edited_by TEXT, PRIMARY KEY (map_id, q, r))"
            )
            db.execute(
                "INSERT INTO hexes_new "
                "(map_id, q, r, terrain, icon, note, note_author, explored, "
                " label, edited_by) "
                "SELECT 1, q, r, terrain, icon, note, note_author, explored, "
                "label, edited_by FROM hexes"
            )
            db.execute("DROP TABLE hexes")
            db.execute("ALTER TABLE hexes_new RENAME TO hexes")
            db.commit()

        meta_cols = {row[1] for row in db.execute("PRAGMA table_info(meta)")}
        if "map_id" not in meta_cols:
            db.execute(
                "CREATE TABLE meta_new ("
                "map_id INTEGER DEFAULT 1, key TEXT, value TEXT, "
                "PRIMARY KEY (map_id, key))"
            )
            db.execute(
                "INSERT INTO meta_new (map_id, key, value) "
                "SELECT 1, key, value FROM meta"
            )
            db.execute("DROP TABLE meta")
            db.execute("ALTER TABLE meta_new RENAME TO meta")
            db.commit()

        for table in ("features", "ops", "undo"):
            cols = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            if "map_id" not in cols:
                db.execute(f"ALTER TABLE {table} ADD COLUMN map_id INTEGER DEFAULT 1")
        db.commit()

        # ensure a default map exists; adopt any pre-existing data under it
        if db.execute("SELECT 1 FROM maps WHERE id = 1").fetchone() is None:
            db.execute(
                "INSERT INTO maps (id, name, ts) VALUES (?, ?, ?)",
                (DEFAULT_MAP_ID, DEFAULT_MAP_NAME, time.time()),
            )
            db.commit()

    # --- maps ---------------------------------------------------------------

    def maps(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT id, name FROM maps ORDER BY id").fetchall()
        return [{"id": i, "name": n} for i, n in rows]

    def map_exists(self, map_id: int) -> bool:
        return (
            self.db.execute("SELECT 1 FROM maps WHERE id = ?", (map_id,)).fetchone()
            is not None
        )

    def create_map(self, name: str) -> dict[str, Any]:
        text = name.strip()[:60] or "New Map"
        cur = self.db.execute(
            "INSERT INTO maps (name, ts) VALUES (?, ?)", (text, time.time())
        )
        map_id = int(cur.lastrowid or 0)
        # start with a single blank hex so the map is centrable and paintable
        self.db.execute(
            "INSERT INTO hexes (map_id, q, r, terrain, icon) "
            "VALUES (?, 0, 0, 'FOG', NULL)",
            (map_id,),
        )
        self.db.commit()
        return {"id": map_id, "name": text}

    def rename_map(self, map_id: int, name: str) -> str:
        text = name.strip()[:60] or "Map"
        self.db.execute("UPDATE maps SET name = ? WHERE id = ?", (text, map_id))
        self.db.commit()
        return text

    def delete_map(self, map_id: int) -> None:
        if map_id == DEFAULT_MAP_ID:
            raise ValueError("cannot delete the default map")
        if self.db.execute("SELECT COUNT(*) FROM maps").fetchone()[0] <= 1:
            raise ValueError("cannot delete the only map")
        for table in ("hexes", "features", "meta", "ops", "undo"):
            self.db.execute(f"DELETE FROM {table} WHERE map_id = ?", (map_id,))
        self.db.execute("DELETE FROM maps WHERE id = ?", (map_id,))
        self.db.commit()
        self.versions.pop(map_id, None)

    # --- versions -----------------------------------------------------------

    def version_of(self, map_id: int) -> int:
        return self.versions[map_id]

    def _bump(self, map_id: int) -> None:
        self.versions[map_id] += 1

    # --- helpers ------------------------------------------------------------

    def count(self, map_id: int = DEFAULT_MAP_ID) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) FROM hexes WHERE map_id = ?", (map_id,)
        ).fetchone()
        return int(row[0])

    _HEX_COLS = "q, r, terrain, icon, note, note_author, explored, label, edited_by"

    def _hex_row(self, map_id: int, q: int, r: int) -> dict[str, Any] | None:
        row = self.db.execute(
            f"SELECT {self._HEX_COLS} FROM hexes WHERE map_id = ? AND q = ? AND r = ?",
            (map_id, q, r),
        ).fetchone()
        if row is None:
            return None
        keys = [c.strip() for c in self._HEX_COLS.split(",")]
        return dict(zip(keys, row, strict=True))

    def _restore_hex(self, map_id: int, row: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO hexes "
            "(map_id, q, r, terrain, icon, note, note_author, explored, label, "
            "edited_by) VALUES (:map_id, :q, :r, :terrain, :icon, :note, "
            ":note_author, :explored, :label, :edited_by)",
            {**row, "map_id": map_id},
        )

    def _all_hex_rows(self, map_id: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            f"SELECT {self._HEX_COLS} FROM hexes WHERE map_id = ?", (map_id,)
        ).fetchall()
        keys = [c.strip() for c in self._HEX_COLS.split(",")]
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def snapshot(self, map_id: int = DEFAULT_MAP_ID) -> dict[str, Any]:
        return {
            "map_id": map_id,
            "maps": self.maps(),
            "version": self.version_of(map_id),
            "party": self.party(map_id),
            "fog": self.fog_enabled(map_id),
            "features": self.features(map_id),
            "can_undo": self.can_undo(map_id),
            "hexes": self._all_hex_rows(map_id),
        }

    # --- hex ops ------------------------------------------------------------

    def set_hex(
        self,
        q: int,
        r: int,
        terrain: str,
        author: str = "someone",
        map_id: int = DEFAULT_MAP_ID,
    ) -> None:
        if terrain not in TERRAINS:
            raise ValueError(f"unknown terrain {terrain!r}")
        prior = self._hex_row(map_id, q, r)
        self.db.execute(
            "INSERT INTO hexes (map_id, q, r, terrain, icon, edited_by) "
            "VALUES (?, ?, ?, ?, NULL, ?) "
            "ON CONFLICT (map_id, q, r) DO UPDATE SET terrain = excluded.terrain, "
            "explored = 1, edited_by = excluded.edited_by",
            (map_id, q, r, terrain, author),
        )
        self.db.commit()
        self._push_undo(
            map_id,
            author,
            f"paint {q},{r}",
            {"kind": "hex_row", "row": prior}
            if prior
            else {"kind": "del_hex", "q": q, "r": r},
        )
        self._bump(map_id)

    def set_icon(
        self,
        q: int,
        r: int,
        icon: str | None,
        author: str = "someone",
        map_id: int = DEFAULT_MAP_ID,
    ) -> None:
        prior = self._hex_row(map_id, q, r)
        cur = self.db.execute(
            "UPDATE hexes SET icon = ?, edited_by = ? "
            "WHERE map_id = ? AND q = ? AND r = ?",
            (icon, author, map_id, q, r),
        )
        self.db.commit()
        if cur.rowcount:
            self._push_undo(
                map_id,
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
            self._bump(map_id)

    def set_note(
        self, q: int, r: int, note: str, author: str, map_id: int = DEFAULT_MAP_ID
    ) -> dict[str, Any]:
        text = note.strip() or None
        prior = self._hex_row(map_id, q, r)
        cur = self.db.execute(
            "UPDATE hexes SET note = ?, note_author = ?, edited_by = ? "
            "WHERE map_id = ? AND q = ? AND r = ?",
            (text, author if text else None, author, map_id, q, r),
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no hex at {q},{r}")
        if prior is not None:
            self._push_undo(
                map_id,
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
        self._bump(map_id)
        return {"note": text, "note_author": author if text else None}

    def set_label(
        self,
        q: int,
        r: int,
        label: str,
        author: str = "someone",
        map_id: int = DEFAULT_MAP_ID,
    ) -> str | None:
        text = label.strip() or None
        prior = self._hex_row(map_id, q, r)
        cur = self.db.execute(
            "UPDATE hexes SET label = ?, edited_by = ? "
            "WHERE map_id = ? AND q = ? AND r = ?",
            (text, author, map_id, q, r),
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no hex at {q},{r}")
        if prior is not None:
            self._push_undo(
                map_id,
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
        self._bump(map_id)
        return text

    def remove_hex(
        self, q: int, r: int, author: str = "someone", map_id: int = DEFAULT_MAP_ID
    ) -> None:
        prior = self._hex_row(map_id, q, r)
        self.db.execute(
            "DELETE FROM hexes WHERE map_id = ? AND q = ? AND r = ?", (map_id, q, r)
        )
        self.db.commit()
        if prior is not None:
            self._push_undo(
                map_id, author, f"remove {q},{r}", {"kind": "hex_row", "row": prior}
            )
        self._bump(map_id)

    def add_layer(
        self, terrain: str, author: str = "someone", map_id: int = DEFAULT_MAP_ID
    ) -> list[dict[str, Any]]:
        if terrain not in TERRAINS:
            raise ValueError(f"unknown terrain {terrain!r}")
        existing = {
            (q, r)
            for q, r in self.db.execute(
                "SELECT q, r FROM hexes WHERE map_id = ?", (map_id,)
            ).fetchall()
        }
        added: list[dict[str, Any]] = []
        for q, r in list(existing):
            for dq, dr in NEIGHBOURS:
                nq, nr = q + dq, r + dr
                if (nq, nr) not in existing:
                    existing.add((nq, nr))
                    added.append({"q": nq, "r": nr, "terrain": terrain, "icon": None})
        self.db.executemany(
            "INSERT INTO hexes (map_id, q, r, terrain, icon) VALUES (?, ?, ?, ?, NULL)",
            [(map_id, h["q"], h["r"], h["terrain"]) for h in added],
        )
        self.db.commit()
        self._push_undo(
            map_id,
            author,
            "add ring",
            {"kind": "del_hexes", "coords": [[h["q"], h["r"]] for h in added]},
        )
        self._bump(map_id)
        return added

    def clear_all(self, author: str = "someone", map_id: int = DEFAULT_MAP_ID) -> None:
        before = {
            "hexes": self._all_hex_rows(map_id),
            "features": self.features(map_id),
            "party": self.party(map_id),
        }
        self.db.execute("DELETE FROM hexes WHERE map_id = ?", (map_id,))
        self.db.execute("DELETE FROM features WHERE map_id = ?", (map_id,))
        self.db.execute(
            "DELETE FROM meta WHERE map_id = ? AND key = 'party'", (map_id,)
        )
        self.db.execute(
            "INSERT INTO hexes (map_id, q, r, terrain, icon) "
            "VALUES (?, 0, 0, 'FOG', NULL)",
            (map_id,),
        )
        self.db.commit()
        self._push_undo(
            map_id, author, "clear map", {"kind": "restore_all", "data": before}
        )
        self._bump(map_id)

    def set_explored(
        self,
        q: int,
        r: int,
        explored: bool,
        author: str = "someone",
        map_id: int = DEFAULT_MAP_ID,
    ) -> None:
        prior = self._hex_row(map_id, q, r)
        cur = self.db.execute(
            "UPDATE hexes SET explored = ? WHERE map_id = ? AND q = ? AND r = ?",
            (1 if explored else 0, map_id, q, r),
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no hex at {q},{r}")
        if prior is not None:
            self._push_undo(
                map_id,
                author,
                f"reveal {q},{r}",
                {"kind": "set_explored", "q": q, "r": r, "explored": prior["explored"]},
            )
        self._bump(map_id)

    # --- per-map meta (party / fog) -----------------------------------------

    def _meta(self, map_id: int, key: str) -> str | None:
        row = self.db.execute(
            "SELECT value FROM meta WHERE map_id = ? AND key = ?", (map_id, key)
        ).fetchone()
        return None if row is None else str(row[0])

    def _set_meta(self, map_id: int, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO meta (map_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT (map_id, key) DO UPDATE SET value = excluded.value",
            (map_id, key, value),
        )

    def fog_enabled(self, map_id: int = DEFAULT_MAP_ID) -> bool:
        return self._meta(map_id, "fog") == "1"

    def set_fog(
        self, enabled: bool, author: str = "someone", map_id: int = DEFAULT_MAP_ID
    ) -> None:
        prior = self.fog_enabled(map_id)
        self._set_meta(map_id, "fog", "1" if enabled else "0")
        self.db.commit()
        self._push_undo(
            map_id, author, "toggle fog", {"kind": "set_fog", "enabled": prior}
        )
        self._bump(map_id)

    def party(self, map_id: int = DEFAULT_MAP_ID) -> dict[str, Any] | None:
        raw = self._meta(map_id, "party")
        if raw is None:
            return None
        loaded: dict[str, Any] = json.loads(raw)
        return loaded

    def set_party(
        self, q: int, r: int, author: str = "someone", map_id: int = DEFAULT_MAP_ID
    ) -> None:
        prior = self.party(map_id)
        self._set_meta(map_id, "party", json.dumps({"q": q, "r": r}))
        self.db.commit()
        self._push_undo(
            map_id, author, "move party", {"kind": "set_party", "party": prior}
        )
        self._bump(map_id)

    def clear_party(
        self, author: str = "someone", map_id: int = DEFAULT_MAP_ID
    ) -> None:
        prior = self.party(map_id)
        self.db.execute(
            "DELETE FROM meta WHERE map_id = ? AND key = 'party'", (map_id,)
        )
        self.db.commit()
        self._push_undo(
            map_id, author, "clear party", {"kind": "set_party", "party": prior}
        )
        self._bump(map_id)

    # --- features -----------------------------------------------------------

    def add_feature(
        self,
        kind: str,
        path: list[tuple[int, int]],
        created_by: str,
        map_id: int = DEFAULT_MAP_ID,
    ) -> dict[str, Any]:
        if kind not in FEATURE_KINDS:
            raise ValueError(f"unknown feature kind {kind!r}")
        cur = self.db.execute(
            "INSERT INTO features (map_id, kind, path, created_by, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                map_id,
                kind,
                json.dumps([[q, r] for q, r in path]),
                created_by,
                time.time(),
            ),
        )
        self.db.commit()
        self._push_undo(
            map_id,
            created_by,
            f"build {kind}",
            {"kind": "del_feature", "id": cur.lastrowid},
        )
        self._bump(map_id)
        return {
            "id": cur.lastrowid,
            "kind": kind,
            "path": [[q, r] for q, r in path],
            "created_by": created_by,
        }

    def remove_feature(
        self, feature_id: int, author: str = "someone", map_id: int = DEFAULT_MAP_ID
    ) -> None:
        row = self.db.execute(
            "SELECT kind, path, created_by FROM features WHERE id = ? AND map_id = ?",
            (feature_id, map_id),
        ).fetchone()
        cur = self.db.execute(
            "DELETE FROM features WHERE id = ? AND map_id = ?", (feature_id, map_id)
        )
        self.db.commit()
        if not cur.rowcount:
            raise ValueError(f"no feature {feature_id}")
        self._push_undo(
            map_id,
            author,
            "remove path",
            {
                "kind": "add_feature",
                "feature_kind": row[0],
                "path": json.loads(row[1]),
                "created_by": row[2],
            },
        )
        self._bump(map_id)

    def features(self, map_id: int = DEFAULT_MAP_ID) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, kind, path, created_by FROM features WHERE map_id = ? "
            "ORDER BY id",
            (map_id,),
        ).fetchall()
        return [
            {"id": i, "kind": k, "path": json.loads(p), "created_by": c}
            for i, k, p, c in rows
        ]

    def features_at(self, q: int, r: int, map_id: int = DEFAULT_MAP_ID) -> list[int]:
        return [f["id"] for f in self.features(map_id) if [q, r] in f["path"]]

    def terrain_map(self, map_id: int = DEFAULT_MAP_ID) -> dict[tuple[int, int], str]:
        rows = self.db.execute(
            "SELECT q, r, terrain FROM hexes WHERE map_id = ?", (map_id,)
        ).fetchall()
        return {(q, r): t for q, r, t in rows}

    # --- undo (per-map, DM-only, capped) ------------------------------------

    def _push_undo(
        self, map_id: int, player: str, label: str, inverse: dict[str, Any]
    ) -> None:
        self.db.execute(
            "INSERT INTO undo (map_id, ts, player, label, inverse) "
            "VALUES (?, ?, ?, ?, ?)",
            (map_id, time.time(), player, label, json.dumps(inverse)),
        )
        self.db.execute(
            "DELETE FROM undo WHERE map_id = ? AND id <= "
            "(SELECT MAX(id) FROM undo WHERE map_id = ?) - 100",
            (map_id, map_id),
        )
        self.db.commit()

    def can_undo(self, map_id: int = DEFAULT_MAP_ID) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM undo WHERE map_id = ? LIMIT 1", (map_id,)
            ).fetchone()
            is not None
        )

    def undo(self, map_id: int = DEFAULT_MAP_ID) -> str | None:
        row = self.db.execute(
            "SELECT id, label, inverse FROM undo WHERE map_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (map_id,),
        ).fetchone()
        if row is None:
            return None
        undo_id, label, inverse = row
        self.db.execute("DELETE FROM undo WHERE id = ?", (undo_id,))
        self._apply_inverse(map_id, json.loads(inverse))
        self.db.commit()
        self._bump(map_id)
        return str(label)

    def _apply_inverse(self, map_id: int, inv: dict[str, Any]) -> None:
        kind = inv["kind"]
        if kind == "del_hex":
            self.db.execute(
                "DELETE FROM hexes WHERE map_id = ? AND q = ? AND r = ?",
                (map_id, inv["q"], inv["r"]),
            )
        elif kind == "hex_row":
            self._restore_hex(map_id, inv["row"])
        elif kind == "set_icon":
            self.db.execute(
                "UPDATE hexes SET icon = ?, edited_by = ? "
                "WHERE map_id = ? AND q = ? AND r = ?",
                (inv["icon"], inv["edited_by"], map_id, inv["q"], inv["r"]),
            )
        elif kind == "set_note":
            self.db.execute(
                "UPDATE hexes SET note = ?, note_author = ?, edited_by = ? "
                "WHERE map_id = ? AND q = ? AND r = ?",
                (
                    inv["note"],
                    inv["note_author"],
                    inv["edited_by"],
                    map_id,
                    inv["q"],
                    inv["r"],
                ),
            )
        elif kind == "set_label":
            self.db.execute(
                "UPDATE hexes SET label = ?, edited_by = ? "
                "WHERE map_id = ? AND q = ? AND r = ?",
                (inv["label"], inv["edited_by"], map_id, inv["q"], inv["r"]),
            )
        elif kind == "set_explored":
            self.db.execute(
                "UPDATE hexes SET explored = ? WHERE map_id = ? AND q = ? AND r = ?",
                (inv["explored"], map_id, inv["q"], inv["r"]),
            )
        elif kind == "set_party":
            if inv["party"] is None:
                self.db.execute(
                    "DELETE FROM meta WHERE map_id = ? AND key = 'party'", (map_id,)
                )
            else:
                self._set_meta(map_id, "party", json.dumps(inv["party"]))
        elif kind == "set_fog":
            self._set_meta(map_id, "fog", "1" if inv["enabled"] else "0")
        elif kind == "del_feature":
            self.db.execute(
                "DELETE FROM features WHERE id = ? AND map_id = ?",
                (inv["id"], map_id),
            )
        elif kind == "add_feature":
            self.db.execute(
                "INSERT INTO features (map_id, kind, path, created_by, ts) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    map_id,
                    inv["feature_kind"],
                    json.dumps(inv["path"]),
                    inv["created_by"],
                    time.time(),
                ),
            )
        elif kind == "del_hexes":
            self.db.executemany(
                "DELETE FROM hexes WHERE map_id = ? AND q = ? AND r = ?",
                [(map_id, q, r) for q, r in inv["coords"]],
            )
        elif kind == "restore_all":
            self.db.execute("DELETE FROM hexes WHERE map_id = ?", (map_id,))
            self.db.execute("DELETE FROM features WHERE map_id = ?", (map_id,))
            self.db.execute(
                "DELETE FROM meta WHERE map_id = ? AND key = 'party'", (map_id,)
            )
            party = inv["data"].get("party")
            if party is not None:
                self._set_meta(map_id, "party", json.dumps(party))
            for row_ in inv["data"]["hexes"]:
                self._restore_hex(map_id, row_)
            for f in inv["data"]["features"]:
                self.db.execute(
                    "INSERT INTO features (map_id, kind, path, created_by, ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        map_id,
                        f["kind"],
                        json.dumps(f["path"]),
                        f["created_by"],
                        time.time(),
                    ),
                )

    # --- audit log (per-map) ------------------------------------------------

    def log_op(
        self,
        player: str,
        op: str,
        detail: dict[str, Any],
        map_id: int = DEFAULT_MAP_ID,
    ) -> None:
        self.db.execute(
            "INSERT INTO ops (map_id, ts, player, op, detail) VALUES (?, ?, ?, ?, ?)",
            (map_id, time.time(), player, op, json.dumps(detail)),
        )
        self.db.execute(
            "DELETE FROM ops WHERE map_id = ? AND id <= "
            "(SELECT MAX(id) FROM ops WHERE map_id = ?) - 1000",
            (map_id, map_id),
        )
        self.db.commit()

    def history(self, limit: int, map_id: int = DEFAULT_MAP_ID) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT ts, player, op, detail FROM ops WHERE map_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (map_id, limit),
        ).fetchall()
        return [
            {"ts": ts, "player": player, "op": op, "detail": json.loads(detail)}
            for ts, player, op, detail in rows
        ]

    # --- import / export ----------------------------------------------------

    def import_hexmap(self, data: dict[str, Any], map_id: int = DEFAULT_MAP_ID) -> None:
        self.db.execute("DELETE FROM hexes WHERE map_id = ?", (map_id,))
        self.db.execute("DELETE FROM undo WHERE map_id = ?", (map_id,))
        self.db.executemany(
            "INSERT OR REPLACE INTO hexes "
            "(map_id, q, r, terrain, icon, note, note_author, label, edited_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    map_id,
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
        self.db.execute("DELETE FROM features WHERE map_id = ?", (map_id,))
        for f in data.get("features", []):
            if f.get("kind") in FEATURE_KINDS and isinstance(f.get("path"), list):
                self.db.execute(
                    "INSERT INTO features (map_id, kind, path, created_by, ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        map_id,
                        f["kind"],
                        json.dumps(f["path"]),
                        f.get("created_by"),
                        time.time(),
                    ),
                )
        self.db.commit()
        self._bump(map_id)

    def export_hexmap(self, map_id: int = DEFAULT_MAP_ID) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT q, r, terrain, icon, note, note_author, label, edited_by "
            "FROM hexes WHERE map_id = ?",
            (map_id,),
        ).fetchall()
        # note/label/edited_by and the features key are extras the desktop ignores
        return {
            "features": self.features(map_id),
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
