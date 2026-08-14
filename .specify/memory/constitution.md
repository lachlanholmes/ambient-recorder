<!--
Sync Impact Report
==================
Version change: template (unversioned) → 1.0.0
Rationale: Initial ratification — first concrete constitution replacing the
untouched placeholder template. MAJOR.MINOR.PATCH starts at 1.0.0.

Modified principles: n/a (all placeholders replaced on first adoption)
Added sections:
  - Core Principles I–VII (Local-First Privacy; Typed Contracts; VRAM Budget;
    Phased Delivery Gates; Fail Fast & Structured Logging; Boring Tech;
    Sessions Are Sacred)
  - Environment Constraints
  - Development Workflow
  - Governance (amendment procedure, versioning policy, compliance review)
Removed sections: none (template comments removed)

Templates:
  ✅ .specify/templates/plan-template.md — Constitution Check gate is generic
     and resolves against this file; Complexity Tracking table matches the
     Governance requirement for justified violations. No change needed.
  ✅ .specify/templates/spec-template.md — no constitution-specific sections
     required; mandatory sections unaffected. No change needed.
  ✅ .specify/templates/tasks-template.md — updated: "Tests" note now states
     contract tests are constitutionally REQUIRED per feature (Principle II /
     Development Workflow), overriding the default "tests optional" stance.
  ✅ .claude/skills/speckit-*/SKILL.md — generic, agent-neutral wording;
     no outdated references. No change needed.

Deferred TODOs: none.
-->

# Ambient Recorder Constitution

## Core Principles

### I. Local-First, Privacy by Default (NON-NEGOTIABLE)

All audio capture, transcription, and inference MUST run on the local machine.
Raw audio and transcripts MUST NOT leave the device. Any future escalation to a
frontier API (router pattern) is a separate, explicitly opted-in feature and
MUST operate on redacted/derived text only — never raw audio. No telemetry of
any kind.

**Rationale**: The system continuously hears private conversations; the only
acceptable trust model is one where nothing leaves the machine unless the user
deliberately ships derived text elsewhere.

### II. Typed Contracts at Every Boundary

Every component boundary MUST be defined by a Pydantic model or a typing
Protocol before implementation begins. Providers (STT, LLM, storage) MUST be
swappable behind Protocols. WebSocket and REST payloads MUST have explicit
schemas. If a contract changes, the contract file changes first, in its own
reviewed commit.

**Rationale**: Swappable local models and evolving pipelines only stay
manageable when the seams are explicit and machine-checked.

### III. VRAM Budget Is the Binding Constraint

Target hardware: RTX 4070 Laptop GPU, 8 GB VRAM, with STT and LLM co-resident.
Every plan that loads a model MUST include the VRAM arithmetic (weights +
KV cache + activation headroom) and MUST fit within 8 GB with ≥1 GB headroom.
Default assumption: quantised 3–4B LLM alongside a medium-class STT model.
Degradation strategy (CPU fallback, model unload) MUST be specified in the
plan, not improvised at runtime.

**Rationale**: Co-residency on 8 GB fails silently and late if it is not
budgeted up front; the arithmetic is cheap, an OOM mid-meeting is not.

### IV. Phased Delivery with Checkpoint Gates

Features MUST be built in small, reviewable phases. Implementation MUST halt
for human approval: (a) after spec, (b) after plan, (c) before any heavy
dependency install (PyTorch/CUDA, model downloads >1 GB), (d) before anything
touching audio devices system-wide. No phase begins until the prior gate is
approved.

**Rationale**: Heavy installs and system-wide audio hooks are expensive or
invasive to reverse; gates keep the human in control of exactly those steps.

### V. Fail Fast, Log Structurally

Errors MUST surface at startup or first use, not mid-meeting. Device
availability, model presence, and disk space MUST be validated before a
session starts. Structured logging (JSON lines) is required from day one;
warnings that are not actionable MUST be suppressed deliberately and the
suppression documented.

### VI. Boring Tech, Single Process First

Prefer the simplest architecture that meets the requirement: one FastAPI
process serving both API and static UI, SQLite for metadata, files on disk for
audio. No message queues, no containers, no microservices unless a spec
demonstrates the need. YAGNI applies to infrastructure especially. Deviations
MUST be justified in the plan's Complexity Tracking section.

### VII. Sessions Are Sacred

A recording session, once started, MUST survive UI disconnects, transient
device hiccups, and process restarts without silent data loss. Audio MUST be
persisted incrementally (chunked), never buffered solely in memory.

**Rationale**: Losing a meeting recording is the worst failure mode this
system has; every design decision that touches a live session is subordinate
to not losing audio.

## Environment Constraints

- Windows 11; Git Bash (MSYS2) is the working shell — scripts MUST tolerate
  `MSYS_NO_PATHCONV` path-mangling issues; prefer forward-slash paths.
- Python with pinned dependencies; PyTorch is installed from the cu128 index
  using the uninstall-then-reinstall pattern (in-place upgrade does not work).
- Ollama is the local LLM runtime (Qwen3, Llama 3.2 3B, Phi-4-mini available).
- FFmpeg lives at `/c/Program Files/Ffmpeg/bin` (not on PATH — reference it
  explicitly).
- HuggingFace token at `~/.transcribe.env` for gated model downloads.

## Development Workflow

- Each feature follows spec → plan → tasks → implement, on its own branch,
  merged via PR referencing the spec directory.
- Contract tests (schema validation, Protocol conformance) are REQUIRED per
  feature; audio-device integration tests run manually, not in CI.
- Pinned versions live in plan.md per feature; project-wide pins graduate to a
  constraints file once two features share them.

## Governance

This constitution supersedes ad-hoc practice for all work in this repository.

- **Amendments**: Any amendment requires a dated changelog entry in this file's
  Sync Impact Report and a stated rationale, and MUST propagate to dependent
  templates (`.specify/templates/*.md`) in the same change.
- **Versioning**: Semantic versioning — MAJOR for principle removals or
  redefinitions, MINOR for new/materially expanded principles or sections,
  PATCH for clarifications and wording fixes.
- **Compliance**: Every plan passes the Constitution Check gate before
  research and again after design. Any plan that violates a principle MUST say
  so explicitly and justify it in the plan's Complexity Tracking section;
  unjustified violations block implementation.

**Version**: 1.0.0 | **Ratified**: 2026-07-26 | **Last Amended**: 2026-07-26
