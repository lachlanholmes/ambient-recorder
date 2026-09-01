"""Tail a conversation's answer stream (003).

Usage: python tests/manual/answer_tail.py <conversation-id>
Prints tokens as they stream, then the terminal status with citations.
"""

from __future__ import annotations

import asyncio
import json
import sys

import websockets


async def main(cid: str) -> None:
    url = f"ws://127.0.0.1:8377/conversations/{cid}/stream"
    async with websockets.connect(url) as ws:
        async for raw in ws:
            m = json.loads(raw)
            if m["type"] == "token":
                print(m["text"], end="", flush=True)
            else:
                print(f"\n--- {m['state']}", flush=True)
                if m.get("citations"):
                    for c in m["citations"]:
                        mm, ss = divmod(int(c["start_s"]), 60)
                        print(f"    [{c['seq']}] at {mm:02d}:{ss:02d}", flush=True)
                if m.get("watermark"):
                    print(f"    watermark: {m['watermark']}", flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
