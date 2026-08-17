# Tasks: Ambient Audio Capture Sessions

**Input**: Design documents from `/specs/001-ambient-audio-capture/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Contract tests are REQUIRED (constitution Principle II / SC-005). Audio-device integration tests are manual scripts, never CI (constitution Development Workflow).

**Organization**: Tasks are grouped by user story. US1 = start/stop capture, US2 = failure survival, US3 = preflight readiness, US4 = ambient readiness.

**⚠️ Constitution gate (d)**: Tasks marked **[GATE-D]** open real audio devices. Implementation MUST halt for human approval before the first such task. Everything else runs device-free (fake provider).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1..US4 per spec.md

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Create project skeleton: `pyproject.toml` (pinned deps per plan.md Pinned Versions, `[dev]` extra, editable install), package dirs `src/ambient_recorder/{models,audio,storage,api}/__init__.py`, test dirs `tests/{contract,integration,unit,manual}/`
- [x] T002 [P] Typed settings in `src/ambient_recorder/config.py`: data_root, port (default 8377), host locked to 127.0.0.1, min_free_disk_mb (default 2048), chunk_seconds (const 10) — env-overridable, validated at import
- [x] T003 [P] JSON-lines structured logging setup in `src/ambient_recorder/logging.py` (constitution V): timestamp, level, event, context fields; configure at process start
- [x] T004 [P] Configure ruff (lint + format) in `pyproject.toml` and a `check` script

**Checkpoint**: `pip install -e ".[dev]"` succeeds; `ruff check` clean

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Contracts-first per constitution II — every boundary typed before any implementation logic.

- [x] T005 [P] Domain models in `src/ambient_recorder/models/session.py`: Session, CaptureSource, AudioChunk, SessionEvent, SourceKind/SessionStatus/SourceStatus/EventType enums, per data-model.md (states, field rules, ULID ids)
- [x] T006 [P] API payload models in `src/ambient_recorder/models/api.py`: SessionCreateRequest, SessionSummary, SessionDetail, SessionListResponse, DeviceReadiness, DeviceReadinessResponse, ErrorResponse with closed error-code enum, per contracts/rest-api.md
- [x] T007 [P] Capture Protocols in `src/ambient_recorder/audio/protocols.py`: DeviceEnumerator, CaptureProvider, CaptureStream (runtime_checkable), DeviceInfo, DeviceUnavailableError, callbacks — per contracts/protocols.md
- [x] T008 [P] Storage Protocols in `src/ambient_recorder/storage/protocols.py`: ChunkStore, MetadataStore, ChunkMeta, DiskFullError, ActiveSessionExistsError — per contracts/protocols.md
- [x] T009 [P] Contract test: schema round-trips in `tests/contract/test_models_roundtrip.py` — every model in models/session.py and models/api.py survives `model_validate(model_dump(mode="json"))` (SC-005)
- [x] T010 FakeCaptureProvider + FakeDeviceEnumerator in `tests/support/fake_capture.py`: injectable frames, refusable devices, triggerable mid-stream device loss; Protocol conformance contract test in `tests/contract/test_protocol_conformance.py`
- [x] T011 SQLite MetadataStore in `src/ambient_recorder/storage/metadata.py`: WAL mode, schema migration-on-open, partial unique index `one_active`, all MetadataStore methods; unit tests in `tests/unit/test_metadata_store.py` (incl. ActiveSessionExistsError)
- [x] T012 [P] Atomic WAV ChunkStore in `src/ambient_recorder/storage/chunks.py`: `.part` write → rename, inventory() with orphan cleanup, DiskFullError on ENOSPC; unit tests in `tests/unit/test_chunk_store.py` (crash-sim: leftover .part discarded)
- [x] T013 FastAPI app assembly in `src/ambient_recorder/main.py` + typed error handlers in `src/ambient_recorder/api/errors.py`: error envelope per contracts/rest-api.md, GET /health, startup logging; contract test for error envelope + /health in `tests/contract/test_error_envelope.py`, plus FR-010 guard: config rejects any non-loopback host and the app binds 127.0.0.1 only

**Checkpoint**: Foundation ready — all contract/unit tests green with zero audio devices touched

---

## Phase 3: User Story 1 - Start and stop a recording session (Priority: P1) 🎯 MVP

**Goal**: POST /sessions captures mic + system audio to separable 16 kHz mono WAV chunks; stop finalises with duration/size; list/inspect work.

**Independent Test**: quickstart.md Scenario 1 — start, capture ~1 min, stop, inspect; ffprobe confirms format and separability.

### Contract tests for User Story 1

- [x] T014 [P] [US1] Contract tests for session endpoints (fake provider) in `tests/contract/test_sessions_api.py`: POST /sessions 201 + atomic create/start, 409 when active exists, 422 malformed; POST stop 200 / 404 / 409; GET list ordering; GET inspect shape per contracts/rest-api.md

### Implementation for User Story 1

- [x] T015 [P] [US1] Resampler in `src/ambient_recorder/audio/resample.py`: native rate/channels → 16 kHz mono s16le via soxr (channel-average downmix); unit tests in `tests/unit/test_resample.py` (48k stereo→16k mono length/dtype)
- [x] T016 [US1] Capture engine in `src/ambient_recorder/audio/engine.py`: per-source bounded queue + writer thread, 10 s chunk cadence, seq numbering, stop() flushes final partial chunk then finalises session, single state lock, session owned by engine (research R6); unit tests for chunk cadence math in `tests/unit/test_engine_chunking.py`
- [x] T017 [US1] Session routes in `src/ambient_recorder/api/routes.py`: POST /sessions (atomic create+start via engine), POST /sessions/{id}/stop, GET /sessions, GET /sessions/{id}; wire into main.py
- [x] T018 [US1] Integration test full lifecycle with fake provider in `tests/integration/test_session_lifecycle.py`: start → inject N frames → stop → chunks on disk are valid WAVs, metadata matches inventory, duration derived from audio length not wall clock
- [x] T019 [US1] **[GATE-D — halt for human approval before this task]** WASAPI provider in `src/ambient_recorder/audio/wasapi.py`: PyAudioWPatch mic + loopback capture, host-API pre-warm at startup (research R7), device_id/label mapping per contracts/protocols.md; includes default-output poll (~2 s interval) that fires on_device_lost for the system source when the default device changes (spec edge case — a loopback stream keeps capturing the old, now-silent device)
- [x] T020 [US1] **[GATE-D]** Manual device test script + instructions in `tests/manual/test_us1_live_capture.py` / `tests/manual/README.md`: quickstart Scenario 1 with real devices, ffprobe verification per NFR-002

**Checkpoint**: US1 fully functional — MVP deliverable

---

## Phase 4: User Story 2 - Survive a mid-meeting failure (Priority: P2)

**Goal**: Ungraceful death loses ≤ 10 s/source; restart reconciles to `interrupted` unaided; client disconnects never affect capture; mid-session device loss degrades gracefully (FR-011).

**Independent Test**: quickstart.md Scenario 2 — kill -9 mid-capture, restart, session `interrupted` with playable chunks.

### Implementation for User Story 2

- [x] T021 [US2] Startup reconciliation in `src/ambient_recorder/storage/metadata.py` + hook in `src/ambient_recorder/main.py`: for each `active` session — discard .part, inventory chunks, recompute end/duration from chunks, status `interrupted`, append `reconciled` event, all before serving requests (research R5)
- [x] T022 [US2] Integration test reconciliation in `tests/integration/test_crash_reconciliation.py`: fabricate active-session rows + chunk files (+ stray .part) → boot app → interrupted status, correct duration, .part gone, idempotent on double boot; no-active-session boot is a silent no-op
- [x] T023 [P] [US2] Device-loss handling in `src/ambient_recorder/audio/engine.py`: on_device_lost → source ends at point of loss (final partial chunk flushed), `device_lost` event with kind/device_id/last_seq, session continues on survivor; both-lost → finalise `completed` (data-model rule); integration test via fake provider in `tests/integration/test_device_loss.py`, including the default-output-change-as-loss path (fake triggers loss the way the T019 poll does)
- [x] T024 [P] [US2] Client-independence test in `tests/integration/test_client_disconnect.py`: drop the HTTP client mid-session; capture continues, later stop succeeds (FR-009)
- [x] T025 [US2] **[GATE-D]** Manual crash + unplug scripts in `tests/manual/test_us2_crash_and_unplug.md`: kill -9 per quickstart Scenario 2; headset unplug mid-session verifying FR-011 event and survivor continuation

**Checkpoint**: US1 + US2 independently verifiable

---

## Phase 5: User Story 3 - Device sanity before it matters (Priority: P3)

**Goal**: Readiness reporting before start; start strictly refused (nothing created) on missing device or low disk.

**Independent Test**: quickstart.md Scenario 3 — unplugged mic → 424 naming `mic`, no session row; low threshold → 507.

### Implementation for User Story 3

- [x] T026 [US3] GET /devices in `src/ambient_recorder/api/routes.py` using DeviceEnumerator.readiness() incl. `default_changed` detection (compare vs last session's device ids from metadata); contract test in `tests/contract/test_devices_api.py`
- [x] T027 [US3] Start preflight in `src/ambient_recorder/api/routes.py` + engine: both sources required (FR-012) → 424 `device_missing` with `detail.missing`; disk check (FR-007, config threshold) → 507 `disk_space_low` with free/required; contract tests in `tests/contract/test_preflight.py` proving no session row is created on refusal
- [x] T028 [P] [US3] Mid-session disk-full safe finalise in `src/ambient_recorder/audio/engine.py`: DiskFullError → `disk_low` event, finalise session cleanly without corrupting persisted chunks; integration test in `tests/integration/test_disk_full.py`
- [x] T029 [US3] **[GATE-D]** Manual readiness walkthrough in `tests/manual/test_us3_readiness.md`: real unplug → 424; threshold bump → 507 (quickstart Scenario 3)

**Checkpoint**: All refusal paths typed, tested, and side-effect-free

---

## Phase 6: User Story 4 - Ambient readiness (Priority: P4)

**Goal**: With the recorder long-running, session start takes effect ≤ 2 s, repeatedly, without process restart.

**Independent Test**: quickstart.md Scenario 4 — timed start on a warm process ≤ 2 s, repeated 3×.

### Implementation for User Story 4

- [x] T030 [US4] Repeated start/stop integration test in `tests/integration/test_repeated_sessions.py`: 5 sequential sessions on one app instance (fake provider), no state leakage, list shows all
- [x] T031 [US4] Start-latency instrumentation in `src/ambient_recorder/audio/engine.py` + `src/ambient_recorder/api/routes.py`: log request→first-frame latency as structured event; CI test asserts only a generous ceiling (< 5 s, flake-resistant) — the strict 2 s SC-004 check is manual (T032)
- [x] T032 [US4] **[GATE-D]** Manual timed-start check in `tests/manual/test_us4_latency.md`: real devices, warm process, `time curl` 3× per quickstart Scenario 4 (SC-004)

**Checkpoint**: All four user stories independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T033 [P] OpenAPI surface guard test in `tests/contract/test_openapi_surface.py`: `app.openapi()` contains exactly the six documented routes (contracts/rest-api.md item 4)
- [x] T034 [P] README.md at repo root: what the recorder is, quickstart pointer, privacy stance (constitution I), gate (d) note for contributors
- [ ] T035 **[GATE-D]** 60-minute soak per `tests/manual/test_soak.md`: SC-001 (both sources intact, ≤ 250 MB/hour) and SC-006 (< 5% CPU, < 200 MB RAM, 0% GPU) recorded in the doc
- [x] T036 Run full quickstart.md validation end-to-end; fix discrepancies between docs and behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → all user stories
- **US1 (Phase 3)**: only on Foundational
- **US2 (Phase 4)**: on US1's engine (T016) — reconciliation and device-loss extend it
- **US3 (Phase 5)**: on US1's routes (T017); T028 on engine
- **US4 (Phase 6)**: on US1; T030 benefits from US2/US3 refusal paths existing but does not require them
- **Polish (Phase 7)**: after desired stories complete

### Parallel Opportunities

- Phase 1: T002, T003, T004 after T001
- Phase 2: T005–T009 all [P] (distinct files); T011/T012 [P] after T008; T010 after T007
- Phase 3: T014 + T015 in parallel; T016 after T015
- Phase 4: T023, T024 in parallel after T021
- Cross-story: after Foundational, US1 contract tests (T014) can be written while US1 implementation proceeds

### Gate-D task set (require approval before first execution)

T019, T020, T025, T029, T032, T035 — everything else is device-free.

---

## Implementation Strategy

**MVP first**: Phases 1–3 (T001–T020) deliver US1 — real capture with durable chunks. Stop and validate via quickstart Scenario 1 before proceeding.

**Incremental delivery**: US2 (durability guarantees) is the highest-value increment after MVP and should follow immediately — the constitution's "sessions are sacred" principle is only fully honored once T021–T025 land. US3 and US4 are each small, independent increments.

**Suggested commit cadence**: one commit per task or per checkpoint; contract files (T005–T008) in their own commits per constitution II.
