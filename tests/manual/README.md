# Manual device tests

Run by a human with real audio devices — **never in CI** (constitution,
Development Workflow). Prereq: `pip install -e ".[dev]"`, then start the
recorder in one terminal:

```bash
python -m ambient_recorder
# first log line contains the pid — you'll need it for the kill test
```

FFmpeg verification uses the machine's install at
`/c/Program Files/Ffmpeg/bin/ffprobe.exe` (not on PATH).

| Scenario | File | Covers |
|----------|------|--------|
| US1 live capture | `test_us1_live_capture.py` (script) | SC-001 format/separability, NFR-002 |
| US2 crash + unplug | `test_us2_crash_and_unplug.md` | SC-002, FR-008, FR-011 |
| US3 readiness | `test_us3_readiness.md` | SC-003, FR-005/007/012 |
| US4 start latency | `test_us4_latency.md` | SC-004 (strict 2 s) |
| Soak (60 min) | `test_soak.md` | SC-001 size, SC-006/NFR-001 overhead |

**Known v1 caveat**: WASAPI loopback only delivers frames while something
is rendering audio. During total output silence the system source produces
no data, so its persisted duration can be shorter than the mic's. Play
audio during tests (and real meetings inherently do).
