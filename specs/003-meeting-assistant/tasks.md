# Tasks: Meeting Assistant

**Input**: Design documents from `/specs/003-meeting-assistant/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Contract tests REQUIRED (constitution II / SC-006). All CI uses `FakeAssistantEngine`; real-model accuracy/latency/VRAM are manual. Feature 001+002 suites are the regression gate (FR-008).

**Organization**: US1 = summaries, US2 = post-meeting Q&A, US3 = live in-meeting assistant, US4 = readiness/honest failure.

**⚠️ Constitution gate (c)**: Tasks marked **[GATE-C]** install Ollama (~700 MB) and pull candidate models (~3 GB). Halt for human approval before the first such task. Everything else is model-free.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T001 Add assistant config to `src/ambient_recorder/config.py`: ollama_url (loopback-validated, default `http://127.0.0.1:11434`), assistant_model (default `llama3.2:3b`), assistant_keep_alive_active/idle (session-active vs 10-min idle, research R6), excerpt_budget_tokens (3000), summary_window_s (1200) — env-overridable `AMBREC_*`
- [x] T002 [P] Package skeleton `src/ambient_recorder/assistant/__init__.py`, `tests/support/fake_assistant.py` stub, manual-test placeholders from quickstart

**Checkpoint**: suite still green, config validated

---

## Phase 2: Foundational (contracts first — constitution II)

- [x] T003 [P] Assistant domain + API models in `src/ambient_recorder/models/assistant.py`: Summary/SummaryItem/ActionItem/Citation (session-qualified), SummaryVersionInfo, Conversation (top-level, session_ids scope validated to exactly 1 in v1), ConversationTurn (TurnState incl. interrupted), AssistantTask, enums, SummaryResponse, ConversationResponse/Detail, TurnResponse, AssistantTaskResponse, AssistantReadiness, WS frames (TokenFrame, TurnStatusFrame incl. interrupted terminal) per data-model.md + contracts/rest-api.md
- [x] T004 [P] Extend `ErrorCode` in `src/ambient_recorder/models/api.py`: assistant_not_ready, transcript_not_final, summary_not_found, conversation_not_found, turn_not_found (own contract commit)
- [x] T005 [P] Assistant Protocols in `src/ambient_recorder/assistant/protocols.py`: AssistantEngine (generate → Iterator[GenerationChunk]), AssistantEngineFactory (readiness/load/release), AssistantStore, EngineError/EngineNotReadyError per contracts/protocols.md
- [x] T006 [P] Contract test round-trips in `tests/contract/test_assistant_models_roundtrip.py`
- [x] T007 FakeAssistantEngine + FakeAssistantFactory in `tests/support/fake_assistant.py`: scripted token streams keyed by prompt matcher, configurable inter-token delay, triggerable EngineError, readiness toggle (ready/not_ready/not_installed); Protocol conformance test in `tests/contract/test_assistant_protocols.py`
- [x] T008 SQLite AssistantStore in `src/ambient_recorder/storage/assistant.py`: tables per data-model.md (incl. conversation_sessions scope join), turn seq assignment, current_summary (newest non-failed), priority-ordered next_queued, open_tasks, reconciliation (requeue running summaries; running asks → turn `interrupted` keeping streamed prefix, task failed); unit tests in `tests/unit/test_assistant_store.py`
- [x] T009 [P] Retrieval (pure) in `src/ambient_recorder/assistant/retrieval.py`: lexical scoring (question+history token overlap, recency weighting when live), excerpt packing to budget with numbered blocks; unit tests in `tests/unit/test_retrieval.py` (relevance ordering, budget respected, live recency bias)
- [x] T010 [P] Grounding (pure) in `src/ambient_recorder/assistant/grounding.py`: `[n]` citation extraction/mapping/validation, decline-phrase detection, verdict grounded/declined/ungrounded; unit tests in `tests/unit/test_grounding.py` (invalid citations dropped, zero-citation assertion → ungrounded, decline exact-match)
- [x] T011 [P] Prompt templates in `src/ambient_recorder/assistant/prompts.py`: qa (system + excerpts + history + question, cite-[n] + decline instructions), summary-map (window → structured bullets with citations), summary-reduce (merge/dedup); golden-file unit test in `tests/unit/test_prompts.py`
- [x] T012 Assistant readiness in `src/ambient_recorder/assistant/readiness.py`: three-way not_installed (never configured/unreachable per FR-009 layering) / not_ready (reachable, model missing or VRAM policy fails — remedy text) / ready; injected probes; unit tests in `tests/unit/test_assistant_readiness.py`

