# 002 manual: live transcription on real devices (T024)

Prereq: recorder running with transcription ready
(`curl 127.0.0.1:8377/transcription/readiness` → `ready:true`).

## Procedure (quickstart Scenarios 1–2)

```bash
# Terminal A — start a session, tail it
SID=$(curl -s -X POST 127.0.0.1:8377/sessions -H 'content-type: application/json' -d '{"title":"live"}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
python tests/manual/ws_tail.py $SID
# Terminal B — produce known speech through the speakers, e.g. Windows TTS:
powershell -c "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('First, the mobile release slipped by one week.')"
# and say a few sentences yourself. Then stop:
curl -s -X POST 127.0.0.1:8377/sessions/$SID/stop
```

PASS criteria: TTS lines appear as `them`, your speech as `me`, each
once; `lag=` column ≤ 15 s for ≥ 95% of segments (SC-002, NFR-001);
after stop, status `finalising` → `completed final=True` within 30 s
(SC-007); reconnecting `ws_tail.py $SID --after N` replays exactly
seq N+1 onward (FR-011).

## Recorded runs

**2026-08-19 — run 3 (after bleed + gap-fill fixes), session
01M0D6H2HGB03ZMRCZXXVFVBV1, `medium/int8_float16/cuda`:**

- 4 scripted TTS lines → all `them`, each once; room speech → `me`.
  Bleed (TTS audible on mic at ~−20 dB) correctly suppressed. **PASS**.
- Segment lag: 1.7–14.5 s, all ≤ 15 s. **PASS** (p95 within bound;
  as designed, ~10–14 s is the chunk-cadence floor).
- Stop → `completed final=True` in ~12 s. **PASS**.
- Track alignment: `them` "Welcome to the product review" at 5.8 s =
  wall-clock TTS start. Correct after the capture-engine gap-fill fix.
- Earlier runs 1–2 (same day) FAILED attribution and exposed two real
  defects, both fixed and unit-tested: (a) bleed rule compared
  segment-by-segment and judged mic before the system chunk was
  transcribed; (b) system-track chunks were not on the session clock
  because loopback delivers nothing during silence (fixed in feature
  001's writer: zero-fill idle gaps).

Known, accepted: lag reads 10–14 s rather than the unrelaxed 10 s
because an utterance is only final at the next 10 s chunk boundary;
sub-second streaming is the named upgrade (docs/backlog.md).
