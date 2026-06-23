# Phase 4 — Frontend SPA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Build the VMS React SPA from scratch — three role-gated views (Guard / Manager / Admin) backed by the existing FastAPI surface. Close the three backend gaps (`GET /api/persons` list, Zones CRUD API, Socket.io real-time server) that the frontend depends on, then deliver sub-plans 4A–4G to a shippable state: scaffold + design system, auth + routing, live guard view, analytics + forensic, admin views, real-time integration, and E2E/a11y/perf gates.

**Architecture:** Feature-based `frontend/` directory (separate from the Python `vms/` package). React 18 + TypeScript SPA built by Vite; TanStack Query for server state, Zustand for client state, socket.io-client for real-time. JWT auth in httpOnly cookie + `Authorization` header. Built artefacts (`frontend/dist/`) are served in production by the FastAPI server via `StaticFiles` with an SPA catch-all. Backend pre-work adds a `GET /api/persons` list route, a new `vms/api/routes/zones.py` with full CRUD, and a Socket.io ASGI server bridging the Redis alert/location streams to connected clients. HLS video transcode (RTSP → HLS) is a **separate infrastructure service** (MediaMTX/FFmpeg) and is explicitly out of scope for this plan.

**Tech Stack:**
- Frontend: React 18 + TypeScript 5.4, Vite 5, Tailwind CSS 3.4 + shadcn/ui, TanStack Query 5, Zustand 4, socket.io-client 4, React Router 6.22, React Hook Form 7 + Zod 3.23, Leaflet 1.9 + react-leaflet 4, Recharts 2.12, HLS.js 1.5, date-fns 3 + date-fns-tz 3, react-intl, react-helmet-async, TanStack Table + react-virtual.
- Testing: Vitest 1.6 + React Testing Library 16 + Playwright 1.44, axe-core.
- Tooling: ESLint 9 + typescript-eslint 7 + prettier 3. Package manager: **pnpm**.
- Backend pre-work: FastAPI + SQLAlchemy + Alembic, `python-socketio` (ASGI), existing `vms.redis_client` stream helpers. `mypy --strict` on all backend changes.

**Spec refs:**
- `docs/superpowers/specs/2026-05-01-vms-frontend-design.md` — frontend source of truth (all sections; §0 prerequisites, §3 routing, §4 file layout, §5 tokens, §6 guard view, §7 analytics, §8 forensic, §9 admin, §10 real-time, §11 state, §12 forms, §13 tables, §14 a11y, §15 perf, §16 errors, §18 testing, §19 build, §20 sub-plan decomposition).
- `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` — §12 (high-level frontend), §C anomaly detectors, §E alert routing, §N state snapshot.
- `docs/superpowers/specs/2026-05-27-vms-production-readiness.md` — Phase 4 is a GA exit gate; a11y + perf budgets are acceptance criteria.

---

## Conventions for this plan

- **TDD rhythm (CLAUDE.md §4.2):** for every task — write a failing test → run it, confirm it fails for the expected reason → implement the minimum → run it, confirm it passes → refactor → commit. The `verify:` line names the command/check that proves the step.
- **Commits (CLAUDE.md §4.3):** one logical change per commit, conventional format (`feat:`, `fix:`, `test:`, `chore:`, …). No AI co-author footer.
- **Backend quality gate (CLAUDE.md §11):** `black vms/ tests/`, `ruff check vms/ tests/`, `mypy vms/` (strict), `pytest`. No `print()` — use `logging.getLogger(__name__)`. Timestamps via `datetime.now(timezone.utc).replace(tzinfo=None)`.
- **Frontend quality gate:** `pnpm lint && pnpm typecheck && pnpm test:run`. Coverage targets: **80% for `src/shared/`, 70% for `src/features/`**.
- **No implementation without this approved plan.** Each sub-plan is independently shippable; commit at the end of every task.
- **Security (CLAUDE.md §7):** every new API endpoint requires authentication + role/permission checks. Never log embeddings, RTSP URLs, JWTs. New routes get at least one positive + one negative (auth/validation) test.
- **Spec coverage (CLAUDE.md §4.5):** when touching a route file, confirm every spec endpoint for that section exists before marking the task done.

---

## Phase 4 Pre-work — backend gaps (DO FIRST, before dependent frontend features)

These three gaps block specific frontend features. Each must be closed and merged before the sub-plan task that consumes it begins. They are backend changes — full backend quality gate applies (`black`, `ruff`, `mypy --strict`, `pytest`).

### P0. `GET /api/persons` list endpoint (blocks 4E Admin persons page)

- [ ] **P0.1** Write failing test `tests/api/test_persons_list.py::test_list_persons_returns_paginated_persons` — authenticated admin gets a paginated list (`items`, `total`, `limit`, `offset`); assert shape + ordering by `full_name`.
  - verify: `pytest tests/api/test_persons_list.py -v` fails (route 404 / not implemented).
- [ ] **P0.2** Write failing negative tests: `test_list_persons_requires_auth` (401 without JWT) and `test_list_persons_rejects_guard_role` (403 for `guard`; persons admin is manager/admin per §9).
  - verify: `pytest tests/api/test_persons_list.py -v` — new tests fail.
