# Feature backlog

Pre-spec ideas and deferred items. When one is picked up, it becomes a
`/speckit-specify` input and gets its own `specs/NNN-*/` directory; remove
it from here in the same commit.

## Candidates

- **Run-anywhere packaging / launch-at-login**: today the recorder must be
  started from the repo root because `data_root` defaults to the relative
  path `data` (or `AMBREC_DATA_ROOT` must be set). A "runs as a background
  app" feature should pin an absolute per-user default (e.g. under
  `%LOCALAPPDATA%/ambient-recorder/`), provide a startup shortcut/service,
  and decide log destination when there's no console. (Noted 2026-08-18.)
- **Sub-second live transcription**: feature 002 rides the 10 s chunk
  cadence (lag 10–15 s at the boundary). Streaming from the capture queue
  with VAD endpointing would cut lag to ~1–2 s but couples STT to the
  capture thread (constitution VII) and needs revisable partial segments.
  Named upgrade path in specs/002 research R3.
- **Loopback silence tail**: the capture engine now zero-fills silence gaps
  *between* frames, but a track that goes silent and never resumes ends at
  its last frame (session `duration_s` uses the longer track). Cosmetic;
  fix = pad to session stop at finalise if ever needed.
- **Echo cancellation**: the energy+text bleed rule works (field-verified
  2026-08-19) but is a heuristic; proper AEC would remove the mic echo
  before STT. Only worth it if the accuracy script (tests/manual/
  accuracy_script.md) shows attribution misses in practice.
- **Graceful shutdown endpoint**: stopping the recorder currently means
  Ctrl+C in its terminal or hunting PIDs — during the 002 soak
  (2026-08-21) an external `taskkill` on the listener killed a 5-hour
  session mid-recording (recovered cleanly via reconciliation, but the
  stop was accidental). A `POST /shutdown` (finalise active session +
  transcript, then exit) would make "stop the recorder" a safe one-liner
  and pair naturally with the future tray/UI feature.
- **Cross-session Q&A**: the conversation model already scopes by
  session list (restricted to 1 in v1) with session-qualified citations —
  lifting the restriction is a retrieval upgrade (multi-transcript
  excerpt selection + budget split). Natural core of the future
  library/search feature.
- **Embedding-based retrieval**: 003 uses lexical retrieval (research
  R3); an embedding index would improve paraphrase recall on long
  meetings at the cost of another model + storage. Revisit if the
  answer-key scores show retrieval misses (not model misses).
- **Proactive assistance**: the assistant only speaks when asked (003
  scope decision); unprompted surfacing of action items/decisions
  mid-meeting is future UI-era work.
- **Frontier router (constitution I's opt-in clause)**: optional
  escalation of *redacted transcript text* to a cloud model for hard
  questions — explicitly a separate feature with its own consent UX;
  never audio, never automatic.
- **Storage retention / library management**: auto-cleanup and archival;
  explicitly deferred out of spec 001 (its disk-space threshold is the only
  v1 guard).
- ~~Loopback keep-alive~~ — resolved 2026-08-19 by zero-filling silence
  gaps in the capture writer (it bit: transcription timestamps drifted).
- ~~Deep-reduce summary citations unreliable~~ — found 2026-09-01 on the
  first 5-hour summary (all 10 items cited seq 6/44.9 s: the reduce
  model renumbered `[n]` markers and validation only checked existence
  in the global excerpt index; plus the 3-digit marker regex hid
  legitimate `[1000+]` citations). Fixed same day in two rounds:
  (1) subset guard — markers in each map/reduce output must be a subset
  of that call's input (retry, then strip) + 4-digit regex; (2) after an
  instrumented repro showed the model simply cannot cite globally
  renumbered excerpts, map prompts now number excerpts locally (1..N,
  translated to global in code), uncited bullets earn the retry, and
  final bullets without valid citations inherit them by fuzzy-matching
  their map-stage source bullet. Result: 0 invalid markers across a
  full 5-h run; all stored citations correct by construction. Residual
  (quality, not correctness): deep-reduce summaries of non-meeting
  ambient audio keep few items; revisit only if real long *meetings*
  summarise thin.
