"""Download Market-1501 via kagglehub and build test videos for the re-ID simulation.

Market-1501 image naming: PPPP_cCsS_FFFFFF_DD.jpg
  PPPP   = person ID (0001-1501; -1 = distractor junk)
  C      = camera ID (1-6)
  S      = sequence index
  FFFFFF = frame index within sequence
  DD     = detection index

Each image is a cropped person bounding box (~128x256px).
This script scales them up and composites them onto a 1280x720 factory-floor
background so SCRFD can detect the faces.

Output layout:
  data/market1501/                  raw downloaded images (read-only)
    bounding_box_test/
    bounding_box_train/
    query/
  data/test_videos/
    market1501_s01_single_person.mp4      scenario 1  (1 person, 2 cameras)
    market1501_s02_five_persons.mp4       scenario 2  (5 persons, 2 cameras)
    market1501_s04_crowd.mp4              scenario 4  (15 persons, 2 cameras)

Usage:
    python scripts/prepare_market1501.py

Requires: kagglehub, opencv-python, numpy
    pip install kagglehub opencv-python numpy
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
MARKET_DIR = DATA_DIR / "market1501"
VIDEOS_DIR = DATA_DIR / "test_videos"

# Output frame size — large enough for SCRFD to find faces (person at ~1/3 height)
FRAME_W, FRAME_H = 1280, 720
# Person crop target height in the composite frame
PERSON_H = 380   # ~53% of frame height → face ~90px tall (above min_face_px=40)
FPS = 25
# Frames each image is held for (longer = more sightings = confirmed gallery)
HOLD_FRAMES = 12  # 12 frames @ 25fps = 0.48s per image


# --------------------------------------------------------------------------
# Image metadata
# --------------------------------------------------------------------------
class ImgMeta(NamedTuple):
    path: Path
    person_id: int
    camera_id: int
    frame_idx: int


_NAME_RE = re.compile(r"^(\d{4})_c(\d)s\d_(\d{6})_\d{2}\.jpg$", re.IGNORECASE)


def parse_images(folder: Path) -> list[ImgMeta]:
    results: list[ImgMeta] = []
    for p in sorted(folder.glob("*.jpg")):
        m = _NAME_RE.match(p.name)
        if not m:
            continue
        pid, cid, fidx = int(m[1]), int(m[2]), int(m[3])
        if pid <= 0:  # skip distractors (-1) and junk (-2)
            continue
        results.append(ImgMeta(path=p, person_id=pid, camera_id=cid, frame_idx=fidx))
    return results


def group_by_person_camera(
    images: list[ImgMeta],
) -> dict[int, dict[int, list[ImgMeta]]]:
    """Return {person_id: {camera_id: [sorted images]}}."""
    by_pc: dict[int, dict[int, list[ImgMeta]]] = defaultdict(lambda: defaultdict(list))
    for img in images:
        by_pc[img.person_id][img.camera_id].append(img)
    # Sort each list by frame_idx
    for pid in by_pc:
        for cid in by_pc[pid]:
            by_pc[pid][cid].sort(key=lambda x: x.frame_idx)
    return {pid: dict(cams) for pid, cams in by_pc.items()}


# --------------------------------------------------------------------------
# Frame compositing
# --------------------------------------------------------------------------
def _make_background() -> np.ndarray:  # type: ignore[type-arg]
    """Create a plain factory-floor-like background (gray concrete)."""
    bg = np.full((FRAME_H, FRAME_W, 3), (80, 75, 70), dtype=np.uint8)
    # Add subtle grid lines to look like floor tiles
    for y in range(0, FRAME_H, 80):
        cv2.line(bg, (0, y), (FRAME_W, y), (70, 65, 60), 1)
    for x in range(0, FRAME_W, 80):
        cv2.line(bg, (x, 0), (x, FRAME_H), (70, 65, 60), 1)
    return bg


_BG = _make_background()


def _scale_crop(img_bgr: np.ndarray, target_h: int) -> np.ndarray:  # type: ignore[type-arg]
    """Scale a person crop so its height equals target_h."""
    h, w = img_bgr.shape[:2]
    scale = target_h / h
    new_w = max(1, int(w * scale))
    return cv2.resize(img_bgr, (new_w, target_h), interpolation=cv2.INTER_LANCZOS4)


def composite_frame(
    persons: list[tuple[np.ndarray, int]],  # (crop_bgr, x_centre_position)
) -> np.ndarray:  # type: ignore[type-arg]
    """Paste person crops onto the background at given x positions."""
    frame = _BG.copy()
    for crop, cx in persons:
        scaled = _scale_crop(crop, PERSON_H)
        h, w = scaled.shape[:2]
        x1 = max(0, cx - w // 2)
        y1 = FRAME_H - h - 20  # stand on the "floor"
        x2, y2 = min(FRAME_W, x1 + w), min(FRAME_H, y1 + h)
        crop_w = x2 - x1
        crop_h = y2 - y1
        frame[y1:y2, x1:x2] = scaled[:crop_h, :crop_w]
    return frame


def _x_positions(n: int, margin: int = 120) -> list[int]:
    """Evenly space n persons across the frame width."""
    if n == 1:
        return [FRAME_W // 2]
    step = (FRAME_W - 2 * margin) // (n - 1)
    return [margin + i * step for i in range(n)]


# --------------------------------------------------------------------------
# Video writer
# --------------------------------------------------------------------------
def write_video(output_path: Path, frame_groups: list[list[np.ndarray]]) -> None:  # type: ignore[type-arg]
    """Write groups of frames to an mp4 file.

    Each inner list is a sequence of frames that play sequentially.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
    writer = cv2.VideoWriter(str(output_path), fourcc, FPS, (FRAME_W, FRAME_H))
    for frames in frame_groups:
        for frame in frames:
            writer.write(frame)
    writer.release()
    size_mb = output_path.stat().st_size / 1_048_576
    print(f"  -> {output_path.name}  ({sum(len(g) for g in frame_groups)} frames, {size_mb:.1f}MB)")


