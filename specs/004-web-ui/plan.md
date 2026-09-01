# Implementation Plan: Web UI

**Branch**: `004-web-ui` | **Date**: 2026-09-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-web-ui/spec.md`

## Summary

A dependency-free browser UI shipped inside the recorder package and
served by the existing FastAPI process at the root path: session list +
session view (live/stored transcript, summary with citation jumps, chat
panel with streamed answers), a readiness header, and honest state
everywhere. **No build step, no Node toolchain, no framework** — plain
ES-module JavaScript, one stylesheet, semantic HTML, all local
(constitution I/VI). The UI is a pure client of the existing typed
APIs; this plan requires **zero new or changed endpoints**. Transcript
rendering is windowed (hand-rolled virtualisation) to satisfy the
5-hour-session performance fixture. Live data arrives over the existing
WebSocket streams with their cursor contracts; slow-changing state
(readiness, session list) is polled while the tab is visible.

## Technical Context

**Language/Version**: Browser ES2020 JavaScript (modules), HTML5, CSS —
no transpilation; Python side unchanged (FastAPI StaticFiles is part of
Starlette, already installed)

**Primary Dependencies**: **None new.** No npm, no CDN, no vendored
frameworks. FastAPI's `StaticFiles` serves `src/ambient_recorder/ui/`.

**Storage**: None server-side (spec: no new entities). Client keeps
only transient view state in page memory.

**Testing**: pytest for the serving contract (index served at `/`, API
routes still win, no-external-asset scan of shipped UI files); UI
behaviour verified in a real browser via quickstart scenarios (the
project's manual-test convention; browser automation available for the
validation pass)

**Target Platform**: Desktop Chromium/Firefox on the recorder's machine

**Project Type**: Single project — static assets inside the existing
package

**Performance Goals**: list render ≤ 1 s (NFR-001); segment on screen
≤ 1 s after server emit (NFR-002); 5-h transcript open ≤ 2 s, smooth
scroll, bounded memory (NFR-003/SC-003)

**Constraints**: zero non-loopback requests (FR-002/SC-004, CI-scanned
+ CSP); pure API client, contract-first for anything new (FR-012);
loopback single-user, multiple tabs tolerated (FR-011)

**Scale/Scope**: one user, a handful of tabs; transcripts to ~3,400
segments (field fixture); 4 views (list, session, summary, chat) in one
page

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Local-First, Privacy by Default | PASS | All assets ship in the package; CI test scans UI files for non-loopback URLs; a CSP **response header** (`default-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://localhost:*`) enforces it in the browser; SC-004 verifies in devtools. No analytics, no fonts, no CDN. |
| II. Typed Contracts at Every Boundary | PASS | The UI consumes only the existing typed REST/WS contracts (consumption map in [contracts/ui-consumption.md](contracts/ui-consumption.md)); zero new endpoints planned; FR-012 routes any future need through contract-first. |
| III. VRAM Budget | PASS (N/A) | No models; the UI adds zero GPU cost. |
| IV. Phased Delivery with Checkpoint Gates | PASS | Gate (a) spec approved; gate (b) this plan. **Gates (c) and (d) NOT triggered** — first feature with no heavy dependencies and no device access at all. |
| V. Fail Fast, Log Structurally | PASS | The UI is a *renderer* of the system's existing honest states (readiness remedies, typed failures, lag); it adds a visible disconnected/reconnecting state for the recorder itself. Server-side logging unchanged. |
| VI. Boring Tech, Single Process First | PASS | The constitution's own words — "one FastAPI process serving both API and static UI" — implemented literally. No build chain, no second process, no framework runtime. |
| VII. Sessions Are Sacred | PASS | Pure client; it can only call the same APIs curl does. Feature 001–003 suites remain the regression gate. |

**Post-Phase-1 re-check**: PASS — design added no endpoints, no
dependencies, no processes.

## Project Structure

### Documentation (this feature)

```text
specs/004-web-ui/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1 (client view-state only; no server entities)
├── quickstart.md        # Phase 1 — browser walkthrough scenarios
├── contracts/
│   └── ui-consumption.md  # Which existing contracts the UI consumes + static-serving contract
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
src/ambient_recorder/
├── ui/                      # shipped static assets (packaged via hatch include)
│   ├── index.html           # shell: readiness header, session list, session view
│   ├── style.css            # single stylesheet; me/them palette; states
│   └── js/
│       ├── app.js           # boot, routing (hash), poll loop, disconnect banner
│       ├── api.js           # thin fetch wrappers over the typed endpoints
│       ├── streams.js       # WS helpers: transcript tail (cursor), answer tail
│       ├── vlist.js         # windowed list rendering (virtualised transcript)
│       └── views/
│           ├── sessions.js  # list view
│           ├── session.js   # transcript pane + live handling + citation jump
│           ├── summary.js   # summary pane + generate/progress
│           └── chat.js      # conversations pane + streamed answers
└── api/
    └── static_ui.py         # mount helper: routes first, UI mount last, CSP header

tests/
├── contract/test_ui_serving.py   # / serves index; API routes still win; CSP present
├── contract/test_ui_local_only.py# asset scan: no non-loopback URL in shipped UI files
└── manual/test_004_ui.md         # quickstart walkthrough record (browser)
```

**Structure Decision**: Assets live inside the package so `pip install`
ships them and `StaticFiles` serves them with no path guesswork. The
mount is added *after* all routers so every API and WS route takes
precedence; the OpenAPI surface guard is unaffected (mounts don't
appear in the schema; the WS-route assertion checks `WebSocketRoute`
instances only).

## Pinned Versions

No new components. (Starlette's StaticFiles arrives via the existing
pinned fastapi/uvicorn.)

## Checkpoint Gates (constitution IV) for this feature

1. **Gate (b) — after plan**: approval of this document.
2. Gates (c)/(d): **not triggered** — no heavy dependencies, no device
   access. This feature runs start-to-finish without further halts.

## Complexity Tracking

No constitution violations — table intentionally empty.
