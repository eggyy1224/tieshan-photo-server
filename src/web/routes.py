"""REST API routes for Photo Annotation Web UI.

All routes are registered via FastMCP's custom_route decorator.
Handlers accept Starlette Request and return Response.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from PIL import Image, ImageOps

import struct

from .. import db, log
from ..config import PROJECT_ROOT
from ..matching import match_face, cosine_similarity
from ..pipeline import detect_faces
from ..preprocessing import preprocess
from ..tools.photo_anchor import photo_anchor, rematch_faces
from .ui import get_html


_UNIDENTIFIED_SQL = "person_id IS NULL AND COALESCE(match_method,'') != 'rejected'"


def _to_float(v) -> float:
    """Convert a value to float, handling bytes (struct-packed) from SQLite."""
    if isinstance(v, bytes):
        if len(v) == 4:
            return struct.unpack('<f', v)[0]
        elif len(v) == 8:
            return struct.unpack('<d', v)[0]
    return float(v)


# ── Helpers ──────────────────────────────────────────────────────────

def _photo_abs_path(photo: dict[str, Any]) -> Path | None:
    """Resolve photo's absolute path from DB record."""
    rel = photo.get("rel_path")
    if not rel:
        return None
    p = PROJECT_ROOT / rel
    return p if p.is_file() else None


def _serve_jpeg(img: Image.Image, quality: int = 85) -> Response:
    """Encode PIL Image as JPEG response."""
    buf = io.BytesIO()
    img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Response(content=buf.read(), media_type="image/jpeg")


# ── Route Registration ───────────────────────────────────────────────

