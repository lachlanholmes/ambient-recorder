# Quickstart: Web UI

Validation guide — all scenarios run in a desktop browser against
`http://127.0.0.1:8377/`. Prereq: recorder running (any layer set).
Primary browser: Chromium-family; repeat Scenario 1 in Firefox
(NFR-004).

## Scenario 1 — full meeting workflow (US1/US3, SC-001)

1. Open the page: readiness header shows devices/transcription/
   assistant states.
2. Start a session with a title; watch elapsed time and the live
   transcript stream in (`me`/`them` distinct, timestamps, lag shown).
3. Open the chat pane mid-meeting; ask about something said a minute
   ago; watch the answer stream with citations; note the live
   watermark.
4. Stop; watch finalising → completed; request the summary; read it;
   click a citation → transcript scrolls and highlights; ask a
   follow-up in the same conversation.
5. **PASS**: the whole flow needed zero terminal commands.

## Scenario 2 — reconnect fidelity (SC-002)

Mid-meeting, close the tab. Reopen the page and the session view.
**PASS**: the transcript shows everything (compare last seq against
`GET /sessions/<id>/transcript`); no gaps, no duplicated rows.

## Scenario 3 — the 5-hour fixture (SC-003, NFR-003)

Open the 5-hour soak session (01M0G93XVGEMHY6NJA6X4Q3MAK).
**PASS**: view opens ≤ 2 s; scrolling is smooth end to end; its
summary's citations jump correctly (superseded-version citations show
the labelled excerpt popover).

## Scenario 4 — zero egress (SC-004)

With devtools Network open through Scenario 1: **PASS**: every request
targets 127.0.0.1 (or localhost); none blocked by CSP.

## Scenario 5 — layered honesty (SC-005)

Point the recorder at a scratch data root with transcription/assistant
absent (or stop Ollama). **PASS**: recording controls fully work;
transcription/assistant panels state unavailability with remedies; no
dead buttons, no console errors.

## Scenario 6 — resilience (FR-011)

1. Kill the recorder while the page is open → "disconnected, retrying"
   banner appears; restart it → the page recovers without reload.
2. Open a second tab; start/stop from one; the other reflects it
   within a poll tick; both live streams show identical segments.
3. While an answer is still streaming in tab A, open the same
   conversation in tab B: the partial answer replays and then tails to
   the same completion (WS prefix-replay contract).

## Scenario 7 — state gallery (SC-006)

Using existing fixture sessions, view: an interrupted session, a
failed transcript (engine_not_ready era), a declined answer, an
ungrounded answer, an interrupted answer, a pending re-summary (old
summary stays readable, progress visible). **PASS**: each state is
visually distinct and labelled.