def imgs_to_frames(
    images: list[ImgMeta],
    positions: list[int],
    other_persons: list[tuple[list[ImgMeta], int]] | None = None,
) -> list[np.ndarray]:  # type: ignore[type-arg]
    """Convert a list of images to composite video frames.

    Each image is held for HOLD_FRAMES frames. Multiple persons can appear
    simultaneously by passing other_persons = [(image_list, x_pos), ...].
    """
    frames: list[np.ndarray] = []
    for i, img_meta in enumerate(images):
        crop = cv2.imread(str(img_meta.path))
        if crop is None:
            continue
        persons_in_frame = [(crop, positions[0])]
        if other_persons:
            for other_imgs, ox in other_persons:
                idx = min(i, len(other_imgs) - 1)
                other_crop = cv2.imread(str(other_imgs[idx].path))
                if other_crop is not None:
                    persons_in_frame.append((other_crop, ox))
        composite = composite_frame(persons_in_frame)
        for _ in range(HOLD_FRAMES):
            frames.append(composite)
    return frames


# --------------------------------------------------------------------------
# Person selection helpers
# --------------------------------------------------------------------------
def pick_persons_with_two_cameras(
    by_pc: dict[int, dict[int, list[ImgMeta]]],
    min_imgs_per_cam: int = 6,
    count: int = 15,
) -> list[tuple[int, int, int]]:
    """Return up to `count` (person_id, cam_a, cam_b) tuples.

    Persons must have >= min_imgs_per_cam images on both cam_a and cam_b.
    Prefer camera pairs (1,2) first, then other pairs.
    """
    candidates: list[tuple[int, int, int]] = []
    for pid, cams in by_pc.items():
        cam_ids = sorted(cams.keys())
        for i in range(len(cam_ids)):
            for j in range(i + 1, len(cam_ids)):
                ca, cb = cam_ids[i], cam_ids[j]
                if len(cams[ca]) >= min_imgs_per_cam and len(cams[cb]) >= min_imgs_per_cam:
                    candidates.append((pid, ca, cb))
    # Prefer cam1+cam2 pairs
    candidates.sort(key=lambda x: (0 if (x[1], x[2]) == (1, 2) else 1, x[0]))
    # Deduplicate by person_id (pick best pair per person)
    seen: set[int] = set()
    result: list[tuple[int, int, int]] = []
    for pid, ca, cb in candidates:
        if pid not in seen:
            seen.add(pid)
            result.append((pid, ca, cb))
        if len(result) >= count:
            break
    return result


