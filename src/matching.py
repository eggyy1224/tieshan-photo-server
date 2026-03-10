"""Cosine similarity matching for face embeddings."""

from __future__ import annotations

from typing import Optional

import numpy as np

from . import db, log
from .config import MATCH_HIGH, MATCH_MEDIUM, MATCH_LOW


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def confidence_level(score: float) -> str:
    """Classify match confidence."""
    if score >= MATCH_HIGH:
        return "HIGH"
    elif score >= MATCH_MEDIUM:
        return "MEDIUM"
    elif score >= MATCH_LOW:
        return "LOW"
    return "NONE"


def match_face(
    embedding: np.ndarray,
    top_k: int = 3,
    exclude_persons: Optional[set[str]] = None,
) -> list[dict]:
    """Match a face embedding against all anchored embeddings.

    Args:
        embedding: The face embedding to match.
        top_k: Number of top matches to return.
        exclude_persons: Person IDs to skip (from negative feedback).

    Returns top-k matches sorted by score descending.
    """
    anchored = db.get_all_anchored_embeddings()
    if not anchored:
        return []

    scores: dict[str, list[float]] = {}
    for row in anchored:
        pid = row["person_id"]
        if exclude_persons and pid in exclude_persons:
            continue
        anchor_emb = db.blob_to_embedding(row["embedding"])
        sim = cosine_similarity(embedding, anchor_emb)
        if pid not in scores:
            scores[pid] = []
        scores[pid].append(sim)

    # For each person, use the max similarity across all their anchors
    person_scores = []
    for pid, sims in scores.items():
        best = max(sims)
        if best >= MATCH_LOW:
            person = db.get_person(pid)
            person_scores.append({
                "person_id": pid,
                "display_name": person["display_name"] if person else pid,
                "score": round(best, 4),
                "confidence": confidence_level(best),
            })

    person_scores.sort(key=lambda x: x["score"], reverse=True)
    return person_scores[:top_k]


def find_person_in_photos(
    person_id: str,
    min_score: float = 0.30,
    limit: int = 50,
) -> list[dict]:
    """Find all photos containing a specific person.

    Compares that person's anchor embeddings against all face embeddings.
    """
    # Get anchor embeddings for this person
    anchors = db.get_anchors_for_person(person_id)
    if not anchors:
        return []

    anchor_embeddings = []
    for anchor in anchors:
        face_rows = db.get_conn().execute(
            "SELECT embedding FROM faces WHERE face_id=?", (anchor["face_id"],)
        ).fetchall()
        for row in face_rows:
            anchor_embeddings.append(db.blob_to_embedding(row["embedding"]))

    if not anchor_embeddings:
        return []

    # Compare against all faces
    all_faces = db.get_all_face_embeddings()
    results = []
    seen_photos: set[str] = set()

    # Batch-load face_ids that rejected this person
    rejected_face_ids = set(
        r["face_id"] for r in db.get_conn().execute(
            "SELECT face_id FROM rejected_matches WHERE person_id=?",
            (person_id,),
        ).fetchall()
    )

    for face_row in all_faces:
        if face_row["face_id"] in rejected_face_ids:
            continue

        face_emb = db.blob_to_embedding(face_row["embedding"])
        best_sim = max(cosine_similarity(face_emb, ae) for ae in anchor_embeddings)

        if best_sim >= min_score:
            photo_id = face_row["photo_id"]
            if photo_id in seen_photos:
                continue
            seen_photos.add(photo_id)

            photo = db.get_photo(photo_id)
            if photo:
                results.append({
                    "photo_id": photo_id,
                    "rel_path": photo["rel_path"],
                    "filename": photo["filename"],
                    "source_dir": photo["source_dir"],
                    "score": round(best_sim, 4),
                    "confidence": confidence_level(best_sim),
                    "has_card": photo["card_path"] is not None,
                })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