- [ ] **P0.3** Add `PersonListResponse` to `vms/api/schemas.py` (`items: list[PersonResponse]`, `total: int`, `limit: int`, `offset: int`) and implement `GET /api/persons` in `vms/api/routes/persons.py` with `limit`/`offset` query params (default 50, max 200), role guard, ordered by `full_name`. Reuse the existing `get_db`/`get_current_user` deps.
  - verify: `pytest tests/api/test_persons_list.py -v` all pass; `pytest tests/api/test_persons*.py` regression green.
- [ ] **P0.4** Spec-coverage check: confirm `persons.py` now covers the §9 Admin-persons read surface (list + search + create + enroll + delete). Backend quality gate + commit.
  - verify: `ruff check vms/ tests/` clean; `mypy vms/` clean; `pytest` green. Commit `feat: add GET /api/persons list endpoint for admin persons view`.

### P1. Zones CRUD API — new `vms/api/routes/zones.py` (blocks 4E zone editor)

- [ ] **P1.1** Confirm a `Zone` ORM model exists in `vms/db/models.py` (polygon geometry, `allowed_hours`, `max_capacity`, `loiter_threshold_s`, `floor_plan_id`). If fields are missing for the editor (§9 zones), STOP — this needs a migration; write the Alembic migration in the same commit (CLAUDE.md §6.1) and round-trip test `upgrade`/`downgrade` locally before proceeding.
  - verify: `grep -n "class Zone" vms/db/models.py`; if migration needed, `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` succeeds.
- [ ] **P1.2** Write failing tests `tests/api/test_zones.py` — `GET /api/zones` (list, auth required), `POST /api/zones` (admin creates, returns 201), `PATCH /api/zones/{id}` (update polygon/capacity), `DELETE /api/zones/{id}` (soft-delete/archive per §9 "soft delete only"). One positive + one negative (401 + 403 for non-admin write) per verb.
  - verify: `pytest tests/api/test_zones.py -v` fails (module/route missing).
- [ ] **P1.3** Add `ZoneCreate`, `ZoneUpdate`, `ZoneResponse` Pydantic schemas to `vms/api/schemas.py` (polygon as list of `[x, y]` float pairs validated non-empty ≥3 points; `allowed_hours`, `max_capacity ≥ 0`, `loiter_threshold_s ≥ 0`).
  - verify: `mypy vms/api/schemas.py` clean.
- [ ] **P1.4** Implement `vms/api/routes/zones.py` with all four endpoints, admin role gate on writes, zone-level permission check on reads (CLAUDE.md §7.1 — check `user_camera_permissions`/zone scope, not just role). Register router in `vms/api/main.py` (`app.include_router(zones.router, prefix="/api")`).
  - verify: `pytest tests/api/test_zones.py -v` all pass.
- [ ] **P1.5** Backend quality gate + commit.
  - verify: `ruff check vms/ tests/` clean; `mypy vms/` clean; `pytest` green. Commit `feat: add zones CRUD API (GET/POST/PATCH/DELETE /api/zones)`.

### P2. Socket.io real-time server (blocks 4C live view + 4F real-time integration)

The guard live view cannot function without server-push. `GET /api/state/snapshot` exists (used for reconnect rehydration); this adds the push channel bridging Redis streams to connected clients. Implements the §10 event contract.

- [ ] **P2.1** Add `python-socketio` (ASGI) to backend deps (`pyproject.toml`/requirements). Create `vms/api/realtime/__init__.py` and `vms/api/realtime/server.py` with an `AsyncServer` (cors restricted to configured origins via `VMS_FRONTEND_ORIGIN`). Add `VMS_FRONTEND_ORIGIN` to `vms/config.py` (no hard-coded origin — CLAUDE.md §12).
  - verify: `mypy vms/api/realtime/server.py` clean; import succeeds.
- [ ] **P2.2** Write failing test `tests/api/test_realtime_auth.py::test_socket_connect_requires_valid_jwt` — connection handshake must validate the JWT (auth token in connect payload); reject unauthenticated connect. Use `socketio.AsyncClient` or the server's test harness.
  - verify: `pytest tests/api/test_realtime_auth.py -v` fails.
- [ ] **P2.3** Implement JWT validation in the `connect` handler (reuse `vms.api.deps` token decode); reject with `ConnectionRefusedError` on invalid/missing token. Implement `subscribe_camera` / `unsubscribe_camera` / `subscribe_track` client→server handlers (room membership per §10). Role-gate: only authenticated users join rooms.
  - verify: `pytest tests/api/test_realtime_auth.py -v` passes.
- [ ] **P2.4** Write failing test `tests/api/test_realtime_bridge.py::test_alert_stream_event_emits_alert_fired` — pushing an event onto the Redis alert stream results in an `alert_fired` emit with the §10 payload shape (`alert_id, alert_type, severity, camera_id, zone_id, global_track_id, snapshot_url, ts`).
  - verify: `pytest tests/api/test_realtime_bridge.py -v` fails.
- [ ] **P2.5** Implement the Redis→Socket.io bridge as an async background task started on app startup: consume the alert stream and `person_location`/`head_count`/`worker_health`/`alert_state_changed`/`track_corrected`/`camera_snapshot` sources, emit the §10 events with their throttling (5fps `person_location` per track diff-only; 1s `head_count`; 2s `camera_snapshot`; immediate for alerts). Do not log embeddings/RTSP. This is a per-frame-adjacent path — batch emits, no per-event DB query (CLAUDE.md §0.6).
  - verify: `pytest tests/api/test_realtime_bridge.py -v` passes.
