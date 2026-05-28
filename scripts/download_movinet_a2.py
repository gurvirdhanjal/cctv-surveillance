"""Download MoViNet A2 Stream (Kinetics-600) — kagglehub or manual tar.gz.

Usage:
  # Option A — kagglehub (recommended, handles caching automatically):
  pip install kagglehub tensorflow tensorflow-hub
  python scripts/download_movinet_a2.py

  # Option B — manual tar.gz (if you already have the Kaggle API curl download):
  curl -L -o ~/Downloads/model.tar.gz \\
    https://www.kaggle.com/api/v1/models/google/movinet/tensorFlow2/a2-stream-kinetics-600-classification/2/download
  python scripts/download_movinet_a2.py --tar ~/Downloads/model.tar.gz

After download, set the printed path as VMS_VIOLENCE_MODEL.

Why A2 (not A4/A5):
  A2: 78.6% Top-1, ~4 ms/frame CPU   ← binary violence classifier sweet spot
  A4: 83.5% Top-1, ~40 ms/frame CPU  ← needs GPU for real-time VMS use
  A5: 84.3% Top-1, ~100 ms/frame CPU ← overkill, GPU mandatory
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile


def download_kagglehub() -> str:
    """Download via kagglehub (handles versioning and local cache)."""
    for pkg, install in [
        ("kagglehub", "pip install kagglehub"),
        ("tensorflow", "pip install tensorflow"),
        ("tensorflow_hub", "pip install tensorflow-hub"),
    ]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"ERROR: {pkg} not installed. Run: {install}", file=sys.stderr)
            sys.exit(1)

    import kagglehub  # type: ignore[import-untyped]

    print("Downloading MoViNet A2 Stream via kagglehub (~28 MB, cached) ...")
    path: str = kagglehub.model_download(
        "google/movinet/tensorFlow2/a2-stream-kinetics-600-classification"
    )
    return path


def extract_tar(tar_path: str) -> str:
    """Extract a Kaggle tar.gz download to models/movinet_a2/ and return SavedModel path."""
    out_dir = os.path.join("models", "movinet_a2")
    os.makedirs(out_dir, exist_ok=True)
    print(f"Extracting {tar_path} to {out_dir} ...")
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(out_dir)
    # Find the directory that contains saved_model.pb
    for root, _dirs, files in os.walk(out_dir):
        if "saved_model.pb" in files or "saved_model.pbtxt" in files:
            return root
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Download MoViNet A2 Stream model")
    parser.add_argument(
        "--tar",
        metavar="TAR_GZ_PATH",
        default=None,
        help=(
            "Extract a manually downloaded tar.gz instead of using kagglehub. "
            "Download URL: https://www.kaggle.com/api/v1/models/google/movinet/"
            "tensorFlow2/a2-stream-kinetics-600-classification/2/download"
        ),
    )
    args = parser.parse_args()

    if args.tar:
        if not os.path.exists(args.tar):
            print(f"ERROR: file not found: {args.tar}", file=sys.stderr)
            sys.exit(1)
        path = extract_tar(args.tar)
    else:
        path = download_kagglehub()

    print()
    print("=" * 60)
    print(f"SavedModel path: {path}")
    print()
    print("Set as environment variable:")
    print(f"  Windows: set VMS_VIOLENCE_MODEL={path}")
    print(f"  Linux:   export VMS_VIOLENCE_MODEL={path}")
    print()
    print("Or add to .env file:")
    print(f"  VMS_VIOLENCE_MODEL={path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