**Checkpoint**: contracts + storage + pure logic green, no runtime, no model

---

## Phase 3: User Story 1 — Summaries (P1) 🎯 MVP

**Goal**: POST summarize on a final-transcript session → structured, cited summary; versioned; long transcripts covered by map-reduce.

**Independent Test**: quickstart Scenario 1 with fake engine in CI; real model + answer key manually.

- [x] T013 [P] [US1] Contract tests for summarize/summary/summaries endpoints in `tests/contract/test_summary_api.py`: 202/200 shapes, 404s, 409 transcript_not_final (active session; live/absent transcript), 503 not_ready, version list supersede flags
- [x] T014 [US1] Windowing + map-reduce orchestration in `src/ambient_recorder/assistant/summarize.py`: 20-min windows, per-window bullet extraction, reduce with second tier when bullets exceed budget, citation carry-through, structured-output parsing with one retry on malformed; unit tests for windowing + parse-retry in `tests/unit/test_summarize.py`
- [x] T015 [US1] Assistant worker core in `src/ambient_recorder/assistant/worker.py`: serial thread, priority queue (live ask 0 > ask 1 > summary 2), engine load-on-first-use via factory, task lifecycle to store, structured events (task_started/completed/failed, tokens/s); summary task execution wired to summarize.py
- [x] T016 [US1] Summary REST routes in `src/ambient_recorder/api/assistant_routes.py` (summarize/summary/summaries) + error handlers for new codes in `src/ambient_recorder/api/errors.py`; wire router + worker + store into `main.py` (create_app takes AssistantEngineFactory, default real; fake in conftest)
- [x] T017 [US1] Integration test summary flow with fakes in `tests/integration/test_summary_flow.py`: final-transcript session → summarize → completed with citations validated against real segment seqs; 5h-scale synthetic transcript exercises second reduce tier; re-summarize supersedes-but-keeps; restart mid-summary requeues (reconciliation)

**Checkpoint**: summaries work end-to-end on fakes — MVP

---

## Phase 4: User Story 2 — Post-meeting Q&A (P2)

**Goal**: Conversations (multiple per session), streamed cited answers, honest declines, follow-up context.

- [x] T018 [P] [US2] Contract tests conversations/ask in `tests/contract/test_conversation_api.py`: top-level create with session_ids scope (422 on empty or >1 in v1, 404 unknown session), list with/without session_id filter, get, ask 202, 404s, 503, question validation (empty/2000+)
- [x] T019 [P] [US2] WS answer-stream contract tests in `tests/contract/test_answer_stream.py`: prefix-replay + tail, terminal status with citations closes socket, no-inflight-turn → latest terminal status + close, 4404
- [x] T020 [US2] Ask pipeline in `worker.py` + `api/assistant_routes.py` + `api/ws.py`: create turn, retrieval → prompt → streamed generation (tokens to store via append_answer_text + published to stream), grounding validation on completion → terminal state (completed/declined/ungrounded), citations + watermark stored; generalise/reuse 002's SegmentStream for token frames
- [x] T021 [US2] Integration tests in `tests/integration/test_qa_flow.py`: cited answer from scripted engine matches excerpt seqs; decline path; ungrounded path (scripted assertion without citations); follow-up uses conversation history in retrieval; two conversations don't share context; engine failure → turn failed, retryable in same conversation
- [x] T022 [US2] Regression gate: full 001+002 suites green with assistant wired (conftest), including OpenAPI surface guard update in `tests/contract/test_openapi_surface.py`

**Checkpoint**: post-meeting assistant complete on fakes

---

## Phase 5: User Story 3 — Live in-meeting assistant (P3)

**Goal**: Asks during active sessions grounded on transcript-so-far; live priority; lag caveat; conversation survives into post-meeting.

- [x] T023 [US3] Live grounding in `worker.py` + `retrieval.py`: transcript-so-far snapshot at generation start, watermark `live:<seq>`, recency weighting, lag-caveat injection when the question's focus window overlaps untranscribed time (uses 002's lag_s); integration test in `tests/integration/test_live_ask.py` with fake capture+STT+assistant: correct citation of a minute-old scripted segment, caveat on the not-yet-transcribed window, watermark recorded
- [x] T024 [P] [US3] Priority test in `tests/integration/test_assistant_priority.py`: slow fake summary running → live ask jumps queue (observed execution order); session stop mid-answer → answer completes against snapshot, conversation continues post-meeting against final transcript
- [x] T025 [P] [US3] Keep-alive/residency policy in `src/ambient_recorder/assistant/readiness.py` + worker: session started → engine loaded + keep_alive active; stopped + idle 10 min → release(); unit test with injected clock in `tests/unit/test_residency.py`

