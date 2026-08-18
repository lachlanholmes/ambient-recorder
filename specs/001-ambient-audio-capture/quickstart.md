# Quickstart: Ambient Audio Capture Sessions

Validation guide proving the feature end-to-end. Contracts:
[contracts/rest-api.md](contracts/rest-api.md). Shell: Git Bash on
Windows 11 (`MSYS_NO_PATHCONV=1` prefix where a path argument must not be
mangled).

## Prerequisites

- Python 3.12 on PATH; working microphone and default output device.
- FFmpeg for verification: `/c/Program Files/Ffmpeg/bin/ffprobe.exe`
  (not on PATH — use the full path).

## Setup

```bash
python -m venv .venv && source .venv/Scripts/activate
pip install -e ".[dev]"        # pinned deps per plan.md
pytest tests/contract tests/unit tests/integration   # all green, no devices needed
```

## Run

```bash
python -m ambient_recorder     # starts uvicorn on 127.0.0.1:8377
# startup logs (JSON lines): pid, config, device readiness, reconciliation result
```

## Scenario 1 — start/stop round trip (US1)

```bash
curl -s http://127.0.0.1:8377/devices          # expect ready: true
curl -s -X POST http://127.0.0.1:8377/sessions -H 'content-type: application/json' \
     -d '{"title":"quickstart"}'               # expect 201, status active
# speak into the mic AND play any audio for ~1 minute, then:
curl -s -X POST http://127.0.0.1:8377/sessions/<id>/stop   # expect 200, completed
curl -s http://127.0.0.1:8377/sessions/<id>    # duration ≈ 60s, both sources, chunk_counts ≈ 6 each
```

Verify separability and format (NFR-002):

```bash
"/c/Program Files/Ffmpeg/bin/ffprobe.exe" -hide_banner data/sessions/<id>/mic/chunk_000000.wav
# expect: pcm_s16le, 16000 Hz, mono — same for system/
```

## Scenario 2 — crash survival (US2, SC-002)

```bash
curl -s -X POST http://127.0.0.1:8377/sessions -d '{"title":"crash test"}' -H 'content-type: application/json'
# capture ≥ 3 minutes, then kill ungracefully — target the recorder's own
# pid (printed in its first startup log line); do NOT kill python.exe by
# image name, that takes out every Python process:
kill -9 <recorder-pid>         # or: taskkill //F //PID <recorder-pid>
python -m ambient_recorder     # restart
curl -s http://127.0.0.1:8377/sessions/<id>
# expect: status interrupted, reconciled event present, no .part files in session dir
# expect: last finalised chunk plays in an external tool; ≤ 10 s lost per source
```

## Scenario 3 — preflight refusals (US3, SC-003)

```bash
# unplug/disable the microphone, then:
curl -s -X POST http://127.0.0.1:8377/sessions -d '{}' -H 'content-type: application/json'
# expect: 424 with error.code device_missing, error.detail.missing == ["mic"]
curl -s http://127.0.0.1:8377/sessions        # expect: no new session created
# disk guard: set min_free_disk_mb above current free space in config, restart, retry
# expect: 507 disk_space_low with free_mb/required_mb in detail
```

## Scenario 4 — ambient readiness (US4, SC-004)

```bash
# with the recorder already running for a while:
time curl -s -X POST http://127.0.0.1:8377/sessions -d '{}' -H 'content-type: application/json'
# expect: response (with capture started) in ≤ 2 s; stop, repeat 3×, no restart needed
```

## Manual device tests

`tests/manual/README.md` scripts cover: mid-session headset unplug
(FR-011 — session continues on surviving source, `device_lost` event
recorded), default-output switch mid-session, and a 60-minute soak
(SC-001: both sources intact, ≤ 250 MB total; SC-006: < 5% CPU,
< 200 MB RAM, 0% GPU in Task Manager). These run by hand — never in CI
(constitution, Development Workflow).
