# VMS Test Video Generation Brief

Use this document as a prompt for AI video generation tools (Runway Gen-3,
Kling AI, Sora, Pika, Luma Dream Machine, or equivalent). Generate each
scenario as a separate video clip. Each clip is self-contained and tests one
specific behavior of the VMS system.

---

## Environment (apply to ALL clips)

**Setting:** Indoor manufacturing plant floor. Concrete floor, industrial
shelving, machinery in the background. Fluorescent overhead lighting with
occasional shadows. Some areas marked with yellow floor tape indicating
restricted zones.

**Camera perspective:** Fixed CCTV-style ceiling mount, approximately
3–4 metres high, angled 30–45 degrees downward. Wide-angle lens (slightly
fisheye). The entire floor area is visible; people appear at roughly 1/4 to
1/3 of frame height.

**People:** Factory workers in high-visibility yellow/orange safety vests.
Mix of: hard hats (white, yellow, red), face masks (some wearing, some not),
safety glasses. Varied heights and builds. Some carry clipboards or tools.

**Technical specs for all clips:**
- Resolution: 1920×1080 (HD)
- Frame rate: 25fps
- Color space: natural, slightly desaturated industrial tone
- No camera movement (fixed mount)
- No text overlays or watermarks
- Save as MP4 H.264

---

## Scenario 1: Basic Cross-Camera Re-ID (Single Person)
**Purpose:** Validate that a confirmed gallery is built and the same person
is re-identified when entering a second camera's field of view.

**Duration:** 30 seconds

**Script:**
- Seconds 0–14: One worker (yellow vest, white hard hat, no mask) enters
  from the LEFT side of frame, walks slowly across the floor toward the
  right side, face clearly visible to camera for at least 8 seconds.
  Worker exits RIGHT side of frame.
- Seconds 15–30: Same worker enters from the LEFT side again (simulating
  a second camera picking them up), walks right, face visible.
  Worker should appear identical in clothing and build to the first segment.

**Key requirements:**
- Face must be clearly visible (frontal or near-frontal, not obscured)
  for at least 8 continuous seconds in each segment
- Worker walks at a normal pace (not running)
- Good even lighting on the face throughout

**Test parameters this validates:**
- `reid_confirm_after_sightings=3`: enough frames to build gallery
- `reid_gallery_size=8`: gallery fills to capacity
- `reid_confirmed_sim=0.60`: real AdaFace similarity range for same person
- `reid_cross_cam_sim=0.65`: unconfirmed threshold
- `reid_margin=0.05`: single person, no competing identities

---

## Scenario 2: Multi-Person Cross-Camera Re-ID (5 People)
**Purpose:** Validate that the per-gid margin check correctly separates
5 simultaneous identities across cameras.

**Duration:** 45 seconds

**Script:**
- Seconds 0–22: Five workers enter from the left one by one, spaced 3
  seconds apart. Each has slightly different clothing or hard hat colour
  (white, yellow, orange, red, blue hat). All walk across the frame.
  Faces are visible to the camera. All five exit RIGHT.
- Seconds 23–45: The SAME five workers enter from the LEFT again in any
  order. Their appearance must match their earlier appearance exactly.

**Key requirements:**
- All five faces clearly visible at some point during their walk
- Workers should not crowd together (maintain 1 metre spacing)
- Distinct visual differences between workers (hat colour, height, vest)

**Test parameters this validates:**
- `reid_margin=0.05`: must distinguish 5 identities cleanly
- Gallery matching with 5 simultaneous candidates in registry
- Correct global_track_id assignment for each person

---

## Scenario 3: Face Occlusion — Body Re-ID Fallback
**Purpose:** Validate that `BodyEmbedder` (OSNet) provides re-ID when
face detection fails due to occlusion.

**Duration:** 35 seconds

**Script:**
- Seconds 0–17: Three workers walk across the frame FACING AWAY from the
  camera (backs to camera), or wearing full face masks, or hard hat pulled
  low covering the face. Body and gait are clearly visible. Workers exit RIGHT.
- Seconds 18–35: The SAME three workers re-enter from LEFT with the same
  body occlusion (back to camera / masked / hat low). They should be
  distinguishable by body size and vest colour.

**Key requirements:**
- Face should NOT be clearly visible in this clip (occluded by mask,
  back-facing, or hard hat angle)
