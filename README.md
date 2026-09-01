# Ambient Recorder

A local-first ambient meeting recorder for Windows 11. It captures your
microphone and everything your machine plays (remote call participants) as
separable audio streams, persisted durably in 10-second chunks, controlled
through a typed local REST API.

## Privacy stance (non-negotiable)

All capture and storage happens on this machine. **Raw audio and transcripts
never leave the device** — the API refuses to bind anything but a loopback
address, there is no telemetry, and no outbound network calls exist anywhere
in the codebase. See `.specify/memory/constitution.md`, Principle I.

## Status

- **Feature 001 — capture sessions**: done and field-verified (live,
  crash-recovery, 69-min soak).
- **Feature 002 — local transcription**: live transcription during
  recording (`me`/`them` attributed, streamed over WebSocket) plus on-demand
  backfill of stored sessions, on faster-whisper `medium` (CUDA). Measured
  on the target RTX 4070: ~1.1 GB VRAM, live lag 2–15 s, on-demand ~2×
  real time on two-track meeting audio.
- **Feature 003 — meeting assistant**: local LLM (Ollama) over the
  transcripts — structured summaries with cited, owned action items;
  multi-turn Q&A with citations and honest "not discussed" declines;
  live in-meeting questions answered from the transcript-so-far. Answers
  stream over `WS /conversations/{cid}/stream`.

## Assistant setup (optional, constitution gate (c))

Capture and transcription work without this; assistant endpoints report
`not_installed`.

```bash
winget install Ollama.Ollama          # local runtime, loopback only
ollama pull llama3.2:3b               # ~2 GB (the measured default; see specs/003 research R2)
curl -s 127.0.0.1:8377/assistant/readiness   # expect ready:true
# then: POST /sessions/<id>/summarize · POST /conversations {"session_ids":[...]}
#       POST /conversations/<cid>/ask · python tests/manual/answer_tail.py <cid>
```

Knobs (env): `AMBREC_ASSISTANT_MODEL`, `AMBREC_OLLAMA_URL` (loopback
enforced), `AMBREC_EXCERPT_BUDGET_TOKENS`, `AMBREC_ASSISTANT_IDLE_UNLOAD_S`
(VRAM freed after idle; model stays resident during recording).

## Transcription setup (optional, constitution gate (c))

Capture works without any of this; sessions simply have no transcript.

```bash
pip install -c constraints.txt -e ".[dev,transcription]"   # ~1 GB CUDA/cuDNN wheels
python scripts/fetch_models.py medium small               # ~2 GB weights → data/models/
python -m ambient_recorder
curl -s 127.0.0.1:8377/transcription/readiness             # expect ready:true, model medium/int8_float16/cuda
```

Then every session is transcribed live; tail one with
`python tests/manual/ws_tail.py <session-id>`, read it back at
`GET /sessions/<id>/transcript`, or backfill an old session with
`POST /sessions/<id>/transcribe`. Tuning knobs (env): `AMBREC_BLEED_DB`,
`AMBREC_OVERLAP_RATIO` (speaker-bleed attribution), `AMBREC_ON_DEMAND_BEAM_SIZE`.
Drop to `small` in `data/models/` for ~3× faster backfill at an accuracy cost.

## Development

```bash
python -m venv .venv && source .venv/Scripts/activate
pip install -c constraints.txt -e ".[dev]"
pytest            # contract + unit + integration; never touches audio devices
ruff check src tests
```

Real-device validation lives in `tests/manual/` and runs by hand only —
never in CI. End-to-end scenarios: `specs/001-ambient-audio-capture/quickstart.md`.

Run the recorder from the repo root (or set `AMBREC_DATA_ROOT` to an
absolute path) — recordings land in `./data/` relative to the working
directory. Future-feature ideas are collected in `docs/backlog.md`.

## Contributor notes

- Every boundary is a typed contract (Pydantic model or Protocol). Contract
  changes land in `specs/*/contracts/` and the contract modules first, in
  their own commit, before implementations.
- Gate (d) tasks are marked **[GATE-D]** in `specs/*/tasks.md`. Do not open
  audio devices — even "just to test" — without approval.
