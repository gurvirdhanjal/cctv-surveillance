"""Download MoViNet A2 Stream into models/movinet_a2/ — same folder as other models.

The model lands in models/movinet_a2/ alongside scrfd_2.5g.onnx, adaface_ir50.onnx, etc.
VMS_VIOLENCE_MODEL=models/movinet_a2 (the default) will work with no further config.

Usage:
  # Option A — kagglehub (recommended, handles caching automatically):
  pip install "kagglehub<1.0" tensorflow tensorflow-hub
  python scripts/download_movinet_a2.py
  # NOTE: kagglehub>=1.0 has a kagglesdk dependency bug -- use <1.0

  # Option B — manual tar.gz (Kaggle API or curl download):
  curl -L -o ~/Downloads/model.tar.gz \\
    https://www.kaggle.com/api/v1/models/google/movinet/tensorFlow2/a2-stream-kinetics-600-classification/2/download
  python scripts/download_movinet_a2.py --tar ~/Downloads/model.tar.gz

Both options install to models/movinet_a2/ with no extra config needed.
models/ is gitignored — the file will never be accidentally committed.

Why A2 (not A4/A5):
  A2: 78.6% Top-1, ~4 ms/frame CPU   ← binary violence classifier sweet spot
  A4: 83.5% Top-1, ~40 ms/frame CPU  ← needs GPU for real-time (10x slower)
  A5: 84.3% Top-1, ~100 ms/frame CPU ← GPU mandatory (27x slower, marginal gain)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile

# Always install into models/ in this repo, next to scrfd/adaface/yolo
_DEST_DIR = os.path.join("models", "movinet_a2")


def _find_saved_model(root_dir: str) -> str:
    """Walk root_dir and return the first directory that contains saved_model.pb."""
    for dirpath, _dirs, files in os.walk(root_dir):
        if "saved_model.pb" in files or "saved_model.pbtxt" in files:
            return dirpath
    return root_dir


def download_via_kagglehub() -> str:
    """Download via kagglehub (caches in ~/.cache/kagglehub/), then copy to models/.

    NOTE: use kagglehub<1.0  — version 1.0.x has a kagglesdk incompatibility.
    Install: pip install "kagglehub<1.0" tensorflow tensorflow-hub
    """
    # Validate deps with specific errors — catch real import errors, not "not installed"
    missing = []
    for pkg, install in [
        ("kagglehub", 'pip install "kagglehub<1.0"'),
        ("tensorflow", "pip install tensorflow"),
        ("tensorflow_hub", "pip install tensorflow-hub"),
    ]:
        try:
            __import__(pkg)
        except ModuleNotFoundError:
            missing.append(f"  {pkg}: run  {install}")
        except ImportError as exc:
            # Installed but broken (e.g. kagglehub 1.0.x kagglesdk conflict)
            print(
                f"ERROR: {pkg} is installed but failed to import: {exc}\n"
                f"Fix: pip install \"{pkg}<1.0\"  (1.0.x has a known dependency bug)",
                file=sys.stderr,
            )
            sys.exit(1)

    if missing:
        print("ERROR: Missing dependencies:\n" + "\n".join(missing), file=sys.stderr)
        sys.exit(1)

    import kagglehub  # type: ignore[import-untyped]

    print("Downloading MoViNet A2 Stream via kagglehub (~28 MB) ...")
    cached_path: str = kagglehub.model_download(
        "google/movinet/tensorFlow2/a2-stream-kinetics-600-classification"
    )

    # Find the SavedModel inside the kagglehub cache (may be nested)
    saved_model_src = _find_saved_model(cached_path)

    # Copy into models/movinet_a2/ so all models live in one place
    if os.path.exists(_DEST_DIR):
        print(f"Removing existing {_DEST_DIR} ...")
        shutil.rmtree(_DEST_DIR)
    print(f"Copying SavedModel to {_DEST_DIR} ...")
    shutil.copytree(saved_model_src, _DEST_DIR)
    return _DEST_DIR


def extract_tar(tar_path: str) -> str:
    """Extract tar.gz directly into models/movinet_a2/ and return the SavedModel path."""
    tmp_dir = _DEST_DIR + "_tmp"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)

    print(f"Extracting {tar_path} ...")
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(tmp_dir)

    saved_model_src = _find_saved_model(tmp_dir)

    if os.path.exists(_DEST_DIR):
        print(f"Removing existing {_DEST_DIR} ...")
        shutil.rmtree(_DEST_DIR)
    shutil.move(saved_model_src, _DEST_DIR)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return _DEST_DIR


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download MoViNet A2 Stream into models/movinet_a2/"
    )
    parser.add_argument(
        "--tar",
        metavar="TAR_GZ_PATH",
        default=None,
        help=(
            "Path to a manually downloaded tar.gz file. "
            "curl command: curl -L -o ~/Downloads/model.tar.gz "
            "https://www.kaggle.com/api/v1/models/google/movinet/"
            "tensorFlow2/a2-stream-kinetics-600-classification/2/download"
        ),
    )
    args = parser.parse_args()

    if args.tar:
        if not os.path.exists(args.tar):
            print(f"ERROR: file not found: {args.tar}", file=sys.stderr)
            sys.exit(1)
        dest = extract_tar(args.tar)
    else:
        dest = download_via_kagglehub()

    dest_abs = os.path.abspath(dest)
    print()
    print("=" * 60)
    print(f"Model installed to: {dest_abs}")
    print()
    print("Default config VMS_VIOLENCE_MODEL=models/movinet_a2 will work automatically.")
    print("Run the server and violence detection is enabled with no extra config.")
    print()
    print("Models folder now contains:")
    for f in sorted(os.listdir("models")):
        tag = "  <-- NEW" if "movinet" in f else ""
        print(f"  models/{f}{tag}")
    print("=" * 60)


if __name__ == "__main__":
    main()
