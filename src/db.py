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

CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_anchors_person ON anchors(person_id);
"""

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


def update_face_match(face_id: int, person_id: str, score: float, method: str) -> None:
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
) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO persons (person_id, display_name, aliases, gender, generation, vault_note)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(person_id) DO UPDATE SET
             display_name=excluded.display_name, aliases=excluded.aliases,
             gender=excluded.gender, generation=excluded.generation, vault_note=excluded.vault_note
        """,
        (person_id, display_name, aliases, gender, generation, vault_note),
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
                  COUNT(DISTINCT f.photo_id) as photo_count,
                  COUNT(f.face_id) as face_count,
                  COUNT(a.anchor_id) as anchor_count
           FROM persons p
           LEFT JOIN faces f ON f.person_id = p.person_id
           LEFT JOIN anchors a ON a.person_id = p.person_id
           GROUP BY p.person_id
           ORDER BY photo_count DESC"""
    ).fetchall()
    return [dict(r) for r in rows]