- [ ] **P2.6** Mount the Socket.io ASGI app under the FastAPI app (e.g. `socketio.ASGIApp(sio, app)` or sub-mount at `/socket.io`) in `vms/api/main.py`; add a `degraded_mode` emit hook when the bridge detects Redis lag/disconnect.
  - verify: app starts; `pytest tests/api/test_realtime*.py` green; manual `GET /api/health` still 200.
- [ ] **P2.7** Backend quality gate + commit.
  - verify: `ruff check vms/ tests/` clean; `mypy vms/` clean; `pytest` green. Commit `feat: add Socket.io real-time server bridging Redis streams (§10)`.

**Pre-work gate (all of P0–P2):** `ruff check vms/ tests/` clean; `mypy vms/` strict clean; `pytest` green. Do not start 4C/4E features that depend on these until merged.

---

## 4A — Scaffold & design system (~10 tasks)

Establishes the `frontend/` workspace, toolchain, design tokens, and primitive components. No backend dependency.

- [ ] **4A.1** Scaffold the Vite + React + TS project under `frontend/` with pnpm. Add `package.json` scripts per spec §19 (`dev`, `build`, `preview`, `test`, `test:run`, `test:e2e`, `test:a11y`, `lint`, `typecheck`). Configure `vite.config.ts` to proxy `/api` and `/socket.io` → `:8000` in dev. Add `tsconfig.json` (strict).
  - verify: `pnpm install` succeeds; `pnpm dev` serves on :5173; `pnpm typecheck` clean.
- [ ] **4A.2** Configure ESLint 9 + typescript-eslint 7 + prettier 3 and Vitest 1.6 + React Testing Library 16 (`vitest.config.ts`, `test-utils/` setup with jsdom + RTL matchers). Add coverage thresholds (shared 80 / features 70).
  - verify: `pnpm lint` clean on scaffold; `pnpm test:run` runs (0 tests OK).
- [ ] **4A.3** Install + configure Tailwind 3.4 with the §5 palette wired through CSS custom properties for dark/light themes (`tailwind.config.ts`, `index.css`). Self-host fonts via `@fontsource/inter` + `@fontsource/jetbrains-mono`.
  - verify: a sample element using `bg-surface-base text-text-primary` renders both themes; `pnpm build` succeeds.
- [ ] **4A.4** Create `src/shared/design-system/tokens.ts` (colors, typography, spacing, elevation, motion from §5). Write `tokens.test.ts` asserting severity colors + theme-resolved token shape.
  - verify: `pnpm test:run src/shared/design-system/tokens.test.ts` passes.
- [ ] **4A.5** TDD `ThemeProvider` + `themeStore` (Zustand, §11) — theme/locale persisted to `localStorage`, `toggleTheme`, `prefers-reduced-motion` respected. Test: toggling theme flips `data-theme` and persists.
  - verify: `pnpm test:run` ThemeProvider test green.
- [ ] **4A.6** TDD primitive `Button` (shadcn-derived) — variants, `loading` spinner, `focus-visible:ring-2 ring-brand-500`, `aria-disabled`. Test render + variants + a11y (axe on component).
  - verify: `pnpm test:run` Button test green.
- [ ] **4A.7** TDD primitive `Input` — `label`, `error`, `aria-invalid`, `aria-describedby` linkage (§12). Test error wiring + label association.
  - verify: `pnpm test:run` Input test green.
- [ ] **4A.8** TDD primitives `Modal`/`Dialog` (focus trap, Esc closes, restore focus to trigger — §14) and `Toast` (`aria-live` polite/assertive — §14/§16). Tests cover focus trap + live region.
  - verify: `pnpm test:run` Modal + Toast tests green.
- [ ] **4A.9** TDD remaining shared primitives needed downstream: `Badge` (severity/tier), `Spinner`, `Table` wrapper (TanStack Table + react-virtual scaffold, §13), `Tabs`, `Select`, `Tooltip`. One render/behavior test each.
  - verify: `pnpm test:run src/shared/design-system` all green; coverage of `shared/design-system` ≥80%.
- [ ] **4A.10** App shell composition: `src/main.tsx`, `src/app/App.tsx` (theme + query client + helmet root), `src/app/providers.tsx`, `src/shared/i18n/` (react-intl `IntlProvider` + `en/` message stubs), error boundary hierarchy scaffold (§16). Quality gate + commit.
  - verify: `pnpm lint && pnpm typecheck && pnpm test:run` all green. Commit `feat(frontend): scaffold Vite app, design system tokens + primitives`.

**4A gate:** `pnpm lint && pnpm typecheck && pnpm test:run`.

---

## 4B — Auth + routing + role guards (~6 tasks)

- [ ] **4B.1** TDD `shared/api/client.ts` — fetch wrapper with JWT injection (Authorization header), typed error mapping to `ApiError`/`UnauthorizedError`/`ForbiddenError`/`NotFoundError`/`ValidationError`/`ServerError` (§16). Test each status→class mapping.
  - verify: `pnpm test:run src/shared/api/client.test.ts` green.
