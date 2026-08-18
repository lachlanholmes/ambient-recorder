# Tasks: Local Transcription

**Input**: Design documents from `/specs/002-local-transcription/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Contract tests are REQUIRED (constitution Principle II / SC-005). Model-dependent accuracy, latency, and VRAM checks are manual (real hardware), never CI. All CI tests use `FakeSpeechEngine`.

**Organization**: US1 = live transcript, US2 = transcription status, US3 = on-demand/backfill, US4 = recording never disturbed.

**⚠️ Constitution gate (c)**: Tasks marked **[GATE-C]** install heavy dependencies (~1 GB CUDA/cuDNN wheels) and download model weights (~1.5 GB). Implementation MUST halt for human approval before the first such task. Everything else is model-free.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [ ] T001 Add `transcription` optional extra to `pyproject.toml` (faster-whisper ~=1.1, ctranslate2 ~=4.5, nvidia-cublas-cu12, nvidia-cudnn-cu12 ~=9) — declared only, not installed until gate (c); add `data/models/` to `.gitignore`
- [ ] T002 [P] Graduate shared pins to `constraints.txt` at repo root (python/fastapi/pydantic/numpy/pytest/httpx per constitution Development Workflow) and reference it from README dev setup
- [ ] T003 [P] Create package skeleton `src/ambient_recorder/transcription/__init__.py` and `tests/support/fake_speech.py` stub, `tests/manual/` placeholders listed in quickstart

**Checkpoint**: `pip install -e ".[dev]"` unchanged and green; `[transcription]` extra resolvable but not installed

---

## Phase 2: Foundational (contracts first — constitution II)

- [ ] T004 [P] Transcript domain + API models in `src/ambient_recorder/models/transcript.py`: Transcript, TranscriptSegment, TranscriptionJob, TranscriptState/JobState/Mode/Source enums, TranscriptResponse, TranscriptListResponse, TranscriptionJobResponse, TranscriptionReadiness, WS frame models (SegmentFrame, StatusFrame) per data-model.md + contracts/rest-api.md
- [ ] T005 [P] Extend `ErrorCode` in `src/ambient_recorder/models/api.py` with transcript_not_found, transcription_not_ready, session_still_active, transcription_already_running (own contract commit)
- [ ] T006 [P] Transcription Protocols in `src/ambient_recorder/transcription/protocols.py`: SpeechEngine, EngineFactory, RawSegment, EngineError/EngineNotReadyError, TranscriptStore, ChunkObserver/SessionObserver types per contracts/protocols.md
- [ ] T007 [P] Contract test round-trips for all new models in `tests/contract/test_transcript_models_roundtrip.py`
- [ ] T008 Capture-engine observer hooks in `src/ambient_recorder/audio/engine.py`: `add_chunk_observer(cb)` invoked on the writer thread after `record_chunk`; `add_session_observer(cb)` for started/stopped/finalized; observers wrapped so an exception is logged and never propagates into capture (constitution VII); unit test in `tests/unit/test_engine_observers.py` incl. a raising observer not affecting chunk writes
- [ ] T009 FakeSpeechEngine + FakeEngineFactory in `tests/support/fake_speech.py`: scripted RawSegments keyed by chunk index/track, configurable per-call delay (for lag/backlog tests), triggerable EngineError, readiness toggle; Protocol conformance test in `tests/contract/test_transcription_protocols.py`
- [ ] T010 SQLite TranscriptStore in `src/ambient_recorder/storage/transcripts.py`: tables transcripts/transcript_segments/transcription_jobs, seq assignment, current_transcript (newest that is neither failed nor pending), pending_transcript(session), segments_after, list/get, open_jobs, next_queued; unit tests in `tests/unit/test_transcript_store.py` (seq monotonic, current selection incl. pending/failed attempts not displacing a live one, supersede-by-insert)
- [ ] T011 [P] EnergyBuffer (per-track 100 ms RMS ring, ~30 s) + attribution rule (pure, returns attributed + deferred) in `src/ambient_recorder/transcription/attribution.py`; AttributionConfig (6 dB, 60% overlap defaults) in `src/ambient_recorder/config.py`; unit tests in `tests/unit/test_attribution.py`: bleed dropped, genuine overlap kept, symmetric case, thresholds boundary, span-not-yet-covered → deferred then resolved on next add
- [ ] T012 [P] Engine readiness/degradation in `src/ambient_recorder/transcription/readiness.py`: three-way outcome — `not_installed` (faster-whisper import fails → live mode skipped, sessions stay state `none`, no transcript row), `not_ready` (installed but model missing / no engine → live transcript created `failed`), `ready` (with chosen model); free-VRAM probe (nvidia-smi / ctranslate2 API, tolerant of absence), model-presence check in `data/models/`, policy medium→small-cuda→small-cpu, `model_missing` reason with the exact download command; unit tests with injected probes in `tests/unit/test_readiness_policy.py` covering all three outcomes
- [ ] T013 Wire store + readiness into `src/ambient_recorder/main.py` (create_app takes an EngineFactory; default = fake-free real factory), startup log of readiness, GET /transcription/readiness route in `src/ambient_recorder/api/routes.py`; contract test in `tests/contract/test_transcription_readiness_api.py`

**Checkpoint**: Contracts + storage + rules all green with no engine and no GPU

---

## Phase 3: User Story 1 — See what is being said, as it is said (P1) 🎯 MVP

**Goal**: A session auto-starts a live transcript; segments (me/them) stream over a cursor WebSocket within the lag bound; stop finalises; transcript persists across restart.

**Independent Test**: quickstart Scenario 1 + 2 with FakeSpeechEngine in CI; real model manually.

### Contract tests for User Story 1

- [ ] T014 [P] [US1] Contract tests for GET /sessions/{id}/transcript (+`?after`), GET /sessions/{id}/transcripts, GET /sessions/{id}/transcripts/{tid} in `tests/contract/test_transcript_api.py`: 200 shapes, 404 session/transcript, ordering by (start_s, seq)
- [ ] T015 [P] [US1] WebSocket contract tests in `tests/contract/test_transcript_stream.py`: replay+tail exactness across `after` values, status frame on connect and on state change, terminal status closes socket, 4404/4409 close codes

### Implementation for User Story 1

- [ ] T016 [US1] Live pipeline in `src/ambient_recorder/transcription/worker.py`: single worker thread with priority queue; on session started → create live Transcript+Job (or `failed: engine_not_ready`); on chunk finalized → enqueue (priority 0); on dequeue feed EnergyBuffer first, then rolling 5 s overlap window + pending-tail dedup (research R3); run attribution across paired-track results, re-queue deferred candidates into the pending tail; append segments; update lag; on session stopped → drain backlog → `finalising` → `completed(final)`; below-normal thread priority
- [ ] T017 [P] [US1] In-process segment pub/sub in `src/ambient_recorder/transcription/stream.py`: per-transcript subscribers, publish(segment|status), bounded per-subscriber buffers, thread-safe hand-off to the event loop
- [ ] T018 [US1] Transcript REST routes in `src/ambient_recorder/api/routes.py` (three GETs from contracts/rest-api.md) using TranscriptStore
- [ ] T019 [US1] WebSocket route in `src/ambient_recorder/api/ws.py`: `/sessions/{id}/transcript/stream?after=`, replay from store then tail from stream.py, status frames on connect/state change/every 5 s, close on terminal state; register in main.py
- [ ] T020 [US1] Integration test live end-to-end with fakes in `tests/integration/test_live_transcription.py`: start session → push chunks (fake provider) → fake engine emits scripted segments → WS client receives me/them segments in order → stop → finalising → completed(final) → GET transcript identical to streamed set → restart app → transcript still current
- [ ] T021 [US1] Integration test rolling-window dedup in `tests/integration/test_live_window.py`: scripted segment straddling a chunk boundary is emitted exactly once, whole
- [ ] T022 [US1] **[GATE-C — halt for human approval before this task]** Install `[transcription]` extra, download Whisper `medium` (and `distil-large-v3` for comparison) into `data/models/` via `scripts/fetch_models.py`; assert `ctranslate2.get_cuda_device_count() > 0` before proceeding (else the "cuda" degradation branch is silently CPU — stop and fix the wheel variant); measure and record real VRAM (weights, peak during transcribe) + throughput on the RTX 4070 into research.md R2, confirm/adjust the model choice
- [ ] T023 [US1] **[GATE-C]** WhisperEngine + WhisperEngineFactory in `src/ambient_recorder/transcription/whisper_engine.py` (faster-whisper, int8_float16, beam 1 live / 5 on-demand, word timestamps, applies readiness policy); make it the default factory in `__main__.py`; structural conformance test (no load) added to `tests/contract/test_transcription_protocols.py`
- [ ] T024 [US1] **[GATE-C]** Manual scripts `tests/manual/ws_tail.py` (WS tail with `--after`) and `tests/manual/test_002_live.md` (quickstart Scenarios 1–2 on real devices + model; record observed lag)

**Checkpoint**: Live transcription works end-to-end — MVP

---

## Phase 4: User Story 2 — Know where transcription stands (P2)

**Goal**: State always inspectable (live+lag, finalising, completed, failed+reason); engine failure never touches recording.

**Independent Test**: quickstart Scenario 6 + status assertions in CI.

- [ ] T025 [US2] Job/state exposure: `job` block in TranscriptResponse (state, lag_s, progress, failure_reason) and lag update cadence in `worker.py`; contract test additions in `tests/contract/test_transcript_api.py`
- [ ] T026 [US2] Engine-failure handling in `worker.py`: EngineError mid-live → transcript `failed` with reason, status frame pushed, socket closed, session continues; integration test in `tests/integration/test_transcription_failure.py` proving chunk_counts keep growing and stop still succeeds
- [ ] T027 [P] [US2] Not-ready-at-start paths: installed-but-not-ready → live transcript created as `failed: engine_not_ready` immediately (SC-005); not-installed → no transcript row, session transcription state `none`, GET transcript 404 transcript_not_found; integration tests for both in `tests/integration/test_engine_not_ready.py`
- [ ] T028 [P] [US2] Structured events in `worker.py`/`readiness.py`: transcription_started, segment_emitted (count), lag_report (every chunk), transcription_finalised, transcription_failed, engine_loaded (model/device/vram) — assert presence in the US1 integration test log capture

**Checkpoint**: Every path lands in a defined state with reason

---

## Phase 5: User Story 3 — Transcribe stored sessions on demand (P3)

**Goal**: POST /transcribe on any non-active session; progress; result becomes current, prior kept superseded; retry after failure; legacy sessions work.

**Independent Test**: quickstart Scenario 3.

- [ ] T029 [P] [US3] Contract tests for POST /sessions/{id}/transcribe in `tests/contract/test_transcribe_api.py`: 202 job, 404, 409 session_still_active, 409 already_running, 503 not_ready
- [ ] T030 [US3] On-demand job execution in `worker.py`: iterate stored chunks per track via ChunkStore.inventory, chunk-granular progress, priority 1 (yields to live), beam 5, same attribution, completed(final) or failed with reason; POST route in `api/routes.py`
- [ ] T031 [US3] Integration tests in `tests/integration/test_on_demand.py`: legacy session (no transcript) → completed; session with live transcript → while job pending the live one is still current and `pending_job` is populated → on success new current + old superseded (list shows both, get-by-id works); failed job → live transcript remains current, retry creates a fresh attempt
- [ ] T032 [US3] Startup reconciliation for transcription in `storage/transcripts.py` + hook in `main.py`: orphaned live → `interrupted_live` (segments kept); orphaned running on-demand → requeued; integration test in `tests/integration/test_transcription_reconciliation.py`
- [ ] T033 [US3] **[GATE-C]** Manual `tests/manual/test_002_on_demand.md`: transcribe a feature-001-era session (e.g. the soak) with the real model; record throughput vs NFR-002 (≥ 4× real time)

**Checkpoint**: Backfill + supersede + restart all covered

---

## Phase 6: User Story 4 — Transcription never disturbs recording (P4)

**Goal**: FR-008 — zero chunk loss under live STT; ≤ 2 s start while an on-demand job runs; live has priority.

**Independent Test**: quickstart Scenario 5.

- [ ] T034 [US4] Priority/yield integration test in `tests/integration/test_transcription_priority.py`: slow fake engine + on-demand job in progress → start new session → start ≤ 5 s (flake-resistant CI ceiling, matching feature 001; strict 2 s is manual in T036), live chunks processed before remaining on-demand chunks
- [ ] T035 [US4] Feature 001 regression gate: full existing suite runs unchanged with the transcription worker active (conftest wiring in `tests/conftest.py`), plus never-skip test in `tests/integration/test_never_skip.py`: slow engine, many chunks → all chunks eventually transcribed, lag rises then falls, `completed` only after backlog drains
- [ ] T036 [US4] **[GATE-C]** Manual `tests/manual/test_002_corun_soak.md`: 2-hour live-transcribed session with playback — chunk_counts ≈ 720/720, zero .part orphans, nvidia-smi steady VRAM recorded, CPU/RAM additive to feature 001 within NFR-003, observed p95 lag vs SC-002; contention test (start during on-demand job) timed

**Checkpoint**: All four stories independently verified

---

## Phase 7: Polish

- [ ] T037 [P] OpenAPI surface guard update in `tests/contract/test_openapi_surface.py` (new REST routes; WS asserted via app.routes)
- [ ] T038 [P] **[GATE-C]** Accuracy script + scoring sheet `tests/manual/accuracy_script.md` (SC-001: scripted two-sided dialogue with deliberate bleed; ≥ 90% attribution) and tune AttributionConfig defaults from results
- [ ] T039 [P] README + docs/backlog.md update: transcription setup (gate-c commands), readiness endpoint, model choice, known lag caveat (chunk-boundary), sub-second streaming as backlog item
- [ ] T040 Run full quickstart.md end-to-end; fix doc/behaviour drift

---

## Dependencies & Execution Order

- Setup → Foundational → US1 → (US2, US3 in parallel) → US4 → Polish
- US2 extends worker.py from US1 (T016); US3 extends worker.py + adds reconciliation; US4 verifies both
- T022 (gate c) blocks only T023/T024 and the other **[GATE-C]** manual tasks (T033, T036, T038); all CI-facing tasks (T001–T021, T025–T032, T034–T035, T037, T039–T040) run without it

### Parallel Opportunities

- Phase 2: T004, T005, T006, T007 together; then T009/T010/T011/T012 together after T006
- Phase 3: T014 + T015 + T017 together; T016 after T009/T010/T011
- Phase 4: T027 + T028 in parallel with T025/T026
- Phase 7: T037, T038, T039 together

### Gate-C task set (approval before first execution)

T022, T023, T024, T033, T036, T038

---

## Implementation Strategy

**MVP**: Phases 1–3 (T001–T024) — live transcription over WebSocket. Everything through T021 is provable in CI with fakes; T022–T024 make it real on the GPU.

**Then**: US2 (honest state) is small and should follow immediately; US3 gives you backfill of the feature-001 archive; US4 is the constitution's insurance and closes with the co-run soak.

**Commit cadence**: contract files (T004–T006) each in own commits; then per task or checkpoint.
