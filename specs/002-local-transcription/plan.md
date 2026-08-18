# Implementation Plan: Local Transcription

**Branch**: `002-local-transcription` | **Date**: 2026-08-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-local-transcription/spec.md`

## Summary

Add local speech-to-text to the recorder in two modes over one engine:
**live** (starts automatically with every session, consumes chunks as the
capture engine finalises them, pushes attributed segments over a
cursor-based WebSocket) and **on-demand** (a queued job over stored
chunks for legacy/interrupted/failed sessions). Both use faster-whisper
(`medium`, int8_float16, CUDA) inside the existing FastAPI process,
budgeted to co-reside with a future ~3.5 GB LLM. Attribution is
two-track (`me`/`them`) with an energy-ratio rule that resolves the
field-verified speaker bleed. Transcripts are versioned per session
(supersede-but-keep) in the existing SQLite store.

## Technical Context

**Language/Version**: Python 3.12 (feature 001's venv)

**Primary Dependencies**: faster-whisper (CTranslate2 backend, CUDA 12 +
cuDNN 9 via `nvidia-*` pip wheels), numpy (already present), FastAPI
WebSocket support (already present via uvicorn[standard]). **No PyTorch**
— CTranslate2 runs Whisper without it (research R1).

**Storage**: Same SQLite (WAL) database as feature 001, three new tables;
Whisper model weights cached on disk (~1.5 GB, one-time download)

**Testing**: pytest; contract tests via a `FakeSpeechEngine` that returns
scripted segments (no model in CI); accuracy/latency/VRAM verified by
manual tests on real hardware

**Target Platform**: Windows 11, RTX 4070 Laptop (8188 MiB VRAM,
measured 0 MiB idle 2026-08-18)

**Project Type**: Single project — extends the existing local web service

**Performance Goals**: live lag ≤ 10 s p95, throughput ≥ 1× real time on
two tracks over 2 h (NFR-001); on-demand ≥ 4× real time (NFR-002);
finalise ≤ 30 s under normal load (SC-007)

**Constraints**: STT VRAM ≤ 3.5 GB steady state so a ~3.5 GB Q4 3–4B LLM
plus 1 GB headroom fit (NFR-003, constitution III); zero impact on
feature 001's chunk-loss and 2 s start guarantees (FR-008); never skip
audio (FR-013); local-only (FR-009); transcript ≤ 5% of audio size
(NFR-004)

**Scale/Scope**: single user; sessions to ~4 h; one live job + at most
one on-demand job at a time; segments at utterance granularity

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Local-First, Privacy by Default | PASS | Whisper runs in-process on the local GPU; transcripts live in the local SQLite; WebSocket bound to 127.0.0.1 like the REST API. The only network use is the one-time model download from Hugging Face (weights, not user data), behind gate (c). |
| II. Typed Contracts at Every Boundary | PASS | New `SpeechEngine` and `TranscriptStore` Protocols, Pydantic models for all REST + WebSocket payloads, defined in Phase 1 before implementation; contract changes land first in their own commits. |
| III. VRAM Budget Is the Binding Constraint | PASS | Arithmetic (research R2): Whisper `medium` int8_float16 ≈ 1.6 GB weights + ≈ 0.6 GB activations/beam ≈ **2.2 GB**; LLM reserve 3.5 GB; headroom 1.0 GB; total **6.7 GB of 8.0 GB** — 1.3 GB spare beyond mandated headroom. Degradation specified: `small` int8 (≈ 0.9 GB) → CPU int8 fallback, chosen at load time by measured free VRAM. |
| IV. Phased Delivery with Checkpoint Gates | PASS | Gate (a) spec approved; gate (b) this plan awaits approval. **Gate (c) triggered**: CTranslate2 CUDA wheels (~1 GB of `nvidia-*` libraries) and Whisper `medium` weights (~1.5 GB) — implementation MUST halt for approval before the install/download task. Gate (d) not re-triggered (no new device access; live mode consumes chunks the capture engine already writes). |
| V. Fail Fast, Log Structurally | PASS | Model presence + VRAM checked at process start (readiness reported like devices); engine failure → typed `failed` state with reason, recording unaffected; JSON-lines events for lag, job transitions, model load. |
| VI. Boring Tech, Single Process First | PASS | Same FastAPI process, same SQLite, one worker thread; no queue broker, no sidecar service, no containers. Ollama is *not* a dependency of this feature (LLM is only a VRAM reservation). |
| VII. Sessions Are Sacred | PASS | Live STT is a *consumer* of finalised chunks, never in the capture path; runs at lower thread priority; FR-008 verified by the feature 001 test suite continuing to pass plus a co-run soak. Never-skip (FR-013) means overload costs latency, not data. |

**Post-Phase-1 re-check**: PASS — design introduces no additional
processes, no new device access, and stays within the VRAM arithmetic;
all boundaries are Protocol/Pydantic typed.

## Project Structure

### Documentation (this feature)

```text
specs/002-local-transcription/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── rest-api.md      # New endpoints + WebSocket stream contract
│   └── protocols.md     # SpeechEngine / TranscriptStore Protocols
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/ambient_recorder/
├── models/
│   └── transcript.py    # Transcript, TranscriptSegment, TranscriptionJob + API payloads
├── transcription/
│   ├── protocols.py     # SpeechEngine, TranscriptStore Protocols
│   ├── whisper_engine.py# faster-whisper implementation (gate c)
│   ├── attribution.py   # me/them decision from paired-track energy (pure fn)
│   ├── worker.py        # Single worker thread: live consumer + on-demand queue, priority
│   ├── stream.py        # In-process pub/sub of segments → WebSocket fan-out
│   └── readiness.py     # Model presence + VRAM check, engine choice/degradation
├── storage/
│   └── transcripts.py   # SQLite TranscriptStore (transcripts, segments, jobs)
├── audio/
│   └── engine.py        # + on_chunk_finalized hook (one line of new surface)
└── api/
    ├── routes.py        # + /sessions/{id}/transcript*, /transcription/readiness
    └── ws.py            # WebSocket /sessions/{id}/transcript/stream

