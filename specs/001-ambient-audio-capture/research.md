# Phase 0 Research: Ambient Audio Capture Sessions

All Technical Context unknowns resolved. Each decision below is final for
this feature unless amended via the spec's Decision Log.

## R1. System-audio (loopback) capture mechanism

- **Decision**: PyAudioWPatch — a maintained PyAudio fork exposing WASAPI
  loopback devices as ordinary input devices; used for BOTH microphone and
  loopback capture so one library and one callback model covers both
  sources.
- **Rationale**: WASAPI loopback is the only driver-free way to capture
  "what the machine plays" on Windows 11. PyAudioWPatch surfaces each output
  device's loopback analogue in the standard device list, which also gives
  us device enumeration/readiness (FR-005) for free. Blocking C-thread
  callbacks deliver frames off the GIL, keeping CPU low (NFR-001).
- **Alternatives considered**:
  - `sounddevice` (PortAudio): fine for mic, but its bundled PortAudio does
    not reliably expose WASAPI loopback — rejected as the loopback path.
  - `soundcard`: pure-Python loopback support exists but the project is
    less maintained and has known thread-safety caveats — rejected.
  - FFmpeg subprocess capture: dshow has no loopback without third-party
    virtual devices; two long-lived subprocesses complicate chunk cadence
    and failure handling — rejected (FFmpeg stays a verification tool only).

## R2. Sample-rate conversion to the persisted format

- **Decision**: Capture at each device's native rate (typically 48 kHz,
  possibly stereo) and convert per 10 s chunk to 16 kHz mono 16-bit PCM
  with `python-soxr` (VHQ preset); downmix by channel averaging before
  resample.
- **Rationale**: Devices won't open reliably at 16 kHz mono; capturing
  native and converting on write is the spec-sanctioned implementation
  choice (spec Assumptions). soxr is a small wheel, high quality, and
  resamples a 10 s chunk in single-digit milliseconds of CPU.
- **Alternatives considered**: scipy.signal (heavyweight dependency for one
  function — rejected, constitution VI); naive decimation/`audioop`
  (aliasing, deprecated in 3.13 — rejected); asking WASAPI for 16 kHz
  (device-dependent, shifts resampling to an opaque layer — rejected).

## R3. Chunk container format

- **Decision**: One self-contained WAV file per source per 10 s chunk,
  written to a temp name and atomically renamed on completion
  (`chunk_000042.wav.part` → `chunk_000042.wav`).
- **Rationale**: Spec requires chunks be "individually valid" and playable
  in an external tool after a crash (SC-002). A finalised WAV has a correct
  header; the atomic rename means a crash can only ever leave one `.part`
  file per source, which reconciliation discards — data-loss window exactly
  one chunk (FR-002). WAV overhead (44 bytes/chunk) is negligible against
  the 500 MB/2 h budget (NFR-003: 2 h ≈ 720 chunks/source ≈ 63 KB total
  overhead).
- **Alternatives considered**: single growing WAV per source (header must
  be rewritten on close; crash corrupts the whole recording — rejected,
  constitution VII); raw PCM chunks (not externally playable — rejected);
  FLAC (halves disk but adds encoder dependency and CPU; disk budget
  already met — rejected, YAGNI).

## R4. Metadata store

- **Decision**: stdlib `sqlite3` in WAL mode, single writer thread; no ORM.
- **Rationale**: Constitution VI names SQLite. WAL survives ungraceful
  termination (reconciliation replays state from chunk files as truth).
  An ORM adds nothing at this scale (5 tables, one process).
- **Alternatives considered**: JSON sidecar files (no queryable session
  list, racy multi-file updates — rejected); SQLAlchemy (dependency weight
  without need — rejected).

## R5. Crash reconciliation strategy

- **Decision**: On startup, before serving requests: every session with
  status `active` in SQLite is reconciled — discard `.part` files,
  inventory finalised chunks per source, recompute per-source end time and
  duration from chunk count × 10 s (+ final chunk's actual length), set
  status `interrupted`, append a `reconciled` session event.
- **Rationale**: Chunk files on disk are the source of truth (they were
  durably written); metadata is derived. This makes FR-008 idempotent and
  user-intervention-free, and it also cleanly handles the "restart with no
  active session" edge case (no-op).
- **Alternatives considered**: journal/WAL of capture intents (duplicates
  what the filesystem already proves — rejected); lazy reconciliation on
  first inspect (leaves lying metadata visible in lists — rejected,
  fail-fast principle).

## R6. Process & concurrency model

- **Decision**: One process, three lanes: (1) PyAudio C-thread callbacks
  push raw frames into bounded `queue.Queue`s; (2) one writer thread per
  active source drains its queue, accumulates 10 s, converts (R2), writes
  the chunk (R3), updates metadata (R4); (3) the asyncio/FastAPI event loop
  serves the API and never touches audio buffers directly. Session state
  transitions are guarded by a single lock in the capture engine.
- **Rationale**: Keeps the API responsive (SC-004), isolates real-time
  capture from request handling (FR-009 — client disconnects can't affect
  lanes 1–2), and stays inside constitution VI's single-process rule.
- **Alternatives considered**: capture subprocess (IPC + lifecycle
  complexity — rejected); pure-asyncio audio handling (PyAudio callbacks
  are thread-based; mixing models adds risk — rejected).

## R7. Meeting the 2-second start (SC-004)

- **Decision**: Keep the PyAudio host-API instance initialised at process
  startup; on session start, run readiness (device enumeration + disk
  check, ~100–300 ms), open both streams, and report the session active
  once first frames arrive. Time budget measured in the manual test.
- **Rationale**: Stream open on WASAPI is sub-second when the host API is
  already initialised; pre-warming at startup moves the one slow step out
  of the request path.
- **Alternatives considered**: permanently-open idle streams (captures when
  not in a session — privacy-adjacent and wasteful — rejected).

## R8. Disk-space guard default (FR-007)

- **Decision**: Configurable `min_free_disk_mb`, default 2048 MB (≈ 4× a
  2-hour session). Checked at session start only, plus a low-disk session
  event and safe finalise if a chunk write fails with disk-full mid-session.
- **Rationale**: 2 GB gives a full worst-case session of margin; the
  mid-session path satisfies the disk-full edge case without new
  requirements.
