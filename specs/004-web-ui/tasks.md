# Tasks: Web UI

**Input**: Design documents from `/specs/004-web-ui/`

**Prerequisites**: plan.md, spec.md, research.md, contracts/ui-consumption.md, quickstart.md

**Tests**: Contract tests (constitution II) cover the one new behaviour —
static serving — plus the local-only asset scan. UI behaviour is
validated in a real browser via quickstart.md (project convention for
what CI cannot see; browser automation available for the validation
pass). No JS unit-test toolchain is introduced (no-build decision, R1).

**Organization**: Grouped by user story; each story is independently
testable in the browser against the running recorder.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Create `src/ambient_recorder/ui/` skeleton (index.html, style.css, js/ with empty modules per plan structure) and add the ui directory to wheel package data in pyproject.toml (hatch include)

---

## Phase 2: Foundational (blocking prerequisites)

**⚠️ CRITICAL**: Serving, shell, and API/stream helpers block every story.

- [X] T002 [P] Contract test in tests/contract/test_ui_serving.py: `GET /` serves index.html with the CSP header; `GET /sessions` still returns API JSON (mount-order guard); missing ui/ dir degrades to 404 + warning with API unaffected; OpenAPI surface guard remains exactly the 001–003 route set
- [X] T003 [P] Contract test in tests/contract/test_ui_local_only.py: every shipped file under src/ambient_recorder/ui/ contains no non-loopback URL (scan for `https?://` and protocol-relative `//`; allowlist 127.0.0.1/localhost) (FR-002)
- [X] T004 Static serving in src/ambient_recorder/api/static_ui.py: mount `StaticFiles(html=True)` at `/` after all routers in create_app; add `Content-Security-Policy: default-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://localhost:*` and `Cache-Control: no-cache` (index) on UI responses; log a warning and skip the mount if ui/ is missing (R2)
- [X] T005 [P] App shell in src/ambient_recorder/ui/index.html + style.css: semantic layout (header with readiness slots, main view container), me/them palette, status-pill / chip / state classes, monospace timestamps — per the design tokens and component sketches in specs/004-web-ui/ui-notes.md
- [X] T006 [P] API client in src/ambient_recorder/ui/js/api.js: thin typed fetch wrappers for every endpoint in contracts/ui-consumption.md, surfacing the API error envelope (code + message) to callers
- [X] T007 Boot/routing/poll loop in src/ambient_recorder/ui/js/app.js: hash routes `#/` and `#/session/<id>`; visible-tab polling (readiness+health 3 s, session list 5 s, paused on document.hidden); failed health poll flips a "recorder disconnected — retrying" banner and first success re-bootstraps all panels (R5, FR-011)
- [X] T008 Stream helpers in src/ambient_recorder/ui/js/streams.js: transcript tail (REST snapshot then `?after=<seq>` WS tail, cursor-based reconnect with 1 s → 10 s backoff) and answer stream (subscribe on ask, token frames, terminal status then re-fetch stored turn) — the two contracts exactly as documented, no new semantics (R4)

**Checkpoint**: `/` serves the shell, contract tests green, polling and streams wired.

---

## Phase 3: User Story 1 — Run a meeting from the browser (P1) 🎯 MVP

**Goal**: Readiness at a glance, titled start, live transcript with honest lag, one-click stop.

**Independent Test**: Complete a short real meeting (readiness → titled start → watch live transcript → stop) using only the browser (quickstart Scenario 1 steps 1–2 + 4).

- [X] T009 [P] [US1] Readiness header in src/ambient_recorder/ui/js/app.js + index.html: three layer chips (devices, transcription, assistant) from the readiness polls, each ready/unavailable with remedy text inline, updating without reload (FR-003)
- [X] T010 [US1] Windowed list renderer in src/ambient_recorder/ui/js/vlist.js: visible rows ± ~100 in a measured spacer, scroll/resize repositioning, live-append with auto-follow that disengages on scroll-up; serves both live and stored transcripts (R3, NFR-003)
- [X] T011 [US1] Session controls in src/ambient_recorder/ui/js/views/session.js + sessions.js: start with optional title, stop, active-session banner with elapsed time; API refusals (device_missing, disk_space_low, session_already_active) rendered in plain language from the error envelope (FR-004)
- [X] T012 [US1] Live transcript pane in src/ambient_recorder/ui/js/views/session.js: streams.js tail into vlist, me/them styling with timestamps, lag chip from the stream's watermark, finalising → completed transition on stop (FR-005, NFR-002)

**Checkpoint**: A meeting can be run end-to-end in the browser — MVP.

---

## Phase 4: User Story 2 — Browse recordings and read what happened (P2)

**Goal**: Session list, smooth stored transcripts (5-h fixture), structured summaries, citation jumps.

**Independent Test**: Open the 5-hour soak session, scroll smoothly, request/read a summary, click citations and land on the right segments (quickstart Scenarios 3 and 1 step 4).

