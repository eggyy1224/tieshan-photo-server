"""SQLite database schema and CRUD operations for face data."""

from __future__ import annotations

import hashlib
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .config import PHOTO_DB_PATH
from . import log

_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    photo_id    TEXT PRIMARY KEY,
    rel_path    TEXT NOT NULL UNIQUE,
    source_dir  TEXT NOT NULL,
    filename    TEXT NOT NULL,
    width       INTEGER,
    height      INTEGER,
    scan_status TEXT DEFAULT 'pending',
    scan_time   TEXT,
    face_count  INTEGER DEFAULT 0,
    card_path   TEXT
);

CREATE TABLE IF NOT EXISTS faces (
    face_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id    TEXT NOT NULL REFERENCES photos(photo_id),
    bbox_x      REAL NOT NULL,
    bbox_y      REAL NOT NULL,
    bbox_w      REAL NOT NULL,
    bbox_h      REAL NOT NULL,
    det_score   REAL NOT NULL,
    embedding   BLOB NOT NULL,
    age_est     INTEGER,
    gender_est  TEXT,
    cluster_id  INTEGER,
    person_id   TEXT,
    match_score REAL,
    match_method TEXT
);

CREATE TABLE IF NOT EXISTS persons (
    person_id    TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    aliases      TEXT,
    gender       TEXT,
    generation   INTEGER,
    vault_note   TEXT
);

CREATE TABLE IF NOT EXISTS anchors (
    anchor_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id     INTEGER NOT NULL REFERENCES faces(face_id),
    person_id   TEXT NOT NULL REFERENCES persons(person_id),
    source      TEXT NOT NULL,
    confidence  REAL DEFAULT 1.0,
    created     TEXT NOT NULL,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS scenes (
    scene_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id      TEXT NOT NULL UNIQUE REFERENCES photos(photo_id),
    model         TEXT NOT NULL,
    scene_type    TEXT,
    location      TEXT,
    architecture  TEXT,
    era_clues     TEXT,
    spatial_desc  TEXT,
    objects_json  TEXT,
    texts_json    TEXT,
    tags_json     TEXT,
    raw_response  TEXT,
    annotate_time TEXT,
    status        TEXT DEFAULT 'done'
);

CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_anchors_person ON anchors(person_id);
CREATE INDEX IF NOT EXISTS idx_scenes_photo ON scenes(photo_id);
CREATE INDEX IF NOT EXISTS idx_scenes_type ON scenes(scene_type);
CREATE INDEX IF NOT EXISTS idx_scenes_location ON scenes(location);

CREATE TABLE IF NOT EXISTS image_embeddings (
    embed_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id    TEXT NOT NULL REFERENCES photos(photo_id),
    model       TEXT NOT NULL,
    embedding   BLOB NOT NULL,
    embed_time  TEXT NOT NULL,
    UNIQUE(photo_id, model)
);
CREATE INDEX IF NOT EXISTS idx_image_embed_photo ON image_embeddings(photo_id);
CREATE INDEX IF NOT EXISTS idx_image_embed_model ON image_embeddings(model);

CREATE TABLE IF NOT EXISTS rejected_matches (
    reject_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id     INTEGER NOT NULL,
    photo_id    TEXT NOT NULL,
    person_id   TEXT NOT NULL,
    created     TEXT NOT NULL,
    UNIQUE(face_id, person_id)
);
CREATE INDEX IF NOT EXISTS idx_rejected_face ON rejected_matches(face_id);
CREATE INDEX IF NOT EXISTS idx_rejected_photo ON rejected_matches(photo_id);

CREATE TABLE IF NOT EXISTS photo_stars (
    photo_id TEXT PRIMARY KEY REFERENCES photos(photo_id),
    created  TEXT NOT NULL
);
"""

_MIGRATIONS = [
    ("persons", "birth_year", "ALTER TABLE persons ADD COLUMN birth_year INTEGER"),
    ("photos", "est_year", "ALTER TABLE photos ADD COLUMN est_year INTEGER"),
    ("photos", "est_year_lo", "ALTER TABLE photos ADD COLUMN est_year_lo INTEGER"),
    ("photos", "est_year_hi", "ALTER TABLE photos ADD COLUMN est_year_hi INTEGER"),
    ("photos", "est_confidence", "ALTER TABLE photos ADD COLUMN est_confidence TEXT"),
    ("photos", "est_method", "ALTER TABLE photos ADD COLUMN est_method TEXT"),
    ("photos", "est_n_faces", "ALTER TABLE photos ADD COLUMN est_n_faces INTEGER"),
    ("photos", "known_year", "ALTER TABLE photos ADD COLUMN known_year INTEGER"),
    ("photos", "scene_status", "ALTER TABLE photos ADD COLUMN scene_status TEXT DEFAULT 'pending'"),
    ("photos", "embed_status", "ALTER TABLE photos ADD COLUMN embed_status TEXT DEFAULT 'pending'"),
]


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent schema migrations — add columns only if missing."""
    for table, column, sql in _MIGRATIONS:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(sql)
            log.info("migration applied", table=table, column=column)
    conn.commit()


_conn: Optional[sqlite3.Connection] = None


def path_to_photo_id(rel_path: str) -> str:
    """Deterministic photo ID from relative path."""
    return hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:16]