- Bodies must be clearly visible (full height, not behind obstacles)
- Consistent clothing/body appearance between segments

**Test parameters this validates:**
- `Tracklet.body_embedding`: populated when face absent
- `BodyEmbedder` crop extraction (OSNet x1.0)
- Body gallery matching via `body_gallery` in `_TrackletEntry`
- `reid_confirmed_sim=0.60` applied to body embedding comparisons

---

## Scenario 4: Crowd Density — High Occupancy Zone
**Purpose:** Validate `CROWD_DENSITY` anomaly detector and `HeadCountAggregator`
under load. Also stress-tests re-ID with 15+ simultaneous persons.

**Duration:** 60 seconds

**Script:**
- Seconds 0–15: 3 workers in the frame moving around normally.
- Seconds 16–30: Additional workers enter from both sides. By second 25,
  there are 10 workers in frame. Some stop and talk. Zone is getting crowded.
- Seconds 31–50: Peak crowd. 15–20 workers visible simultaneously, spread
  across the floor. Some huddle near machinery (simulating shift change).
  Workers overlap, partially occlude each other.
- Seconds 51–60: Crowd disperses; workers leave in groups.

**Key requirements:**
- Workers should be individuals (not clones) — vary heights, builds, hat colours
- Natural movement (some walk, some stand, some gesture)
- Camera must capture all of them within the same frame

**Test parameters this validates:**
- `CROWD_DENSITY` detector: zone head count threshold crossing
- `HeadCountAggregator`: `on_tracking_event` + `snapshot()` under load
- `reid_gallery_size=8` + `reid_confirm_after_sightings=3` under 15+ persons
- Per-gid margin check with 15+ competing identities in registry
- Memory eviction: `evict_stale()` under high registry load
- `reid_margin=0.05`: still above noise floor with many persons

---

## Scenario 5: Intrusion — Restricted Zone Entry
**Purpose:** Validate `INTRUSION` anomaly detector (zone polygon crossing).

**Duration:** 25 seconds

**Script:**
- Seconds 0–8: One worker walks normally in the safe area (left side of
  frame). A clearly visible yellow-taped boundary line is visible on the
  floor 2/3 of the way across the frame.
- Seconds 9–16: The worker approaches and STEPS OVER the yellow tape line,
  entering the restricted zone (right side). Worker moves into the
  restricted area and stands there.
- Seconds 17–25: Worker remains in the restricted zone, then slowly exits
  the way they came.

**Key requirements:**
- Yellow floor tape boundary must be clearly visible
- The moment of zone crossing should be unambiguous (one clear step over)
- Worker face should be visible when entering

**Test parameters this validates:**
- `INTRUSION` detector: `zone_presence` entry event
- `ZonePresenceTracker.update()`: `_open()` / `_close()` transitions
- `AlertFSM`: sustain_ms, cooldown_ms, dedup_key logic
- Homography projection: bbox foot-point → floor coordinates
- `point_in_polygon` geometry for zone boundary

---

## Scenario 6: Loitering — Extended Zone Dwell
**Purpose:** Validate `LOITERING` anomaly detector (dwell time threshold).

**Duration:** 90 seconds

**Script:**
- Seconds 0–10: Worker enters frame, walks to a spot near a piece of
  machinery in the centre of the frame.
- Seconds 11–75: Worker stays in roughly the same area. They pace slowly
  back and forth within a 2-metre radius, occasionally look at their phone
  or clipboard, but do NOT leave the area.
- Seconds 76–90: Worker finally walks away and exits the frame.

**Key requirements:**
- Worker must stay visibly in-frame for the full 65-second dwell period
- Small movement is fine (pacing, turning) but no large displacement
- Face should be intermittently visible (turning to face camera sometimes)

**Test parameters this validates:**
- `LOITERING` detector: dwell time threshold (typically 60s)
- `AlertFSM.sustain_ms`: trigger only after sustained presence
- `ZonePresenceTracker`: single zone entry, no exit during dwell
- `HeadCountAggregator`: steady count of 1 for the dwell period

---

## Scenario 7: Violence — Physical Altercation
**Purpose:** Validate `VIOLENCE` detector (`ViolenceModel` MoViNet A2 score).

**Duration:** 20 seconds

**Script:**
- Seconds 0–5: Two workers stand facing each other, having a conversation.
  Normal posture, no aggression.
