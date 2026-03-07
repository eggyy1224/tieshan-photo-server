#!/usr/bin/env python3
"""Phase 0 Pilot: Validate InsightFace on old Xu family photos.

Tests:
1. Detection rate across photo categories (solo / small group / medium / large)
2. CLAHE preprocessing impact on detection
3. Cross-photo cosine similarity for known same-person pairs
4. Age estimation accuracy (where ground truth is available)

Usage:
    cd tools/photo_server
    uv run python run_pilot.py

Output:
    data/pilot_report.md
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import PROJECT_ROOT, PHOTO_MODEL_DIR, PHOTO_DET_THRESHOLD
from src.preprocessing import preprocess, preprocess_for_comparison

# ── Pilot photo selection ────────────────────────────────────────────
# Each entry: (relative_path, category, expected_persons, notes)
# Categories: solo, small (2-5), medium (6-15), large (16+)

PILOT_PHOTOS: list[dict] = [
    # Solo portraits
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/許天催/許天催 寫字.jpg",
        "category": "solo",
        "expected_faces": 1,
        "persons": ["許天催"],
        "notes": "許天催寫字照，清晰正面",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/許天催/許天催正式坐像.jpg",
        "category": "solo",
        "expected_faces": 1,
        "persons": ["許天催"],
        "notes": "許天催正式坐像",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/許天象相簿/img110-2.jpg",
        "category": "solo",
        "expected_faces": 1,
        "persons": ["許天象"],
        "notes": "許天象青年照",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/許黃秀鸞/img114.jpg",
        "category": "solo",
        "expected_faces": 1,
        "persons": ["許黃秀鸞"],
        "notes": "許黃秀鸞獨照",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/雜集/170704_0030.jpg",
        "category": "solo",
        "expected_faces": 1,
        "persons": ["許天德"],
        "notes": "許天德晚年照",
    },
    # Small groups (2-5 people)
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/許天德相關/img102.jpg",
        "category": "small",
        "expected_faces": 3,
        "persons": ["許林月", "許天德", "許清貴"],
        "notes": "三人合照",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/許天德相關/img038-2.jpg",
        "category": "small",
        "expected_faces": None,
        "persons": ["許天德"],
        "notes": "許天德一家玉山",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/許雲陽相簿/img056.jpg",
        "category": "small",
        "expected_faces": 3,
        "persons": ["許美崙", "許雲陽"],
        "notes": "許美崙許雲陽許瑞庭",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/許雲從相簿/img242-2.jpg",
        "category": "small",
        "expected_faces": None,
        "persons": ["許雲從"],
        "notes": "許雲從相簿",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/339268680.jpg",
        "category": "small",
        "expected_faces": 2,
        "persons": ["頭山秀三", "許天德"],
        "notes": "頭山秀三與許天德合影",
    },
    # Medium groups (6-15)
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/外埔許家成員-7.jpg",
        "category": "medium",
        "expected_faces": None,
        "persons": ["許天德"],
        "notes": "許天德父子與頭山滿家族合影",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/1614332.jpg",
        "category": "medium",
        "expected_faces": None,
        "persons": ["許天催", "許天象", "許雲陽"],
        "notes": "許天催許天象許雲陽等",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/外埔許家照-3.jpg",
        "category": "medium",
        "expected_faces": None,
        "persons": ["許雲從"],
        "notes": "許雲從出征前家族合影",
    },
    # Large groups (16+)
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/許雲陽相簿/許天象 昭和18年6月10日 全家福.jpg",
        "category": "large",
        "expected_faces": 20,
        "persons": ["許天象", "許雲陽", "許錫玉", "許雲鵬"],
        "notes": "許天象全家福約20人",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/外埔許家家族結婚照.jpg",
        "category": "large",
        "expected_faces": None,
        "persons": ["許天奎"],
        "notes": "許天奎林獻堂吳淮水同框",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/img029.jpg",
        "category": "large",
        "expected_faces": None,
        "persons": [],
        "notes": "大甲鳳梨罐詰商會解散記念撮影",
    },
    {
        "path": "鐵山老照片from大舅舅/鐵山老照片from 大舅舅/1943年 臺中州產業組合 幹部鍊成會.jpg",
        "category": "large",
        "expected_faces": None,
        "persons": [],
        "notes": "1943年臺中州產業組合幹部鍊成會",
    },
]


def run_detection_test(app, photo: dict) -> dict:
    """Run face detection on one photo, both raw and CLAHE."""
    abs_path = PROJECT_ROOT / photo["path"]
    result = {
        "path": photo["path"],
        "category": photo["category"],
        "expected_faces": photo["expected_faces"],
        "exists": abs_path.exists(),
    }

    if not abs_path.exists():
        result["error"] = "file not found"
        return result

    img = cv2.imread(str(abs_path))
    if img is None:
        result["error"] = "cannot read image"
        return result

    h, w = img.shape[:2]
    result["dimensions"] = f"{w}x{h}"

    # Detection on raw (resized only)
    original, enhanced = preprocess_for_comparison(img)

    faces_raw = app.get(original)
    faces_clahe = app.get(enhanced)

    result["raw_faces"] = len(faces_raw)
    result["clahe_faces"] = len(faces_clahe)
    result["clahe_delta"] = len(faces_clahe) - len(faces_raw)

    # Collect embeddings for cross-photo matching
    result["embeddings_raw"] = [f.normed_embedding for f in faces_raw]
    result["embeddings_clahe"] = [f.normed_embedding for f in faces_clahe]

    # Age/gender estimates from CLAHE version
    result["face_details"] = []
    for f in faces_clahe:
        result["face_details"].append({
            "det_score": float(f.det_score),
            "age": int(f.age) if hasattr(f, "age") else None,
            "gender": "M" if getattr(f, "gender", None) == 1 else "F" if getattr(f, "gender", None) == 0 else None,
            "bbox_size": int((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])),
        })

    return result


def compute_cross_similarity(results: list[dict]) -> list[dict]:
    """Compute cosine similarity between same-person embeddings across photos."""
    # Build person → embeddings map
    person_embeddings: dict[str, list[tuple[str, np.ndarray]]] = {}
    for r in results:
        if "embeddings_clahe" not in r:
            continue
        for person in PILOT_PHOTOS:
            if person["path"] == r["path"]:
                for pname in person["persons"]:
                    if pname not in person_embeddings:
                        person_embeddings[pname] = []
                    # If solo photo, we know which embedding belongs to whom
                    if person["category"] == "solo" and r["embeddings_clahe"]:
                        person_embeddings[pname].append((r["path"], r["embeddings_clahe"][0]))
                break

    # Cross-photo similarity for persons with 2+ solo photos
    cross_results = []
    for person, emb_list in person_embeddings.items():
        if len(emb_list) < 2:
            continue
        for i in range(len(emb_list)):
            for j in range(i + 1, len(emb_list)):
                sim = float(np.dot(emb_list[i][1], emb_list[j][1]))
                cross_results.append({
                    "person": person,
                    "photo_a": emb_list[i][0].split("/")[-1],
                    "photo_b": emb_list[j][0].split("/")[-1],
                    "similarity": round(sim, 4),
                })

    return cross_results


def generate_report(results: list[dict], cross_sims: list[dict], elapsed: float) -> str:
    """Generate pilot report in Markdown."""
    lines = [
        "---",
        "type: pilot_report",
        f"generated: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"model: buffalo_l",
        f"det_threshold: {PHOTO_DET_THRESHOLD}",
        "---",
        "",
        "# Phase 0 Pilot Report: InsightFace on Xu Family Old Photos",
        "",
        f"> Generated: {time.strftime('%Y-%m-%d %H:%M')} | Elapsed: {elapsed:.1f}s",
        "",
        "## 1. Detection Rate by Category",
        "",
        "| Category | Photos | Avg Raw Faces | Avg CLAHE Faces | CLAHE Improvement |",
        "|---|---|---|---|---|",
    ]

    by_cat: dict[str, list] = {}
    for r in results:
        if "error" in r:
            continue
        cat = r["category"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(r)

    for cat in ["solo", "small", "medium", "large"]:
        group = by_cat.get(cat, [])
        if not group:
            lines.append(f"| {cat} | 0 | - | - | - |")
            continue
        avg_raw = sum(r["raw_faces"] for r in group) / len(group)
        avg_clahe = sum(r["clahe_faces"] for r in group) / len(group)
        delta = avg_clahe - avg_raw
        lines.append(f"| {cat} | {len(group)} | {avg_raw:.1f} | {avg_clahe:.1f} | {delta:+.1f} |")

    lines.extend(["", "## 2. Per-Photo Detection Results", ""])
    lines.append("| Photo | Cat | Dim | Raw | CLAHE | Delta | Notes |")
    lines.append("|---|---|---|---|---|---|---|")

    for r in results:
        if "error" in r:
            short = r["path"].split("/")[-1]
            lines.append(f"| `{short}` | - | - | - | - | - | {r['error']} |")
            continue
        short = r["path"].split("/")[-1][:40]
        dim = r.get("dimensions", "?")
        lines.append(
            f"| `{short}` | {r['category']} | {dim} | {r['raw_faces']} | "
            f"{r['clahe_faces']} | {r['clahe_delta']:+d} | |"
        )

    lines.extend(["", "## 3. Cross-Photo Same-Person Similarity", ""])
    if cross_sims:
        lines.append("| Person | Photo A | Photo B | Cosine Sim |")
        lines.append("|---|---|---|---|")
        for cs in cross_sims:
            lines.append(f"| {cs['person']} | `{cs['photo_a'][:30]}` | `{cs['photo_b'][:30]}` | {cs['similarity']} |")
    else:
        lines.append("> No same-person pairs with multiple solo photos found.")

    lines.extend(["", "## 4. Face Size Distribution (CLAHE)", ""])
    all_details = []
    for r in results:
        all_details.extend(r.get("face_details", []))

    if all_details:
        sizes = [d["bbox_size"] for d in all_details]
        scores = [d["det_score"] for d in all_details]
        lines.append(f"- Total faces detected: {len(all_details)}")
        lines.append(f"- Bbox area range: {min(sizes):,} – {max(sizes):,} px^2")
        lines.append(f"- Det score range: {min(scores):.3f} – {max(scores):.3f}")
        lines.append(f"- Median det score: {sorted(scores)[len(scores)//2]:.3f}")
        lines.append(f"- Faces < 30px wide (approx): {sum(1 for s in sizes if s < 900)}")

    lines.extend([
        "",
        "## 5. Decision",
        "",
        "> **TODO**: Review results above and decide:",
        "> - Detection rate acceptable? (target: >50% on solo/small)",
        "> - CLAHE helping? (positive delta = yes)",
        "> - Cross-photo similarity shows discrimination? (same person > 0.3, different < 0.3)",
        "> - Proceed to Phase 1 or adjust strategy?",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    print("=== tieshan-photo Phase 0 Pilot ===\n")

    # Load model
    print("Loading InsightFace buffalo_l model...")
    try:
        import insightface
        app = insightface.app.FaceAnalysis(
            name="buffalo_l",
            root=str(PHOTO_MODEL_DIR),
            providers=["CoreMLExecutionProvider", "CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_thresh=PHOTO_DET_THRESHOLD, det_size=(640, 640))
        print("  Model loaded.\n")
    except Exception as e:
        print(f"ERROR: Cannot load model: {e}", file=sys.stderr)
        print("  Run: python download_models.py", file=sys.stderr)
        return 1

    # Run detection on each pilot photo
    start = time.time()
    results = []
    for i, photo in enumerate(PILOT_PHOTOS):
        short = photo["path"].split("/")[-1][:50]
        print(f"  [{i+1}/{len(PILOT_PHOTOS)}] {short} ... ", end="", flush=True)
        r = run_detection_test(app, photo)
        if "error" in r:
            print(f"SKIP ({r['error']})")
        else:
            print(f"raw={r['raw_faces']} clahe={r['clahe_faces']}")
        results.append(r)

    elapsed = time.time() - start
    print(f"\nDetection complete in {elapsed:.1f}s")

    # Cross-photo similarity
    print("Computing cross-photo similarities...")
    cross_sims = compute_cross_similarity(results)

    # Generate report
    report = generate_report(results, cross_sims, elapsed)
    report_path = Path(__file__).parent / "data" / "pilot_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {report_path}")

    # Summary
    total = sum(1 for r in results if "error" not in r)
    detected = sum(r.get("clahe_faces", 0) for r in results if "error" not in r)
    print(f"\n  Photos tested: {total}/{len(PILOT_PHOTOS)}")
    print(f"  Total faces (CLAHE): {detected}")
    if cross_sims:
        avg_sim = sum(cs["similarity"] for cs in cross_sims) / len(cross_sims)
        print(f"  Avg same-person similarity: {avg_sim:.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
