"""REST API routes for Photo Annotation Web UI.

All routes are registered via FastMCP's custom_route decorator.
Handlers accept Starlette Request and return Response.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from PIL import Image, ImageOps

import struct

from .. import db
from ..config import PROJECT_ROOT
from ..matching import match_face
from ..tools.photo_anchor import photo_anchor
from .ui import get_html


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
                "p.photo_id IN (SELECT DISTINCT photo_id FROM faces WHERE person_id IS NULL)"
            )

        where = " AND ".join(conditions)
        limit = min(int(request.query_params.get("limit", "200")), 1000)
        offset = int(request.query_params.get("offset", "0"))

        rows = conn.execute(
            f"""SELECT p.photo_id, p.rel_path, p.source_dir, p.filename,
                       p.width, p.height, p.face_count,
                       COALESCE(u.unid_count, 0) as unid_count,
                       COALESCE(a.anchor_count, 0) as anchor_count
                FROM photos p
                LEFT JOIN (
                    SELECT photo_id, COUNT(*) as unid_count
                    FROM faces WHERE person_id IS NULL
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
            matches = match_face(emb, top_k=3)
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

        # Delete anchor
        conn.execute("DELETE FROM anchors WHERE face_id=?", (face_id,))

        # Clear face assignment (only if it was an anchor, not auto)
        conn.execute(
            "UPDATE faces SET person_id=NULL, match_score=NULL, match_method=NULL WHERE face_id=? AND match_method='anchor'",
            (face_id,),
        )
        conn.commit()

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

        conn.execute(
            "UPDATE faces SET person_id=NULL, match_score=NULL, match_method=NULL WHERE face_id=?",
            (face_id,),
        )
        conn.commit()

        return JSONResponse({"cleared": True, "face_id": face_id})

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
