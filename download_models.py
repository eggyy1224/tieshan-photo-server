#!/usr/bin/env python3
"""Download InsightFace buffalo_l model pack (~300MB).

Usage:
    python download_models.py

The model is downloaded to ./models/buffalo_l/ via InsightFace's built-in
model downloader. If the model already exists, this is a no-op.

Manual download (if automatic fails):
    1. Go to https://github.com/deepinsight/insightface/releases
    2. Download buffalo_l.zip from the model zoo
    3. Extract to ./models/buffalo_l/
"""

from __future__ import annotations

import sys
from pathlib import Path

MODEL_DIR = Path(__file__).parent / "models"


def download_insightface() -> bool:
    """Download InsightFace buffalo_l model. Returns True if successful."""
    buffalo_dir = MODEL_DIR / "buffalo_l"
    if buffalo_dir.exists() and any(buffalo_dir.glob("*.onnx")):
        print(f"InsightFace model already exists at {buffalo_dir}")
        print(f"  Files: {[f.name for f in buffalo_dir.glob('*.onnx')]}")
        return True

    print("Downloading InsightFace buffalo_l model pack...")
    print(f"  Destination: {MODEL_DIR}")
    print("  This may take a few minutes (~300MB)...")
    print()

    try:
        import insightface
        app = insightface.app.FaceAnalysis(
            name="buffalo_l",
            root=str(MODEL_DIR),
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
        print()
        print("InsightFace download complete!")
        print(f"  Model location: {buffalo_dir}")
        return True
    except ImportError:
        print("ERROR: insightface not installed.", file=sys.stderr)
        print("  Run: uv sync", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print()
        print("Manual download instructions:")
        print("  1. Visit https://github.com/deepinsight/insightface/releases")
        print("  2. Download buffalo_l.zip from model zoo")
        print(f"  3. Extract to {buffalo_dir}/")
        return False


def download_siglip() -> bool:
    """Download SigLIP model for image embedding. Returns True if successful."""
    siglip_dir = MODEL_DIR / "siglip"

    # Check if already cached (HuggingFace cache structure)
    if siglip_dir.exists() and any(siglip_dir.rglob("config.json")):
        print(f"SigLIP model already cached at {siglip_dir}")
        return True

    print("Downloading SigLIP model (google/siglip-base-patch16-384)...")
    print(f"  Cache dir: {siglip_dir}")
    print("  This may take a few minutes (~350MB)...")
    print()

    try:
        from transformers import AutoModel, AutoProcessor, AutoTokenizer

        model_name = "google/siglip-base-patch16-384"
        cache_dir = str(siglip_dir)

        print("  Downloading processor...")
        AutoProcessor.from_pretrained(model_name, cache_dir=cache_dir)

        print("  Downloading tokenizer...")
        AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)

        print("  Downloading model weights...")
        AutoModel.from_pretrained(model_name, cache_dir=cache_dir)

        print()
        print("SigLIP download complete!")
        print(f"  Cache location: {siglip_dir}")
        return True
    except ImportError:
        print("ERROR: transformers or torch not installed.", file=sys.stderr)
        print("  Run: uv sync", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False


def main() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    ok = True
    ok = download_insightface() and ok
    print()
    ok = download_siglip() and ok

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
