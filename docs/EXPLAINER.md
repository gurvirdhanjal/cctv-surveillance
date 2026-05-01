# VMS — Smart Camera System for the Plant 🏭

> **Written in plain English. No jargon. No computer science degree needed.**
> Think of this as the "explain it to your mum" version of the project.

---

## What Is This?

Imagine you own a big factory and you have **52 security cameras** spread all across the building. Right now, a security guard has to sit and stare at 52 screens at the same time. That's impossible.

This project builds a **smart system** that:

- Watches all 52 cameras by itself
- Recognises the faces of your employees
- Tracks a person as they walk from one camera to another
- Shouts "HEY! There's a stranger here!" automatically
- Remembers where everyone has been, so you can rewind and investigate later

Think of it like hiring a security guard who **never sleeps, never blinks, and has a perfect memory.**

---

## The Big Picture — How It All Works

Let's use a simple story to explain the whole system.

---

### 🏃 The Story of Raju Walking Through the Plant

1. **Raju walks through Gate 1.** Camera 1 spots him.

2. The camera sends its picture to a **worker** (a small computer program). That worker quickly takes a photo of the frame and puts it in a shared notebook (called **Shared Memory**). Then it sends a note to the next guy saying *"Hey, photo is ready, go check the notebook"*.

3. A **smart AI brain** (running on the GPU — the powerful graphics chip) picks up that note, reads the photo from the notebook, and does three things:
   - Finds all the **faces** in the picture (using a model called **SCRFD**)
   - Finds all the **people/bodies** in the picture (using **YOLOv8**)
   - Gives each face a **fingerprint** — a unique 512-number code that represents that face (using **AdaFace**)

4. The AI brain also gives Raju a **tracking number** for this camera — say, `Track #42`. This is managed by something called **ByteTrack**, which is like giving Raju a sticker that says "42" so we don't lose him while he's on Camera 1.

5. Now, Raju walks to Camera 2. Camera 2 doesn't know who he is. So we check his **face fingerprint** against our list of known employees. We find a match — it's Raju! We give him back his global ID: *"That's Employee #007, Raju"*.

6. His position gets drawn on a **floor plan map** of the factory. So the guard can see a dot moving around the building.

7. All of this — every second of Raju's movement — gets saved to a **database** (like a giant Excel sheet that never forgets).

8. The **guard's screen** shows live dots on the map, camera tiles, and alerts — all updating in real time.

---

## The Parts of the System

Think of the system like a **factory assembly line** — each worker does one job and passes the result to the next.

```
📷 Cameras  →  ⚡ Ingestion Workers  →  🔴 Redis (the conveyor belt)
    →  🎮 GPU Brain  →  🧠 Identity Service  →  🗄️ Database
    →  🔌 API Server  →  💻 Guard's Screen
```

---

### 📷 Cameras (52 of them)

These are your eyes. Each camera sends a live video stream (called **RTSP stream** — just a video signal over the network).

We start with just **one webcam** to test everything works. Then we add the 52 factory cameras one by one.

---

### ⚡ Ingestion Workers (4 of them)

These are like **postmen**. Each one handles about 13 cameras.

Their only job: grab each video frame, store it in **Shared Memory** (explained below), and post a tiny note to the conveyor belt saying *"New frame ready!"*

---

### 🗒️ Shared Memory — Why We Use It

Here's a simple analogy:

> Imagine you need to tell your colleague about a 100-page document.
>
> **Bad way:** Read the entire document out loud over the phone. Slow. Expensive.
>
> **Smart way:** Put it on the shared office desk and just say *"It's on the desk, go read it."* Fast. Zero effort.

That's what Shared Memory does. The frame (which can be 2MB) stays in a shared folder in RAM. The postman only sends a tiny 24-byte note: *"Camera 7, frame number 1234, here's where to find it."*

Redis (the conveyor belt) only carries these tiny notes — never the actual video.

---

### 🔴 Redis — The Conveyor Belt

**Redis** is a super-fast message system. Think of it like a **WhatsApp group** for the different programs.

When the ingestion worker has a new frame ready, it posts a message to Redis. The GPU brain is subscribed to that group and immediately picks it up.

Redis also keeps a backlog of up to **500 messages** in case the GPU is temporarily busy. Messages older than 200 milliseconds (0.2 seconds) get thrown away — stale frames are useless.

---

### 🎮 GPU Brain — The Inference Engine

This is the smartest worker. It runs on the **GPU** (the gaming graphics card) because GPUs can process images extremely fast.

It runs **4 AI models**:

| What | Model Name | What It Does |
|---|---|---|
| Find faces | **SCRFD 2.5g** | Draws a box around every face in the frame |
| Fingerprint faces | **AdaFace IR50** | Converts a face into 512 numbers (a unique fingerprint) |
| Find bodies | **YOLOv8n** | Draws a box around every person |
| Track people | **ByteTrack** | Gives each person a stable ID number within one camera |

**Face fingerprint explained:**
> Imagine every face is like a song. AdaFace listens to the song and writes down 512 notes that describe it. Two photos of the same person will produce very similar 512-note descriptions. Two different people will produce very different descriptions. We compare these to identify people.

**Quality checks the brain does:**
- If a face is too **blurry** (like a smeared photo) → ignore it
- If a face is too **small** (less than 40 pixels wide) → ignore it
- If the frame is too **old** (more than 200ms) → throw it away, don't waste time

---

### 🧠 Identity & Tracking Service

This is the part that answers the question: **"Who is this person, and is this the same person I saw on Camera 3?"**

It does three things:

#### 1. Cross-Camera Recognition (Re-ID)
When someone appears on a new camera, we check their face fingerprint against our database using **FAISS** — a super-fast search tool made by Facebook.

Think of FAISS like a **Shazam for faces**. Instead of matching a song, it matches a face fingerprint to find the closest known person.