**Checkpoint**: live assistant complete on fakes

---

## Phase 6: User Story 4 — Readiness & honest failure (P4)

- [x] T026 [P] [US4] Readiness contract test in `tests/contract/test_assistant_readiness_api.py`: ready/not_ready(+remedy)/not_installed shapes; 503s carry the same reason
- [x] T027 [US4] Failure-isolation integration test in `tests/integration/test_assistant_isolation.py`: engine failure mid-summary and mid-ask → typed failed states; capture + live transcription continue unaffected (chunk counts grow, STT segments still arrive); not_installed factory → summarize/ask 503, sessions/transcripts untouched (FR-009)

**Checkpoint**: all four stories verified on fakes

---

## Phase 7: Gate (c) + real-model integration

- [x] T028 **[GATE-C — halt for human approval before this task]** Install Ollama (Windows installer, service on 127.0.0.1:11434), pull candidates `llama3.2:3b`, `qwen3:4b`, `phi4-mini`; measure per candidate on field transcripts: VRAM resident (nvidia-smi, alone and alongside a live-STT session), tokens/s, summary + Q&A quality on the answer key; record in research.md R2 and freeze the model choice; apply the constitution environment-line amendment per Governance (dated Sync Impact Report entry + PATCH version bump to 1.0.1)
- [x] T029 **[GATE-C]** OllamaEngine + factory in `src/ambient_recorder/assistant/ollama_engine.py`: /api/generate streaming client, keep_alive control, cancellation on iterator close, loopback pin (R9); make default factory in `__main__.py`; structural conformance in `tests/contract/test_assistant_protocols.py`
- [x] T030 **[GATE-C]** Manual answer-key accuracy in `tests/manual/assistant_answer_key.md`: scripted meeting (5 decisions, 5 action items) recorded + transcribed → summary ≥ 90% capture, zero unsupported statements (SC-001); 10-question Q&A set 7 answerable ≥ 90% correct-with-citation, 3 declined (SC-003); tune retrieval/prompts if needed
- [X] T031 **[GATE-C]** Manual latency + co-residency in `tests/manual/test_003_latency_vram.md`: post-meeting first token ≤ 10 s / complete ≤ 60 s (NFR-002); live first token ≤ 15 s during a real session with zero chunk loss + STT lag in bound (SC-004/SC-005, NFR-003); nvidia-smi co-resident reading vs the ≤ 6.5 GB arithmetic (NFR-004); **a ~60-minute session (the 001 soak or a slice) summarises in ≤ 3 min (NFR-001/SC-002)** and the 5-hour soak summary completes (SC-002); egress check (SC-007, quickstart Scenario 5)

---

## Phase 8: Polish

- [x] T032 [P] README assistant section (setup incl. gate-(c) commands, endpoints, knobs) + docs/backlog.md updates (embeddings retrieval, proactive assistance, frontier router as the constitution's opt-in feature)
- [x] T033 Run full quickstart.md end-to-end; fix doc/behaviour drift

---

## Dependencies & Execution Order

- Setup → Foundational → US1 → US2 → US3 → US4 → Gate (c) → Polish
- US2 builds on T015 worker + T016 wiring; US3 on US2's ask pipeline; T028 blocks only T029–T031
- All CI-facing work (T001–T027, T032–T033 partially) runs with zero model/runtime

### Parallel Opportunities

- Phase 2: T003–T006 together; then T007/T009/T010/T011/T012 together after T005
- Phase 3: T013 with T014; Phase 4: T018+T019 together; Phase 5: T024+T025 together
- Phase 8: T032 alongside T031

### Gate-C task set (approval before first execution)

T028, T029, T030, T031

---

## Implementation Strategy

**MVP**: Phases 1–3 (T001–T017) — summaries end-to-end on the fake engine. Then US2 (the Q&A machinery US3 reuses), US3 live, US4 isolation. Gate (c) turns it real; T028's measurement freezes the model before T029 wires it in.

**Commit cadence**: contract files (T003–T005) in own commits; per task or checkpoint after.
