"""Download MoViNet A2 Stream (Kinetics-600) from Kaggle Hub.

Usage:
    pip install kagglehub tensorflow
    python scripts/download_movinet_a2.py

The model is cached in ~/.cache/kagglehub/ and never re-downloaded unless
the version changes. After download, set the path in your environment:

    set VMS_VIOLENCE_MODEL=<printed path>

Or add it to your .env file.

Model info:
    Name:     MoViNet-A2 Stream (streaming / stateful variant)
    Dataset:  Kinetics-600 (600 action classes)
    Format:   TensorFlow 2 SavedModel
    Size:     ~28 MB
    Accuracy: Top-1 71.5% on Kinetics-600
    Latency:  ~4 ms/frame on CPU (streaming, 1 frame at a time)
"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        import kagglehub  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: kagglehub not installed. Run: pip install kagglehub", file=sys.stderr)
        sys.exit(1)

    try:
        import tensorflow  # type: ignore[import-untyped]  # noqa: F401
    except ImportError:
        print("ERROR: tensorflow not installed. Run: pip install tensorflow", file=sys.stderr)
        sys.exit(1)

    print("Downloading MoViNet A2 Stream (Kinetics-600) from Kaggle Hub...")
    print("This is ~28 MB and will be cached in ~/.cache/kagglehub/")
    print()

    path = kagglehub.model_download(
        "google/movinet/tensorFlow2/a2-stream-kinetics-600-classification"
    )

    print()
    print("=" * 60)
    print("Download complete!")
    print(f"Path to model files: {path}")
    print()
    print("To use this model, set:")
    print(f"  set VMS_VIOLENCE_MODEL={path}")
    print()
    print("Or add to your .env file:")
    print(f"  VMS_VIOLENCE_MODEL={path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