To make it faster, we only compare against:
- People who were seen in the **same zone or nearby zones** (no point checking if someone was last seen 200 metres away)
- People seen in the **last 5 minutes** (old entries don't count)

#### 2. Floor Plan Position (Homography)
Each camera sees the world from a certain angle — like a photo. We need to figure out where on the **flat floor map** that person is standing.

This is done using **Homography** — a maths trick that converts "pixel position in camera image" → "real-world X, Y position on the floor plan".

Imagine holding a photograph of the floor and finding where each person is standing on an actual map. That's what homography does.

#### 3. Alert FSM (The Alarm System)
FSM stands for **Finite State Machine** — just a fancy name for a set of rules.

Three types of alarm:

| Alarm | When It Fires |
|---|---|
| 🔴 **UNKNOWN PERSON** | Someone with no known identity stays on camera for more than 0.5 seconds |
| 🟡 **PERSON LOST** | A tracked person disappears from ALL cameras for more than 30 seconds |
| 🟢 **CROWD DENSITY** | Too many people in one zone for more than 10 seconds |

Each alarm has a **cooldown** so it doesn't spam the guard every second. Once an alarm fires, it won't fire again for 60–300 seconds depending on the type.

---

### 🗄️ Database — MSSQL Server

This is the **memory of the entire system**. Everything gets saved here.

Think of it like a set of filing cabinets, one per topic:

| Cabinet | What's Inside |
|---|---|
| **persons** | Names and photos of all enrolled employees |
| **person_embeddings** | The 512-number face fingerprints for each person |
| **cameras** | List of all cameras, their locations, and settings |
| **zones** | Named areas in the plant (e.g., "Assembly Line A", "Warehouse") |
| **tracking_events** | Every single moment a person was seen by a camera |
| **alerts** | Every alarm that was fired |
| **reid_matches** | Every time the system matched a person across two cameras |
| **zone_presence** | How long each person spent in each zone |
| **users** | Guard and manager accounts with passwords |

The **tracking_events** table is the busiest — with 52 cameras, it can get millions of rows per day. So we split it by month (like having a separate filing drawer for each month) to keep queries fast.

---

### 🔌 API Server — FastAPI

The API Server is like a **receptionist at a hotel**. The frontend (the guard's screen) asks questions, and the receptionist fetches the answers.

Examples of questions:
- *"Give me the last 1 hour of movement for Employee #007"*
- *"Show me all alerts from Camera 12 today"*
- *"Add this new employee to the system"*

**Security:** Every request needs a **JWT token** — like a hotel key card. You log in, get a card that lasts 8 hours, and every request you make swipes that card. If the card is expired or fake, you get a 401 error (rejected at the door).

**Three roles:**
- **Guard** — can see live cameras, alerts, follow a person
- **Manager** — can see analytics, reports, dwell times
- **Admin** — can add cameras, enroll employees, set up zones

**WebSocket (live updates):**
Instead of the browser asking "any new alerts?" every second (like a kid asking "are we there yet?"), the server pushes updates automatically when something happens. This is called a **WebSocket** — a permanent two-way connection between the browser and the server.

---

### 💻 The Frontend — React App

This is what the guard and manager actually see on their screen.

**Three views:**

#### Guard View — "What's happening RIGHT NOW"
- A grid of camera tiles (like a TV wall)
- Normally shows a still photo updated every 2 seconds to save bandwidth
- Click on a camera → it opens the live video stream for just that one camera
- Alert sidebar on the right shows current alarms
- "Follow Person" button → highlights that person on all cameras at once
- A floor plan map with moving dots showing where everyone is

#### Manager View — "What HAPPENED"
- Floor plan heatmap — shows which areas were busiest
- Timeline scrubber — drag it back in time to replay where everyone was
- Person search — type a name, see everywhere they went today
- Charts showing how long people stayed in each zone
- Export to CSV for reports

#### Admin View — "Set things UP"
- Enroll a new employee (take 6 photos from webcam, system learns their face)
- Add cameras, set their RTSP address
- Calibrate the floor plan mapping (click 4 corners of a room in the camera image, match them to the floor plan → system calculates the maths automatically)
- Set zone boundaries, capacity limits
- Manage user accounts and permissions

---

## What Happens When Things Break?

This system is designed to handle failures gracefully — not crash and burn.

| What Breaks | What Happens |
|---|---|
| A camera disconnects | System waits 1 second, tries again. Then 2s, 4s, 8s, 60s. Marks camera offline after 3 fails. |
| A worker process crashes | Supervisor restarts it in under 5 seconds. Messages it missed are recovered automatically. |
| Redis (the conveyor belt) goes down | Each part buffers frames/data in memory and keeps retrying every 2 seconds. Cross-camera tracking stops but individual cameras still work. |
| Database write fails | Retries 3 times. Then stores up to 50,000 rows in memory. Then writes to a backup file. Nothing is lost. |
| GPU runs out of memory | Cuts the batch size in half and tries again. |
| Guard makes a wrong identity correction | They fix it in the UI. System updates all records and tells all connected screens. |

**When Redis is fully down**, a banner appears on the guard's screen: **"System degraded — Re-ID offline"**. Guards know tracking between cameras is paused but individual cameras still work.

---

## The Technology Choices — And Why

| Thing | We Use | Why |
|---|---|---|
| AI models | ONNX format | Works on both GPU and CPU. No TensorFlow/PyTorch needed at runtime. Fast. |
| Face detection | SCRFD 2.5g | Lightweight and accurate. Designed for real-time use. |
| Face identity | AdaFace IR50 | State of the art for face recognition, especially with low-quality/blurry images. |
| Person tracking | ByteTrack | Works even when people overlap or are briefly hidden. Used in top CCTV systems. |
| Cross-cam matching | FAISS | Can search millions of face fingerprints in milliseconds. Made by Facebook AI. |
| Message passing | Redis Streams | Like Kafka but simpler. Persistent. Can replay messages. Already runs on most servers. |
| Database | MSSQL Server | Already hosted by the company. Team knows it. No new infrastructure. |
| Backend | FastAPI | Modern Python. Fast. Auto-generates API docs. Easy to test. |
| Frontend | React + TypeScript | Industry standard. Huge ecosystem. shadcn/ui gives us professional components for free. |

---

## The 5 Phases — How We Build This

We don't build everything at once. We build in **5 stages**:

### Phase 1 — Make the Foundation (Current Work)
Get the basic pipeline working with a **single webcam** on your desk.

By the end of Phase 1 you can:
- Open a webcam
- See faces being detected in real time
- Enroll an employee (take 6 photos, system learns their face)
- See tracking events being saved to MSSQL

This uses 14 tasks, all built with tests written first (TDD — Test Driven Development, meaning we write a test that fails, then write code to make it pass).

### Phase 2 — Add Cross-Camera Tracking
Wire up the FAISS identity matching, floor plan homography, and the alert alarm system.

By the end of Phase 2 you can:
- Put two webcams on your desk, walk between them, and the system says "it's the same person"
- See alerts firing on the screen

### Phase 3 — Build the Frontend
Build the actual Guard, Manager, and Admin screens in React.

### Phase 4 — Harden for Production
Test with all 52 cameras. Add Prometheus metrics and Grafana dashboards so you can monitor the system's health. Load test. Fix everything that breaks.

### Phase 5 — Roll Out to the Plant
Connect all 52 factory cameras. Calibrate each one's floor plan mapping. Train the guards. Go live.

---

## What We Already Have (The Prototype)

Before this project started, there was already a working prototype in this folder:

| File | What It Does |
|---|---|
| `main.py` | Opens the webcam, finds faces, recognises enrolled employees |
| `face_utils.py` | The SCRFD + AdaFace wrapper — the "face brain" |
| `enrollment_emp.py` | Takes 6 webcam photos of a new employee and saves their face fingerprint |
| `config.py` | Simple settings — which camera to use, which models to load |
| `bytetrack_custom.yaml` | Settings for the ByteTrack person tracker |
| `requirements.txt` | List of Python packages needed |

The prototype works for **one webcam, one person at a time**. This project turns that prototype into a **52-camera production system**.

---

## Where The New Code Will Live

```
D:\facial_recognistion\
│
├── vms\                    ← All new production code goes here
│   ├── config.py           ← Settings (camera addresses, thresholds, etc.)
│   ├── ingestion\          ← The postmen (workers that read cameras)
│   │   ├── shm.py          ← Shared Memory read/write
│   │   └── worker.py       ← One worker process per group of cameras
│   ├── inference\          ← The GPU brain
│   │   ├── detector.py     ← SCRFD face detector
│   │   ├── embedder.py     ← AdaFace face fingerprinter
│   │   ├── tracker.py      ← ByteTrack per-camera tracker
│   │   └── engine.py       ← Puts it all together
│   ├── db\                 ← Database models and connection
│   │   ├── models.py       ← The 11 database tables
│   │   └── session.py      ← How to connect to MSSQL
│   ├── writer\             ← Saves events to the database
│   │   └── db_writer.py    ← Batches and flushes rows
│   └── api\                ← The receptionist (FastAPI)
│       ├── main.py         ← App entry point
│       ├── deps.py         ← Auth and database helpers
│       ├── schemas.py      ← Data shapes (what the API sends/receives)
│       └── routes\         ← Individual API endpoints
│           ├── health.py   ← GET /api/health
│           └── persons.py  ← Enrollment endpoints
│
├── tests\                  ← All tests (one file per vms module)
│
├── docs\
│   ├── presentation\       ← Browser presentation for directors
│   │   ├── index.html      ← Open this to see the slides
│   │   └── serve.py        ← Run this to open the presentation
│   └── superpowers\
│       ├── specs\          ← Full design document
│       └── plans\          ← Phase 1 implementation plan
│
└── README.md               ← You are here
```

---

## How To Run The Presentation

The slides you saw earlier — showing the full architecture — can be opened any time:

```
"C:\Users\APL TECHNO\AppData\Local\Programs\Python\Python310\python.exe" docs\presentation\serve.py
```

This opens your browser at `http://localhost:7420`. Use **arrow keys** or the dots at the bottom to move between slides.

---

## Key Numbers To Remember

| Number | Meaning |
|---|---|
| **52** | Cameras in the plant |
| **512** | Numbers in a face fingerprint (embedding) |
| **0.72** | Similarity threshold to say "yes, I know this person" (out of 1.0) |
| **0.65** | Similarity threshold to say "same person, different camera" |
| **200ms** | If a frame is older than this, throw it away — too stale |
| **500ms** | How long an unknown person must be visible before an alarm fires |
| **30s** | How long a person must be missing before "person lost" alarm fires |
| **5 min** | How far back we search for a face match (the FAISS time window) |
| **11** | Number of database tables |
| **14** | Number of tasks in Phase 1 |
| **5** | Total implementation phases |

---

## Glossary — Words Used In This Project

| Word | What It Means In Plain English |
|---|---|
| **RTSP** | The video signal your IP cameras send over the network |
| **Shared Memory** | A section of RAM that two programs can both read — super fast |
| **Redis** | A fast message board that programs use to talk to each other |
| **ONNX** | A file format for AI models, like .mp3 is for music |
| **GPU** | The graphics card — very good at doing many calculations at once |
| **FAISS** | Facebook's tool for searching through millions of face fingerprints fast |
| **Embedding** | The 512-number fingerprint that represents a face |
| **Re-ID** | Re-Identification — recognising the same person on a different camera |
| **Homography** | Maths that maps a camera's 2D image to a real-world floor map |
| **ByteTrack** | The algorithm that gives each person a stable ID within one camera |
| **FSM** | Finite State Machine — a set of if/then rules for the alarm system |
| **JWT** | JSON Web Token — a digital key card for logging in to the API |
| **WebSocket** | A permanent connection so the server can push live updates to the browser |
| **MSSQL** | Microsoft SQL Server — the database where everything is stored |
| **Alembic** | A tool that manages database changes safely (like version control for the DB) |
| **FastAPI** | The Python framework we use to build the API server |
| **React** | The JavaScript framework we use to build the browser UI |
| **TDD** | Test Driven Development — write a failing test first, then write the code |

---

*Built for: Plant Security & Operations Management*
*Started: April 2026*
*Stack: Python · FastAPI · React · MSSQL · Redis · ONNX · FAISS*
# cctv-surveillance
