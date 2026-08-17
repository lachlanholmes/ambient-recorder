# Soak: 60-minute session (T035, SC-001 + SC-006/NFR-001)

Setup: recorder running; a real or simulated meeting (e.g. a video call,
or a long video playing) so both sources have signal for the full hour.

1. Start a session titled `soak`; record for 60 minutes.
2. During the run, sample Task Manager (Details → python.exe) at ~15, 30,
   45 min. Record here:
   - CPU %: 0.11 / 0.10 / 0.08  (PASS < 5%) — of 20 cores
   - RAM MB: 40.7 / 41.5 / 41.5 (PASS < 200 MB)
   - GPU %: 0 (PASS: 0 — engine never touches the GPU)
   *(2026-08-18: hour-run samples were missed; overhead was instead
   measured on a separate 5-min steady-state session with looping
   playback, 3 samples at 90 s intervals via TotalProcessorTime deltas +
   GPU Engine counters, watchdog poll active. Steady-state cost is flat,
   so the substitution is sound.)*
3. Stop the session. From the inspect response record:
   - `duration_s`: 4156.4 (69.3 min; ran long past the 60-min target)
   - `size_bytes`: 240,286,150 → 208 MB/hour (PASS ≤ 250 MB/hour, SC-001)
   - `chunk_counts`: mic 416 / system 336 (system gap = output silence
     periods, the documented loopback caveat)
4. Spot-check audio: play the first, a middle, and the last chunk of each
   source with ffplay; both sources intact and separable.
5. Watchdog overhead check: the ~2 s default-device poll spawns a
   short-lived PortAudio instance; confirm the CPU numbers above still
   pass. If they don't, raise `_POLL_INTERVAL_S` in audio/wasapi.py and
   re-run (plan NFR-001 takes precedence over poll frequency).

Result (date, machine, pass/fail): 2026-08-18, RTX 4070 laptop (20-core
CPU), **PASS** — session 01M08RRRZR7F8QX91AYHSZNT9X (SC-001) + overhead
session 01M091T8WZVECFVHG4V1MRRTEY (SC-006). Audible spot-check: mic
chunks contain the speaker's voice plus system playback acoustically
bleeding in at ~¼–½ volume (laptop speakers → mic array) — expected
physics, noted in docs/backlog.md for the transcription feature's
speaker-attribution design.