- [X] T013 [P] [US2] Session list view in src/ambient_recorder/ui/js/views/sessions.js: newest-first with title, date, duration, size, status pill, transcription state; opens `#/session/<id>` (FR-006)
- [X] T014 [US2] Stored transcript rendering in src/ambient_recorder/ui/js/views/session.js: load via `?after` pagination into vlist; transcript-state rendering (live/finalising/completed/failed/interrupted) with the on-demand transcribe button where the API offers it (FR-006, FR-013)
- [X] T015 [US2] Summary pane in src/ambient_recorder/ui/js/views/summary.js: structured render (overview, key points, decisions, action items with owner/deadline), generate/re-summarize buttons, pending progress that never hides the readable current summary (FR-007, FR-013)
- [X] T016 [US2] Citation jumps in src/ambient_recorder/ui/js/views/session.js: citation click scrolls+highlights via vlist index when the target is the displayed transcript; superseded-version targets fetch `GET /sessions/{id}/transcripts/{tid}` and show the cited segment ±2 in a version-labelled excerpt popover (FR-008, R6)

**Checkpoint**: The archive is readable end-to-end, including the 5-hour fixture.

---

## Phase 5: User Story 3 — Ask the assistant, including mid-meeting (P3)

**Goal**: Conversations with streamed, cited answers; live asks with watermark; honest terminal states.

**Independent Test**: During a live scripted session, ask about content a minute old via the panel and get a streamed cited answer; after stop, continue the same conversation (quickstart Scenario 1 step 3 + Scenario 7's answer states).

- [X] T017 [P] [US3] Chat panel in src/ambient_recorder/ui/js/views/chat.js: conversation list/create/continue for the session, ask box, streamed answer rendering via streams.js, interactive citations reusing the US2 jump (FR-009)
- [X] T018 [US3] Terminal answer states in src/ambient_recorder/ui/js/views/chat.js: completed (citations), declined (honest no-answer, not an error), ungrounded (flagged unverified), failed, interrupted (partial + label) — each visually distinct (FR-009, SC-006)
- [X] T019 [US3] Live asks in src/ambient_recorder/ui/js/views/chat.js: panel works during an active session, shows the transcript watermark the answer saw and the assistant's lag caveat when present; assistant-unavailable state shows the remedy with everything else functional (FR-010)

**Checkpoint**: All three stories work independently.

---

## Phase 6: Polish & validation

- [ ] T020 [P] Multi-tab pass: verify both tabs converge within a poll tick on start/stop and both live streams show identical segments (quickstart Scenario 6.2); fix any client assumption that breaks idempotence (R8)
- [ ] T021 [P] Reconnect fidelity pass: close/reopen mid-meeting and diff the reassembled transcript against `GET /sessions/<id>/transcript` (quickstart Scenario 2, SC-002)
- [ ] T022 Performance validation against NFR-001/002/003: list render ≤ 1 s, live segment ≤ 1 s, 5-h session open ≤ 2 s with smooth scroll and bounded memory; record numbers in tests/manual/test_004_ui.md
- [ ] T023 Capture-only validation: scratch data root without transcription/assistant; record quickstart Scenario 5 results (SC-005)
- [ ] T024 Run the full quickstart.md walkthrough in a real browser (Scenarios 1–7 incl. devtools egress check SC-004), repeating Scenario 1 in Firefox (NFR-004), and record results in tests/manual/test_004_ui.md
- [X] T025 Docs: add the UI to docs/quickstart or README usage notes (open 127.0.0.1:8377 in a browser); note the layered-honesty behaviour

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 → stories**: T004 depends on T001; T002/T003 written first and failing until T004/T001 satisfy them; T007 depends on T005/T006; T008 depends on T006.
- **US1 (P1)**: needs Phase 2. T010 (vlist) before T012; T009/T011 parallel to T010.
- **US2 (P2)**: needs Phase 2; reuses T010's vlist (built in US1 — if US2 is tackled first, pull T010 forward). T016 depends on T014.
- **US3 (P3)**: needs Phase 2; T017 reuses T016's citation jump for full effect but functions without it (citations render, jump degrades to nothing until US2 lands).
- **Polish**: after the stories it validates (T020–T024 need US1–US3; T021 needs US1 only).

### Parallel opportunities

- T002 ∥ T003 (different test files); T005 ∥ T006 (markup vs js)
- T009 ∥ T010 ∥ T011 within US1; T013 ∥ T015 within US2; T020 ∥ T021 in polish

---

## Implementation Strategy

MVP is Phase 1–3 (US1): the recorder becomes browser-operable for a
live meeting. US2 makes the archive readable (and carries the 5-hour
performance fixture), US3 surfaces the assistant. Each checkpoint is
independently demonstrable against the running recorder; commit after
each task or coherent group, contract-first if any endpoint gap
appears (FR-012).
