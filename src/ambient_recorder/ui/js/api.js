// Thin typed fetch wrappers over the recorder's REST contracts —
// exactly the endpoints in specs/004-web-ui/contracts/ui-consumption.md.
// Every non-2xx response carries the error envelope
// {error: {code, message, detail}}; it surfaces to callers as ApiError.

export class ApiError extends Error {
  constructor(status, code, message, detail = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function req(method, path, body) {
  const opts = { method };
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null; // non-JSON body (shouldn't happen on API routes)
    }
  }
  if (!res.ok) {
    const err = (data && data.error) || {};
    throw new ApiError(
      res.status,
      err.code || "http_error",
      err.message || `HTTP ${res.status}`,
      err.detail || {},
    );
  }
  return data;
}

const get = (p) => req("GET", p);
const post = (p, body) => req("POST", p, body);

export const api = {
  // 001 — health, devices, sessions
  health: () => get("/health"),
  devices: () => get("/devices"),
  createSession: (title) => post("/sessions", { title: title || null }),
  stopSession: (id) => post(`/sessions/${id}/stop`),
  listSessions: () => get("/sessions"),
  getSession: (id) => get(`/sessions/${id}`),
  // 002 — transcription
  transcriptionReadiness: () => get("/transcription/readiness"),
  getTranscript: (id, after = -1) => get(`/sessions/${id}/transcript?after=${after}`),
  listTranscripts: (id) => get(`/sessions/${id}/transcripts`),
  getTranscriptVersion: (id, tid, after = -1) =>
    get(`/sessions/${id}/transcripts/${tid}?after=${after}`),
  transcribe: (id) => post(`/sessions/${id}/transcribe`),
  // 003 — assistant
  assistantReadiness: () => get("/assistant/readiness"),
  summarize: (id) => post(`/sessions/${id}/summarize`),
  getSummary: (id) => get(`/sessions/${id}/summary`),
  listSummaries: (id) => get(`/sessions/${id}/summaries`),
  getSummaryVersion: (id, sid) => get(`/sessions/${id}/summaries/${sid}`),
  createConversation: (sessionId) => post("/conversations", { session_ids: [sessionId] }),
  listConversations: (sessionId) =>
    get(sessionId ? `/conversations?session_id=${encodeURIComponent(sessionId)}` : "/conversations"),
  getConversation: (cid) => get(`/conversations/${cid}`),
  ask: (cid, question) => post(`/conversations/${cid}/ask`, { question }),
};

// Plain-language rendering for API refusals (FR-004): friendly text per
// error code, falling back to the envelope's own message.
const FRIENDLY = {
  device_missing: (e) =>
    `Can't record: audio device missing (${(e.detail.missing || []).join(", ") || "unknown"}). ` +
    "Reconnect or enable the device, then try again.",
  disk_space_low: (e) =>
    `Can't record: disk space is low (${e.detail.free_mb} MB free, ` +
    `${e.detail.required_mb} MB required). Free some space first.`,
  session_already_active: () => "A session is already recording — stop it first.",
  session_not_active: () => "This session is not recording.",
  session_still_active: () => "The session is still recording — stop it before transcribing.",
  transcription_already_running: () => "A transcription is already running for this session.",
  transcription_not_ready: (e) =>
    `Transcription isn't ready: ${e.detail.reason || e.message}`,
  assistant_not_ready: (e) => `The assistant isn't ready: ${e.detail.reason || e.message}`,
  transcript_not_final: () =>
    "The transcript isn't final yet — wait for it to complete (or transcribe the session) first.",
};

export function friendly(err) {
  if (!(err instanceof ApiError)) return err.message || String(err);
  const f = FRIENDLY[err.code];
  return f ? f(err) : err.message;
}
