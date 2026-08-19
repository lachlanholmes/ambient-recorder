"""Tail a session's live transcript stream (T024).

Usage: python tests/manual/ws_tail.py <session-id> [--after N]
Prints each segment as it arrives with arrival lag (wall-clock now minus
session start + segment end) so SC-002 can be eyeballed, plus status frames.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime

import httpx
import websockets

BASE = "http://127.0.0.1:8377"


async def main(session_id: str, after: int) -> None:
    s = httpx.get(f"{BASE}/sessions/{session_id}").json()
    started = datetime.fromisoformat(s["started_at"].replace("Z", "+00:00")).timestamp()
    url = f"ws://127.0.0.1:8377/sessions/{session_id}/transcript/stream?after={after}"
    async with websockets.connect(url) as ws:
        async for raw in ws:
            m = json.loads(raw)
            if m["type"] == "segment":
                seg = m["segment"]
                lag = time.time() - (started + seg["end_s"])
                print(
                    f"#{seg['seq']:>4} [{seg['start_s']:7.1f}-{seg['end_s']:7.1f}] "
                    f"{seg['source']:>4}  lag={lag:5.1f}s  {seg['text']}",
                    flush=True,
                )
            else:
                print(
                    f"--- status: {m['state']} lag={m.get('lag_s')} final={m.get('final')}",
                    flush=True,
                )


if __name__ == "__main__":
    sid = sys.argv[1]
    after = int(sys.argv[sys.argv.index("--after") + 1]) if "--after" in sys.argv else -1
    asyncio.run(main(sid, after))
