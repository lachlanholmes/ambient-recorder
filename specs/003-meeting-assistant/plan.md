# Implementation Plan: Meeting Assistant

**Branch**: `003-meeting-assistant` | **Date**: 2026-08-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-meeting-assistant/spec.md`

## Summary

Add a local-LLM assistant layer over feature 002's attributed transcripts:
structured summaries (staged condensation for long meetings), multi-turn
grounded Q&A with citation validation, and live in-meeting questions
against the transcript-so-far — answers streamed over WebSocket as they
generate. Runtime is **Ollama** (constitution-named; found NOT installed —
installing it and pulling a ~2 GB quantised 3B model is this feature's
gate (c)), driven from a new serial assistant worker inside the existing
FastAPI process. Grounding is retrieval-based: the model only ever sees
numbered transcript excerpts, and citations are validated before a turn
completes. Storage extends the same SQLite with summaries, conversations,
turns, and tasks — supersede-but-keep throughout.

## Technical Context

**Language/Version**: Python 3.12 (existing venv)

**Primary Dependencies**: Ollama (external localhost service, installed at
gate (c)); httpx (already present) for its streaming API. **No new Python
ML dependencies** — the LLM lives behind Ollama.

**Storage**: Existing SQLite (WAL): `summaries`, `conversations`,
`conversation_turns`, `assistant_tasks` tables

**Testing**: pytest; `FakeAssistantEngine` (scripted token streams) for
all CI; real-model accuracy/latency/VRAM are manual tests

**Target Platform**: Windows 11, RTX 4070 Laptop 8 GB (0 MiB idle
measured 2026-08-24)

**Project Type**: Single project — extends the existing service

**Performance Goals**: summary of 60-min meeting ≤ 3 min (NFR-001);
post-meeting answer first token ≤ 10 s, complete ≤ 60 s (NFR-002); live
answer first token ≤ 15 s (NFR-003)

**Constraints**: LLM + live STT co-resident in 8 GB with ≥ 1 GB headroom
(NFR-004; STT measured 1.12 GB); assistant strictly below capture/STT
priority (FR-008/FR-011); grounded-with-citations only (FR-002/FR-012);
local-only, no egress except gate-(c) model pull (FR-007/SC-007);
layered install honesty (FR-009)

**Scale/Scope**: single user; transcripts to ~5 h (field-proven size:
3,406 segments); one assistant task at a time, live questions first

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Local-First, Privacy by Default | PASS | Ollama bound to 127.0.0.1; model pull at gate (c) is the only network use (weights, not user data); assistant consumes transcript text only, never audio; SC-007 asserts no egress during operation. This feature is NOT the router clause — no frontier escalation anywhere. |
| II. Typed Contracts at Every Boundary | PASS | `AssistantEngine`/`AssistantStore` Protocols + Pydantic models for every REST/WS payload defined in Phase 1 before implementation; contract-first commits. |
| III. VRAM Budget Is the Binding Constraint | PASS | Measured arithmetic (research R2): STT co-resident 1.12 GB + Q4 3B LLM ≈ 2.6–3.4 GB incl. KV cache + 1.0 GB headroom = **≤ 5.5 of 8.0 GB**. Degradation specified: smaller context → smaller model (qwen3 1.7B-class) → assistant `not_ready` (capture/STT never degrade for the assistant's sake). Re-measured at gate (c) before the model choice freezes. |
| IV. Phased Delivery with Checkpoint Gates | PASS | Gate (a) spec approved; gate (b) this plan. **Gate (c) triggered**: install Ollama (~700 MB) + pull candidate models (~2–3 GB); halt for approval before that task. Gate (d) not triggered (no device access; assistant is a transcript consumer). |
| V. Fail Fast, Log Structurally | PASS | Readiness checks runtime-reachable + model-present at startup and on demand with remedies (`ollama_not_running`, `model_missing: ollama pull …`); typed task failures; JSON-lines events for task lifecycle, token throughput, citation validation. |
| VI. Boring Tech, Single Process First | PASS with note | Ollama is a second local process — sanctioned by the constitution's own Environment Constraints naming it the LLM runtime (the explicit carve-out; our code stays one process talking to it over localhost HTTP). Discovered stale: Ollama is not currently installed although the constitution lists it as available — gate (c) installs it, and a constitution PATCH amendment should update that environment line afterwards. |
| VII. Sessions Are Sacred | PASS | Assistant is a pure consumer (transcript store + 002's segment stream); its failure cannot touch capture or STT (separate worker, observer-isolated); FR-008 verified by running the 001+002 suites with the assistant wired plus a live co-run check. |

**Post-Phase-1 re-check**: PASS — design adds no new processes beyond the
constitution-named runtime, no new device access; all boundaries typed.

## Project Structure

### Documentation (this feature)

```text
specs/003-meeting-assistant/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── rest-api.md      # REST + WS answer-stream contract
│   └── protocols.md     # AssistantEngine / AssistantStore Protocols
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
src/ambient_recorder/
├── models/
│   └── assistant.py     # Summary, Conversation, Turn, AssistantTask + API payloads
├── assistant/
│   ├── protocols.py     # AssistantEngine, AssistantStore Protocols
│   ├── ollama_engine.py # Ollama HTTP client engine (streaming), gate (c)
│   ├── readiness.py     # runtime-reachable + model-present + VRAM policy
│   ├── retrieval.py     # lexical segment retrieval + prompt-budget packing (pure)
│   ├── prompts.py       # prompt templates: qa, summary-map, summary-reduce
│   ├── grounding.py     # citation extraction/validation (pure)
│   ├── summarize.py     # staged condensation orchestration
│   └── worker.py        # serial task queue: live-ask > ask > summarize
├── storage/
│   └── assistant.py     # SQLite AssistantStore
└── api/
    ├── assistant_routes.py  # readiness, summarize, summary(ies), conversations, ask
    └── ws.py                # + /conversations/{cid}/stream (answer tokens)

tests/
├── contract/            # model round-trips, endpoint + WS contracts, Protocol conformance
├── integration/         # fake-engine: summary flow, Q&A grounding, live ask, supersede, restart
├── unit/                # retrieval packing, citation validation, task queue priority
├── support/fake_assistant.py
└── manual/              # accuracy answer-key runs, latency, VRAM co-residency
```

**Structure Decision**: Same boundary-per-directory rule as 001/002. The
assistant never imports capture or transcription internals — its inputs
are the transcript store (read-only) and 002's segment stream
(subscribe); its only new external seam is the Ollama HTTP API behind the
`AssistantEngine` Protocol, so CI runs entirely on the fake.

## Pinned Versions

| Component | Version | Note |
|-----------|---------|------|
| Ollama | latest stable at gate (c), recorded then | external service; Windows installer |
| llama3.2:3b (default candidate) | Q4_K_M | ~2.0 GB; candidates measured at gate (c) |
| httpx | 0.28.x | already pinned (constraints.txt) |

No new Python packages. Project-wide pins unchanged.

## Checkpoint Gates (constitution IV) for this feature

1. **Gate (b) — after plan**: approval of this document.
2. **Gate (c) — heavy dependencies**: approval before installing Ollama
   and pulling candidate models (~3 GB total download). Everything
   before it (contracts, store, retrieval/grounding logic, worker, API,
   WS, fake-engine CI suite) is model-free.
3. Gate (d): not triggered.

## Complexity Tracking

No constitution violations — the second-process note under Principle VI
is covered by the constitution's own environment constraints; table
otherwise intentionally empty.