- [ ] **4B.2** Generate `shared/api/types.ts` from the backend OpenAPI schema (script in `package.json`, e.g. `openapi-typescript` against `/openapi.json`). Commit the generated file. Test: a representative type compiles against a sample payload.
  - verify: `pnpm typecheck` clean with generated types imported.
- [ ] **4B.3** TDD `authStore` + `AuthProvider` + `useAuth` (§11) — `login(creds)` calls `POST /api/auth/token`, stores token + decoded user/role, `logout` clears. JWT decoded client-side for routing only (server still authorises). Test login success + failure paths.
  - verify: `pnpm test:run` auth store/provider tests green.
- [ ] **4B.4** TDD `LoginPage` (`/login`) — React Hook Form + Zod, error toast on 401, redirect to `?next=` on success. Test submit happy path + invalid creds.
  - verify: `pnpm test:run` LoginPage test green.
- [ ] **4B.5** TDD `RoleGuard` (§3 role table: guard / manager / admin) + route table `src/app/routes.tsx` with `React.lazy` per top-level route (§15 code splitting). Tests: guard role blocked from `/analytics` (→ `/403`), admin allowed all, unauthenticated → `/login`.
  - verify: `pnpm test:run` RoleGuard + routing tests green.
- [ ] **4B.6** `/403` and `/404` pages + app-level `UnauthorizedError`→`/login` redirect effect (§16). Quality gate + commit.
  - verify: `pnpm lint && pnpm typecheck && pnpm test:run` green. Commit `feat(frontend): auth flow, route table, role guards, 403/404 pages`.

**4B gate:** `pnpm lint && pnpm typecheck && pnpm test:run`.

---

## 4C — Live (Guard) view (~14 tasks)

Depends on **P2 (Socket.io)** and existing `GET /api/state/snapshot`, `GET /api/cameras`, `GET /api/alerts`. HLS playback assumes the external transcoder exists (graceful "stream unavailable" state if not).

- [ ] **4C.1** TDD `liveStore` (Zustand, §11) — `reset(snapshot)`, `applyLocations`, `applyAlertFired`, `applyAlertStateChanged`, `setFocusedCamera`, `setFollowedTrack`, `headCount`, `degraded`. Tests cover each action's state transition.
  - verify: `pnpm test:run src/features/live/store/liveStore.test.ts` green.
- [ ] **4C.2** TDD `useCameraSnapshot` hook — polls `GET /api/cameras/:id/snapshot` every 2s (5s in degraded mode, §10). Test interval + degraded switch (fake timers).
  - verify: `pnpm test:run` hook test green.
- [ ] **4C.3** TDD `CameraTile` — states `online`/`offline`/`auth_failed`/`maintenance` with distinct icon + badge + tier chip (FULL/MID/LOW); `auth_failed` amber border (§6). Memoised. Tests cover each state render.
  - verify: `pnpm test:run` CameraTile test green.
- [ ] **4C.4** TDD `CameraGrid` — 4×3 paginated grid, keyboard ←/→ paginate, Esc returns to focused, active tile brand border, maintenance dimmed + calendar icon (§6). Tests: pagination + selection + keyboard.
  - verify: `pnpm test:run` CameraGrid test green.
- [ ] **4C.5** TDD `FocusedCamera` — HLS.js attach to `<video>`, "stream unavailable" fallback when no HLS source, lazy-loaded HLS.js (live chunk, §15). Test: source attach + fallback (HLS.js mocked).
  - verify: `pnpm test:run` FocusedCamera test green.
- [ ] **4C.6** TDD bbox overlay SVG layer for FocusedCamera — subscribes to `person_location` for the focused camera, throttled 5fps; named persons show colour band, unknown red dotted box (§6). Direct DOM update via rAF (§15), not per-event React state. Test: overlay renders boxes from store; throttle batching.
  - verify: `pnpm test:run` overlay test green.
- [ ] **4C.7** TDD `AlertCard` — severity colour bar + icon + label (colour never sole carrier, §14), time-since, camera+zone, Acknowledge/Resolve CTAs. Memoised. Test render + CTA callbacks.
  - verify: `pnpm test:run` AlertCard test green.
- [ ] **4C.8** TDD `AlertSidebar` — sorted severity DESC then triggered_at DESC, grouped by `global_track_id` ("+N similar"), filter dropdown (severity/type/zone), sticky-scroll "New alerts above ↑" toast, click→focus camera (§6). Tests: sort, grouping, filter.
  - verify: `pnpm test:run` AlertSidebar test green.
- [ ] **4C.9** TDD `useLiveAlerts` hook — seeds historical from `GET /api/alerts`, merges `alert_fired`/`alert_state_changed` socket events into `liveStore`. Acknowledge/Resolve call backend (`/api/alerts` state transition) with optimistic update + rollback on error. Test merge + optimistic path.
  - verify: `pnpm test:run` hook test green.
- [ ] **4C.10** TDD `HeadCountBanner` + TopBar HeadCount badge — live total + per-zone breakdown modal, updates from `head_count` socket event (§6/§10), "stale" indicator in degraded mode. Test render + stale state.
  - verify: `pnpm test:run` HeadCountBanner test green.
