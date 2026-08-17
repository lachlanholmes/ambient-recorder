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
- **Transcription (feature 002 candidate)**: local STT over the separable
  per-source chunks; the mic/system split exists precisely to give it a
  cheap speaker-attribution signal (spec 001 FR-003).
- **Storage retention / library management**: auto-cleanup and archival;
  explicitly deferred out of spec 001 (its disk-space threshold is the only
  v1 guard).
- **Loopback keep-alive (only if it bites)**: WASAPI loopback delivers no
  frames during total output silence, so the system source can be shorter
  than the mic (documented in tests/manual/README.md). A silent keep-alive
  render stream would close the gap — YAGNI until a real meeting shows a
  problem.
