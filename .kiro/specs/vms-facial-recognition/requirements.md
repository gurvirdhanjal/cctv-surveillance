# Requirements Document

## Introduction

A plant-floor Video Management System (VMS) supporting 52–53 IP cameras with identity-aware surveillance. The system detects, recognises, and tracks registered employees and unknown visitors across cameras in real time using facial recognition and cross-camera re-identification. It serves two primary user groups: security guards (live alerts, person tracking) and plant management (analytics, zone reports). All processing runs on-premises on a single GPU server.

## Glossary

- **VMS**: The Video Management System described in this document.
- **Ingestion_Worker**: An OS process that decodes RTSP/webcam streams, writes frames to shared memory, and publishes frame-pointer events to Redis Streams.
- **Inference_Engine**: A GPU OS process that reads frame pointers, runs SCRFD + AdaFace + ByteTrack, and publishes confirmed tracklets.
- **Identity_Service**: An OS process that performs cross-camera re-identification, homography projection, alert FSM evaluation, and DB writes.
- **DB_Writer**: An async process that batch-inserts tracking events into PostgreSQL.
- **API_Server**: The FastAPI application serving REST and WebSocket endpoints.
- **SCRFD_Detector**: The SCRFD 2.5g ONNX model used for face detection.
- **AdaFace_Embedder**: The AdaFace IR50 ONNX model producing 512-dim face embeddings.
- **ByteTracker**: The per-camera ByteTrack instance producing stable local track IDs.
- **FAISS_Index**: The in-memory FAISS flat IP index used for cross-camera re-identification.
- **Alert_FSM**: The finite state machine that evaluates alert entry, sustain, cooldown, and reset conditions.
- **SHM_Slot**: A shared memory segment owned by one Ingestion_Worker, holding one frame with a 16-byte header (seq_id + timestamp_ms).
- **Redis_Stream**: A Redis Streams channel used as the inter-process message bus.
- **global_track_id**: A UUID assigned by the Identity_Service to a person across all cameras.
- **local_track_id**: A ByteTrack-assigned integer ID per camera per tracklet.
- **Guard**: A system user with the `guard` role who monitors live alerts and tracks persons.
- **Manager**: A system user with the `manager` role who accesses analytics and reports.
- **Admin**: A system user with the `admin` role who manages enrollment, cameras, zones, and permissions.

---

## Requirements

### Requirement 1: Real-Time Face Detection

**User Story:** As a Guard, I want the system to detect faces in live camera feeds, so that I can be alerted to the presence of unknown persons.

#### Acceptance Criteria

1. WHEN a video frame is received from a camera, THE SCRFD_Detector SHALL detect all faces with bounding-box dimension ≥ 40 pixels and confidence ≥ 0.60.
2. WHEN a detected face has a Laplacian variance < 25.0, THE SCRFD_Detector SHALL discard the face crop without producing an embedding.
3. WHEN a detected face bounding box is smaller than 40 × 40 pixels, THE SCRFD_Detector SHALL discard the detection.
4. THE SCRFD_Detector SHALL process frames at 640 × 640 input resolution using the CUDAExecutionProvider.
5. IF the GPU is unavailable, THEN THE SCRFD_Detector SHALL fall back to CPUExecutionProvider and continue processing.

---

### Requirement 2: Face Embedding and Identity Matching

**User Story:** As a Guard, I want detected faces to be matched against the employee database, so that I know whether a person is registered or unknown.

#### Acceptance Criteria

1. WHEN a valid face crop is detected, THE AdaFace_Embedder SHALL produce a 512-dimensional L2-normalised embedding.
2. WHEN an embedding is produced, THE Identity_Service SHALL compare it against the FAISS_Index using cosine similarity.
3. WHEN the best cosine similarity ≥ 0.72 AND the margin between best and second-best similarity ≥ 0.08, THE Identity_Service SHALL assign the matching `person_id` to the tracklet.
4. WHEN the best cosine similarity < 0.72, THE Identity_Service SHALL treat the person as unknown and assign no `person_id`.
5. THE FAISS_Index SHALL be rebuilt from the `person_embeddings` table at Identity_Service startup.
6. THE FAISS_Index SHALL contain only embeddings from persons seen within the last 5 minutes for cross-camera re-identification queries.