- [ ] **4C.11** TDD `SystemStatusStrip` + `TopBar` — logo, site title, Cmd+K person search (autocomplete from `/api/persons/search`), GPU util bar, active-alert count link (§6). Test: Cmd+K opens search, selecting tracked person → `/live/follow/:trackId`.
  - verify: `pnpm test:run` TopBar test green.
- [ ] **4C.12** TDD `LivePage` — three-column layout (CameraGrid 320px / Focused 1fr / AlertSidebar 380px), wires grid selection ↔ focused ↔ alert focus (§6). Integration test with mocked API + socket.
  - verify: `pnpm test:run` LivePage integration test green.
- [ ] **4C.13** TDD `FocusedCameraPage` (`/live/cameras/:cameraId`) + `FollowPersonPage`/`FollowPersonPanel` (`/live/follow/:trackId`) — follow mode auto-switches focused video to the camera holding the track, movement timeline strip, mini floor-plan (Leaflet) with live dot, `subscribe_track` emit (§6/§10). Tests: route param wiring + follow subscription.
  - verify: `pnpm test:run` follow-mode tests green.
- [ ] **4C.14** `useTrackedPersons` hook + memoised `PersonDot` (direct DOM transform updates, §15) consolidating location subscriptions. Quality gate + commit.
  - verify: `pnpm lint && pnpm typecheck && pnpm test:run` green; `features/live` coverage ≥70%. Commit `feat(frontend): guard live view — grid, focused camera, alerts, head count, follow`.

**4C gate:** `pnpm lint && pnpm typecheck && pnpm test:run`.

---

## 4D — Analytics + forensic (~12 tasks)

Light theme. Depends on `GET /api/alerts`, `GET /api/persons/*`, `GET /api/zones` (P1), `GET /api/cameras`. Timeline time-series + forensic CLIP search are **deferred** (see Known defers) — build the UI shells with disabled/empty states pointing at the deferred backends.

- [ ] **4D.1** TDD `AnalyticsLayout` + light-theme route shell for `/analytics/*` (lazy chunk; Recharts isolated to this chunk, §15).
  - verify: `pnpm test:run` layout test green.
- [ ] **4D.2** TDD KPI metric cards (`/analytics` dashboard row 1) — head count peak, avg dwell, unknown-person events, camera uptime %. TanStack Query fetch with §11 stale times. Test render + loading/error states.
  - verify: `pnpm test:run` KPI cards test green.
- [ ] **4D.3** TDD dashboard charts (row 2) — Recharts line (head count 7d) + bar (alert volume by type top 5) from `GET /api/alerts`. Test data→chart mapping.
  - verify: `pnpm test:run` charts test green.
- [ ] **4D.4** TDD `FloorPlan` component (Leaflet image overlay + custom marker layer for person dots, §7). Reusable by timeline/heatmap/follow. Test: image overlay mount + marker render.
  - verify: `pnpm test:run` FloorPlan test green.
- [ ] **4D.5** TDD `TimeScrubber` UI (`/analytics/timeline`) — date/time slider (24h default, up to 7d), playback controls (0.5×–10×), pause + frame-step, zone/person/alert filters (§7). **Data source `GET /api/tracking/timeline` is deferred (Phase 5)** — render the scrubber against a mocked/empty trail with a "timeline data pending (Phase 5)" notice. Test control state machine (play/pause/speed).
  - verify: `pnpm test:run` TimeScrubber test green.
- [ ] **4D.6** TDD `HeatmapOverlay` (`/analytics/heatmap`) — per-zone polygons (from `GET /api/zones`) coloured by dwell intensity, legend, time-window selector (today/week/month/custom) (§7). Test polygon colour mapping + legend.
  - verify: `pnpm test:run` Heatmap test green.
- [ ] **4D.7** TDD `DwellChart` + `PersonTimeline` components for person profile (§7). Test horizontal zone-presence timeline render.
  - verify: `pnpm test:run` person-component tests green.
- [ ] **4D.8** TDD `PersonProfilePage` (`/analytics/persons/:id`) — header (name/ID/dept/last-seen/photo from `/api/persons/:id`), 24h journey, per-zone dwell heatmap, recent alerts, "Open in timeline scrubber" CTA (§7). Integration test with mocked API.
  - verify: `pnpm test:run` PersonProfile test green.
- [ ] **4D.9** TDD `AnalyticsDashboardPage` composition (row 3 quick actions) tying KPIs + charts + nav to timeline/heatmap/forensic. Integration test.
  - verify: `pnpm test:run` dashboard test green.
- [ ] **4D.10** TDD `ForensicSearchPage` (`/forensic`) — query input, time-range/zone/camera filters, results grid, empty-state hints (§8). **`GET /api/forensic/search` returns 501 (CLIP blocked)** — render a clear "Forensic search unavailable — CLIP text encoder not yet deployed" state on 501, keep the input + filters disabled/labelled accordingly. Test: 501→disabled-state render.
  - verify: `pnpm test:run` ForensicSearch test green.
- [ ] **4D.11** TDD `ClipResultCard` + clip side-drawer — thumb, time, zone, score; drawer plays 10s HLS clip via `GET /api/forensic/clips/{global_track_id}` (this endpoint IS implemented), tracklet metadata, "Open in timeline" CTA (§8). Virtualise results when ≥100 (§13). Test card render + drawer open.
  - verify: `pnpm test:run` ClipResultCard test green.
