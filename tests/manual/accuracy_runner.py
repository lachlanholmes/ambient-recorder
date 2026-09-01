"""T038 runner: drives accuracy_script.md end-to-end and scores the result.

Usage (recorder must be running and transcription ready):
    python tests/manual/accuracy_runner.py

B lines play through the speakers via Windows TTS; for A lines, read the
prompt aloud and press Enter when done. The runner then stops the session,
waits for the transcript to finalise, and prints a scoring table for the
sheet in accuracy_script.md.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time

import httpx

BASE = "http://127.0.0.1:8377"

SCRIPT: list[tuple[str, str]] = [
    ("B", "Good morning, shall we start with the roadmap?"),
    ("A", "Yes, let's begin with the mobile release."),
    ("B", "The certificate problem pushed it by a week."),
    ("A", "I saw that, do we have a new date?"),
    ("B", "Thursday the fourteenth, pending QA sign-off."),
    ("A", "Okay. Second item is the dashboard feedback."),
    ("B", "Customers love the new filters, very positive."),
    ("A", "Great, any complaints at all?"),
    ("B", "Only the export button, it is hard to find."),
    ("A", "Noted. Third, the pricing decision."),
    ("B", "We need it before the end of the month."),
    ("A", "Agreed, I will draft options by Friday."),
]

_WORD = re.compile(r"[a-z0-9']+")


def tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def speak(text: str, wait: bool = True) -> subprocess.Popen | None:
    cmd = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Volume = 100; $s.Speak('{text.replace(chr(39), chr(39) * 2)}')"
    )
    if wait:
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=True)
        return None
    return subprocess.Popen(["powershell", "-NoProfile", "-Command", cmd])


def main() -> int:
    r = httpx.get(f"{BASE}/transcription/readiness").json()
    if not r["ready"]:
        print(f"transcription not ready: {r.get('reason')}")
        return 1
    print("Starting session. Speak the YOU lines clearly; press Enter after each.")
    sid = httpx.post(f"{BASE}/sessions", json={"title": "accuracy T038"}).json()["id"]
    print(f"session: {sid}\n")
    time.sleep(2)

    for i, (side, line) in enumerate(SCRIPT, 1):
        if side == "B":
            print(f"  {i:2}. [speakers] {line}")
            speak(line)
            time.sleep(1.0)
        else:
            input(f"  {i:2}. [YOU say ] {line!r}   — press Enter when done ")
            time.sleep(0.5)

    if input("\nOverlap check: replay line 11 WHILE you say line 12? [y/N] ").lower() == "y":
        proc = speak(SCRIPT[10][1], wait=False)
        print(f"      [YOU say, NOW, over the top] {SCRIPT[11][1]!r}")
        proc.wait()
        time.sleep(1.0)

    print("\nLetting the last chunks land (~15 s)...")
    time.sleep(15)
    httpx.post(f"{BASE}/sessions/{sid}/stop")
    print("Stopped; waiting for the transcript to finalise...")
    deadline = time.monotonic() + 120
    t = None
    while time.monotonic() < deadline:
        t = httpx.get(f"{BASE}/sessions/{sid}/transcript").json()
        if t["state"] == "completed":
            break
        time.sleep(3)
    if not t or t["state"] != "completed":
        print(f"transcript did not finalise in time (state={t and t['state']})")
        return 1

    me_text = " ".join(s["text"] for s in t["segments"] if s["source"] == "me")
    them_text = " ".join(s["text"] for s in t["segments"] if s["source"] == "them")
    me_tok, them_tok = tokens(me_text), tokens(them_text)

    present = correct = bleed = 0
    print(f"\n{'#':>2} {'want':>4} {'me%':>4} {'them%':>5}  verdict")
    for i, (side, line) in enumerate(SCRIPT, 1):
        lt = tokens(line)
        cov_me = len(lt & me_tok) / len(lt)
        cov_them = len(lt & them_tok) / len(lt)
        want = "me" if side == "A" else "them"
        got_me, got_them = cov_me >= 0.7, cov_them >= 0.7
        is_present = got_me or got_them
        is_correct = (got_me and want == "me") or (got_them and want == "them")
        is_bleed = got_me and got_them
        present += is_present
        correct += is_correct and not is_bleed
        bleed += is_bleed
        if is_bleed:
            verdict = "BLEED-DUP"
        elif is_correct:
            verdict = "ok"
        else:
            verdict = "wrong side" if is_present else "MISSING"
        print(f"{i:>2} {want:>4} {cov_me:>4.0%} {cov_them:>5.0%}  {verdict}")

    n = len(SCRIPT)
    print(f"\npresent exactly once: {present - bleed}/{n}")
    print(f"correct attribution : {correct}/{n} = {correct / n:.0%}  (PASS >= 90%)")
    print(f"bleed duplicates    : {bleed}  (PASS 0)")
    print(f"segments: {len(t['segments'])}  model: {t['model']}  session: {sid}")
    print("\nCopy these numbers into tests/manual/accuracy_script.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
