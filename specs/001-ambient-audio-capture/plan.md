# Implementation Plan: Ambient Audio Capture Sessions

**Branch**: `001-ambient-audio-capture` | **Date**: 2026-07-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-ambient-audio-capture/spec.md`

## Summary

Deliver the recorder's foundation: a single long-lived local FastAPI process
that captures microphone and system (loopback) audio concurrently, persists
both as separable 10-second WAV chunks at 16 kHz mono 16-bit PCM, records
session metadata in SQLite, and exposes a typed local REST API for session
lifecycle (create/start, stop, list, inspect) plus device readiness.
Durability is the design driver: incremental chunk writes bound data loss to
10 s per source, and startup reconciliation finalises interrupted sessions
without user intervention.

## Technical Context

**Language/Version**: Python 3.12 (pinned in plan; see Pinned Versions below)

**Primary Dependencies**: FastAPI + uvicorn (API), Pydantic v2 (contracts),
PyAudioWPatch (WASAPI mic + loopback capture), python-soxr (48 kHz → 16 kHz
resample), numpy (buffer handling), stdlib sqlite3 (metadata)

**Storage**: SQLite (WAL mode) for session metadata; WAV chunk files on local
disk under a per-session directory (`data/sessions/<id>/<source>/`)

**Testing**: pytest; contract tests via Pydantic schema round-trips +
FastAPI TestClient with a fake capture provider; audio-device integration
tests run manually (constitution: not in CI)

**Target Platform**: Windows 11 desktop, local-only (binds 127.0.0.1)

**Project Type**: Single project — one local web-service process

**Performance Goals**: Session start ≤ 2 s from request to first captured
frame; steady-state < 5% CPU, 0% GPU, < 200 MB RAM alongside a live video
call (NFR-001, SC-004, SC-006)

**Constraints**: Max data-loss window 10 s per source (FR-002); persisted
format fixed at 16 kHz mono 16-bit PCM per source (NFR-002); ≤ ~500 MB per
2-hour session (NFR-003); no off-machine transmission (FR-010); recording
survives client disconnects (FR-009)

**Scale/Scope**: Single user, single machine, one active session at a time,
sessions up to ~4 hours; two capture sources per session

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Local-First, Privacy by Default | PASS | API binds 127.0.0.1 only; no telemetry; no outbound calls anywhere in design (FR-010). |
| II. Typed Contracts at Every Boundary | PASS | Phase 1 defines Pydantic models for all REST payloads and `Protocol`s for capture/storage providers before any implementation ([contracts/](contracts/)). Contract changes land first in contract files. |
| III. VRAM Budget Is the Binding Constraint | PASS (N/A) | This feature loads no ML models. VRAM arithmetic: 0 GB used, 8 GB free — full headroom preserved for future STT/LLM features. NFR-001 additionally forbids GPU use for capture. |
| IV. Phased Delivery with Checkpoint Gates | PASS | Gate (a) spec: approved. Gate (b) plan: this document awaits approval. Gate (c) heavy deps: **not triggered** — no PyTorch/CUDA, no model downloads; all deps are small wheels. Gate (d) audio devices: **triggered** — implementation MUST halt for approval before the first task that opens system audio devices. |
| V. Fail Fast, Log Structurally | PASS | Startup validates device presence and disk space before any session (FR-005, FR-007); JSON-lines logging is a foundational task from day one. |
| VI. Boring Tech, Single Process First | PASS | One FastAPI process, SQLite, files on disk. No queues, containers, or extra services. |
| VII. Sessions Are Sacred | PASS | 10 s chunked writes (never memory-only), session owned by the recorder process not the client (FR-009), startup reconciliation (FR-008), device loss degrades rather than aborts (FR-011). |

**Post-Phase-1 re-check**: PASS — design artifacts introduce no new
violations; all provider boundaries are Protocol-typed, all payloads are
Pydantic models, storage remains SQLite + files.

## Project Structure

### Documentation (this feature)

```text
specs/001-ambient-audio-capture/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── rest-api.md      # HTTP endpoint contracts (payload schemas, errors)
│   └── protocols.md     # Internal provider Protocols (capture, storage)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/ambient_recorder/
├── __init__.py
├── main.py              # FastAPI app assembly, startup validation, reconciliation
├── config.py            # Settings (paths, disk threshold, port) — env/file, typed
├── logging.py           # JSON-lines structured logging setup
├── models/              # Pydantic contracts shared by API + internals
│   ├── session.py       # Session, CaptureSource, AudioChunk, SessionEvent
│   └── api.py           # Request/response/error payloads
├── audio/
│   ├── protocols.py     # CaptureProvider / DeviceEnumerator Protocols
│   ├── wasapi.py        # PyAudioWPatch implementation (mic + loopback)
│   ├── resample.py      # 48 kHz device rate → 16 kHz mono via soxr
│   └── engine.py        # Session capture orchestration, chunk cadence
├── storage/
│   ├── protocols.py     # ChunkStore / MetadataStore Protocols
│   ├── chunks.py        # WAV chunk writer (atomic per-chunk files)
│   └── metadata.py      # SQLite metadata store (WAL), reconciliation queries
└── api/
    ├── routes.py        # /devices, /sessions endpoints
    └── errors.py        # Typed error responses, exception handlers

tests/
├── contract/            # Schema round-trips, Protocol conformance (REQUIRED)
├── integration/         # Fake-provider session lifecycle, crash reconciliation
├── unit/                # Chunking math, resampler, reconciliation logic
└── manual/              # Real-device scripts (run by a human, not CI)
```

**Structure Decision**: Single project (constitution VI). The package splits
by boundary — `models` (contracts), `audio` (capture), `storage`
(persistence), `api` (transport) — so each Protocol seam in
[contracts/protocols.md](contracts/protocols.md) maps to exactly one
directory, and the fake capture provider used in CI tests plugs in at the
`audio.protocols` seam.

## Pinned Versions

Per constitution (Development Workflow), pins live here until shared by a
second feature:

| Package | Version | Note |
|---------|---------|------|
| Python | 3.12.x | CPython, python.org build |
| fastapi | 0.115.x | |
| uvicorn | 0.34.x | standard extra |
| pydantic | 2.10.x | v2 API |
| PyAudioWPatch | 0.2.12.x | WASAPI loopback fork of PyAudio |
| soxr | 0.5.x | resampling |
| numpy | 2.2.x | frame buffers |
| pytest | 8.x | dev only |
| httpx | 0.28.x | dev only (TestClient) |

No PyTorch, no CUDA, no model downloads — gate (c) is not triggered by this
feature.

## Checkpoint Gates (constitution IV) for this feature

1. **Gate (b) — after plan**: human approval of this plan before
   `/speckit-tasks` / implementation.
2. **Gate (d) — before audio devices**: approval required before executing
   the first task that opens real capture devices (the `audio/wasapi.py`
   implementation and any manual device test). Everything earlier (models,
   storage, API with fake provider) proceeds without touching devices.

## Complexity Tracking

No constitution violations — table intentionally empty.
