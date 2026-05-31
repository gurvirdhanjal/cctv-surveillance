"""Download OSNet AIN x1.0 weights trained on MSMT17 from HuggingFace.

Usage:
    python scripts/download_osnet_ain_msmt17.py

Output: models/osnet_ain_x1_0_msmt17.pth  (~22MB)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OUT_PATH = REPO_ROOT / "models" / "osnet_ain_x1_0_msmt17.pth"

HF_REPO = "kaiyangzhou/osnet"
HF_FILENAME = (
    "osnet_ain_x1_0_msmt17_256x128_amsgrad_ep50_lr0.0015_coslr_b64_fb10_softmax_labsmth_flip_jitter.pth"
)


def main() -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: pip install huggingface-hub")
        sys.exit(1)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if OUT_PATH.exists():
        print(f"Already present: {OUT_PATH}  ({OUT_PATH.stat().st_size / 1_048_576:.1f} MB)")
    else:
        print(f"Downloading {HF_FILENAME} from {HF_REPO} ...")
        local = hf_hub_download(
            repo_id=HF_REPO,
            filename=HF_FILENAME,
            local_dir=str(OUT_PATH.parent),
        )
        src = Path(local)
        if src.resolve() != OUT_PATH.resolve():
            src.replace(OUT_PATH)  # replace() overwrites on Windows; rename() does not
        size_mb = OUT_PATH.stat().st_size / 1_048_576
        print(f"Saved: {OUT_PATH}  ({size_mb:.1f} MB)")

    # Quick sanity check
    try:
        from torchreid.utils import FeatureExtractor
        import numpy as np

        print("Running sanity check with FeatureExtractor ...")
        extractor = FeatureExtractor(
            model_name="osnet_ain_x1_0",
            model_path=str(OUT_PATH),
            device="cpu",
            verbose=False,
        )
        dummy = np.zeros((256, 128, 3), dtype=np.uint8)
        features = extractor([dummy])
        print(f"Sanity check: input (256,128,3) -> features {tuple(features.shape)}")
        assert features.shape == (1, 512), f"expected (1,512), got {features.shape}"
        print("OK — 512-dim output confirmed.")
    except ImportError:
        print("torchreid not installed — skipping sanity check.")


if __name__ == "__main__":
    main()