- Seconds 6–15: An argument develops. Workers gesture aggressively, one
  pushes the other, the other pushes back. Physical contact occurs (pushing,
  grabbing). Movement is fast and erratic.
- Seconds 16–20: A third worker enters and separates them. Situation calms.

**Key requirements:**
- At least 2 people clearly in frame during altercation
- Fast, erratic body movement (the MoViNet model scores motion energy)
- Faces at least partially visible
- Avoid truly graphic violence — pushing/shoving is sufficient

**Test parameters this validates:**
- `ViolenceModel.score_frame()`: MoViNet A2 Stream score
- `violence_gate_min_persons=2`: trigger only with >= 2 persons
- `violence_threshold=0.65`: score must cross this value
- `AlertFSM` sustain_ms: brief altercation should still trigger alert
- `DetectionFrame.violence_score`: populated correctly

---

## Scenario 8: Unknown Person — Not in Enrollment Database
**Purpose:** Validate `UNKNOWN_PERSON` detector (FAISS misses → alert).

**Duration:** 20 seconds

**Script:**
- Seconds 0–10: Visitor in civilian clothes (no safety vest, no hard hat —
  a clear visual distinction from enrolled workers) enters from the right
  side, looking around as if unfamiliar with the space.
- Seconds 11–20: Visitor continues walking through the facility. Their face
  is clearly visible to the camera.

**Key requirements:**
- Person must look distinctly different from a standard worker
  (no vest, no hard hat, different clothing style)
- Face clearly visible and well-lit throughout

**Test parameters this validates:**
- `UNKNOWN_PERSON` detector: FAISS search returns no match above `adaface_min_sim=0.72`
- `ReIdService.identify()`: returns None for unknown
- `adaface_min_sim=0.72` + `reid_margin=0.08`: no false positive match
- Alert triggered after `reid_confirm_after_sightings` failed identifications

---

## Scenario 9: Person Lost — Disappears Mid-Track
**Purpose:** Validate `PERSON_LOST` detector (global_track_id disappears).

**Duration:** 30 seconds

**Script:**
- Seconds 0–12: One worker walks slowly across the frame, face visible.
  They are clearly tracked (gallery should build up).
- Seconds 13–16: Worker walks behind a large piece of machinery or shelving
  unit that blocks the camera's view completely. Worker does NOT reappear.
- Seconds 17–30: Empty area where worker was. Camera shows no movement.
  Worker is gone.

**Key requirements:**
- The obstruction (machinery/shelving) must completely block the person
  from camera view after second 12
- Worker should not reappear in any part of the frame after the obstruction
- At least 10 seconds of clear tracking before disappearance

**Test parameters this validates:**
- `PERSON_LOST` detector: confirmed track disappears for > X seconds
- `reid_stale_ms=300_000` vs `reid_confirmed_stale_ms=600_000`:
  confirmed person should stay in registry longer
- `evict_stale()`: timing of when the tracklet is cleaned up
- `AlertFSM`: trigger after absence exceeds threshold

---

## Scenario 10: Re-ID After Long Absence (Topology Gate Validation)
**Purpose:** Validate `CameraTopology` transit time gate — correct rejection
of instant cross-camera appearance and acceptance of plausible transit.

**Duration:** 50 seconds

**Script:**
Shoot this as a SINGLE continuous clip with one person:
- Seconds 0–20: Worker walks across the frame LEFT to RIGHT. Face visible
  for at least 12 seconds. Worker exits RIGHT edge of frame.
- Seconds 21–25: EMPTY FRAME. No people visible. (Simulates transit time.)
- Seconds 26–50: Same worker re-enters from LEFT, walks RIGHT again.

When testing:
- In the simulation script, set `--split 0.5` (frame 0–25 = cam1, 26–50 = cam2)
- Configure `VMS_REID_CAMERA_TOPOLOGY_JSON={"1-2": {"min_ms": 5000, "max_ms": 60000}}`
  The 5-second minimum transit (5000ms) should PASS for 5s empty gap.
- To test REJECTION: edit to `min_ms=30000` — the 5s gap is too fast → new UUID expected.

**Key requirements:**
- The same person MUST look identical in both halves of the clip
- Clear face visibility in both halves
- The empty middle section must be truly empty (no other faces)

