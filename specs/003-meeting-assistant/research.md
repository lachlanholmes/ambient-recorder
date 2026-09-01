# Phase 0 Research: Meeting Assistant

Estimates marked for re-measurement are confirmed at gate (c) before the
model choice freezes (same discipline as 002 R2, which proved estimates
2× conservative).

## R1. LLM runtime

- **Decision**: Ollama as a localhost service (`127.0.0.1:11434`),
  driven via its streaming HTTP API with httpx. Installed at gate (c) —
  probed 2026-08-24: **not currently installed** despite the
  constitution's environment note; that line gets a PATCH amendment
  after gate (c) executes.
- **Rationale**: Constitution-named runtime (the explicit second-process
  carve-out); trivial Windows install; robust GPU offload with no new
  Python CUDA dependencies (002's cuBLAS pinning pain stays contained);
  `keep_alive` gives precise load/unload control for the residency
  policy (R6); native token streaming matches FR-012.
- **Alternatives considered**: llama-cpp-python in-process (keeps single
  process, but Windows CUDA wheels are third-party/spotty and a C++
  crash would take the recorder down with it — capture safety argues for
  process isolation here); CTranslate2 text generation (already
  installed, but generation support/model coverage is weak vs
  llama.cpp-family — rejected); transformers+PyTorch (the exact
  dependency stack 002 deliberately avoided — rejected).

## R2. Model and VRAM arithmetic (constitution III)

- **Decision**: default candidate `llama3.2:3b` (Q4_K_M, ~2.0 GB
  weights); gate (c) pulls and measures it against `qwen3:4b` and
  `phi4-mini` on summary + Q&A quality over the project's own field
  transcripts, then freezes the choice.
- **Measured at gate (c), 2026-08-24, Ollama 0.32.15, RTX 4070 8188 MiB**
  (T028; quality judged on the T038 accuracy session's real transcript,
  4-question probe + summary-map; VRAM via nvidia-smi deltas vs 0 idle):

  | Model | Resident | Warm speed | Cold load | Probe quality |
  |-------|----------|-----------|-----------|---------------|
  | llama3.2:3b | 2577 MiB | 89 tok/s, first ~0.8 s | 2.7 s | 2/3 answerable + decline OK; **declined an easy answerable** |
  | qwen3:4b | 3169 MiB | 62 tok/s | 7 s | **unusable**: thinking-mode model; leaks reasoning monologue into the response even with `think:false` |
  | **phi4-mini** | 3083 MiB | 47–69 tok/s, first ~0.8 s | **19.7 s** | **4/4**: all answerable correct with citations, clean decline |

  **Decision: `phi4-mini` default** — grounding quality is the feature's
  core promise (SC-001/SC-003) and it was the only clean sweep. Its slow
  cold load is mitigated in code rather than accepted: the worker
  pre-warms the engine at session start (spec's residency assumption,
  now actually implemented) and at conversation creation, so every
  NFR-002/NFR-003 path meets its first-token budget with a warm model.
  Residual known edge: asking on an *old* conversation after a long idle
  pays the ~20 s load once. `llama3.2:3b` is the documented low-latency
  alternative (`AMBREC_ASSISTANT_MODEL`); T030's full answer key can
  overturn the default cheaply. Co-resident total: 1123 (STT) + 3083
  (LLM) = **4206 MiB, well inside 8188 − 1024 headroom**. Note: the
  three-candidate download totalled ~7 GB, not the plan's ~3 GB
  estimate.
- **Arithmetic** (planning estimates, superseded by the table above):

  | Item | Estimate |
  |------|----------|
  | STT co-resident (002, **measured**) | 1.12 GB |
  | 3B LLM weights Q4 | ~2.0 GB |
  | KV cache @ 8k context + runtime overhead | ~0.6–1.4 GB |
  | **Committed with 1.0 GB headroom** | **≤ 5.5–6.5 of 8.0 GB** |

- **Context budget**: 8k tokens (~ the model class's comfortable window
  at this VRAM). A 2-hour transcript ≈ 20–30k tokens, so neither Q&A nor
  summaries ever send the whole transcript — see R3/R4.
- **Degradation strategy** (specified, not improvised): insufficient
  VRAM at load → reduce context 8k→4k → smaller model class (~1.7B) with
  a logged accuracy warning → assistant `not_ready` with reason. The
  assistant never causes STT or capture to degrade; if anything must
  give, it is the assistant.

## R3. Grounded Q&A: retrieval + citation validation (FR-002/003)

- **Decision**: The model only ever sees transcript excerpts we select —
  grounding by construction. Per question: lexical retrieval over
  segments (token-overlap scoring with the question + conversation
  context, recency-weighted for live), packed to a ~3k-token excerpt
  budget as numbered blocks `[12] 00:14:32 them: …`; instruction
  requires citing `[n]` after each claim and answering exactly
  "not discussed in this meeting" when the excerpts don't contain the
  answer. `grounding.py` validates streamed output post-hoc: extract
  cited `[n]`, drop invalid ones, and mark the turn `ungrounded` if an
  answer asserts content with zero valid citations (surfaced in the
  terminal status; SC-003's test enforces behaviour).
- **Rationale**: No embedding model (would cost VRAM, deps, and an
  index); lexical retrieval over attributed, timestamped segments is
  strong for meeting-scale corpora and is a pure, unit-testable
  function. Citation validation is cheap string work.
- **Alternatives considered**: embeddings + vector store (better recall
  on paraphrase, but a whole new model + storage for marginal gain at
  5-hour scale — rejected for v1, named upgrade); full-transcript
  stuffing with a long-context model (VRAM-impossible in budget —
  rejected); no citations, trust the model (violates FR-002 — rejected).

## R4. Summaries of long transcripts: staged condensation (FR-001, SC-002)

- **Decision**: Map-reduce. Map: transcript split into ~20-minute
  windows, each summarised to structured bullets (points, decisions,
  action items) with segment citations carried through. Reduce: bullets
  merged and deduplicated into the final Summary; a second reduce tier
  activates when the bullet volume itself exceeds the context budget
  (the 5-hour soak needs it). Every action item keeps ≥ 1 citation from
  its source window.
- **Rationale**: Covers any transcript length within a fixed context
  window; citations survive the pipeline so FR-002 holds end-to-end;
  windows parallelise naturally if ever needed (serial in v1).

## R5. Worker, priority, and FR-008

- **Decision**: One `assistant` worker thread with a priority queue:
  live questions (0) > post-meeting questions (1) > summaries (2). One
  Ollama request in flight at a time. The worker subscribes to 002's
  segment stream for live grounding but only ever *reads*; it holds no
  locks shared with capture/STT. GPU contention with live STT is
  measured, not scheduled: STT inference bursts ~1–2 s per 10 s chunk,
  and Ollama requests run 3–30 s; the co-run manual test verifies STT
  lag stays in bound while answers generate (SC-005). If measurement
  shows contention, the specified mitigation is pausing token generation
  between STT bursts (Ollama supports request cancellation; resume =
  re-ask with prefix) — held in reserve, not built pre-emptively.
- **Rationale**: Serial + priorities is the smallest mechanism honouring
  "the person in the meeting is waiting"; process isolation means an
  Ollama crash is a typed `failed` task, never a recorder crash.

## R6. Model residency (spec assumption → policy)

- **Decision**: During an active session the model is kept loaded
  (`keep_alive` refreshed on session events) so live answers avoid a
  cold load; after session stop + 10 min idle it unloads (VRAM freed
  between meetings). First post-meeting request after idle pays one
  ~2–5 s load, inside NFR-002's 10 s first-token budget.
- **Rationale**: Live latency (NFR-003) can't afford a cold load;
  between meetings, freeing ~2–3 GB respects the machine's other uses.

## R7. Storage and versioning

- **Decision**: Four tables in the existing SQLite: `summaries`
  (insert-only versions per session, current = newest non-failed,
  provenance: transcript id + model), `conversations` (id, session,
  created_at, live-born flag), `conversation_turns` (conversation, seq,
  question, answer, citations JSON, watermark segment seq, state),
  `assistant_tasks` (queue/progress/failure — summary and ask tasks).
  Startup reconciliation: `running` tasks → requeued (summaries) or
  `failed: interrupted` (asks — the asker is gone; the turn keeps any
  streamed prefix marked incomplete).
- **Rationale**: Mirrors 002's proven versioning/reconciliation
  philosophy; conversations are append-only so no supersede logic
  needed there.

## R8. Streaming transport

- **Decision**: WebSocket `/conversations/{cid}/stream` following 002's
  pattern: on connect, replay the in-flight turn's streamed prefix (if
  any), then tail tokens; frames `{"type":"token"}`,
  `{"type":"status"}` with terminal status carrying validated
  citations. `POST …/ask` returns the turn id immediately (202).
- **Rationale**: Same machinery and test patterns as 002's segment
  stream (SegmentStream generalises); a disconnected client reads the
  stored turn (FR-012).

## R9. Egress guard (SC-007)

- **Decision**: The engine client pins its base URL to
  `http://127.0.0.1:11434` (config-validated loopback-only, same rule
  as the API bind); readiness verifies the server reports only local
  models; the manual test observes zero non-loopback connections from
  both processes during assistant operations.
