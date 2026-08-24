"""WS /sessions/{id}/transcript/stream?after=<seq> — contracts/rest-api.md.

Replay stored segments with seq > after, then tail the in-process stream.
Guarantee: replay + tail == exactly the segments after `after`, each once.
Status frame on connect, on change, and at least every 5 s while
live/finalising; the socket closes after a terminal status.
"""

from __future__ import annotations

import asyncio
import queue

from fastapi import APIRouter, WebSocket
from starlette.concurrency import run_in_threadpool

from ambient_recorder.models.assistant import TokenFrame, TurnState, TurnStatusFrame
from ambient_recorder.models.transcript import SegmentFrame, StatusFrame, TranscriptState

router = APIRouter()

_TERMINAL = {TranscriptState.COMPLETED, TranscriptState.FAILED, TranscriptState.INTERRUPTED_LIVE}
_TURN_TERMINAL = {TurnState.COMPLETED, TurnState.UNGROUNDED, TurnState.DECLINED,
                  TurnState.FAILED, TurnState.INTERRUPTED}
_HEARTBEAT_S = 5.0


@router.websocket("/sessions/{session_id}/transcript/stream")
async def transcript_stream(ws: WebSocket, session_id: str, after: int = -1):
    app = ws.scope["app"]
    store, meta, stream = app.state.transcripts, app.state.metadata, app.state.segment_stream

    if await run_in_threadpool(meta.get_session, session_id) is None:
        await ws.close(code=4404)
        return
    t = await run_in_threadpool(store.current_transcript, session_id)
    if t is None:
        t = await run_in_threadpool(store.pending_transcript, session_id)
    if t is None:
        await ws.close(code=4409)
        return
    await ws.accept()

    # Subscribe BEFORE replay so nothing produced during replay is missed;
    # dedupe by seq to keep the guarantee exact.
    sub = stream.subscribe(t.id)
    try:
        last_seq = after
        for seg in await run_in_threadpool(store.segments_after, t.id, after):
            await ws.send_text(SegmentFrame(segment=seg).model_dump_json())
            last_seq = seg.seq

        current = await run_in_threadpool(store.get_transcript, t.id)
        job = await run_in_threadpool(store.get_job, t.id)
        state = current.state if current else t.state
        await ws.send_text(
            StatusFrame(
                state=state, lag_s=job.lag_s if job else None, final=bool(current and current.final)
            ).model_dump_json()
        )
        if state in _TERMINAL:
            await ws.close()
            return

        while True:
            try:
                frame = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: sub.get(timeout=_HEARTBEAT_S)
                )
            except queue.Empty:
                cur = await run_in_threadpool(store.get_transcript, t.id)
                job = await run_in_threadpool(store.get_job, t.id)
                await ws.send_text(
                    StatusFrame(
                        state=cur.state, lag_s=job.lag_s if job else None, final=cur.final
                    ).model_dump_json()
                )
                if cur.state in _TERMINAL:
                    await ws.close()
                    return
                continue
            if frame is None:  # stream closed by publisher (terminal or overflow)
                cur = await run_in_threadpool(store.get_transcript, t.id)
                await ws.send_text(
                    StatusFrame(state=cur.state, lag_s=0.0, final=cur.final).model_dump_json()
                )
                await ws.close()
                return
            if isinstance(frame, SegmentFrame):
                if frame.segment.seq <= last_seq:
                    continue  # already replayed
                last_seq = frame.segment.seq
            await ws.send_text(frame.model_dump_json())
            if isinstance(frame, StatusFrame) and frame.state in _TERMINAL:
                await ws.close()
                return
    except Exception:  # noqa: BLE001 — client went away or send failed
        pass
    finally:
        stream.unsubscribe(sub)


@router.websocket("/conversations/{cid}/stream")
async def answer_stream(ws: WebSocket, cid: str):
    """Contracts/003: replay in-flight turn's prefix, tail tokens, close on
    terminal status. Flat path by design — conversations are top-level."""
    app = ws.scope["app"]
    astore, stream = app.state.assistant_store, app.state.segment_stream

    conv = await run_in_threadpool(astore.get_conversation, cid)
    if conv is None:
        await ws.close(code=4404)
        return
    await ws.accept()

    sub = stream.subscribe(cid)
    try:
        turns = conv.turns
        inflight = next((t for t in turns if t.state == TurnState.STREAMING), None)
        if inflight is None:
            if turns:
                last = turns[-1]
                await ws.send_text(TurnStatusFrame(
                    turn_seq=last.seq, state=last.state, citations=last.citations,
                    watermark=last.watermark).model_dump_json())
            await ws.close()
            return
        if inflight.answer:
            await ws.send_text(TokenFrame(turn_seq=inflight.seq,
                                          text=inflight.answer).model_dump_json())
        while True:
            try:
                frame = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: sub.get(timeout=_HEARTBEAT_S)
                )
            except queue.Empty:
                turn = await run_in_threadpool(astore.get_turn, inflight.id)
                if turn is not None and turn.state in _TURN_TERMINAL:
                    await ws.send_text(TurnStatusFrame(
                        turn_seq=turn.seq, state=turn.state, citations=turn.citations,
                        watermark=turn.watermark).model_dump_json())
                    await ws.close()
                    return
                continue
            if frame is None:  # publisher closed the stream
                turn = await run_in_threadpool(astore.get_turn, inflight.id)
                if turn is not None:
                    await ws.send_text(TurnStatusFrame(
                        turn_seq=turn.seq, state=turn.state, citations=turn.citations,
                        watermark=turn.watermark).model_dump_json())
                await ws.close()
                return
            await ws.send_text(frame.model_dump_json())
            if isinstance(frame, TurnStatusFrame) and frame.state in _TURN_TERMINAL:
                await ws.close()
                return
    except Exception:  # noqa: BLE001 — client went away
        pass
    finally:
        stream.unsubscribe(sub)
