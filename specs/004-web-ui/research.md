# Phase 0 Research: Web UI

## R1. Rendering technology: no-build vanilla ES modules

- **Decision**: Plain ES-module JavaScript + one CSS file + semantic
  HTML. No framework, no bundler, no Node toolchain anywhere in the
  repo. Small hand-rolled helpers (DOM builder ~20 lines, windowed
  list ~80 lines) instead of libraries.
- **Rationale**: Constitution VI is explicit ("boring tech", and
  literally "static UI"). The UI's real complexity is stream wiring
  and virtualisation — neither needs a framework at this scope (4
  views, one user). A build chain would be the project's first, adding
  a second language ecosystem to maintain for no functional gain.
- **Alternatives considered**: React/Vue/Svelte (bundler + node_modules
  + build step for a 4-view page — rejected); htmx/server templates
  (elegant for CRUD, but the WS-streaming panels dominate this UI and
  need client JS anyway — rejected); vendored microframework like
  preact (still a dependency to track for marginal ergonomics —
  rejected). Revisit only if the UI grows genuinely stateful (library
  feature era).

## R2. Serving: root path, mount order, packaging

- **Decision**: `StaticFiles(directory=<pkg>/ui, html=True)` mounted at
  `/` **after** all routers in `create_app`, via a small
  `api/static_ui.py` helper that also adds `Content-Security-Policy:
  default-src 'self'; connect-src 'self' ws:` on UI responses. Assets
  are included in the wheel (hatch package data). If the ui directory
  is missing (dev edge), the app still serves the API and logs a
  warning — the UI is a layer, like everything else.
- **Rationale**: Starlette resolves routes before mounts added later,
  so `/sessions` (API) and `/` (UI) coexist on one port — the
  constitution's declared shape with zero new process or port. CSP is
  belt-and-braces on top of the CI asset scan (R7).
- **Alternatives considered**: separate port (violates stated shape);
  `/ui` prefix with `/` redirect (works, but the root path is the
  product's front door — no reason to indirect).

## R3. Transcript virtualisation (NFR-003)

- **Decision**: Fixed-window rendering: the transcript pane renders
  only the visible rows ± ~100, inside a spacer sized by
  estimated-then-measured row heights; scroll/resize reposition the
  window. Same component serves stored and live views (live appends
  adjust the tail; auto-follow sticks to bottom unless the user has
  scrolled up).
- **Rationale**: 3,400 segments × full DOM is exactly the jank NFR-003
  forbids; windowing is ~80 lines and keeps memory bounded for
  multi-hour live meetings (edge case). Height estimation is safe
  because rows are single-paragraph text with a measured average.
- **Alternatives considered**: render-everything (fails the fixture);
  pagination (breaks citation jumps and live following); a
  virtualisation library (dependency for 80 lines — rejected).

## R4. Stream wiring

- **Decision**: `streams.js` wraps the two existing WS contracts
  exactly as documented: transcript = snapshot via REST then
  `?after=<last seq>` tail, reconnect with the stored cursor
  (exponential backoff, 1 s → 10 s cap); answers = subscribe on ask,
  render token frames, terminal status closes and the stored turn is
  re-fetched as the durable record. No new stream semantics invented
  client-side.
- **Rationale**: 002/003 built and contract-tested these guarantees
  (gap-free cursor replay, prefix+tail); the UI's job is to *not*
  reimplement them wrongly. SC-002 tests precisely this through the
  browser.

## R5. Non-streamed state: visible-tab polling

- **Decision**: While the tab is visible, poll `/health` +
  `/*/readiness` every 3 s and the session list every 5 s; pause
  entirely when `document.hidden`. A failed health poll flips the UI
  into a "recorder disconnected — retrying" banner; the first success
  re-bootstraps all panels (handles recorder restarts, FR-011).
- **Rationale**: Single-user loopback polling at this rate is
  negligible (<10 req/s worst case, all local); it avoids inventing a
  server-push channel for state that has none (FR-012 — no new
  endpoints). The restart edge case falls out of the same mechanism.
- **Alternatives considered**: a new SSE/WS "events" endpoint (cleaner
  long-term; requires a new contract — deliberately deferred, noted
  for the backlog if polling ever feels laggy).

## R6. Citation jumps, including superseded transcripts

- **Decision**: A citation carries `{session_id, transcript_id, seq}`.
  If it targets the currently displayed transcript, scroll+highlight
  via the virtual list's index. If it targets another version
  (superseded — possible after re-transcription), fetch that version
  read-only (`GET /sessions/{id}/transcripts/{tid}`) and show the
  cited segment with ±2 neighbours in an inline excerpt popover,
  labelled with its version, rather than swapping the main view.
- **Rationale**: The spec's edge case; the API already serves old
  versions, so no contract change — and a labelled excerpt is clearer
  than silently switching transcripts under the reader.

## R7. Local-only enforcement (FR-002/SC-004)

- **Decision**: Three layers: (1) CI test scanning every shipped UI
  file for `https?://` and `//`-protocol URLs (allowlist:
  `127.0.0.1`, `localhost`); (2) CSP `default-src 'self'` so a slip
  fails loudly in the browser; (3) SC-004's manual devtools check in
  quickstart.
- **Rationale**: Constitution I deserves the same
  enforced-not-promised treatment the loopback bind got in 001.

## R8. Multi-tab and idempotence

- **Decision**: No client-side coordination. All reads are idempotent;
  both tabs' streams are independent subscribers (the pub/sub fans
  out); mutating actions (start/stop/ask) rely on the APIs' existing
  guards (409s render as normal error states). The session view
  re-syncs on every poll tick, so tab B reflects tab A's actions
  within one tick.
- **Rationale**: The server was built single-writer multi-reader from
  001 onward; the UI just inherits it.