---

### Requirement 3: Per-Camera Person Tracking

**User Story:** As a Guard, I want persons to be tracked consistently within each camera view, so that I can follow a person's movement without identity flickering.

#### Acceptance Criteria

1. WHEN person detections are received for a camera frame, THE ByteTracker SHALL assign a stable `local_track_id` to each confirmed tracklet.
2. THE ByteTracker SHALL maintain one independent instance per camera.
3. WHEN a tracklet is lost for more than the ByteTrack configuration's `track_buffer` frames, THE ByteTracker SHALL remove the tracklet from the active set.
4. THE Inference_Engine SHALL publish confirmed tracklets to the `detections` Redis_Stream with fields: `cam_id`, `local_track_id`, `bbox`, `embedding`, `timestamp_ms`, `seq_id`.

---

### Requirement 4: Cross-Camera Re-Identification

**User Story:** As a Guard, I want a person to retain the same identity label as they move between cameras, so that I can track their path across the plant floor.

#### Acceptance Criteria

1. WHEN a new tracklet arrives, THE Identity_Service SHALL compare its embedding only against active tracklets in the same zone or adjacent zones (zone adjacency pre-filter).
2. WHEN cosine similarity ≥ 0.65 AND margin ≥ 0.08 against an existing tracklet, THE Identity_Service SHALL assign the existing `global_track_id` to the new tracklet.
3. WHEN no match meets the threshold, THE Identity_Service SHALL assign a new UUID as `global_track_id`.
4. THE Identity_Service SHALL log every match to the `reid_matches` table with `confidence`, `match_source`, `from_camera_id`, and `to_camera_id`.
5. WHEN a Guard manually corrects an identity via the UI, THE Identity_Service SHALL update all `tracking_events` rows with the same `global_track_id` and emit a `track_corrected` WebSocket event.

---

### Requirement 5: Floor Plan Position Mapping

**User Story:** As a Guard, I want to see a person's position on the floor plan, so that I can dispatch security to the correct location.

#### Acceptance Criteria

1. WHEN a camera has a calibrated homography matrix, THE Identity_Service SHALL project each tracklet's bounding-box centre to `floor_x`, `floor_y` coordinates using the stored 3 × 3 homography matrix.
2. WHEN a camera has no calibrated homography matrix, THE Identity_Service SHALL store `NULL` for `floor_x` and `floor_y` in `tracking_events`.
3. THE Admin SHALL be able to calibrate a camera homography by marking 4 reference points on a captured frame and matching them to the floor plan image.
4. WHEN the reprojection error of a calibration attempt is ≥ 2 pixels, THE API_Server SHALL reject the calibration and return a descriptive error.
5. THE API_Server SHALL store the validated homography matrix as a JSON row-major 9-float array in `cameras.homography_matrix`.

---

### Requirement 6: Real-Time Alert Generation

**User Story:** As a Guard, I want to receive immediate alerts for unknown persons and other security events, so that I can respond before an incident escalates.

#### Acceptance Criteria

1. WHEN a person with no `person_id` is continuously present in a camera frame for > 500ms, THE Alert_FSM SHALL emit an `UNKNOWN_PERSON` alert with severity HIGH.
2. WHEN a `global_track_id` is absent from all cameras for > 30 seconds, THE Alert_FSM SHALL emit a `PERSON_LOST` alert.
3. WHEN the number of persons in a zone exceeds `zones.max_capacity` continuously for > 10 seconds, THE Alert_FSM SHALL emit a `CROWD_DENSITY` alert.
4. THE Alert_FSM SHALL suppress duplicate alerts of the same `(alert_type, zone_id)` within a 60-second deduplication window.
5. THE Alert_FSM SHALL enforce a per-alert-type cooldown: `UNKNOWN_PERSON` 60s, `PERSON_LOST` 120s, `CROWD_DENSITY` 300s.
6. THE Alert_FSM SHALL evaluate alerts on `timestamp_ms` event time, not message arrival order.
7. WHEN an event arrives more than 5 seconds late relative to the current event time, THE Alert_FSM SHALL discard the event.
8. THE API_Server SHALL store no more than 10 active alerts per zone; additional alerts SHALL be grouped in the frontend.