def embedding_to_blob(emb: np.ndarray) -> bytes:
    """Convert float32 numpy array to bytes."""
    return emb.astype(np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    """Convert bytes back to float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32).copy()


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        PHOTO_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(PHOTO_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.executescript(_SCHEMA)
        _run_migrations(_conn)
        log.info("database opened", path=str(PHOTO_DB_PATH))
    return _conn


def close() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


# ── Photos CRUD ──────────────────────────────────────────────────────

def upsert_photo(
    rel_path: str,
    source_dir: str,
    filename: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    card_path: Optional[str] = None,
) -> str:
    """Insert or update photo record. Returns photo_id."""
    photo_id = path_to_photo_id(rel_path)
    conn = get_conn()
    conn.execute(
        """INSERT INTO photos (photo_id, rel_path, source_dir, filename, width, height, card_path)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(photo_id) DO UPDATE SET
             width=excluded.width, height=excluded.height, card_path=excluded.card_path
        """,
        (photo_id, rel_path, source_dir, filename, width, height, card_path),
    )
    conn.commit()
    return photo_id


def mark_scanned(photo_id: str, face_count: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE photos SET scan_status='scanned', scan_time=?, face_count=? WHERE photo_id=?",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), face_count, photo_id),
    )
    conn.commit()


def mark_failed(photo_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE photos SET scan_status='failed', scan_time=? WHERE photo_id=?",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), photo_id),
    )
    conn.commit()


def get_photo(photo_id: str) -> Optional[dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM photos WHERE photo_id=?", (photo_id,)).fetchone()
    return dict(row) if row else None


def get_photo_by_path(rel_path: str) -> Optional[dict[str, Any]]:
    photo_id = path_to_photo_id(rel_path)
    return get_photo(photo_id)


# ── Faces CRUD ───────────────────────────────────────────────────────

def insert_face(
    photo_id: str,
    bbox: tuple[float, float, float, float],
    det_score: float,
    embedding: np.ndarray,
    age_est: Optional[int] = None,
    gender_est: Optional[str] = None,
) -> int:
    """Insert face record. Returns face_id."""
    conn = get_conn()
    # Convert bbox to Python floats (numpy float64 → BLOB in SQLite otherwise)
    bx, by, bw, bh = (float(v) for v in bbox)
    cur = conn.execute(
        """INSERT INTO faces (photo_id, bbox_x, bbox_y, bbox_w, bbox_h, det_score, embedding, age_est, gender_est)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (photo_id, bx, by, bw, bh, float(det_score), embedding_to_blob(embedding), age_est, gender_est),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_faces_for_photo(photo_id: str) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM faces WHERE photo_id=?", (photo_id,)).fetchall()
    return [dict(r) for r in rows]


def get_all_anchored_embeddings() -> list[dict[str, Any]]:
    """Get all face embeddings that have anchors (known person assignments)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT f.face_id, f.embedding, a.person_id, a.confidence
           FROM faces f
           JOIN anchors a ON f.face_id = a.face_id""",
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_face_embeddings() -> list[dict[str, Any]]:
    """Get all face embeddings (for clustering)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT face_id, photo_id, embedding, person_id, cluster_id FROM faces"
    ).fetchall()
    return [dict(r) for r in rows]


def update_face_match(
    face_id: int,
    person_id: Optional[str],
    score: Optional[float],
    method: Optional[str],
) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE faces SET person_id=?, match_score=?, match_method=? WHERE face_id=?",
        (person_id, score, method, face_id),
    )
    conn.commit()


def update_face_cluster(face_id: int, cluster_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE faces SET cluster_id=? WHERE face_id=?",
        (cluster_id, face_id),
    )
    conn.commit()


def delete_faces_for_photo(photo_id: str) -> None:
    conn = get_conn()
    # Note: rejected_matches is keyed by photo_id (not face_id FK),
    # so rejections survive face re-detection across rescans.
    conn.execute("DELETE FROM anchors WHERE face_id IN (SELECT face_id FROM faces WHERE photo_id=?)", (photo_id,))
    conn.execute("DELETE FROM faces WHERE photo_id=?", (photo_id,))
    conn.commit()


# ── Persons CRUD ─────────────────────────────────────────────────────

def upsert_person(
    person_id: str,
    display_name: str,
    aliases: Optional[str] = None,
    gender: Optional[str] = None,
    generation: Optional[int] = None,
    vault_note: Optional[str] = None,
    birth_year: Optional[int] = None,
) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO persons (person_id, display_name, aliases, gender, generation, vault_note, birth_year)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(person_id) DO UPDATE SET
             display_name=excluded.display_name, aliases=excluded.aliases,
             gender=excluded.gender, generation=excluded.generation,
             vault_note=excluded.vault_note, birth_year=excluded.birth_year
        """,
        (person_id, display_name, aliases, gender, generation, vault_note, birth_year),
    )
    conn.commit()


