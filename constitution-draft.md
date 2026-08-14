# Ambient Recorder Constitution

<!-- Paste-ready seed for /speckit.constitution. Speckit will reformat into its
     template (numbered principles, governance section, version stamp) — the
     content below is what matters; let it own the structure. -->

## Core Principles

### I. Local-First, Privacy by Default (NON-NEGOTIABLE)
All audio capture, transcription, and inference run on the local machine. Raw
audio and transcripts MUST NOT leave the device. Any future escalation to a
frontier API (router pattern) is a separate, explicitly opted-in feature and
MUST operate on redacted/derived text only — never raw audio. No telemetry.

### II. Typed Contracts at Every Boundary
Every component boundary is defined by a Pydantic model or a typing Protocol
before implementation begins. Providers (STT, LLM, storage) are swappable
behind Protocols. WebSocket and REST payloads have explicit schemas. If a
contract changes, the contract file changes first, in its own reviewed commit.

### III. VRAM Budget Is the Binding Constraint
Target hardware: RTX 4070 Laptop GPU, 8 GB VRAM, with STT and LLM co-resident.
Every plan that loads a model MUST include the VRAM arithmetic (weights + KV
cache + activation headroom) and MUST fit within 8 GB with ≥1 GB headroom.
Default assumption: quantised 3–4B LLM alongside a medium-class STT model.
Degradation strategy (CPU fallback, model unload) is specified, not improvised.

### IV. Phased Delivery with Checkpoint Gates
Features are built in small, reviewable phases. Implementation halts for human
approval: (a) after spec, (b) after plan, (c) before any heavy dependency
install (PyTorch/CUDA, model downloads >1 GB), (d) before anything touching
audio devices system-wide. No phase begins until the prior gate is approved.

### V. Fail Fast, Log Structurally
Errors surface at startup or first use, not mid-meeting. Device availability,
model presence, and disk space are validated before a session starts.
Structured logging (JSON lines) from day one; warnings that are not actionable
are suppressed deliberately and documented.

### VI. Boring Tech, Single Process First
Prefer the simplest architecture that meets the requirement: one FastAPI
process serving both API and static UI, SQLite for metadata, files on disk for
audio. No message queues, no containers, no microservices unless a spec
demonstrates the need. YAGNI applies to infrastructure especially.

### VII. Sessions Are Sacred
A recording session, once started, must survive UI disconnects, transient
device hiccups, and process restarts without silent data loss. Audio is
persisted incrementally (chunked), never buffered solely in memory. Losing a
meeting recording is the worst failure mode this system has.

## Environment Constraints

- Windows 11; Git Bash (MSYS2) is the working shell — scripts must tolerate
  `MSYS_NO_PATHCONV` path-mangling issues; prefer forward-slash paths.
- Python with pinned dependencies; PyTorch from the cu128 index using the
  uninstall-then-reinstall pattern (in-place upgrade does not work).
- Ollama is the local LLM runtime (Qwen3, Llama 3.2 3B, Phi-4-mini available).
- FFmpeg at `/c/Program Files/Ffmpeg/bin` (not on PATH — reference explicitly).
- HuggingFace token at `~/.transcribe.env` for gated model downloads.

## Development Workflow

- Each feature: spec → plan → tasks → implement, on its own branch, merged via
  PR referencing the spec directory.
- Contract tests (schema validation, Protocol conformance) are required per
  feature; audio-device integration tests run manually, not in CI.
- Pinned versions live in plan.md per feature; project-wide pins graduate to
  a constraints file once two features share them.

## Governance

This constitution supersedes ad-hoc practice. Amendments require a dated
changelog entry and a stated rationale. Any plan that violates a principle
must say so explicitly and justify it in a "Complexity Tracking" note.
