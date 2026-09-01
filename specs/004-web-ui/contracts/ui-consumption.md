# Contract: UI Consumption Map + Static Serving

This feature adds **no new API contracts**. This document is the
authoritative map of which existing contracts the UI consumes (so
`/speckit-analyze` and future changes can see the coupling), plus the
one thing 004 does add: the static-serving behaviour.

## Existing contracts consumed (all unchanged)

| UI surface | Contract | Source |
|---|---|---|
| Readiness header | `GET /health`, `GET /devices`, `GET /transcription/readiness`, `GET /assistant/readiness` | 001/002/003 |
| Start/stop, refusals | `POST /sessions`, `POST /sessions/{id}/stop` (+ error envelope: device_missing, disk_space_low, session_already_active…) | 001 |
| Session list/detail | `GET /sessions`, `GET /sessions/{id}` | 001 |
| Transcript pane | `GET /sessions/{id}/transcript[?after]`, `GET /sessions/{id}/transcripts`, `GET /sessions/{id}/transcripts/{tid}` | 002 |
| Live transcript tail | `WS /sessions/{id}/transcript/stream?after=` (cursor replay+tail, status frames, terminal close) | 002 |
| Backfill button | `POST /sessions/{id}/transcribe` (+ 409/503 states) | 002 |
| Summary pane | `POST /sessions/{id}/summarize`, `GET /sessions/{id}/summary`, `GET /sessions/{id}/summaries[/{sid}]` | 003 |
| Chat pane | `POST /conversations`, `GET /conversations[?session_id]`, `GET /conversations/{cid}`, `POST /conversations/{cid}/ask` | 003 |
| Answer stream | `WS /conversations/{cid}/stream` (prefix replay+tail, terminal states incl. interrupted) | 003 |

Contract-first rule (FR-012): if implementation discovers a genuinely
missing endpoint, it is added to the owning feature's contract docs and
models first, in its own commit, before UI code uses it.

## Static serving contract (the one new behaviour)

- `GET /` → `ui/index.html`; `GET /js/*`, `GET /style.css` → shipped
  assets. Served by the same process/port; mounted after all API
  routers so **every existing route keeps winning** (OpenAPI surface
  guard unchanged — mounts are not schema paths).
- UI responses carry `Content-Security-Policy: default-src 'self';
  connect-src 'self' ws://127.0.0.1:* ws://localhost:*` — no
  non-loopback origin can load even by mistake.
- Missing `ui/` directory (dev edge): API unaffected; a warning is
  logged; `/` returns 404.
- Cache: `no-cache` on index.html (UI updates apply on reload);
  default caching for hashed-free assets is acceptable at local scale.

## Contract tests (REQUIRED)

1. `/` serves the shell with CSP header; `/sessions` still returns the
   API JSON (mount-order guard).
2. Shipped UI files contain no non-loopback URLs (scan; allowlist
   127.0.0.1/localhost).
3. OpenAPI surface guard remains exactly the 001–003 route set.
