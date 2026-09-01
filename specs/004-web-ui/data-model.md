# Data Model: Web UI

**No server-side entities.** The UI renders existing domain objects
(sessions, transcripts, segments, summaries, conversations, readiness)
exactly as their owning features define them.

## Client view-state (page memory only, never persisted)

| State | Contents | Lifetime |
|---|---|---|
| Route | `#/` (list) or `#/session/<id>` | URL hash |
| Readiness cache | last poll results for the header | until next poll |
| Session cache | list + open session detail | until next poll/navigation |
| Transcript window | loaded segments, virtual-list scroll metrics, live cursor (`last seq`), auto-follow flag | while the session view is open |
| Chat state | conversation list, open conversation turns, in-flight stream handle | while the chat pane is open |
| Connection state | `ok \| reconnecting` + backoff timer | continuous |

Rules:
- The live cursor is the single source for reconnects (R4); it is never
  guessed from timestamps.
- No client persistence (localStorage etc.) in v1 — a reload
  re-bootstraps from the APIs, which are the only truth.
