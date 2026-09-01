# Feature Specification: Web UI

**Feature Branch**: `004-web-ui` (branched from `003-meeting-assistant` — this feature renders 003's API surface)

**Created**: 2026-09-01

**Status**: Draft

**Input**: User description: "Web UI for the ambient recorder: a local browser interface served by the recorder itself that makes everything the APIs already provide usable without curl — see and control recording sessions (start/stop, device readiness, session list with status/duration), watch the live transcript stream as a meeting happens, read summaries with their citations, and chat with the assistant (streamed answers, citations that jump to the transcript moment, live in-meeting questions). Constitution already anticipates this: one FastAPI process serving both API and static UI; local-only, no external assets."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a meeting from the browser (Priority: P1)

The user opens the recorder's local page, sees at a glance whether
everything is ready (capture devices, transcription, assistant), starts
a session with an optional title, watches the live transcript grow as
the meeting happens — `me` and `them` visually distinct, with a
keeping-up indicator — and stops the session with one click.

**Why this priority**: This replaces every curl command in the daily
workflow. Until it exists, the product is developer-only; with it, the
recorder becomes an appliance.

**Independent Test**: With the recorder running, complete an entire
short meeting — readiness check, titled start, live transcript
watching, stop — using only the browser.

**Acceptance Scenarios**:

1. **Given** the recorder is running, **When** the user opens its local
   address in a browser, **Then** they see readiness for capture
   devices, transcription, and assistant, each with a clear
   available/unavailable state and remedy text when unavailable.
2. **Given** readiness is good, **When** the user starts a session with
   a title, **Then** recording begins, the UI shows the session as
   active with elapsed time, and live transcript segments appear as
   they are produced, attributed and timestamped.
3. **Given** a live session, **When** transcription falls behind,
   **Then** the UI shows the current lag honestly rather than
   pretending the transcript is current.
4. **Given** a live session, **When** the user clicks stop, **Then**
   the session ends, the transcript finalises visibly
   (finalising → completed), and the session appears in the list.
5. **Given** a start attempt with a device missing or disk low,
   **When** the user clicks start, **Then** the refusal reason is shown
   in plain language (no session is created), matching the API's error.

---

### User Story 2 - Browse recordings and read what happened (Priority: P2)

The user browses past sessions (title, date, duration, size, status),
opens one, reads its transcript with speakers distinguished, reads or
requests its summary, and clicks any citation to jump to the exact
transcript moment it references.

**Why this priority**: The archive is where the recorder's value
accumulates; reading must be effortless or the recordings stay opaque
despite all the machinery underneath.

**Independent Test**: Open an existing session (including the 5-hour
soak), read its transcript smoothly, request a summary, click
citations, and land on the right segments.

**Acceptance Scenarios**:

1. **Given** stored sessions exist, **When** the user opens the
   session list, **Then** sessions appear newest-first with title,
   date, duration, size, and status (completed/interrupted), and
   transcription state where present.
2. **Given** a session with a transcript, **When** opened, **Then** the
   transcript renders with `me`/`them` visually distinct and
   timestamps, and remains smooth to scroll even for multi-hour
   sessions (thousands of segments).
3. **Given** a session with a final transcript and no summary, **When**
   the user requests one, **Then** progress is visible and the finished
   summary renders structured: overview, key points, decisions, action
   items with owners and deadlines.
4. **Given** a summary or answer citation, **When** clicked, **Then**
   the transcript view scrolls to and highlights the cited segment.
5. **Given** a session whose transcript is missing or interrupted,
   **When** viewed, **Then** the state is plainly shown with the
   available action (e.g. transcribe now) offered as a button.

---

### User Story 3 - Ask the assistant, including mid-meeting (Priority: P3)

The user chats with the assistant about a session: picks or starts a
conversation, asks in a text box, watches the answer stream in with
citations attached, and clicks citations to see the source moments.
During a live meeting, the same chat panel works against the
transcript-so-far.

**Why this priority**: This is the surface for feature 003's whole
value; live in-meeting asks (the option-C vision) only became truly
usable with this panel.

**Independent Test**: During a live scripted session, ask about
something said a minute ago via the chat panel and receive a streamed,
cited answer; after stop, continue the same conversation.

**Acceptance Scenarios**:

1. **Given** an open session view, **When** the user starts a
   conversation and asks a question, **Then** the answer streams into
   the chat visibly as it generates, ending with citations.
2. **Given** an active session, **When** the user asks about recent
   content, **Then** the answer is grounded in the transcript-so-far
   and the UI indicates it answered against a live transcript
   (watermark), including the lag caveat when the assistant gives one.
3. **Given** a declined answer ("not discussed in this meeting"),
   **Then** the UI presents it as an honest no-answer, visually
   distinct from a failure.
4. **Given** past conversations exist for a session, **When** the user
   opens the chat panel, **Then** conversations are listed and can be
   continued with context intact.
5. **Given** the assistant is not installed or not ready, **Then** the
   chat panel says so with the remedy, and everything else still works.

---

### Edge Cases

- Browser tab closed and reopened mid-session: the live transcript
  view reconnects and shows the full transcript-so-far with no gaps or
  duplicates (the stream's cursor contract).
- Two tabs open simultaneously: both show consistent live state;
  actions from either work (single recorder, multiple viewers).
- Recorder process restarts while the page is open: the UI detects the
  lost connection, says so, and recovers automatically when the
  recorder returns rather than requiring a manual reload.
- A summary or answer citation referencing a superseded transcript
  version: the jump still resolves (the UI fetches the cited version)
  or degrades to a labelled excerpt rather than a broken link.
- Capture-only install: recording controls fully work; transcription
  and assistant panels state their unavailability with remedies
  (layered honesty, mirroring the APIs).
- An in-flight answer's conversation is opened in a second view:
  the stream replays the partial answer and tails (WS contract).
- Very long live meeting left open for hours: the live view stays
  responsive; memory in the page does not grow unboundedly (older
  segments virtualised, not all in DOM).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The recorder MUST serve the UI itself at its local
  address — same process, same port, loopback-only, no separate server
  to run (constitution VI's stated shape).
- **FR-002**: The UI MUST load and function with zero requests to any
  non-loopback origin — no CDN scripts, fonts, or analytics; all
  assets ship with the recorder (constitution I; verifiable in
  devtools).
- **FR-003**: The UI MUST surface readiness of all three layers
  (devices, transcription, assistant) with remedy text, updating
  without a manual reload.
- **FR-004**: The UI MUST provide session start (optional title) and
  stop, showing API refusals (device missing, disk low, already
  active) in plain language.
- **FR-005**: The UI MUST render the live transcript via the existing
  stream (cursor reconnect, no gaps/duplicates), show `me`/`them`
  distinctly with timestamps, display current lag, and show the
  finalising → completed transition on stop.
- **FR-006**: The UI MUST list sessions (newest first: title, date,
  duration, size, status) and render any session's transcript,
  remaining responsive for multi-hour transcripts (thousands of
  segments).
- **FR-007**: The UI MUST display summaries structured (overview, key
  points, decisions, action items with owner/deadline), offer
  generate/regenerate where the API allows, show progress while
  pending, and never hide a readable summary behind a pending re-run
  (mirroring the API's currency rule).
- **FR-008**: Citations — in summaries and answers — MUST be
  interactive: activating one navigates the transcript view to the
  cited segment and highlights it.
- **FR-009**: The chat panel MUST list/create/continue conversations,
  stream answers as they generate, and render terminal states
  distinctly: completed (with citations), declined, ungrounded,
  failed, interrupted.
- **FR-010**: The chat panel MUST work during an active session (live
  asks), indicating the transcript watermark the answer saw.
- **FR-011**: The UI MUST handle recorder disconnects visibly and
  recover automatically on return, and MUST tolerate multiple
  simultaneous tabs.
- **FR-012**: The UI MUST be a pure client of the existing typed APIs.
  Any new or changed endpoint it needs goes through the contract-first
  process like any other consumer (constitution II); the UI gets no
  private backdoors.
- **FR-013**: On-demand actions the APIs already offer — transcribe a
  legacy/interrupted session, re-summarize — MUST be reachable as
  buttons in the relevant states.

### Non-Functional Requirements

- **NFR-001**: First meaningful render of the session list within 1
  second of opening the page on the target machine.
- **NFR-002**: A live segment appears in the page within 1 second of
  the server emitting it (UI adds negligible latency on top of the
  pipeline's own).
- **NFR-003**: The transcript view for the project's largest real
  session (5 hours, ~3,400 segments) opens within 2 seconds and
  scrolls without jank; the live view's page memory stays bounded over
  a multi-hour meeting.
- **NFR-004**: The UI works in current Chromium- and Firefox-family
  browsers; no plugins.

### Key Entities

No new domain entities — the UI renders existing ones (sessions,
transcripts, segments, summaries, conversations, readiness). Any purely
presentational state (e.g. which panel is open) lives in the page and
is not persisted server-side.

## Out of Scope *(this feature)*

- Authentication/multi-user (loopback single-user stands, per 001).
- Editing anything: transcripts, summaries, and answers are
  read-and-request only.
- Audio playback in the browser (chunks remain playable via external
  tools; a player is future work).
- Cross-session search or a combined library view beyond the session
  list (future library feature).
- Mobile/responsive layouts beyond incidental usability; desktop
  browsers are the target.
- Packaging changes (launch-at-login, tray icon — separate backlog
  item); the UI appears when the recorder runs, as today.
- Dark/light theming and visual polish beyond clear, legible defaults.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A complete meeting workflow — readiness check, titled
  start, watching live transcript, one live question, stop, reading
  the summary, one follow-up question — is performed end-to-end in the
  browser with zero terminal commands.
- **SC-002**: Closing and reopening the tab mid-meeting loses nothing:
  the reassembled live transcript is identical to the API's record
  (cursor reconnect verified through the UI).
- **SC-003**: The 5-hour soak session's transcript opens in ≤ 2 s and
  scrolls smoothly; its summary renders with working citation jumps.
- **SC-004**: A full workflow session shows zero non-loopback network
  requests in browser devtools (FR-002 verified).
- **SC-005**: On a capture-only configuration, the recording workflow
  works fully in the UI while transcription/assistant panels show
  their unavailability and remedies (no dead controls, no errors).
- **SC-006**: All UI-visible state transitions (session
  active/completed/interrupted; transcript live/finalising/completed/
  failed; answer streaming/completed/declined/failed) render
  distinctly — verified against the scripted flows of the three
  underlying features' test scenarios.

## Assumptions

- The UI is served at the recorder's existing address (the root path),
  with the API continuing to live alongside it — one process, one
  port.
- Single-page interaction model: session list plus a session view with
  transcript, summary, and chat panels; no separate "apps".
- The existing APIs are sufficient for v1; if implementation reveals a
  genuinely missing endpoint (e.g. a UI bootstrap/config read), it
  follows contract-first like every prior feature (FR-012).
- Desktop Chromium/Firefox on the recorder's own machine is the
  supported environment; anything else is best-effort.
- English-only UI text, matching the product's current language.
- The 003 branch's API surface is the baseline (this branch forks from
  it); 004 merges after 003.
