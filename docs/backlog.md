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
- **Transcript summarisation / assistant (feature 003 candidate)**: the
  LLM the 002 VRAM plan reserves ~3.5 GB for. Inputs are ready: `me`/`them`
  segments with timestamps, current transcript per session, live stream.
- **Storage retention / library management**: auto-cleanup and archival;
  explicitly deferred out of spec 001 (its disk-space threshold is the only
  v1 guard).
- ~~Loopback keep-alive~~ — resolved 2026-08-19 by zero-filling silence
  gaps in the capture writer (it bit: transcription timestamps drifted).
