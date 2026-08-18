"""US1 live-capture walkthrough (T020) — run against a running recorder.

Usage: python tests/manual/test_us1_live_capture.py [seconds]
Speak into the mic AND play audio (music/video) while it records.
"""

from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8377"
SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def main() -> int:
    devices = httpx.get(f"{BASE}/devices").json()
    print("readiness:", devices)
    if not devices["ready"]:
        print("FAIL: devices not ready")
        return 1

    sid = httpx.post(f"{BASE}/sessions", json={"title": "manual US1"}).json()["id"]
    print(f"recording session {sid} for {SECONDS}s — speak AND play audio now")
    time.sleep(SECONDS)
    detail = httpx.post(f"{BASE}/sessions/{sid}/stop").json()
    print("stopped:", {k: detail[k] for k in ("status", "duration_s", "size_bytes")})

    ok = detail["status"] == "completed"
    session_dir = Path("data/sessions") / sid
    for kind in ("mic", "system"):
        chunks = sorted((session_dir / kind).glob("chunk_*.wav"))
        print(f"{kind}: {len(chunks)} chunks")
        if not chunks:
            print(f"FAIL: no {kind} chunks (for system: was audio playing?)")
            ok = False
            continue
        with wave.open(str(chunks[0]), "rb") as w:
            fmt = (w.getframerate(), w.getnchannels(), w.getsampwidth())
        if fmt != (16000, 1, 2):
            print(f"FAIL: {kind} format {fmt}, expected 16 kHz mono s16")
            ok = False
    print("verify audibly with e.g.:")
    print(f'  "/c/Program Files/Ffmpeg/bin/ffplay.exe" {session_dir}/mic/chunk_000000.wav')
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
