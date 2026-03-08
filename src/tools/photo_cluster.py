"""photo_cluster — Auto-cluster unassigned faces (Phase 2)."""

from __future__ import annotations

import numpy as np

from .. import db, log
from ..config import MATCH_MEDIUM


async def photo_cluster(eps: float = 0.55, min_samples: int = 2, det_score_min: float = 0.0) -> dict:
    """Cluster unassigned faces using DBSCAN on cosine distance.

    Args:
        eps: Maximum distance for DBSCAN (1 - cosine_similarity).
        min_samples: Minimum faces per cluster.
        det_score_min: Minimum detection score to include (0.0 = all).

    Returns:
        Dict with cluster info and sample faces.
    """
    from sklearn.cluster import DBSCAN

    all_faces = db.get_all_face_embeddings()
    unassigned = [f for f in all_faces if f["person_id"] is None]
    if det_score_min > 0:
        conn = db.get_conn()
        det_scores = {r["face_id"]: r["det_score"] for r in conn.execute(
            "SELECT face_id, det_score FROM faces WHERE person_id IS NULL AND det_score >= ?",
            (det_score_min,)
        ).fetchall()}
        unassigned = [f for f in unassigned if f["face_id"] in det_scores]

    if len(unassigned) < min_samples:
        return {"message": "Not enough unassigned faces to cluster", "unassigned_count": len(unassigned)}

    embeddings = np.array([db.blob_to_embedding(f["embedding"]) for f in unassigned])

    # Cosine distance matrix (clip to avoid negative values from float precision)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normed = embeddings / norms
    dist_matrix = np.clip(1 - normed @ normed.T, 0, 2)

    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed")
    labels = clustering.fit_predict(dist_matrix)

    # Update DB and collect results
    clusters: dict[int, list] = {}
    for i, label in enumerate(labels):
        if label == -1:
            continue
        face = unassigned[i]
        db.update_face_cluster(face["face_id"], int(label))
        if label not in clusters:
            clusters[label] = []
        photo = db.get_photo(face["photo_id"])
        clusters[label].append({
            "face_id": face["face_id"],
            "photo_id": face["photo_id"],
            "rel_path": photo["rel_path"] if photo else None,
        })

    result_clusters = []
    for cid, members in sorted(clusters.items()):
        result_clusters.append({
            "cluster_id": cid,
            "face_count": len(members),
            "sample_photos": members[:5],
        })

    noise_count = sum(1 for l in labels if l == -1)
    log.info("clustering done", clusters=len(clusters), noise=noise_count)

    return {
        "total_unassigned": len(unassigned),
        "cluster_count": len(clusters),
        "noise_count": noise_count,
        "clusters": result_clusters,
    }
