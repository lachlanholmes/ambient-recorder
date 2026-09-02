// WS helpers wrapping the two existing stream contracts exactly as
// documented (research R4) — no new semantics invented client-side.
//
// Transcript: caller loads a REST snapshot first, then tails with
// `?after=<last seq>`; reconnects reuse the cursor (the single source of
// truth per data-model.md), with 1 s → 10 s exponential backoff. The
// server replays gap-free after the cursor and closes after a terminal
// status frame.
//
// Answers: subscribe on ask; the server replays the in-flight turn's
// prefix, tails token frames, and closes after a terminal status — the
// caller then re-fetches the stored turn as the durable record.

const WS_BASE = (location.protocol === "https:" ? "wss://" : "ws://") + location.host;

export const TERMINAL_TRANSCRIPT = new Set(["completed", "failed", "interrupted_live"]);
export const TERMINAL_TURN = new Set([
  "completed", "ungrounded", "declined", "failed", "interrupted",
]);

export function tailTranscript({ sessionId, after = -1, onSegment, onStatus, onEnd }) {
  let cursor = after;
  let ws = null;
  let stopped = false;
  let terminal = false;
  let backoff = 1000;
  let timer = 0;

  function connect() {
    if (stopped) return;
    ws = new WebSocket(`${WS_BASE}/sessions/${sessionId}/transcript/stream?after=${cursor}`);
    ws.onopen = () => {
      backoff = 1000;
    };
    ws.onmessage = (ev) => {
      let frame;
      try {
        frame = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (frame.type === "segment") {
        if (frame.segment.seq <= cursor) return; // belt+braces dedupe
        cursor = frame.segment.seq;
        onSegment(frame.segment);
      } else if (frame.type === "status") {
        if (TERMINAL_TRANSCRIPT.has(frame.state)) terminal = true;
        onStatus(frame);
      }
    };
    ws.onclose = () => {
      if (stopped) return;
      if (terminal) {
        stopped = true;
        if (onEnd) onEnd();
        return;
      }
      // Not terminal: transient drop (or transcript not created yet, close
      // 4409 right after session start) — reconnect from the cursor.
      timer = setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 10000);
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch { /* already closed */ }
    };
  }

  connect();
  return {
    close() {
      stopped = true;
      clearTimeout(timer);
      try {
        ws && ws.close();
      } catch { /* already closed */ }
    },
    get cursor() {
      return cursor;
    },
  };
}

export function streamAnswer({ cid, turnSeq, onToken, onStatus, onEnd }) {
  const ws = new WebSocket(`${WS_BASE}/conversations/${cid}/stream`);
  let terminal = false;
  ws.onmessage = (ev) => {
    let frame;
    try {
      frame = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (turnSeq !== undefined && frame.turn_seq !== undefined && frame.turn_seq !== turnSeq) return;
    if (frame.type === "token") onToken(frame.text);
    else if (frame.type === "status") {
      if (TERMINAL_TURN.has(frame.state)) terminal = true;
      onStatus(frame);
    }
  };
  ws.onclose = () => {
    if (onEnd) onEnd(terminal);
  };
  return {
    close() {
      try {
        ws.close();
      } catch { /* already closed */ }
    },
  };
}