- [ ] **4D.12** Quality gate + commit.
  - verify: `pnpm lint && pnpm typecheck && pnpm test:run` green; `features/analytics` + `features/forensic` coverage ≥70%. Commit `feat(frontend): analytics dashboard, timeline shell, heatmap, person profile, forensic shell`.

**4D gate:** `pnpm lint && pnpm typecheck && pnpm test:run`.

---

## 4E — Admin views (~16 tasks)

Light theme, sidebar nav. Depends on `GET /api/persons` (P0), Zones CRUD (P1), and existing cameras/anomaly/maintenance/routing/audit endpoints.

- [ ] **4E.1** TDD `AdminLayout` (sidebar nav per §9 section table) + `AdminDashboardPage` (`/admin`) — worker health, GPU util, PG write-queue depth, Redis stream lag, latest migration, model versions (from health/state endpoints). Test nav + dashboard render.
  - verify: `pnpm test:run` AdminLayout/Dashboard test green.
- [ ] **4E.2** TDD `AdminPersonsPage` (`/admin/persons`) list — virtualised table (§13) from **`GET /api/persons` (P0)**, search box (`/api/persons/search`). Test list render + search.
  - verify: `pnpm test:run` AdminPersons list test green.
- [ ] **4E.3** TDD `EnrolmentWizard` 4-step modal (name/ID → capture → quality check → save) with React Hook Form + Zod (`employee_id` regex `^EMP-\d{3,6}$`, §12), `POST /api/persons` + `POST /api/persons/{id}/embeddings`. Cancel-with-edits confirm (§9). Test step progression + validation + submit.
  - verify: `pnpm test:run` EnrolmentWizard test green.
- [ ] **4E.4** TDD GDPR delete flow on persons page — typed full-name confirmation + reason string, admin-only, `DELETE /api/persons/{id}` (CLAUDE.md §7.3). Test: confirmation gate blocks until name matches.
  - verify: `pnpm test:run` person-delete test green.
- [ ] **4E.5** TDD `AdminCamerasPage` (`/admin/cameras`) — list from `GET /api/cameras`, per-row tier badge + shutter chip, "Run profiler" CTA, add/edit form (`POST`/`PATCH /api/cameras/{id}`, `rtsp_url` Zod `^rtsp://`, §12). Test list + add form validation.
  - verify: `pnpm test:run` AdminCameras test green.
- [ ] **4E.6** TDD `CameraDetail` tabbed page (`/admin/cameras/{id}`) shell with 5 tabs (Overview / Hardware / Overrides / Maintenance / Calibration) + role gating (Hardware editable only by super_admin — disabled controls + "Super Admin required" label, §9). Test tab switching + role-gated disable.
  - verify: `pnpm test:run` CameraDetail shell test green.
- [ ] **4E.7** TDD Hardware tab — "Run Profiler" → `POST /api/cameras/{id}/profile` (inline progress), suggestion banner on shutter mismatch, Confirm/Override → `PATCH /api/cameras/{id}/hardware`, measured-properties table from `GET /api/cameras/{id}/profile` (§9). Test profiler flow + confirm/override PATCH.
  - verify: `pnpm test:run` Hardware tab test green.
- [ ] **4E.8** TDD Overrides tab — diff view from `GET /api/cameras/{id}/resolved-config` (rows where `source != "global_default"`), amber banner for `shutter:`-prefixed sources, "Show all settings" toggle, "+Add Override" key-picker → `PATCH /api/cameras/{id}/overrides` (§9). Test diff filter + save.
  - verify: `pnpm test:run` Overrides tab test green.
- [ ] **4E.9** TDD `HomographyCalibrator` (Calibration tab) — 6-step flow, 4-point pick on frame + floor plan, live reprojection error, Save activates only when err < 2px (§9). Test step gating + Save enable threshold.
  - verify: `pnpm test:run` Calibrator test green.
- [ ] **4E.10** TDD `ZoneEditor` (`/admin/zones`) — Leaflet polygon draw on floor-plan image, `allowed_hours` editor, `max_capacity`, loiter threshold; CRUD against **Zones API (P1)**; soft-delete typed confirmation (§9). Test polygon create + save + edit.
  - verify: `pnpm test:run` ZoneEditor test green.
- [ ] **4E.11** TDD `AdminUsersPage` (`/admin/users`) — CRUD + zones×users permission toggle matrix (§9). (If a users API endpoint is missing, STOP and add a pre-work sub-task before continuing — do not silently defer; CLAUDE.md §4.5.) Test matrix toggle + CRUD.
  - verify: `pnpm test:run` AdminUsers test green; confirm users endpoints exist or sub-task filed.
- [ ] **4E.12** TDD `MaintenanceCalendar` (`/admin/maintenance`) — month/Gantt view from `GET /api/maintenance` + `GET /api/maintenance/calendar`, create/edit/delete (`POST`/`PATCH`/`DELETE /api/maintenance/{id}`), one-time + cron (`cron_expr` preview of next 3 fire times via `cron-parser`, §12). Reused by Camera Maintenance tab filtered by `scope_type=camera`. Test create modal + cron preview.
  - verify: `pnpm test:run` MaintenanceCalendar test green.