def get_person(person_id: str) -> Optional[dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM persons WHERE person_id=?", (person_id,)).fetchone()
    return dict(row) if row else None


def find_person_by_name(name: str) -> Optional[dict[str, Any]]:
    """Find person by display_name or alias (case-insensitive partial match)."""
    conn = get_conn()
    # Exact display_name match first
    row = conn.execute("SELECT * FROM persons WHERE display_name=?", (name,)).fetchone()
    if row:
        return dict(row)
    # Partial match on display_name
    row = conn.execute("SELECT * FROM persons WHERE display_name LIKE ?", (f"%{name}%",)).fetchone()
    if row:
        return dict(row)
    # Search in aliases JSON
    rows = conn.execute("SELECT * FROM persons WHERE aliases IS NOT NULL").fetchall()
    for r in rows:
        if name in (r["aliases"] or ""):
            return dict(r)
    return None


# ── Anchors CRUD ─────────────────────────────────────────────────────

def insert_anchor(
    face_id: int,
    person_id: str,
    source: str,
    confidence: float = 1.0,
    note: Optional[str] = None,
) -> int:
    conn = get_conn()
    existing = conn.execute(
        "SELECT anchor_id, person_id FROM anchors WHERE face_id=?",
        (face_id,),
    ).fetchone()
    if existing:
        if existing["person_id"] != person_id:
            raise ValueError(
                f"Face {face_id} already anchored to {existing['person_id']}"
            )
        return existing["anchor_id"]  # type: ignore[return-value]

    # Clear any rejection for this face+person (anchor overrides rejection)
    conn.execute(
        "DELETE FROM rejected_matches WHERE face_id=? AND person_id=?",
        (face_id, person_id),
    )

    cur = conn.execute(
        """INSERT INTO anchors (face_id, person_id, source, confidence, created, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (face_id, person_id, source, confidence, time.strftime("%Y-%m-%dT%H:%M:%S"), note),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_anchors_for_person(person_id: str) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM anchors WHERE person_id=?", (person_id,)).fetchall()
    return [dict(r) for r in rows]


def get_anchor_for_face(face_id: int) -> Optional[dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM anchors WHERE face_id=?", (face_id,)).fetchone()
    return dict(row) if row else None


# ── Rejected Matches CRUD ────────────────────────────────────────

def insert_rejected_match(face_id: int, person_id: str, photo_id: str | None = None) -> None:
    """Record that face_id is NOT person_id (negative feedback).

    Keyed by (face_id, person_id) for per-face precision.
    photo_id is stored for bookkeeping but not used as query key.
    No FK on face_id so rows survive delete_faces_for_photo (rescan).
    """
    conn = get_conn()
    if photo_id is None:
        row = conn.execute(
            "SELECT photo_id FROM faces WHERE face_id=?", (face_id,)
        ).fetchone()
        photo_id = row["photo_id"] if row else ""
    conn.execute(
        """INSERT OR IGNORE INTO rejected_matches (face_id, photo_id, person_id, created)
           VALUES (?, ?, ?, ?)""",
        (face_id, photo_id, person_id, time.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    conn.commit()


def delete_rejected_matches_for_face(face_id: int, person_id: str | None = None) -> int:
    """Delete rejection records for a specific face.

    If person_id is given, only delete that specific pair.
    Otherwise delete all rejections for the face.
    Returns number of rows deleted.
    """
    conn = get_conn()
    if person_id:
        cur = conn.execute(
            "DELETE FROM rejected_matches WHERE face_id=? AND person_id=?",
            (face_id, person_id),
        )
    else:
        cur = conn.execute(
            "DELETE FROM rejected_matches WHERE face_id=?",
            (face_id,),
        )
    conn.commit()
    return cur.rowcount


def delete_rejected_matches(photo_id: str, person_id: str | None = None) -> int:
    """Delete rejection records for an entire photo.

    If person_id is given, only delete that specific pair.
    Otherwise delete all rejections for the photo.
    Returns number of rows deleted.
    """
    conn = get_conn()
    if person_id:
        cur = conn.execute(
            "DELETE FROM rejected_matches WHERE photo_id=? AND person_id=?",
            (photo_id, person_id),
        )
    else:
        cur = conn.execute(
            "DELETE FROM rejected_matches WHERE photo_id=?",
            (photo_id,),
        )
    conn.commit()
    return cur.rowcount


def get_rejected_persons_for_face(face_id: int) -> list[str]:
    """Get all person_ids rejected for this specific face."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT person_id FROM rejected_matches WHERE face_id=?",
        (face_id,),
    ).fetchall()
    return [r["person_id"] for r in rows]


def get_rejected_persons_for_photo(photo_id: str) -> list[str]:
    """Get all person_ids rejected across any face in a photo."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT person_id FROM rejected_matches WHERE photo_id=?",
        (photo_id,),
    ).fetchall()
    return [r["person_id"] for r in rows]


# ── Photo Stars CRUD ────────────────────────────────────────────────

def star_photo(photo_id: str) -> bool:
    """Add star to photo. Returns True if newly starred, False if already starred."""
    conn = get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO photo_stars (photo_id, created) VALUES (?, ?)",
        (photo_id, time.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    conn.commit()
    return cur.rowcount > 0


def unstar_photo(photo_id: str) -> bool:
    """Remove star from photo. Returns True if removed, False if wasn't starred."""
    conn = get_conn()
    cur = conn.execute("DELETE FROM photo_stars WHERE photo_id=?", (photo_id,))
    conn.commit()
    return cur.rowcount > 0


def is_starred(photo_id: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM photo_stars WHERE photo_id=?", (photo_id,)
    ).fetchone()
    return row is not None


def get_starred_photo_ids() -> set[str]:
    """Return set of all starred photo_ids."""
    conn = get_conn()
    rows = conn.execute("SELECT photo_id FROM photo_stars").fetchall()
    return {r["photo_id"] for r in rows}


# ── Stats ────────────────────────────────────────────────────────────

def get_stats() -> dict[str, Any]:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    scanned = conn.execute("SELECT COUNT(*) FROM photos WHERE scan_status='scanned'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM photos WHERE scan_status='failed'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM photos WHERE scan_status='pending'").fetchone()[0]
    face_count = conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
    anchored = conn.execute("SELECT COUNT(DISTINCT face_id) FROM anchors").fetchone()[0]
    matched = conn.execute("SELECT COUNT(*) FROM faces WHERE person_id IS NOT NULL").fetchone()[0]
    person_count = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    with_cards = conn.execute("SELECT COUNT(*) FROM photos WHERE card_path IS NOT NULL").fetchone()[0]
    return {
        "total_photos": total,
        "scanned": scanned,
        "failed": failed,
        "pending": pending,
        "face_count": face_count,
        "anchored_faces": anchored,
        "matched_faces": matched,
        "person_count": person_count,
        "photos_with_cards": with_cards,
    }


def get_stats_by_source() -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT source_dir, COUNT(*) as photo_count,
                  SUM(CASE WHEN scan_status='scanned' THEN 1 ELSE 0 END) as scanned,
                  SUM(face_count) as faces
           FROM photos GROUP BY source_dir ORDER BY photo_count DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats_by_person() -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.person_id, p.display_name,
                  COALESCE(f.photo_count, 0) as photo_count,
                  COALESCE(f.face_count, 0) as face_count,
                  COALESCE(a.anchor_count, 0) as anchor_count
           FROM persons p
           LEFT JOIN (
               SELECT person_id,
                      COUNT(DISTINCT photo_id) as photo_count,
                      COUNT(*) as face_count
               FROM faces
               WHERE person_id IS NOT NULL
               GROUP BY person_id
           ) f ON f.person_id = p.person_id
           LEFT JOIN (
               SELECT person_id, COUNT(*) as anchor_count
               FROM anchors
               GROUP BY person_id
           ) a ON a.person_id = p.person_id
           ORDER BY photo_count DESC, p.display_name"""
    ).fetchall()
    return [dict(r) for r in rows]


# ── Scenes CRUD ─────────────────────────────────────────────────────

def upsert_scene(
    photo_id: str,
    model: str,
    scene_type: Optional[str] = None,
    location: Optional[str] = None,
    architecture: Optional[str] = None,
    era_clues: Optional[str] = None,
    spatial_desc: Optional[str] = None,
    objects_json: Optional[str] = None,
    texts_json: Optional[str] = None,
    tags_json: Optional[str] = None,
    raw_response: Optional[str] = None,
) -> None:
    """Insert or replace a scene annotation for a photo."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO scenes
             (photo_id, model, scene_type, location, architecture,
              era_clues, spatial_desc, objects_json, texts_json,
              tags_json, raw_response, annotate_time, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'done')
           ON CONFLICT(photo_id) DO UPDATE SET
             model=excluded.model, scene_type=excluded.scene_type,
             location=excluded.location, architecture=excluded.architecture,
             era_clues=excluded.era_clues, spatial_desc=excluded.spatial_desc,
             objects_json=excluded.objects_json, texts_json=excluded.texts_json,
             tags_json=excluded.tags_json, raw_response=excluded.raw_response,
             annotate_time=excluded.annotate_time, status='done'
        """,
        (
            photo_id, model, scene_type, location, architecture,
            era_clues, spatial_desc, objects_json, texts_json,
            tags_json, raw_response, time.strftime("%Y-%m-%dT%H:%M:%S"),
        ),
    )
    conn.commit()


def get_scene(photo_id: str) -> Optional[dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM scenes WHERE photo_id=?", (photo_id,)).fetchone()
    return dict(row) if row else None


def mark_scene_status(photo_id: str, status: str) -> None:
    """Update scene_status on the photos table."""
    conn = get_conn()
    conn.execute(
        "UPDATE photos SET scene_status=? WHERE photo_id=?",
        (status, photo_id),
    )
    conn.commit()


def search_scenes_db(
    query: str = "",
    scene_type: str = "",
    location: str = "",
    tag: str = "",
    has_text: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Multi-condition search on scenes + photos."""
    conn = get_conn()
    conditions: list[str] = []
    params: list[Any] = []

    if query:
        conditions.append(
            "(s.spatial_desc LIKE ? OR s.objects_json LIKE ? OR s.era_clues LIKE ? OR s.architecture LIKE ?)"
        )
        q = f"%{query}%"
        params.extend([q, q, q, q])
    if scene_type:
        conditions.append("s.scene_type = ?")
        params.append(scene_type)
    if location:
        conditions.append("s.location LIKE ?")
        params.append(f"%{location}%")
    if tag:
        conditions.append("s.tags_json LIKE ?")
        params.append(f"%{tag}%")
    if has_text:
        conditions.append("s.texts_json IS NOT NULL AND s.texts_json != '[]' AND s.texts_json != 'null'")

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"""SELECT s.*, p.rel_path, p.source_dir, p.filename
            FROM scenes s
            JOIN photos p ON s.photo_id = p.photo_id
            WHERE {where}
            ORDER BY s.annotate_time DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()
    return [dict(r) for r in rows]


# ── Image Embeddings CRUD ──────────────────────────────────────────

def upsert_image_embedding(
    photo_id: str,
    model: str,
    embedding: np.ndarray,
) -> None:
    """Insert or replace whole-image embedding for a photo."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO image_embeddings (photo_id, model, embedding, embed_time)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(photo_id, model) DO UPDATE SET
             embedding=excluded.embedding, embed_time=excluded.embed_time
        """,
        (photo_id, model, embedding_to_blob(embedding), time.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    conn.execute(
        "UPDATE photos SET embed_status='done' WHERE photo_id=?",
        (photo_id,),
    )
    conn.commit()


def get_image_embedding(photo_id: str, model: str) -> Optional[np.ndarray]:
    """Get a single photo's image embedding. Returns None if not found."""
    conn = get_conn()
    row = conn.execute(
        "SELECT embedding FROM image_embeddings WHERE photo_id=? AND model=?",
        (photo_id, model),
    ).fetchone()
    if row is None:
        return None
    return blob_to_embedding(row["embedding"])


def get_all_image_embeddings(model: str) -> list[dict[str, Any]]:
    """Get all image embeddings for a given model. Returns list of {photo_id, embedding}."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT photo_id, embedding FROM image_embeddings WHERE model=?",
        (model,),
    ).fetchall()
    return [{"photo_id": r["photo_id"], "embedding": blob_to_embedding(r["embedding"])} for r in rows]


def get_embed_stats(model: str = "") -> dict[str, Any]:
    """Aggregate image embedding statistics."""
    conn = get_conn()
    total_photos = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]

    if model:
        embedded = conn.execute(
            "SELECT COUNT(*) FROM image_embeddings WHERE model=?", (model,)
        ).fetchone()[0]
    else:
        embedded = conn.execute("SELECT COUNT(*) FROM image_embeddings").fetchone()[0]

    pending = conn.execute(
        "SELECT COUNT(*) FROM photos WHERE embed_status='pending'"
    ).fetchone()[0]
    done = conn.execute(
        "SELECT COUNT(*) FROM photos WHERE embed_status='done'"
    ).fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM photos WHERE embed_status='failed'"
    ).fetchone()[0]

    return {
        "total_photos": total_photos,
        "embedded": embedded,
        "pending": pending,
        "done": done,
        "failed": failed,
        "coverage_pct": round(100 * embedded / total_photos, 1) if total_photos else 0,
    }


def mark_embed_status(photo_id: str, status: str) -> None:
    """Update embed_status on the photos table."""
    conn = get_conn()
    conn.execute(
        "UPDATE photos SET embed_status=? WHERE photo_id=?",
        (status, photo_id),
    )
    conn.commit()


def get_scene_stats_db() -> dict[str, Any]:
    """Aggregate scene annotation statistics."""
    conn = get_conn()
    total_scanned = conn.execute(
        "SELECT COUNT(*) FROM photos WHERE scan_status='scanned'"
    ).fetchone()[0]
    annotated = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]

    by_type = conn.execute(
        """SELECT scene_type, COUNT(*) as cnt FROM scenes
           GROUP BY scene_type ORDER BY cnt DESC"""
    ).fetchall()

    by_location = conn.execute(
        """SELECT location, COUNT(*) as cnt FROM scenes
           WHERE location IS NOT NULL
           GROUP BY location ORDER BY cnt DESC LIMIT 20"""
    ).fetchall()

    with_text = conn.execute(
        "SELECT COUNT(*) FROM scenes WHERE texts_json IS NOT NULL AND texts_json != '[]' AND texts_json != 'null'"
    ).fetchone()[0]

    # Top tags: parse tags_json across all scenes
    tag_rows = conn.execute("SELECT tags_json FROM scenes WHERE tags_json IS NOT NULL").fetchall()
    tag_counts: dict[str, int] = {}
    import json as _json
    for r in tag_rows:
        try:
            tags = _json.loads(r["tags_json"])
            if isinstance(tags, list):
                for t in tags:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
        except (ValueError, TypeError):
            pass
    top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:20]

    return {
        "total_scanned": total_scanned,
        "annotated": annotated,
        "coverage_pct": round(100 * annotated / total_scanned, 1) if total_scanned else 0,
        "with_text": with_text,
        "by_scene_type": [dict(r) for r in by_type],
        "by_location": [dict(r) for r in by_location],
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
    }
