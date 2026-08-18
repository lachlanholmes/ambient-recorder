# Quickstart: Local Transcription

Validation guide. Contracts: [contracts/rest-api.md](contracts/rest-api.md).
Recorder must be run from the repo root (`data/` is relative).

## Prerequisites

- Feature 001 working (`pytest` green, `python -m ambient_recorder` runs).
- **Gate (c) approved and executed**: CUDA/cuDNN wheels installed and
  Whisper `medium` downloaded to `data/models/` (see tasks.md gate task).
- `nvidia-smi` available for VRAM checks.

## Setup

```bash
source .venv/Scripts/activate
pip install -e ".[dev,transcription]"     # transcription extra = faster-whisper + CUDA wheels
pytest                                     # device- and model-free suite, all green
python -m ambient_recorder
curl -s 127.0.0.1:8377/transcription/readiness
# expect ready:true, model "medium/int8_float16/cuda", free_vram_mb ≈ 8000
```

## Scenario 1 — live transcript (US1, SC-002)

```bash
# Terminal A: subscribe before speaking (websocat or the manual script)
python tests/manual/ws_tail.py <session-id>       # prints segments + status frames as they arrive
# Terminal B:
curl -s -X POST 127.0.0.1:8377/sessions -H 'content-type: application/json' -d '{"title":"live"}'
# speak a few sentences; play a video with clear speech; note wall-clock per utterance
# expect: 'me' segments for your speech, 'them' for the video, each within ~10-13 s of being spoken
curl -s -X POST 127.0.0.1:8377/sessions/<id>/stop
# expect: status finalising → completed (final:true) within 30 s; socket closes
curl -s 127.0.0.1:8377/sessions/<id>/transcript | python -m json.tool | head -40
```

## Scenario 2 — reconnect is lossless (FR-011)

```bash
# during a live session, kill ws_tail.py, note the last seq printed (N), then:
python tests/manual/ws_tail.py <session-id> --after N
# expect: first segment received has seq N+1; no gaps, no repeats
```

## Scenario 3 — on-demand backfill + supersede (US3, SC-006)

```bash
curl -s -X POST 127.0.0.1:8377/sessions/<feature-001-era-id>/transcribe   # 202
curl -s 127.0.0.1:8377/sessions/<id>/transcript | grep -E '"state"|progress'
# expect: running with advancing progress_chunks → completed
curl -s 127.0.0.1:8377/sessions/<live-session-id>/transcribe                # re-transcribe a live one
curl -s 127.0.0.1:8377/sessions/<live-session-id>/transcripts
# expect: two entries — on_demand (current), live (superseded:true); both readable by id
```

## Scenario 4 — attribution and bleed (SC-001)

Use `tests/manual/accuracy_script.md`: a scripted two-sided dialogue
(you read lines A; a played recording speaks lines B, loud enough to
bleed). Score: every scripted line appears once; ≥ 90% correct me/them.

## Scenario 5 — recording never disturbed (SC-004, FR-008)

```bash
# start an on-demand job on a long session, then immediately:
time curl -s -X POST 127.0.0.1:8377/sessions -d '{"title":"contention"}' -H 'content-type: application/json'
# expect ≤ 2 s; on-demand job progress pauses while live chunks arrive, resumes after stop
# 2-hour live-transcribed soak: chunk_counts ≈ 720/720 (both fed), zero .part orphans,
# nvidia-smi steady ≈ 2.2 GB, Task Manager CPU/RAM within NFR-003 additive budget
```

## Scenario 6 — failure is honest (US2)

```bash
# simulate: rename data/models/<medium dir> while idle, restart, start a session
curl -s 127.0.0.1:8377/transcription/readiness      # ready:false, reason model_missing + command
curl -s 127.0.0.1:8377/sessions/<id>/transcript     # state failed, reason engine_not_ready
# recording itself proceeds normally; restore the model, on-demand transcribe → completed
```