def register_routes(mcp) -> None:  # noqa: ANN001 (FastMCP type)
    """Register all Web UI routes on the FastMCP server."""

    # ── GET /ui — Single-page HTML app ──────────────────────────────

    @mcp.custom_route("/ui", methods=["GET"])
    async def ui_page(request: Request) -> Response:
        return Response(content=get_html(), media_type="text/html")

    # ── GET /api/photos — Photo list ────────────────────────────────

    @mcp.custom_route("/api/photos", methods=["GET"])
    async def api_photos(request: Request) -> JSONResponse:
        conn = db.get_conn()
        conditions: list[str] = ["p.scan_status='scanned'"]
        params: list[Any] = []

        source_dir = request.query_params.get("source_dir", "")
        if source_dir:
            conditions.append("p.source_dir=?")
            params.append(source_dir)

        has_unidentified = request.query_params.get("has_unidentified", "")
        if has_unidentified == "1":
            conditions.append(
                "p.photo_id IN (SELECT DISTINCT photo_id FROM faces "
                f"WHERE {_UNIDENTIFIED_SQL})"
            )

        where = " AND ".join(conditions)
        limit = min(int(request.query_params.get("limit", "200")), 10000)
        offset = int(request.query_params.get("offset", "0"))

        rows = conn.execute(
            f"""SELECT p.photo_id, p.rel_path, p.source_dir, p.filename,
                       p.width, p.height, p.face_count,
                       COALESCE(u.unid_count, 0) as unid_count,
                       COALESCE(a.anchor_count, 0) as anchor_count
                FROM photos p
                LEFT JOIN (
                    SELECT photo_id, COUNT(*) as unid_count
                    FROM faces WHERE {_UNIDENTIFIED_SQL}
                    GROUP BY photo_id
                ) u ON u.photo_id = p.photo_id
                LEFT JOIN (
                    SELECT f.photo_id, COUNT(*) as anchor_count
                    FROM faces f JOIN anchors a ON a.face_id = f.face_id
                    GROUP BY f.photo_id
                ) a ON a.photo_id = p.photo_id
                WHERE {where}
                ORDER BY p.source_dir, p.filename
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

        total = conn.execute(
            f"SELECT COUNT(*) FROM photos p WHERE {where}", params
        ).fetchone()[0]

        return JSONResponse({
            "photos": [dict(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    # ── GET /api/photo/{photo_id} — Single photo detail ─────────────

    @mcp.custom_route("/api/photo/{photo_id}", methods=["GET"])
    async def api_photo_detail(request: Request) -> JSONResponse:
        photo_id = request.path_params["photo_id"]
        photo = db.get_photo(photo_id)
        if not photo:
            return JSONResponse({"error": "NOT_FOUND"}, status_code=404)

        faces_raw = db.get_faces_for_photo(photo_id)
        faces = []
        for f in faces_raw:
            emb = db.blob_to_embedding(f["embedding"])
            # Exclude rejected persons from candidate list
            rejected = db.get_rejected_persons_for_face(f["face_id"])
            exclude = set(rejected) if rejected else None
            matches = match_face(emb, top_k=3, exclude_persons=exclude)
            faces.append({
                "face_id": f["face_id"],
                "bbox": [_to_float(f["bbox_x"]), _to_float(f["bbox_y"]),
                         _to_float(f["bbox_w"]), _to_float(f["bbox_h"])],
                "det_score": round(float(f["det_score"]), 3),
                "age_est": f["age_est"],
                "gender_est": f["gender_est"],
                "person_id": f["person_id"],
                "match_score": round(f["match_score"], 4) if f["match_score"] else None,
                "match_method": f["match_method"],
                "matches": matches,
                "rejected_persons": rejected or [],
            })
        # Note: embedding blob excluded from response
        # Sort by det_score descending
        faces.sort(key=lambda x: x["det_score"], reverse=True)

        return JSONResponse({
            "photo_id": photo["photo_id"],
            "rel_path": photo["rel_path"],
            "source_dir": photo["source_dir"],
            "filename": photo["filename"],
            "width": photo["width"],
            "height": photo["height"],
            "face_count": photo["face_count"],
            "faces": faces,
        })

    # ── GET /api/image/{photo_id} — Serve photo JPEG ────────────────

    @mcp.custom_route("/api/image/{photo_id}", methods=["GET"])
    async def api_image(request: Request) -> Response:
        photo_id = request.path_params["photo_id"]
        photo = db.get_photo(photo_id)
        if not photo:
            return JSONResponse({"error": "NOT_FOUND"}, status_code=404)

        abs_path = _photo_abs_path(photo)
        if not abs_path:
            return JSONResponse({"error": "FILE_NOT_FOUND"}, status_code=404)

        max_dim = int(request.query_params.get("max_dim", "0"))
        try:
            img = ImageOps.exif_transpose(Image.open(abs_path))
        except Exception:
            img = Image.open(abs_path)

        if max_dim and max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        return _serve_jpeg(img)

    # ── GET /api/face/{face_id}/crop — Face crop JPEG ───────────────

    @mcp.custom_route("/api/face/{face_id}/crop", methods=["GET"])
    async def api_face_crop(request: Request) -> Response:
        face_id = int(request.path_params["face_id"])
        conn = db.get_conn()
        face = conn.execute(
            "SELECT * FROM faces WHERE face_id=?", (face_id,)
        ).fetchone()
        if not face:
            return JSONResponse({"error": "FACE_NOT_FOUND"}, status_code=404)

        photo = db.get_photo(face["photo_id"])
        if not photo:
            return JSONResponse({"error": "PHOTO_NOT_FOUND"}, status_code=404)

        abs_path = _photo_abs_path(photo)
        if not abs_path:
            return JSONResponse({"error": "FILE_NOT_FOUND"}, status_code=404)

        try:
            img = ImageOps.exif_transpose(Image.open(abs_path))
        except Exception:
            img = Image.open(abs_path)
        w, h = img.size

        # bbox is normalized [0,1], may be stored as bytes in older records
        bx = _to_float(face["bbox_x"])
        by = _to_float(face["bbox_y"])
        bw = _to_float(face["bbox_w"])
        bh = _to_float(face["bbox_h"])

        # Add 20% padding
        pad_w = bw * 0.2
        pad_h = bh * 0.2
        x1 = max(0, bx - pad_w) * w
        y1 = max(0, by - pad_h) * h
        x2 = min(1, bx + bw + pad_w) * w
        y2 = min(1, by + bh + pad_h) * h

        crop = img.crop((int(x1), int(y1), int(x2), int(y2)))
        # Resize to reasonable size
        crop.thumbnail((300, 300), Image.LANCZOS)
        return _serve_jpeg(crop, quality=90)

    # ── GET /api/persons — All persons ──────────────────────────────

    @mcp.custom_route("/api/persons", methods=["GET"])
    async def api_persons(request: Request) -> JSONResponse:
        conn = db.get_conn()
        rows = conn.execute(
            """SELECT p.person_id, p.display_name, p.gender, p.birth_year,
                      COUNT(a.anchor_id) as anchor_count
               FROM persons p
               LEFT JOIN anchors a ON a.person_id = p.person_id
               GROUP BY p.person_id
               ORDER BY anchor_count DESC, p.display_name"""
        ).fetchall()
        return JSONResponse({"persons": [dict(r) for r in rows]})

    # ── GET /api/person/{person_id}/portrait — Best portrait ────────

    @mcp.custom_route("/api/person/{person_id}/portrait", methods=["GET"])
    async def api_person_portrait(request: Request) -> Response:
        person_id = request.path_params["person_id"]

        # 1. Check reference_portraits directory
        ref_dir = Path(__file__).resolve().parent.parent.parent / "data" / "reference_portraits"
        if ref_dir.is_dir():
            for ext in (".jpg", ".jpeg", ".png"):
                ref_path = ref_dir / f"{person_id}{ext}"
                if ref_path.is_file():
                    img = Image.open(ref_path)
                    img.thumbnail((200, 200), Image.LANCZOS)
                    return _serve_jpeg(img, quality=90)

        # 2. Fallback: highest-score anchored face crop
        conn = db.get_conn()
        row = conn.execute(
            """SELECT f.face_id, f.photo_id, f.bbox_x, f.bbox_y, f.bbox_w, f.bbox_h
               FROM anchors a
               JOIN faces f ON f.face_id = a.face_id
               WHERE a.person_id = ?
               ORDER BY a.confidence DESC
               LIMIT 1""",
            (person_id,),
        ).fetchone()

        if not row:
            return JSONResponse({"error": "NO_PORTRAIT"}, status_code=404)

        photo = db.get_photo(row["photo_id"])
        if not photo:
            return JSONResponse({"error": "PHOTO_NOT_FOUND"}, status_code=404)

        abs_path = _photo_abs_path(photo)
        if not abs_path:
            return JSONResponse({"error": "FILE_NOT_FOUND"}, status_code=404)

        try:
            img = ImageOps.exif_transpose(Image.open(abs_path))
        except Exception:
            img = Image.open(abs_path)
        w, h = img.size
        bx = _to_float(row["bbox_x"])
        by = _to_float(row["bbox_y"])
        bw = _to_float(row["bbox_w"])
        bh = _to_float(row["bbox_h"])
        pad_w = bw * 0.15
        pad_h = bh * 0.15
        x1 = max(0, bx - pad_w) * w
        y1 = max(0, by - pad_h) * h
        x2 = min(1, bx + bw + pad_w) * w
        y2 = min(1, by + bh + pad_h) * h
        crop = img.crop((int(x1), int(y1), int(x2), int(y2)))
        crop.thumbnail((200, 200), Image.LANCZOS)
        return _serve_jpeg(crop, quality=90)

    # ── POST /api/anchor — Create anchor ────────────────────────────

    @mcp.custom_route("/api/anchor", methods=["POST"])
    async def api_anchor(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "INVALID_JSON"}, status_code=400)

        face_id = body.get("face_id")
        person_id = body.get("person_id")
        note = body.get("note", "")

        if not face_id or not person_id:
            return JSONResponse(
                {"error": "MISSING_FIELDS", "message": "face_id and person_id required"},
                status_code=400,
            )

        result = await photo_anchor(
            face_id=int(face_id),
            person_id=str(person_id),
            note=str(note) if note else "",
            scope="photo",
        )
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return JSONResponse(result)

    # ── DELETE /api/anchor — Remove anchor ─────────────────────────

    @mcp.custom_route("/api/anchor/{face_id}", methods=["DELETE"])
    async def api_delete_anchor(request: Request) -> JSONResponse:
        face_id = int(request.path_params["face_id"])
        conn = db.get_conn()

        # Check anchor exists
        anchor = conn.execute(
            "SELECT anchor_id, person_id FROM anchors WHERE face_id=?", (face_id,)
        ).fetchone()
        if not anchor:
            return JSONResponse(
                {"error": "NO_ANCHOR", "message": f"No anchor for face {face_id}"},
                status_code=404,
            )

        person_id = anchor["person_id"]
        face = conn.execute(
            "SELECT photo_id FROM faces WHERE face_id=?", (face_id,)
        ).fetchone()
        if not face:
            return JSONResponse({"error": "FACE_NOT_FOUND"}, status_code=404)

        # Delete anchor
        conn.execute("DELETE FROM anchors WHERE face_id=?", (face_id,))

        # Clear face assignment (only if it was an anchor, not auto)
        conn.execute(
            "UPDATE faces SET person_id=NULL, match_score=NULL, match_method=NULL WHERE face_id=? AND match_method='anchor'",
            (face_id,),
        )
        conn.commit()
        rematch_faces(photo_id=face["photo_id"], reset_auto_matches=True)

        person = db.get_person(person_id)
        display_name = person["display_name"] if person else person_id

        return JSONResponse({
            "removed": True,
            "face_id": face_id,
            "person_id": person_id,
            "display_name": display_name,
        })

    # ── POST /api/face/{face_id}/clear — Clear auto-match ──────────

    @mcp.custom_route("/api/face/{face_id}/clear", methods=["POST"])
    async def api_clear_match(request: Request) -> JSONResponse:
        face_id = int(request.path_params["face_id"])
        conn = db.get_conn()

        face = conn.execute(
            "SELECT face_id, person_id, match_method FROM faces WHERE face_id=?",
            (face_id,),
        ).fetchone()
        if not face:
            return JSONResponse({"error": "FACE_NOT_FOUND"}, status_code=404)

        if face["match_method"] == "anchor":
            return JSONResponse(
                {"error": "IS_ANCHOR", "message": "Use anchor delete to remove anchored matches"},
                status_code=400,
            )

        # Save rejection pair (negative feedback) before clearing
        rejected_person_id = face["person_id"]
        if rejected_person_id:
            db.insert_rejected_match(face_id, rejected_person_id)

        # Mark as 'rejected' so cascade re-matching skips this face
        conn.execute(
            "UPDATE faces SET person_id=NULL, match_score=NULL, match_method='rejected' WHERE face_id=?",
            (face_id,),
        )
        conn.commit()

        return JSONResponse({
            "cleared": True,
            "face_id": face_id,
            "rejected_person": rejected_person_id,
        })

    # ── POST /api/face/{face_id}/unreject — Undo rejection ────────

    @mcp.custom_route("/api/face/{face_id}/unreject", methods=["POST"])
    async def api_unreject(request: Request) -> JSONResponse:
        face_id = int(request.path_params["face_id"])
        conn = db.get_conn()

        face = conn.execute(
            "SELECT face_id, photo_id, match_method FROM faces WHERE face_id=?",
            (face_id,),
        ).fetchone()
        if not face:
            return JSONResponse({"error": "FACE_NOT_FOUND"}, status_code=404)

        if face["match_method"] != "rejected":
            return JSONResponse(
                {
                    "error": "NOT_REJECTED",
                    "message": "Only rejected faces can be unrejected",
                },
                status_code=400,
            )

        # Clear rejection records for this specific face only
        cleared_count = db.delete_rejected_matches_for_face(face_id)

        conn.execute(
            "UPDATE faces SET person_id=NULL, match_score=NULL, match_method=NULL WHERE face_id=?",
            (face_id,),
        )
        conn.commit()

        return JSONResponse({
            "unrejected": True,
            "face_id": face_id,
            "rejections_cleared": cleared_count,
        })

    # ── POST /api/rematch — Global rematch ──────────────────────────

    @mcp.custom_route("/api/rematch", methods=["POST"])
    async def api_rematch(request: Request) -> JSONResponse:
        new_matches = rematch_faces(photo_id=None, reset_auto_matches=True)
        return JSONResponse({"new_auto_matches": new_matches})

    # ── GET /api/source_dirs — Available source directories ─────────

    @mcp.custom_route("/api/source_dirs", methods=["GET"])
    async def api_source_dirs(request: Request) -> JSONResponse:
        conn = db.get_conn()
        rows = conn.execute(
            """SELECT source_dir, COUNT(*) as count
               FROM photos WHERE scan_status='scanned'
               GROUP BY source_dir ORDER BY count DESC"""
        ).fetchall()
        return JSONResponse({"source_dirs": [dict(r) for r in rows]})

    # ── GET /api/dashboard — Aggregate stats for overview ─────────

    @mcp.custom_route("/api/dashboard", methods=["GET"])
    async def api_dashboard(request: Request) -> JSONResponse:
        conn = db.get_conn()

        # Total scanned photos
        total_photos = conn.execute(
            "SELECT COUNT(*) FROM photos WHERE scan_status='scanned'"
        ).fetchone()[0]

        # Face status counts
        face_row = conn.execute(
            """SELECT
                   COUNT(*) as total,
                   SUM(CASE WHEN match_method='anchor' THEN 1 ELSE 0 END) as anchored,
                   SUM(CASE WHEN person_id IS NOT NULL
                            AND COALESCE(match_method,'') != 'anchor' THEN 1 ELSE 0 END) as auto_matched,
                   SUM(CASE WHEN match_method='rejected' THEN 1 ELSE 0 END) as rejected
               FROM faces"""
        ).fetchone()
        total_faces = face_row["total"] or 0
        anchored = face_row["anchored"] or 0
        auto_matched = face_row["auto_matched"] or 0
        rejected = face_row["rejected"] or 0
        unidentified = total_faces - anchored - auto_matched - rejected
        identified = anchored + auto_matched

        # Per-person stats (only persons with at least one match)
        person_rows = conn.execute(
            """SELECT p.person_id, p.display_name,
                      SUM(CASE WHEN f.match_method='anchor' THEN 1 ELSE 0 END) as anchor_count,
                      SUM(CASE WHEN f.person_id IS NOT NULL
                               AND COALESCE(f.match_method,'') != 'anchor' THEN 1 ELSE 0 END) as auto_count
               FROM persons p
               JOIN faces f ON f.person_id = p.person_id
               GROUP BY p.person_id
               ORDER BY (anchor_count + auto_count) DESC"""
        ).fetchall()

        # Per-source-dir stats
        dir_rows = conn.execute(
            """SELECT p.source_dir,
                      COUNT(DISTINCT p.photo_id) as photo_count,
                      COUNT(f.face_id) as face_count,
                      SUM(CASE WHEN f.person_id IS NOT NULL THEN 1 ELSE 0 END) as identified
               FROM photos p
               LEFT JOIN faces f ON f.photo_id = p.photo_id
               WHERE p.scan_status='scanned'
               GROUP BY p.source_dir
               ORDER BY photo_count DESC"""
        ).fetchall()

        # Top photos with most unidentified faces
        top_unid = conn.execute(
            """SELECT p.photo_id, p.filename, p.source_dir, p.face_count,
                      COUNT(f.face_id) as unid_count
               FROM photos p
               JOIN faces f ON f.photo_id = p.photo_id
               WHERE f.person_id IS NULL
                 AND COALESCE(f.match_method,'') != 'rejected'
                 AND p.scan_status='scanned'
               GROUP BY p.photo_id
               ORDER BY unid_count DESC
               LIMIT 10"""
        ).fetchall()

        # Negative feedback stats
        rejection_pairs = conn.execute(
            "SELECT COUNT(*) FROM rejected_matches"
        ).fetchone()[0]

        return JSONResponse({
            "total_photos": total_photos,
            "total_faces": total_faces,
            "anchored": anchored,
            "auto_matched": auto_matched,
            "rejected": rejected,
            "unidentified": unidentified,
            "rejection_pairs": rejection_pairs,
            "coverage_pct": round(identified / total_faces * 100, 1) if total_faces > 0 else 0,
            "persons": [dict(r) for r in person_rows],
            "source_dirs": [
                {**dict(r), "coverage_pct": round((r["identified"] or 0) / r["face_count"] * 100, 1)
                 if r["face_count"] else 0}
                for r in dir_rows
            ],
            "top_unid_photos": [dict(r) for r in top_unid],
        })

    # ── POST /api/person — Create/update person (no restart) ─────

    @mcp.custom_route("/api/person", methods=["POST"])
    async def api_create_person(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "INVALID_JSON"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"error": "INVALID_JSON", "message": "Request body must be a JSON object"}, status_code=400)

        import re

        raw_pid = body.get("person_id")
        person_id = str(raw_pid).strip() if raw_pid else ""
        if not person_id:
            return JSONResponse(
                {"error": "MISSING_FIELDS", "message": "person_id is required"},
                status_code=400,
            )
        # person_id must be snake_case: lowercase ASCII, digits, underscores
        if not re.fullmatch(r"[a-z][a-z0-9_]*", person_id):
            return JSONResponse(
                {"error": "INVALID_PERSON_ID",
                 "message": "person_id must be snake_case (lowercase letters, digits, underscores; must start with a letter)"},
                status_code=400,
            )

        from ..persons import save_person, _UNSET, _find_yaml_source

        # ── Validate display_name ──
        # Check both SQLite and YAML sources — the DB may not be populated
        # yet if load_family_tree() hasn't run (e.g. test fixtures).
        existing = db.get_person(person_id) or _find_yaml_source(person_id)
        raw_dn = body.get("display_name")
        raw_dn_stripped = str(raw_dn).strip() if raw_dn else ""
        if not existing and not raw_dn_stripped:
            return JSONResponse(
                {"error": "MISSING_FIELDS", "message": "display_name is required for new persons"},
                status_code=400,
            )

        # ── Parse input → YAML-native kwargs ──
        # Only fields present in the request body are included;
        # omitted fields stay _UNSET and are preserved by save_person.
        kwargs: dict[str, Any] = {}

        # display_name: non-empty string or skip (preserve existing)
        # Reject HTML markup to prevent stored XSS (rendered via innerHTML in UI)
        if "display_name" in body:
            dn = str(raw_dn).strip() if raw_dn else ""
            if dn:
                if re.search(r"[<>&\"]", dn):
                    return JSONResponse(
                        {"error": "INVALID_DISPLAY_NAME",
                         "message": "display_name must not contain HTML characters (<, >, &, \")"},
                        status_code=400,
                    )
                kwargs["display_name"] = dn

        # aliases → list[str] | None
        if "aliases" in body:
            raw_aliases = body["aliases"]
            if isinstance(raw_aliases, list):
                kwargs["aliases"] = [a for a in raw_aliases if isinstance(a, str) and a.strip()] or None
            elif raw_aliases is not None:
                s = str(raw_aliases).strip()
                kwargs["aliases"] = [s] if s else None
            else:
                kwargs["aliases"] = None

        # gender → "male" / "female" / None
        if "gender" in body:
            g = body["gender"]
            if not g or (isinstance(g, str) and not g.strip()):
                kwargs["gender"] = None
            else:
                g_normalized = str(g).strip().lower()
                if g_normalized in ("m", "male"):
                    kwargs["gender"] = "male"
                elif g_normalized in ("f", "female"):
                    kwargs["gender"] = "female"
                else:
                    return JSONResponse(
                        {"error": "INVALID_GENDER", "message": f"gender must be M/F/male/female or empty, got {g!r}"},
                        status_code=400,
                    )

        # generation, birth_year → int | None (with validation)
        bad_fields: list[str] = []
        for field in ("generation", "birth_year"):
            if field in body:
                raw = body[field]
                if raw is None:
                    kwargs[field] = None
                else:
                    s = str(raw).strip()
                    if not s:
                        kwargs[field] = None
                    else:
                        try:
                            v = int(s)
                        except ValueError:
                            bad_fields.append(f"{field}: {raw!r}")
                        else:
                            if field == "birth_year" and not (1000 <= v <= 9999):
                                bad_fields.append(f"{field}: {raw!r} (must be 4-digit year)")
                            else:
                                kwargs[field] = v

        if bad_fields:
            return JSONResponse(
                {"error": "INVALID_NUMERIC", "message": f"Invalid numeric value(s): {', '.join(bad_fields)}"},
                status_code=400,
            )

        # vault_note = Obsidian note path; notes = narrative text
        if "vault_note" in body:
            vn = body["vault_note"]
            kwargs["vault_note"] = str(vn).strip() if vn else None
        if "notes" in body:
            n = body["notes"]
            kwargs["notes"] = str(n).strip() if n else None

        # ── Single write path: YAML → SQLite ──
        final_name = save_person(str(person_id), **kwargs)

        return JSONResponse({"ok": True, "person_id": person_id, "display_name": final_name})

    # ── POST /api/compare — Compare ref photo vs target photo faces ──

    @mcp.custom_route("/api/compare", methods=["POST"])
    async def api_compare(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "INVALID_JSON"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"error": "INVALID_JSON", "message": "Request body must be a JSON object"}, status_code=400)

        ref_photo = body.get("ref_photo")
        target_photo_id = body.get("target_photo_id")

        if not ref_photo or not target_photo_id:
            return JSONResponse(
                {"error": "MISSING_FIELDS", "message": "ref_photo and target_photo_id required"},
                status_code=400,
            )
        if not isinstance(ref_photo, str) or not isinstance(target_photo_id, str):
            return JSONResponse(
                {"error": "INVALID_FIELDS", "message": "ref_photo and target_photo_id must be strings"},
                status_code=400,
            )

        # 1. Resolve ref_photo path — restrict to PROJECT_ROOT to prevent
        #    path-traversal (.. segments, absolute escapes).
        ref_path = Path(ref_photo)
        if not ref_path.is_absolute():
            ref_path = PROJECT_ROOT / ref_path
        try:
            ref_resolved = ref_path.resolve(strict=False)
            project_resolved = PROJECT_ROOT.resolve(strict=False)
            if not str(ref_resolved).startswith(str(project_resolved) + os.sep) and ref_resolved != project_resolved:
                return JSONResponse(
                    {"error": "REF_PHOTO_OUTSIDE_PROJECT", "message": "ref_photo must be within the project directory"},
                    status_code=403,
                )
        except (OSError, ValueError):
            return JSONResponse(
                {"error": "INVALID_PATH", "message": "Invalid ref_photo path"},
                status_code=400,
            )

        if not ref_path.is_file():
            return JSONResponse(
                {"error": "REF_PHOTO_NOT_FOUND", "message": f"File not found: {ref_photo}"},
                status_code=404,
            )

        # 2. Load reference image — use raw cv2.imread() (no EXIF transpose)
        #    to match process_photo() which stores target embeddings the same way.
        import cv2
        ref_img = cv2.imread(str(ref_path))
        if ref_img is None:
            return JSONResponse(
                {"error": "REF_PHOTO_UNREADABLE", "message": f"Cannot read image: {ref_photo}"},
                status_code=400,
            )

        try:

            ref_processed = preprocess(ref_img)
            ref_faces = detect_faces(ref_processed)

            if not ref_faces:
                return JSONResponse(
                    {"error": "NO_FACES_IN_REF", "message": "No faces detected in reference photo"},
                    status_code=400,
                )

            # 3. Get target photo faces from DB
            target_photo = db.get_photo(target_photo_id)
            if not target_photo:
                return JSONResponse(
                    {"error": "TARGET_NOT_FOUND", "message": f"Photo not found: {target_photo_id}"},
                    status_code=404,
                )

            target_faces_raw = db.get_faces_for_photo(target_photo_id)
            if not target_faces_raw:
                return JSONResponse(
                    {"error": "NO_FACES_IN_TARGET", "message": "No detected faces in target photo"},
                    status_code=400,
                )

            # 4. Compute cosine similarity: each ref face vs each target face
            results = []
            for ref_idx, ref_face in enumerate(ref_faces):
                ref_emb = ref_face["embedding"]
                rankings = []

                for tf in target_faces_raw:
                    target_emb = db.blob_to_embedding(tf["embedding"])
                    score = cosine_similarity(ref_emb, target_emb)

                    rankings.append({
                        "face_id": tf["face_id"],
                        "bbox": [
                            _to_float(tf["bbox_x"]),
                            _to_float(tf["bbox_y"]),
                            _to_float(tf["bbox_w"]),
                            _to_float(tf["bbox_h"]),
                        ],
                        "score": float(round(score, 4)),
                        "person_id": tf["person_id"],
                        "match_method": tf["match_method"],
                    })

                rankings.sort(key=lambda x: x["score"], reverse=True)

                results.append({
                    "ref_face_index": ref_idx,
                    "ref_bbox": [float(v) for v in ref_face["bbox"]],
                    "ref_det_score": float(round(ref_face["det_score"], 3)),
                    "ref_age_est": int(ref_face["age"]) if ref_face["age"] is not None else None,
                    "ref_gender_est": ref_face["gender"],
                    "rankings": rankings,
                })

            return JSONResponse({
                "ref_photo": ref_photo,
                "target_photo_id": target_photo_id,
                "ref_face_count": len(ref_faces),
                "target_face_count": len(target_faces_raw),
                "results": results,
            })
        except Exception:
            import traceback
            log.error("compare failed", error=traceback.format_exc())
            return JSONResponse({"error": "COMPARE_ERROR", "message": "Face comparison failed"}, status_code=500)