---

### Requirement 7: Zone-Level Analytics and Dwell-Time Reporting

**User Story:** As a Manager, I want to see how long persons spend in each zone, so that I can optimise plant-floor workflows and identify bottlenecks.

#### Acceptance Criteria

1. WHEN a `global_track_id` enters a zone, THE Identity_Service SHALL insert a `zone_presence` record with `entered_at`.
2. WHEN a `global_track_id` exits a zone, THE Identity_Service SHALL update the `zone_presence` record with `exited_at`.
3. THE API_Server SHALL expose `GET /api/zones/{id}/presence?from=&to=` returning dwell-time records for the requested time range.
4. THE API_Server SHALL support CSV export of zone presence data.
5. THE API_Server SHALL provide daily person count, average dwell time, unknown person count, and camera uptime statistics.

---

### Requirement 8: Investigation Timeline Playback

**User Story:** As a Manager, I want to replay a person's movement history, so that I can investigate incidents after the fact.

#### Acceptance Criteria

1. THE API_Server SHALL expose `GET /api/persons/{id}/timeline?from=&to=` returning ordered `tracking_events` for one person within the requested time range.
2. THE API_Server SHALL expose `GET /api/persons/search?q=` supporting lookup by name and employee ID.
3. WHEN a Manager uses the time scrubber, THE Frontend SHALL reconstruct person movement trails from `tracking_events` for the selected time window.
4. THE Frontend SHALL display per-zone dwell times for a selected person over a 24-hour period.

---

### Requirement 9: Person Enrollment

**User Story:** As an Admin, I want to enroll employees with face samples, so that the system can recognise them across all cameras.

#### Acceptance Criteria

1. THE API_Server SHALL expose `POST /api/persons` accepting `full_name`, `employee_id`, `department`, and `person_type`.
2. THE API_Server SHALL expose `POST /api/persons/{id}/embeddings` accepting a face image and storing the resulting 512-dim embedding in `person_embeddings`.
3. WHEN an enrollment submission contains fewer than 6 face samples, THE API_Server SHALL return a 422 error with a descriptive message.
4. WHEN a face sample has quality_score below the configured threshold, THE API_Server SHALL reject the sample and return a descriptive error.
5. WHEN enrollment is complete, THE Identity_Service SHALL rebuild the FAISS_Index to include the new person's embeddings within 5 seconds.

---

### Requirement 10: Ingestion Pipeline

**User Story:** As a system operator, I want camera frames to be reliably ingested and distributed to the inference pipeline, so that no camera feed is a single point of failure.

#### Acceptance Criteria

1. THE Ingestion_Worker SHALL decode RTSP and webcam streams using OpenCV and write each frame to a SHM_Slot with a 16-byte header containing `seq_id` (u64) and `timestamp_ms` (u64).
2. THE Ingestion_Worker SHALL publish a frame-pointer event to the appropriate `frames:{group}` Redis_Stream containing `cam_id`, `shm_name`, `seq_id`, and `timestamp_ms`.
3. THE Redis_Stream SHALL be capped at MAXLEN 500 per group with approximate trimming.
4. WHEN the Inference_Engine reads a SHM_Slot and `now_ms - timestamp_ms > 200`, THE Inference_Engine SHALL skip the frame, XACK the message, and increment the `frames_dropped` metric.
5. WHEN an Ingestion_Worker crashes, THE system supervisor SHALL restart it within 5 seconds and XAUTOCLAIM SHALL recover unACKed messages after 10 seconds.
6. WHEN a Redis_Stream consumer lag exceeds 500 messages, THE VMS SHALL emit an admin alert.
7. WHEN a Redis message is delivered 3 times without ACK, THE VMS SHALL move it to a `dead_letter` stream and XACK the original.

---

### Requirement 11: Database Persistence

**User Story:** As a system operator, I want all tracking events persisted reliably to PostgreSQL, so that the investigation and analytics features have a complete audit trail.

#### Acceptance Criteria