- [ ] **4E.13** TDD `AnomalyDetectorsPage` (`/admin/anomaly-detectors`) — list from `GET /api/anomaly-detectors`, enable/disable toggle + per-detector config JSON editor with schema validation, `PATCH /api/anomaly-detectors/{id}` (§9/§C). Test toggle + invalid-config rejection.
  - verify: `pnpm test:run` AnomalyDetectors test green.
- [ ] **4E.14** TDD `AlertRoutingPage` (`/admin/alert-routing`) — rule table + CRUD (`GET`/`POST`/`PATCH`/`DELETE /api/alert-routing[/{id}]`), test-fire button per rule, `webhook_target` HTTPS-required Zod (HTTP only with explicit confirm, §12). Test CRUD + webhook validation.
  - verify: `pnpm test:run` AlertRouting test green.
- [ ] **4E.15** TDD `ModelManager` (`/admin/models`) — installed model versions + per-camera override editor + signed upload form (§9). Read-only against model manifest data exposed by backend; if no models API exists, render from available source + file a sub-task for any missing endpoint (do not silently defer). Test list render + override row.
  - verify: `pnpm test:run` ModelManager test green.
- [ ] **4E.16** TDD `AuditLogViewer` (`/admin/audit`) — virtualised filterable table, "Verify chain" button → `GET /api/audit/verify`, "Export PDF" → `GET /api/audit/export` (§9/§F.3). Test filter + verify + export trigger. Quality gate + commit.
  - verify: `pnpm lint && pnpm typecheck && pnpm test:run` green; `features/admin` coverage ≥70%. Commit `feat(frontend): admin views — persons, cameras, zones, users, maintenance, detectors, routing, models, audit`.

**4E gate:** `pnpm lint && pnpm typecheck && pnpm test:run`.

---

## 4F — Real-time integration (~6 tasks)

Wires the client to the **P2 Socket.io server**. The §10 event contract + reconnect rehydration + degraded UX.

- [ ] **4F.1** TDD `shared/api/socket.ts` — socket.io-client with auth token in handshake, `reconnection: true`, `reconnectionDelay: 500`, `reconnectionDelayMax: 5000` (§10). Test: client constructs, attaches auth.
  - verify: `pnpm test:run src/shared/api/socket.test.ts` green (socket mocked).
- [ ] **4F.2** TDD rAF-batched `person_location` throttle (`queuePersonLocation`/`flush` per §10) feeding `liveStore.applyLocations`. Test: multiple queued events flush once per frame, last-write-wins per track.
  - verify: `pnpm test:run` throttle test green.
- [ ] **4F.3** TDD socket event dispatch layer — `alert_fired`, `alert_state_changed`, `track_corrected`, `camera_snapshot`, `worker_health`, `head_count` → store actions (§10). Test each event→store mutation.
  - verify: `pnpm test:run` dispatch test green.
- [ ] **4F.4** TDD reconnect rehydration (§10) — on `connect`: `GET /api/state/snapshot` → `liveStore.reset`, re-emit `subscribe_camera`/`subscribe_track` for current focus/follow. Test: connect handler refetches + re-subscribes.
  - verify: `pnpm test:run` reconnect test green.
- [ ] **4F.5** TDD degraded UX (§10 table) — `degraded_mode` event / disconnect → "Reconnecting..." banner after 3s, camera grid polling 5s, AlertSidebar paused banner, frozen overlays, stale head count; recovery re-syncs via snapshot. Test: degraded state propagation per component contract.
  - verify: `pnpm test:run` degraded-mode test green.
- [ ] **4F.6** Integration test: live page + mocked socket server — alert_fired appears in sidebar ≤ render budget, person_location moves a dot, disconnect shows banner, reconnect clears it. Quality gate + commit.
  - verify: `pnpm lint && pnpm typecheck && pnpm test:run` green. Commit `feat(frontend): socket.io real-time integration, throttling, reconnect, degraded mode`.

**4F gate:** `pnpm lint && pnpm typecheck && pnpm test:run`.

---

## 4G — E2E + a11y + perf budget (~8 tasks)

- [ ] **4G.1** Configure `playwright.config.ts` + `e2e/` against a docker-compose stack (FastAPI + PostgreSQL test DB + Redis, pre-seeded) per §18. Add a compose file + seed fixture.
  - verify: `docker compose -f e2e/docker-compose.yml up -d` healthy; `pnpm test:e2e --list` enumerates specs.
- [ ] **4G.2** E2E `e2e/guard.spec.ts` — login as guard, see alerts, acknowledge, follow person (§18).
  - verify: `pnpm test:e2e e2e/guard.spec.ts` green against the stack.
- [ ] **4G.3** E2E `e2e/admin.spec.ts` — enrol person, calibrate camera, edit zone, create maintenance window (§18).
  - verify: `pnpm test:e2e e2e/admin.spec.ts` green.
- [ ] **4G.4** E2E `e2e/forensic.spec.ts` — search clips by text (expect graceful 501 unavailable-state), open a clip drawer via `GET /api/forensic/clips/{id}` (§18).
  - verify: `pnpm test:e2e e2e/forensic.spec.ts` green.
- [ ] **4G.5** axe-core a11y harness — `pnpm test:a11y` runs axe against each page (§14). Fix any AA violations surfaced (focus rings, aria-labels, contrast, role=alert on form errors).
  - verify: `pnpm test:a11y` reports 0 serious/critical violations.