# --------------------------------------------------------------------------
# Scenario builders
# --------------------------------------------------------------------------
def build_scenario_single_person(
    by_pc: dict[int, dict[int, list[ImgMeta]]],
    out_path: Path,
) -> None:
    print("Building scenario 1: single person, 2 cameras...")
    chosen = pick_persons_with_two_cameras(by_pc, min_imgs_per_cam=8, count=1)
    if not chosen:
        print("  SKIP: no suitable person found")
        return
    pid, ca, cb = chosen[0]
    imgs_cam1 = by_pc[pid][ca][:20]   # cap at 20 images per camera
    imgs_cam2 = by_pc[pid][cb][:20]
    print(f"  person={pid:04d}  cam{ca}={len(imgs_cam1)}imgs  cam{cb}={len(imgs_cam2)}imgs")
    # 2 second gap between cameras (simulate transit time)
    gap_frames = [_BG.copy() for _ in range(FPS * 2)]
    frames_cam1 = imgs_to_frames(imgs_cam1, [FRAME_W // 2])
    frames_cam2 = imgs_to_frames(imgs_cam2, [FRAME_W // 2])
    write_video(out_path, [frames_cam1, gap_frames, frames_cam2])


def build_scenario_five_persons(
    by_pc: dict[int, dict[int, list[ImgMeta]]],
    out_path: Path,
) -> None:
    print("Building scenario 2: five persons, 2 cameras...")
    chosen = pick_persons_with_two_cameras(by_pc, min_imgs_per_cam=6, count=5)
    if len(chosen) < 5:
        print(f"  SKIP: only found {len(chosen)} suitable persons (need 5)")
        return
    positions = _x_positions(5)
    cam1_group: list[np.ndarray] = []
    cam2_group: list[np.ndarray] = []
    # Show all 5 persons simultaneously, same position in both halves
    max_len_c1 = max(len(by_pc[p][ca][:15]) for p, ca, _ in chosen)
    max_len_c2 = max(len(by_pc[p][cb][:15]) for p, _, cb in chosen)
    for frame_i in range(max_len_c1):
        persons_in_frame = []
        for idx, (pid, ca, cb) in enumerate(chosen):
            imgs = by_pc[pid][ca][:15]
            img_idx = min(frame_i, len(imgs) - 1)
            crop = cv2.imread(str(imgs[img_idx].path))
            if crop is not None:
                persons_in_frame.append((crop, positions[idx]))
        composite = composite_frame(persons_in_frame)
        for _ in range(HOLD_FRAMES):
            cam1_group.append(composite)
    for frame_i in range(max_len_c2):
        persons_in_frame = []
        for idx, (pid, ca, cb) in enumerate(chosen):
            imgs = by_pc[pid][cb][:15]
            img_idx = min(frame_i, len(imgs) - 1)
            crop = cv2.imread(str(imgs[img_idx].path))
            if crop is not None:
                persons_in_frame.append((crop, positions[idx]))
        composite = composite_frame(persons_in_frame)
        for _ in range(HOLD_FRAMES):
            cam2_group.append(composite)
    gap = [_BG.copy() for _ in range(FPS * 2)]
    pids_str = ", ".join(f"{p:04d}" for p, _, _ in chosen)
    print(f"  persons={pids_str}")
    write_video(out_path, [cam1_group, gap, cam2_group])


def build_scenario_crowd(
    by_pc: dict[int, dict[int, list[ImgMeta]]],
    out_path: Path,
    n_persons: int = 15,
) -> None:
    print(f"Building scenario 4: crowd ({n_persons} persons), 2 cameras...")
    chosen = pick_persons_with_two_cameras(by_pc, min_imgs_per_cam=5, count=n_persons)
    if len(chosen) < n_persons:
        print(f"  Using {len(chosen)} persons (fewer than {n_persons} available)")
    positions = _x_positions(len(chosen), margin=60)
    cam1_group: list[np.ndarray] = []
    cam2_group: list[np.ndarray] = []
    max_imgs = max(
        (max(len(by_pc[p][ca][:10]), len(by_pc[p][cb][:10])) for p, ca, cb in chosen),
        default=0,
    )
    for frame_i in range(max_imgs):
        p1, p2 = [], []
        for idx, (pid, ca, cb) in enumerate(chosen):
            imgs_c1 = by_pc[pid][ca][:10]
            imgs_c2 = by_pc[pid][cb][:10]
            i1 = min(frame_i, len(imgs_c1) - 1)
            i2 = min(frame_i, len(imgs_c2) - 1)
            c1 = cv2.imread(str(imgs_c1[i1].path))
            c2 = cv2.imread(str(imgs_c2[i2].path))
            if c1 is not None:
                p1.append((c1, positions[idx]))
            if c2 is not None:
                p2.append((c2, positions[idx]))
        comp1 = composite_frame(p1)
        comp2 = composite_frame(p2)
        for _ in range(HOLD_FRAMES):
            cam1_group.append(comp1)
            cam2_group.append(comp2)
    gap = [_BG.copy() for _ in range(FPS * 2)]
    print(f"  {len(chosen)} persons selected")
    write_video(out_path, [cam1_group, gap, cam2_group])


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("Market-1501 Dataset Preparation")
    print("=" * 60)

    # Step 1: Download
    print("\n[1/4] Downloading Market-1501 via kagglehub...")
    try:
        import kagglehub
        raw_path = kagglehub.dataset_download("pengcw1/market-1501")
        print(f"  Downloaded to: {raw_path}")
    except Exception as e:
        print(f"  ERROR: {e}")
        print("  Make sure you are logged in: run  kaggle api init  or set KAGGLE_USERNAME + KAGGLE_KEY")
        sys.exit(1)

    # Step 2: Locate the bounding_box_test folder
    print("\n[2/4] Locating image folder...")
    raw_root = Path(raw_path)
    # kagglehub may nest: raw_path/Market-1501-v15.09.15/bounding_box_test
    bbox_test = None
    for candidate in [
        raw_root / "bounding_box_test",
        raw_root / "Market-1501-v15.09.15" / "bounding_box_test",
        *raw_root.rglob("bounding_box_test"),
    ]:
        if isinstance(candidate, Path) and candidate.is_dir():
            bbox_test = candidate
            break
    if bbox_test is None:
        print(f"  ERROR: bounding_box_test not found under {raw_root}")
        print(f"  Contents: {list(raw_root.iterdir())}")
        sys.exit(1)
    print(f"  Found: {bbox_test}")

    # Step 3: Copy/symlink to data/market1501 for reference
    print("\n[3/4] Organising data/market1501/...")
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    dest = MARKET_DIR / "bounding_box_test"
    if not dest.exists():
        print(f"  Copying images to {dest} ...")
        shutil.copytree(str(bbox_test), str(dest))
    else:
        print(f"  Already exists: {dest} (skipping copy)")

    # Step 4: Parse and build videos
    print("\n[4/4] Building test videos...")
    images = parse_images(dest)
    print(f"  Parsed {len(images)} images")
    by_pc = group_by_person_camera(images)
    print(f"  {len(by_pc)} unique persons  |  "
          f"cameras: {sorted({c for cams in by_pc.values() for c in cams.keys()})}")

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    build_scenario_single_person(
        by_pc,
        VIDEOS_DIR / "market1501_s01_single_person.mp4",
    )
    build_scenario_five_persons(
        by_pc,
        VIDEOS_DIR / "market1501_s02_five_persons.mp4",
    )
    build_scenario_crowd(
        by_pc,
        VIDEOS_DIR / "market1501_s04_crowd.mp4",
        n_persons=15,
    )

    print("\n" + "=" * 60)
    print("Done. Test videos written to data/test_videos/")
    print("Run the simulation with:")
    print("  python scripts/simulate_cross_camera_reid.py \\")
    print("    --video data/test_videos/market1501_s01_single_person.mp4 \\")
    print("    --split 0.47 --diag")
    print("  (--split 0.47 skips the 2-second gap, putting cam1 in first half)")
    print("=" * 60)


if __name__ == "__main__":
    main()
