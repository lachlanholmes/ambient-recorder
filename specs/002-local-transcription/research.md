# Phase 0 Research: Local Transcription

Version numbers and memory figures below are planning estimates as of
2026-08-18; task T-gate-c includes a measurement step that records the
real numbers on the target GPU into this file before the model choice is
frozen.

## R1. Speech engine and runtime

- **Decision**: faster-whisper (CTranslate2) with the CUDA 12 / cuDNN 9
  pip wheels (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`). No PyTorch.
- **Rationale**: CTranslate2 runs Whisper 2–4× faster than the reference
  implementation at a fraction of the memory, supports int8_float16 on
  Ada GPUs, and ships CUDA via pip wheels — sidestepping the
  constitution's noted PyTorch cu128 uninstall/reinstall pain entirely.
  Its `transcribe()` yields segments lazily with word timestamps, which
  suits both streaming windows and on-demand passes.
- **Alternatives considered**: openai-whisper (PyTorch; ~2× the VRAM,
  slower — rejected); whisper.cpp via bindings (excellent CPU story, but
  CUDA build on Windows is a self-compile chore and Python bindings lag —
  rejected for v1, noted as the CPU-fallback upgrade path); NVIDIA
  Parakeet/Canary via NeMo (strong accuracy, but pulls PyTorch + NeMo,
  ~6 GB of deps and larger VRAM — rejected under gate (c)/VRAM budget);
  Ollama-hosted STT (not a supported modality — rejected).

## R2. Model class and VRAM arithmetic (constitution III)

- **Decision**: `medium` (multilingual, or `medium.en` if measured
  accuracy is equal — English primary) at `int8_float16`, beam_size 1 for
  live, beam_size 5 for on-demand.
- **Arithmetic** (to be re-measured at gate c):

  | Item | Estimate |
  |------|----------|
  | Whisper `medium` int8_float16 weights | ~1.6 GB |
  | Activations + beam + CTranslate2 workspace (30 s window, beam 5) | ~0.6 GB |
  | **STT total** | **~2.2 GB** |
  | LLM reserve (Q4 3–4B + modest KV cache, spec Q3) | 3.5 GB |
  | Constitution headroom | 1.0 GB |
  | **Committed** | **6.7 GB of 8.0 GB** (1.3 GB spare) |

- **Degradation strategy** (specified, not improvised): at engine load,
  measure free VRAM. ≥ 3.0 GB free → `medium` on CUDA. 1.5–3.0 GB →
  `small` int8 on CUDA (~0.9 GB; accuracy drop logged as a warning and
  surfaced in readiness). < 1.5 GB or CUDA unavailable → `small` int8 on
  CPU (real-time on two tracks is *not* guaranteed; lag reporting makes
  that visible; never-skip still holds). Choice is logged and exposed via
  `/transcription/readiness`.
- **Alternatives considered**: `large-v3-turbo` (~3.2 GB int8 — best
  accuracy/speed but consumes the whole STT slice and leaves zero margin
  for the LLM's KV cache growth — rejected as default; noted as an
  opt-in if the LLM reserve is later relaxed); `distil-large-v3` (English
  only, ~2.5 GB — plausible alternative to measure alongside `medium` at
  gate c; pick whichever is more accurate on the field recordings within
  ≤ 2.5 GB); `small` (fits trivially but noticeably worse on quiet mic /
  compressed loopback audio — kept as fallback only).

## R3. Live windowing and never-skip backlog

- **Decision**: Consume finalised 10 s chunks per track (already the
  durable unit from feature 001) with a rolling window: transcribe each
  new chunk together with the trailing 5 s of the previous chunk, use
  Whisper's segment/word timestamps to keep only segments that *end*
  after the window's start point, and carry a small "pending tail" so a
  segment cut by the chunk boundary is emitted once, whole, when the next
  chunk arrives. Segments are emitted only when final for their window
  (stable-once-delivered, FR-002). Chunks queue in order; overload grows
  the queue and the reported lag; nothing is dropped (FR-013).
- **Rationale**: 10 s chunk cadence gives ~10–13 s worst-case lag at
  steady state (chunk finalises → transcribed within ~1–2 s on GPU) —
  inside NFR-001's ≤ 10 s target measured to segment delivery *for
  utterances that ended before the chunk boundary*, and honest that
  utterances straddling a boundary land ~one chunk later. Reusing the
  chunk cadence avoids a second audio path or shared buffers with the
  capture engine (constitution VII), and makes live and on-demand paths
  content-equivalent (FR-013).
- **Alternatives considered**: sub-second streaming from the capture
  queue (lower lag, but couples STT to the capture thread and needs
  VAD-driven endpointing plus revision of partial segments — conflicts
  with stable segments and constitution VII; rejected for v1, the clear
  upgrade path); word-level "typing" partials (UX nicety; contradicts
  FR-002 stability — rejected).

## R4. Two-track attribution and speaker bleed (FR-003, SC-001)

- **Decision**: Transcribe both tracks independently, then apply a pure
  attribution rule per candidate segment: for each mic segment, compute
  RMS energy of the mic track over the segment's span vs the *system*
  track over the same span (time-aligned by session-relative timestamps).
  If system energy exceeds mic energy by ≥ 6 dB *and* the system track
  produced an overlapping segment with ≥ 60% token overlap (normalised),
  the mic segment is bleed → dropped; the system segment is kept as
  `them`. Symmetric rule for the rarer reverse case (headphones leaking
  into mic is the same direction; the reverse — mic audio on loopback —
  does not occur physically, so the symmetric check is cheap insurance).
  Otherwise both are kept (genuine overlap talk). Thresholds live in one
  config block and are validated in the manual accuracy test.
- **Rationale**: Field-verified bleed is ~¼–½ volume (−6 to −12 dB), so
  the energy ratio alone is a strong signal; the token-overlap guard
  prevents dropping a genuine `me` utterance that merely coincides with
  loud remote audio. Pure function → unit-testable without a model.
- **Alternatives considered**: acoustic echo cancellation before STT
  (correct long-term fix, but DSP work + tuning; explicitly out of scope
  in spec — deferred); transcribe only the louder track per window (loses
  genuine overlap talk — rejected); speaker diarisation model (out of
  scope; two-track split makes it unnecessary for `me`/`them`).

## R5. Push transport and cursor semantics (FR-011)

- **Decision**: WebSocket at `/sessions/{id}/transcript/stream?after=<seq>`
  served by FastAPI/uvicorn in-process; server sends one JSON
  `TranscriptSegment` per message, plus periodic `status` frames
  (state, lag). On connect, the server replays segments with
  `seq > after` from the store, then tails the in-process pub/sub.
  Segment `seq` is a per-transcript monotonic integer assigned by the
  store on insert (single writer), so replay + tail is gap-free and
  duplicate-free.
- **Rationale**: WebSocket is already available (uvicorn[standard]),
  bidirectional isn't needed but WS has the best client support for the
  future web UI; the store-assigned `seq` makes the cursor trivially
  correct. SSE was the runner-up (simpler, but Windows/proxy quirks and
  the future UI may want bidirectional control).
- **Alternatives considered**: long-polling (adds latency, more code —
  rejected); SSE (viable; kept as a fallback if WS proves awkward in the
  UI feature).

## R6. Concurrency, priority, and FR-008

- **Decision**: One `transcription` worker thread owns the engine (single
  model instance, serial inference). It services a priority queue: live
  chunks (priority 0) always before on-demand work (priority 1); an
  on-demand job is chunk-granular so it yields between chunks when live
  work arrives (US4 acceptance 2). The worker runs at below-normal OS
  thread priority. Feature 001's capture/writer threads are untouched;
  the only coupling is an `on_chunk_finalized(session_id, kind, meta)`
  observer the engine invokes *after* the chunk row is committed.
- **Rationale**: One model instance is the VRAM budget; a priority queue
  is the smallest mechanism that guarantees live-over-backfill; observer
  hook keeps constitution VII intact (STT can crash and capture won't
  notice). FR-008 is verified by re-running the entire feature 001 suite
  plus a manual co-run soak.
- **Alternatives considered**: separate process for STT (isolates crashes
  better, but IPC + VRAM ownership across processes and violates
  single-process-first — rejected); async in event loop (inference is
  blocking C++ — rejected).

## R7. Persistence, versioning, and restart

- **Decision**: Three tables in the existing DB — `transcripts` (one row
  per transcription attempt: session_id, mode, state/final/superseded,
  engine+model provenance, timestamps), `transcript_segments` (transcript
  id, seq, source, start_s, end_s, text), `transcription_jobs` (queue +
  progress + failure reason). "Current transcript" = newest non-failed
  per session (query, not a flag, so supersede is an insert not an
  update). On startup: any `live` job for a session that is no longer
  active → its transcript is marked `final=false, superseded=false,
  state=interrupted_live` (segments kept, spec edge case) and the session
  is flagged as transcribable on demand; any `running` on-demand job →
  requeued from scratch (jobs are idempotent per FR-006).
- **Rationale**: Insert-only versioning matches "supersede but keep";
  restart rules mirror feature 001's reconciliation philosophy (durable
  data on disk is truth); segments ≤ 5% of audio trivially (an hour of
  speech ≈ 60 KB text vs ~115 MB audio).

## R8. Model acquisition and gate (c)

- **Decision**: Whisper weights fetched by faster-whisper from Hugging
  Face into `data/models/` (repo-local, gitignored) using the token at
  `~/.transcribe.env` if gated variants are chosen; download and CUDA
  wheel install are one explicit task marked **[GATE-C]**. Readiness
  reports `model_missing` (with the exact download command) rather than
  auto-downloading at runtime, so the recorder never silently pulls
  1.5 GB during a meeting.
- **Rationale**: Constitution IV gate (c) and V fail-fast; the recorder
  must be fully usable for capture even if transcription isn't set up.
