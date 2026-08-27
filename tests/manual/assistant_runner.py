"""T030 runner: records the keyed meeting, then scores summary + Q&A.

Usage (recorder running, transcription AND assistant ready):
    python tests/manual/assistant_runner.py

Exactly like accuracy_runner.py: lines marked [speakers] play via TTS
("them"); for [YOU say] lines, read the line aloud, then press Enter.
No second person needed. Afterwards the runner summarizes the session,
asks the 10-question set, and prints the SC-001/SC-003 scoring for
tests/manual/assistant_answer_key.md.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time

import httpx

BASE = "http://127.0.0.1:8377"

# Two-sided dialogue embedding the answer key: 5 decisions, 5 action items.
SCRIPT: list[tuple[str, str]] = [
    ("B", "Good morning, let's get through the agenda quickly."),
    ("A", "Sure. First up, when do we ship the mobile release?"),
    ("B", "We decided to ship on Thursday the fourteenth."),
    ("A", "Agreed, Thursday the fourteenth it is."),
    ("B", "Next, the export button. Users say it is hard to find."),
    ("A", "Let's keep the export button but move it to the toolbar."),
    ("B", "Good decision. Now, pricing."),
    ("A", "The pricing change goes to the board for approval."),
    ("B", "Then you should book the board slot."),
    ("A", "Yes, I will book the board slot."),
    ("B", "On hiring, we agreed to hire two engineers next quarter."),
    ("A", "Right, and you will write the job descriptions."),
    ("B", "I will write the job descriptions. What about the legacy importer?"),
    ("A", "We decided to drop the legacy importer."),
    ("B", "Then you must email the importer deprecation notice by the end of the month."),
    ("A", "I will email the deprecation notice by the end of the month."),
    ("B", "I will send the updated forecast before the meeting."),
    ("A", "And I will draft pricing options by Friday."),
    ("B", "Perfect, that is everything for today."),
]

# key: (required words, human label)
DECISION_KEYS = [
    ({"thursday"}, "ship Thursday the 14th"),
    ({"export", "move"}, "keep export button, move it"),
    ({"pricing", "board"}, "pricing change goes to the board"),
    ({"two", "engineers"}, "hire two engineers next quarter"),
    ({"importer", "drop"}, "drop the legacy importer"),
]
ACTION_KEYS = [
    ("me", {"pricing", "options"}, "me: draft pricing options by Friday"),
    ("them", {"forecast"}, "them: send updated forecast"),
    ("me", {"board", "slot"}, "me: book the board slot"),
    ("them", {"job", "descriptions"}, "them: write the job descriptions"),
    ("me", {"deprecation"}, "me: email deprecation notice"),
]

QA = [  # (question, expected keyword | None for unanswerable)
    ("when do we ship the mobile release?", "thursday"),
    ("what did we decide about the export button?", "move"),
    ("who is writing the job descriptions?", "job description"),
    ("how many engineers are we hiring?", "two"),
    ("what will I draft by Friday?", "pricing"),
    ("what happens to the legacy importer?", "drop"),
    ("what will they send before the meeting?", "forecast"),
    ("what did we decide about the office move?", None),
    ("what is the marketing budget for next year?", None),
    ("what was said about the vacation policy?", None),
]

_WORD = re.compile(r"[a-z0-9']+")


def speak(text: str) -> None:
    cmd = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Volume = 100; $s.Speak('{text.replace(chr(39), chr(39) * 2)}')"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=True)


def wait_for(fn, timeout_s=180, every=4):
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(every)
    return None


def main() -> int:
    for probe, name in (
        ("/transcription/readiness", "transcription"),
        ("/assistant/readiness", "assistant"),
    ):
        r = httpx.get(f"{BASE}{probe}").json()
        if not r["ready"]:
            print(f"{name} not ready: {r.get('reason')}")
            return 1

    print("Recording the keyed meeting. Read [YOU say] lines aloud; Enter when done.\n")
    sid = httpx.post(f"{BASE}/sessions", json={"title": "assistant answer key T030"}).json()["id"]
    print(f"session: {sid}\n")
    time.sleep(2)
    for i, (side, line) in enumerate(SCRIPT, 1):
        if side == "B":
            print(f"  {i:2}. [speakers] {line}")
            speak(line)
            time.sleep(0.8)
        else:
            input(f"  {i:2}. [YOU say ] {line!r}   — Enter when done ")
            time.sleep(0.5)

    print("\nLetting the last chunks land (~15 s)...")
    time.sleep(15)
    httpx.post(f"{BASE}/sessions/{sid}/stop")
    print("Waiting for the transcript to finalise...")
    ok = wait_for(
        lambda: httpx.get(f"{BASE}/sessions/{sid}/transcript").json()["state"] == "completed"
    )
    if not ok:
        print("transcript did not finalise")
        return 1

    # ---- summary (SC-001) ----
    print("Summarizing...")
    httpx.post(f"{BASE}/sessions/{sid}/summarize")
    s = wait_for(
        lambda: (lambda x: x if x["state"] != "pending" else None)(
            httpx.get(f"{BASE}/sessions/{sid}/summary").json()
        ),
        timeout_s=300,
    )
    if not s or s["state"] != "completed":
        print(f"summary failed: {s and s.get('failure_reason')}")
        return 1
    c = s["content"]
    blob = " ".join(
        [c["overview"]]
        + [i["text"] for i in c["key_points"]]
        + [i["text"] for i in c["decisions"]]
        + [a["text"] for a in c["action_items"]]
    ).lower()
    print("\n== SUMMARY SCORING (SC-001) ==")
    dec_hits = 0
    for words, label in DECISION_KEYS:
        hit = all(w in blob for w in words)
        dec_hits += hit
        print(f"  decision {'OK  ' if hit else 'MISS'} {label}")
    act_hits = owner_ok = 0
    for owner, words, label in ACTION_KEYS:
        match = next(
            (a for a in c["action_items"] if all(w in a["text"].lower() for w in words)), None
        )
        in_blob = all(w in blob for w in words)
        act_hits += bool(match) or in_blob
        if match:
            owner_ok += match["owner"] == owner
        state = "OK  " if match else ("blob" if in_blob else "MISS")
        if match:
            oa = " owner=" + ("OK" if match["owner"] == owner else match["owner"])
        else:
            oa = " owner=-"
        print(f"  action   {state} {label}{oa}")
    total = dec_hits + act_hits
    print(f"  captured: {total}/10  (PASS >= 9)   owners correct: {owner_ok}/{act_hits or 1}")

    # ---- Q&A (SC-003) ----
    cid = httpx.post(f"{BASE}/conversations", json={"session_ids": [sid]}).json()["id"]
    print(f"\n== Q&A SCORING (SC-003) ==  conversation {cid}")
    ans_ok = dec_ok = 0
    for q, expect in QA:
        httpx.post(f"{BASE}/conversations/{cid}/ask", json={"question": q}, timeout=30)
        turn = wait_for(
            lambda: (lambda t: t if t["state"] != "streaming" else None)(
                httpx.get(f"{BASE}/conversations/{cid}").json()["turns"][-1]
            ),
            timeout_s=120,
        )
        if turn is None:
            print(f"  TIMEOUT  {q}")
            continue
        a, st, cits = turn["answer"].lower(), turn["state"], turn["citations"]
        if expect is None:
            good = st == "declined"
            dec_ok += good
            print(f"  {'DECLINED-OK' if good else 'FAIL(' + st + ')':14} {q}")
        else:
            good = st == "completed" and expect in a and len(cits) >= 1
            ans_ok += good
            why = "" if good else f"  [state={st} cits={len(cits)} ans={a[:60]!r}]"
            print(f"  {'OK+cit' if good else 'FAIL':14} {q}{why}")
    print(f"\n  answerable correct-with-citation: {ans_ok}/7  (PASS >= 6.3 -> 7 or 6)")
    print(f"  unanswerable declined:            {dec_ok}/3  (PASS 3/3)")
    print(f"\nsession {sid} — copy these numbers into tests/manual/assistant_answer_key.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