tests/
├── contract/            # schema round-trips, endpoint + WS contracts, Protocol conformance
├── integration/         # live pipeline with FakeSpeechEngine, on-demand, supersede, restart
├── unit/                # attribution rule, cursor semantics, job state machine
├── support/fake_speech.py
└── manual/              # accuracy (SC-001), latency (SC-002), VRAM, co-run soak
```

**Structure Decision**: New `transcription/` package mirrors feature 001's
boundary-per-directory rule: `models` (contracts), `transcription`
(engine + orchestration), `storage/transcripts.py` (persistence),
`api/ws.py` (transport). The capture engine gains a single observer hook
so live mode is decoupled from capture — feature 001's engine never
imports transcription code.

## Pinned Versions

| Package | Version | Note |
|---------|---------|------|
| faster-whisper | 1.1.x | CTranslate2 Whisper |
| ctranslate2 | 4.5.x | pulled by faster-whisper; CUDA 12 build |
| nvidia-cublas-cu12, nvidia-cudnn-cu12 | 12.x / 9.x | pip wheels; no system CUDA toolkit needed |
| websockets | 13.x | already via uvicorn[standard] |

Project-wide pins graduate to a constraints file now that two features
share Python/FastAPI/Pydantic/numpy pins (constitution, Development
Workflow) — a setup task.

## Checkpoint Gates (constitution IV) for this feature

1. **Gate (b) — after plan**: approval of this document.
2. **Gate (c) — heavy dependencies**: approval before installing the
   CUDA/cuDNN wheels (~1 GB) and downloading Whisper `medium` (~1.5 GB).
   Everything before it (contracts, store, worker, WS, fake engine, full
   CI suite) is model-free.
3. Gate (d): not triggered.

## Complexity Tracking

No constitution violations — table intentionally empty.
