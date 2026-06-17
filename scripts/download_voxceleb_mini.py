"""Download a 50-pair VoxCeleb1 mini test set for face verification eval.

What this does:
  1. Fetches the public veri_test2.txt pairs file from Oxford VGG.
  2. Selects 25 same-person + 25 different-person pairs where the two clips
     reference DIFFERENT YouTube video IDs (harder test than within-video pairs).
  3. Downloads the first 10 seconds of each unique YouTube video via yt-dlp.
  4. Writes  data/voxceleb_mini/pairs.csv  and  data/voxceleb_mini/clips/*.mp4.

Requirements:
  pip install yt-dlp

License note:
  VoxCeleb1 is published for non-commercial research only.  The underlying
  YouTube content is publicly available.  Do not use the downloaded clips for
  any purpose other than developing or evaluating this pipeline.

Usage:
    python scripts/download_voxceleb_mini.py
    python scripts/download_voxceleb_mini.py --out data/voxceleb_mini --pairs 50
    python scripts/download_voxceleb_mini.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import logging
import subprocess
import sys
import urllib.request
from pathlib import Path
from random import Random

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PAIRS_URL = "https://www.robots.ox.ac.uk/~vgg/data/voxceleb/meta/veri_test2.txt"
YT_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"
CLIP_SECONDS = 10  # download only the first N seconds of each video


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_pairs(text: str) -> list[tuple[int, str, str]]:
    """Parse veri_test2.txt into (label, path1, path2) triples.

    Line format:  label  speakerID/videoID/segID  speakerID/videoID/segID
    """
    rows: list[tuple[int, str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3:
            continue
        label, p1, p2 = int(parts[0]), parts[1], parts[2]
        rows.append((label, p1, p2))
    return rows


def _video_id(path: str) -> str:
    """Extract the YouTube video ID from a VoxCeleb1 path (speaker/video/seg)."""
    return path.split("/")[1]


def _speaker_id(path: str) -> str:
    return path.split("/")[0]


# ---------------------------------------------------------------------------
# Pair selection
# ---------------------------------------------------------------------------


def _select_pairs(
    rows: list[tuple[int, str, str]],
    n_same: int = 25,
    n_diff: int = 25,
    seed: int = 42,
) -> list[tuple[int, str, str]]:
    """Select balanced pairs where the two clips are from different YouTube videos."""
    rng = Random(seed)  # noqa: S311 (not cryptographic)

    # Filter: different video IDs only (harder cross-video test)
    same = [r for r in rows if r[0] == 1 and _video_id(r[1]) != _video_id(r[2])]
    diff = [r for r in rows if r[0] == 0 and _video_id(r[1]) != _video_id(r[2])]

    logger.info(
        "After filtering: %d same-person cross-video pairs, %d different-person pairs",
        len(same),
        len(diff),
    )

    if len(same) < n_same:
        logger.warning("Only %d same-person pairs available; using all", len(same))
        n_same = len(same)
    if len(diff) < n_diff:
        logger.warning("Only %d different-person pairs available; using all", len(diff))
        n_diff = len(diff)

    rng.shuffle(same)
    rng.shuffle(diff)
    return same[:n_same] + diff[:n_diff]


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def _check_ytdlp() -> None:
    result = subprocess.run(
        ["yt-dlp", "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            "\nERROR: yt-dlp not found.  Install it with:\n"
            "    pip install yt-dlp\n"
            "or:\n"
            "    winget install yt-dlp  (Windows)\n"
        )
        sys.exit(1)
    logger.info("yt-dlp version: %s", result.stdout.strip())


def _download_clip(video_id: str, out_path: Path, seconds: int = CLIP_SECONDS) -> bool:
    """Download the first `seconds` of a YouTube video to out_path.

    Returns True on success, False on failure (video unavailable, etc.)
    """
    if out_path.exists() and out_path.stat().st_size > 10_000:
        logger.debug("Already downloaded: %s", out_path.name)
        return True

    url = YT_TEMPLATE.format(video_id=video_id)
    result = subprocess.run(
        [
            "yt-dlp",
            url,
            "--download-sections",
            f"*00:00-00:{seconds:02d}",
            "--output",
            str(out_path),
            "--format",
            "mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
            "--merge-output-format",
            "mp4",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        logger.warning("Failed to download %s: %s", video_id, result.stderr[:200])
        return False
    if not out_path.exists() or out_path.stat().st_size < 5_000:
        logger.warning("Download produced no/empty file for %s", video_id)
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(
    out_dir: str = "data/voxceleb_mini",
    n_same: int = 25,
    n_diff: int = 25,
    dry_run: bool = False,
) -> None:
    _check_ytdlp()

    out = Path(out_dir)
    clips_dir = out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: fetch pairs file
    logger.info("Fetching pairs file from Oxford VGG...")
    with urllib.request.urlopen(PAIRS_URL, timeout=30) as resp:
        pairs_text = resp.read().decode("utf-8")

    all_pairs = _parse_pairs(pairs_text)
    logger.info("Loaded %d pairs from veri_test2.txt", len(all_pairs))

    # Step 2: select balanced subset
    selected = _select_pairs(all_pairs, n_same=n_same, n_diff=n_diff)
    logger.info(
        "Selected %d pairs (%d same, %d different)",
        len(selected),
        sum(r[0] for r in selected),
        sum(1 - r[0] for r in selected),
    )

    # Collect unique video IDs needed
    video_ids: set[str] = set()
    for _, p1, p2 in selected:
        video_ids.add(_video_id(p1))
        video_ids.add(_video_id(p2))
    logger.info("Need %d unique YouTube videos", len(video_ids))

    if dry_run:
        print(f"[DRY RUN] Would download {len(video_ids)} videos to {clips_dir}")
        print(f"[DRY RUN] Would write {len(selected)} pairs to {out / 'pairs.csv'}")
        return

    # Step 3: download videos
    downloaded: dict[str, bool] = {}
    for i, vid_id in enumerate(sorted(video_ids), 1):
        out_path = clips_dir / f"{vid_id}.mp4"
        ok = _download_clip(vid_id, out_path)
        downloaded[vid_id] = ok
        status = "OK  " if ok else "FAIL"
        print(f"  [{i:3d}/{len(video_ids)}] {vid_id}  {status}")

    n_ok = sum(downloaded.values())
    logger.info("Downloaded %d/%d videos successfully", n_ok, len(video_ids))

    # Step 4: write pairs.csv (only pairs where both clips downloaded)
    valid_pairs: list[tuple[int, str, str]] = []
    for label, p1, p2 in selected:
        vid1, vid2 = _video_id(p1), _video_id(p2)
        if downloaded.get(vid1) and downloaded.get(vid2):
            clip1 = f"{vid1}.mp4"
            clip2 = f"{vid2}.mp4"
            valid_pairs.append((label, clip1, clip2))

    pairs_csv = out / "pairs.csv"
    with pairs_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["label", "clip1_path", "clip2_path"])
        writer.writerows(valid_pairs)

    n_same_written = sum(r[0] for r in valid_pairs)
    n_diff_written = sum(1 - r[0] for r in valid_pairs)
    print(f"\nWrote {len(valid_pairs)} pairs to {pairs_csv}")
    print(f"  same-person : {n_same_written}")
    print(f"  different   : {n_diff_written}")
    print(f"\nRun the eval with:")
    print(f"  python scripts/eval_video_pipeline.py --pairs {pairs_csv}")
    print(f"  pytest tests/test_eval_video_pipeline.py -m eval -v")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", default="data/voxceleb_mini", help="Output directory")
    p.add_argument(
        "--pairs",
        type=int,
        default=50,
        help="Total pairs to download (split evenly same/different)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(
        out_dir=args.out,
        n_same=args.pairs // 2,
        n_diff=args.pairs - args.pairs // 2,
        dry_run=args.dry_run,
    )