1. THE DB_Writer SHALL batch-insert `tracking_events` rows using SQLAlchemy `executemany`, flushing every 500ms or every 100 rows, whichever comes first.
2. THE DB_Writer SHALL use `INSERT ... ON CONFLICT DO NOTHING` on the unique constraint `(camera_id, local_track_id, event_ts)` to prevent duplicate writes on retry.
3. WHEN a PostgreSQL write fails, THE DB_Writer SHALL retry 3 times with exponential backoff before buffering rows in a circular in-memory buffer of 50,000 rows.
4. WHEN the in-memory buffer is full, THE DB_Writer SHALL write overflow rows to a local JSON file for manual replay.
5. THE `tracking_events` table SHALL be partitioned by month using PostgreSQL declarative range partitioning (Phase 5).

---

### Requirement 12: API Authentication and Authorisation

**User Story:** As a system operator, I want all API endpoints protected by role-based access control, so that only authorised users can access sensitive data.

#### Acceptance Criteria

1. THE API_Server SHALL issue JWT tokens with 8-hour expiry on successful login.
2. THE API_Server SHALL enforce role-based route guards for roles: `guard`, `manager`, `admin`.
3. THE API_Server SHALL enforce zone-level access via `user_zone_permissions` and camera-level access via `user_camera_permissions` on every relevant endpoint.
4. WHEN a request carries an expired or invalid JWT, THE API_Server SHALL return HTTP 401.
5. WHEN a request is authenticated but lacks the required role or permission, THE API_Server SHALL return HTTP 403.

---

### Requirement 13: Real-Time WebSocket Updates

**User Story:** As a Guard, I want the live view to update in real time without polling, so that I see person movements and alerts as they happen.

#### Acceptance Criteria

1. THE API_Server SHALL emit `person_location` WebSocket events throttled to 5fps per `global_track_id`, containing only changed fields (diff-only).
2. THE API_Server SHALL emit `alert_fired` WebSocket events immediately with no throttle.
3. THE API_Server SHALL emit `track_corrected` WebSocket events immediately when an identity correction is applied.
4. THE API_Server SHALL emit `camera_snapshot` WebSocket events every 2 seconds per subscribed camera.
5. WHEN a WebSocket client reconnects, THE Frontend SHALL call `GET /api/state/snapshot` before processing the first diff event to rehydrate state.
6. THE API_Server SHALL publish WebSocket events to a Redis pub/sub channel so that all API_Server replicas fan out to their own connected clients.

---

### Requirement 14: System Observability and Health

**User Story:** As an Admin, I want to monitor the health of all pipeline components, so that I can detect and respond to failures before they affect security coverage.

#### Acceptance Criteria

1. THE VMS SHALL expose a Prometheus metrics endpoint per process reporting: inference latency (p50/p95/p99), frames dropped, Redis stream lag, DB write queue depth, and GPU utilisation.
2. THE VMS SHALL emit a structured JSON heartbeat to Redis key `heartbeat:{worker_id}` with a 15-second TTL, refreshed every 10 seconds.
3. WHEN a worker heartbeat expires, THE VMS SHALL emit an admin alert within 15 seconds.
4. THE API_Server SHALL expose `GET /api/health` returning the status of all workers, Redis connectivity, and PostgreSQL connectivity.
5. THE Frontend SHALL display per-worker status, GPU utilisation, PostgreSQL write queue depth, and Redis stream lag in the Admin health panel.

---

### Requirement 15: Degraded Mode Operation

**User Story:** As a Guard, I want the system to continue providing camera snapshots even when the message bus is unavailable, so that security coverage is not completely lost during outages.

#### Acceptance Criteria

1. WHEN Redis is unavailable, THE Ingestion_Worker SHALL buffer up to 200 frames per camera in an in-memory deque and retry the Redis connection every 2 seconds.
2. WHEN Redis is unavailable, THE Inference_Engine SHALL continue running locally with each detection assigned an ephemeral UUID; cross-camera re-identification SHALL be disabled.
3. WHEN Redis is unavailable, THE DB_Writer SHALL buffer writes to a local JSON file (max 100MB; oldest entries dropped when full) for replay on recovery.
4. WHEN Redis is unavailable, THE Frontend SHALL display a "System degraded — Re-ID offline" banner.
5. WHEN Redis recovers, THE Ingestion_Worker SHALL drain the in-memory buffer, discarding frames older than 5 seconds.