- [ ] **4G.6** Bundle budget gate in CI — initial JS ≤ 800kB gzipped (fail), route chunk ≤ 300kB (warn) / 400kB (fail) (§15). Add a build-size check script; verify code-splitting (Recharts in analytics chunk, Leaflet/HLS.js in their chunks).
  - verify: `pnpm build` + size-check script passes thresholds.
- [ ] **4G.7** Lighthouse/perf budget check — FCP ≤ 1.5s, TTI ≤ 3s, LCP ≤ 2.5s, CLS < 0.1 (§15) on the preview build; floor-plan 50-dot render ≤ 16ms/frame spot-check.
  - verify: Lighthouse CI report within budgets (warnings acceptable, hard-fail on CLS ≥ 0.25 / bundle over hard limits).
- [ ] **4G.8** Production serve integration: configure FastAPI to mount `frontend/dist/` (see Deployment notes) + SPA catch-all; verify a built bundle is served and deep links resolve. Final quality gate + commit; mark plan COMPLETE.
  - verify: `pnpm build` then FastAPI serves `/`, `/live`, `/admin` deep-links return `index.html`; `pnpm lint && pnpm typecheck && pnpm test:run` green; backend `pytest` green. Commit `feat(frontend): e2e suites, a11y + perf gates, production static serving`.

**4G gate:** `pnpm lint && pnpm typecheck && pnpm test:run` + `pnpm test:e2e` + `pnpm test:a11y`.

---

## Deployment notes

- **FastAPI serves the built SPA.** In production, mount `frontend/dist/` at `/` via `StaticFiles` with an SPA history-mode catch-all that returns `index.html` for non-`/api`, non-`/socket.io`, non-`/media`, non-`/metrics` paths. Follow the existing mount pattern in `vms/api/main.py` (`_apply_media_mount` already mounts `/media` via `StaticFiles`; the SPA mount is the last route registered so API routers take precedence). Gate the SPA mount behind a `VMS_SERVE_FRONTEND` config flag (default off in dev — Vite dev server proxies `/api` + `/socket.io` to `:8000`; on in production).
- **Dev flow (§19):** `pnpm dev` on :5173 with Vite proxy → FastAPI `:8000`. No StaticFiles mount in dev.
- **Socket.io mount:** the `python-socketio` ASGI app is sub-mounted under the FastAPI app at `/socket.io` (P2.6); the Vite dev proxy forwards `/socket.io` as well.
- **HLS infrastructure is OUT OF SCOPE.** RTSP→HLS transcode is a **separate service** (MediaMTX or an FFmpeg pipeline) and a deployment-architecture decision (frontend spec §0 "Critical blocker"). This plan only consumes HLS URLs; `FocusedCamera` and the forensic clip drawer render a graceful "stream unavailable" state when no HLS source is configured. The transcoder rollout is tracked separately (Phase 6 camera-rollout / infra plan).
- **CORS / origins:** `VMS_FRONTEND_ORIGIN` config drives both Socket.io CORS and any API CORS allowance — no hard-coded origins (CLAUDE.md §12).

---

## Known defers (tracked — not silent)

| Deferred item | Why | Tracking |
|---|---|---|
| `GET /api/forensic/search` (CLIP text search) | Returns 501 — blocked on CLIP-ViT-B/32 ONNX text encoder (`VMS_CLIP_MODEL`); needs recording/analytics spec Phase 3 | UI ships a disabled "unavailable" state (4D.10). CLAUDE.md §3 Known Gaps |
| `GET /api/tracking/timeline` (time-series query) | Frontend spec §0 marks Phase 5; backend endpoint not yet built | TimeScrubber UI shell ships against empty/mocked trail with "pending Phase 5" notice (4D.5). File backend task in Phase 5 plan |
| Storybook + Chromatic visual regression | Frontend spec §18 / §14 — Phase 4.x, not v1 ship | Deferred to Phase 4.x; `pnpm test:a11y` runs axe against pages directly in the interim (4G.5) |
| Hindi (`hi`) i18n messages | Spec §17 — v2.x; English only for v1 | `react-intl` + `<FormattedMessage>` wired from day one (4A.10); adding Hindi is a translation file, not a code change |
| Users / Models API endpoints (if missing) | Discovered during 4E.11 / 4E.15 | If absent, file an explicit pre-work sub-task before building the dependent page — do NOT silently defer (CLAUDE.md §4.5) |

---

## Phase completion checklist (run before marking Status: COMPLETE)

- [ ] All pre-work P0–P2 merged; backend `ruff`/`mypy --strict`/`pytest` green.
- [ ] All sub-plan 4A–4G tasks checked.
- [ ] Frontend coverage: `shared/` ≥ 80%, `features/` ≥ 70%.
- [ ] `pnpm lint && pnpm typecheck && pnpm test:run` green; `pnpm test:e2e` + `pnpm test:a11y` green.
- [ ] Bundle + perf budgets within §15 limits.
- [ ] Production static serving verified (4G.8).
- [ ] Update CLAUDE.md §3 (active phase), write `docs/superpowers/notes/2026-06-24-vms-phase4-implementation-notes.md`, and use the `phase-wrap-up` skill.
- [ ] All "Known defers" have a tracked follow-up; none silently dropped.

---

**End of Phase 4 Frontend Implementation Plan.**