**Test parameters this validates:**
- `CameraTopology.transit_ok()`: min/max window enforcement
- `reid_camera_topology_json`: JSON config parsing
- `elapsed_ms = now_ms - entry.last_seen_ms`: timing calculation
- Per-gid margin with same person on two cameras simultaneously

---

## Scenario 11: Multiple Cameras — Simultaneous Coverage (Future)
**Purpose:** Future test for 4-camera topology graph validation.
(Requires the simulation script to be extended to 4 virtual cameras.)

**Duration:** 60 seconds

**Script:**
Divide the frame into 4 quadrants (representing 4 camera angles):
- Top-left quadrant: entry zone (door)
- Top-right quadrant: production floor A
- Bottom-left quadrant: production floor B
- Bottom-right quadrant: exit zone

3 workers enter top-left, move through the quadrants in sequence over 60s.
Each quadrant transition simulates a camera handoff.

**Test parameters this validates (future):**
- Multi-hop re-ID: person seen on cam1 → cam2 → cam3 → cam4
- `CameraTopology` with 4+ cameras and directed adjacency graph
- Gallery accumulation across 4 camera appearances
- `reid_confirmed_stale_ms=600_000`: person survives all 4 hops

---

## Scenario 12: Low Light / Night Mode (Future)
**Purpose:** Validate model performance under poor lighting (IR cameras,
dim factory areas).

**Duration:** 30 seconds
**Lighting:** Dim overhead lights, some areas in near-darkness. Grayscale
or near-grayscale appearance (simulating IR camera output).

**Script:** Same as Scenario 1 (single person cross-camera) but under
dim lighting. Worker's face should be visible but with reduced contrast.

**Test parameters this validates (future):**
- `scrfd_conf=0.60`: does face detection still trigger under low light?
- `adaface_min_sim=0.72`: do embeddings degrade enough to miss threshold?
- `min_blur=25.0`: blur filter triggers on low-light frames
- `min_face_px=40`: minimum face size still met?

---

## Generation Instructions for AI Tool

When submitting to an AI video generation tool, use this template
per scenario:

```
Generate a 30-second (adjust per scenario) CCTV-style surveillance video
shot from a fixed ceiling-mounted camera at 3-4 metres height, angled 45
degrees downward, wide-angle lens, 1920x1080 resolution at 25fps.

Setting: indoor manufacturing plant with concrete floor, industrial
shelving, fluorescent overhead lighting.

[Paste the scenario SCRIPT section here verbatim]

Style: realistic, no camera movement, natural industrial lighting,
slightly desaturated. No text overlays. Output as MP4 H.264.
```

---

## Quick Test Matrix

| Scenario | Script flag | Key threshold tested | Pass condition |
|---|---|---|---|
| 1: Single person | `--split 0.5 --diag` | `reid_confirmed_sim` | 1/1 matched |
| 2: 5 persons | `--split 0.5 --diag` | `reid_margin` | 5/5 matched |
| 3: Face occluded | `--split 0.5 --diag` | `body_gallery` | 3/3 matched via body |
| 4: Crowd 15+ | `--split 0.5 --verbose` | margin under load | 15/15 matched |
| 5: Intrusion | run full pipeline | zone detector | alert fires |
| 6: Loitering | run full pipeline | dwell timer | alert at ~60s |
| 7: Violence | run full pipeline | violence score | score > 0.65 |
| 8: Unknown | run full pipeline | FAISS miss | UNKNOWN alert |
| 9: Person lost | run full pipeline | stale eviction | PERSON_LOST alert |
| 10: Topology | `--split 0.5 --diag` | transit_ok() | match/reject as configured |

Run the simulation script against each video:
```powershell
python scripts/simulate_cross_camera_reid.py --video scenario_01.mp4 --split 0.5 --diag
python scripts/simulate_cross_camera_reid.py --video scenario_02.mp4 --split 0.5 --diag
python scripts/simulate_cross_camera_reid.py --video scenario_03.mp4 --split 0.5 --diag --verbose
python scripts/simulate_cross_camera_reid.py --video scenario_04.mp4 --split 0.5 --diag
python scripts/simulate_cross_camera_reid.py --video scenario_10.mp4 --split 0.42 --diag
```

For scenarios 5–9 (full anomaly pipeline), use the main VMS server with
Redis + DB running and point cameras at the video via RTSP re-stream.
