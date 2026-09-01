// Chat pane (FR-009/FR-010): list/create/continue conversations,
// streamed answers via the answer-stream contract, distinct terminal
// states (completed, declined, ungrounded, failed, interrupted), live
// asks with the transcript watermark the answer saw, and the honest
// assistant-unavailable state with everything else functional.

import { api, friendly } from "../api.js";
import { clear, el } from "../dom.js";
import { streamAnswer } from "../streams.js";

const STATE_TAG = {
  declined: ["idle", "declined"],
  ungrounded: ["warn", "unverified"],
  failed: ["critical", "failed"],
  interrupted: ["warn", "interrupted — partial answer"],
};

export async function renderChatPane(panel, sessionId, state, ctx) {
  let conversations = [];
  let openId = null;
  let detail = null; // ConversationDetail of the open conversation
  let stream = null;
  let streamNode = null; // text node receiving live tokens
  let streamSeq = null;
  let error = null;
  let busy = false;
  let destroyed = false;

  async function loadConversations() {
    try {
      conversations = (await api.listConversations(sessionId)).conversations
        .slice()
        .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    } catch {
      conversations = [];
    }
    if (!openId && conversations.length) {
      openId = conversations[conversations.length - 1].id;
    }
  }

  async function loadDetail() {
    if (!openId) {
      detail = null;
      return;
    }
    try {
      detail = await api.getConversation(openId);
    } catch {
      detail = null;
      return;
    }
    const inflight = detail.turns.find((t) => t.state === "streaming");
    if (inflight && !stream) openStream(inflight.seq);
  }

  function openStream(seq) {
    // Prefix replay + tail (WS contract): safe for turns already partway.
    streamSeq = seq;
    stream = streamAnswer({
      cid: openId,
      turnSeq: seq,
      onToken: (text) => {
        if (streamNode) streamNode.nodeValue += text;
      },
      onStatus: () => { /* terminal handling happens in onEnd */ },
      onEnd: async () => {
        stream = null;
        streamSeq = null;
        streamNode = null;
        // The stored turn is the durable record — re-fetch it (R4).
        await loadDetail();
        if (!destroyed) render();
      },
    });
  }

  async function newConversation() {
    busy = true;
    error = null;
    render();
    try {
      const conv = await api.createConversation(sessionId);
      openId = conv.id;
      await loadConversations();
      await loadDetail();
    } catch (e) {
      error = friendly(e);
    }
    busy = false;
    render();
  }

  async function ask(question) {
    question = question.trim();
    if (!question || busy) return;
    busy = true;
    error = null;
    render();
    try {
      if (!openId) {
        const conv = await api.createConversation(sessionId);
        openId = conv.id;
        conversations.push(conv);
        detail = { ...conv, turns: [] };
      }
      const turn = await api.ask(openId, question);
      detail.turns.push(turn);
      busy = false;
      render();
      openStream(turn.seq);
    } catch (e) {
      error = friendly(e);
      busy = false;
      render();
    }
  }

  // ---- rendering --------------------------------------------------------

  function citationChips(citations) {
    let n = 0;
    return (citations || []).map((c) => {
      n += 1;
      return el("button.cite", `[${n}]`, {
        title: "jump to the cited transcript moment",
        onclick: () => ctx.onCitation(c),
      });
    });
  }

  function watermarkText(w) {
    if (!w) return null;
    if (w === "final") return "answered against the final transcript";
    const m = w.match(/^live:(\d+)$/);
    if (m) return `answered against the live transcript (through segment ${m[1]})`;
    return `watermark: ${w}`;
  }

  function turnNodes(turn) {
    const nodes = [el("div.turn-q", turn.question)];
    const a = el("div.turn-a");
    const tag = STATE_TAG[turn.state];
    if (tag) a.append(el(`span.state-tag.${tag[0]}`, tag[1]), " ");
    if (turn.state === "declined") a.classList.add("declined");
    if (turn.state === "failed") a.classList.add("failed");

    if (turn.state === "streaming") {
      const text = document.createTextNode(turn.answer || "");
      if (turn.seq === streamSeq) streamNode = text;
      a.append(text, el("span.caret", " "));
    } else {
      a.append(turn.answer ||
        (turn.state === "declined" ? "That wasn't discussed in this meeting." :
         turn.state === "failed" ? "The assistant couldn't answer this question." : ""));
      if (turn.citations?.length) {
        a.append(el("div", citationChips(turn.citations)));
      }
      if (turn.state === "failed") {
        a.append(" ", el("button", "Retry", {
          disabled: busy || !state.assistant?.ready,
          onclick: () => ask(turn.question),
        }));
      }
    }
    const wm = watermarkText(turn.watermark);
    if (wm) a.append(el("div.turn-meta", wm));
    nodes.push(a);
    return nodes;
  }

  function render() {
    clear(panel);
    streamNode = null;
    const head = el("div.panel-head", el("h2", "Assistant"));
    panel.append(head);

    // Conversation list / create / continue (FR-009).
    if (conversations.length) {
      panel.append(el("div.conv-list",
        conversations.map((c, i) =>
          el("button" + (c.id === openId ? ".active" : ""), `#${i + 1}`, {
            title: new Date(c.created_at).toLocaleString(),
            onclick: async () => {
              if (openId === c.id) return;
              stream?.close();
              stream = null;
              openId = c.id;
              await loadDetail();
              render();
            },
          })),
        el("button", "+ New", {
          disabled: busy || !state.assistant?.ready,
          onclick: newConversation,
        })));
    }

    const ready = !!state.assistant?.ready;
    if (state.assistant && !ready) {
      panel.append(el("div.remedy-line",
        `Assistant ${state.assistant.status === "not_installed" ? "not installed" : "not ready"}` +
        (state.assistant.reason ? ` — ${state.assistant.reason}` : "") +
        ". Past conversations stay readable; asking needs the assistant."));
    }

    const turnsBox = el("div.chat-turns");
    if (detail?.turns?.length) {
      for (const t of detail.turns) turnsBox.append(...turnNodes(t));
    } else if (ready) {
      turnsBox.append(el("div.empty", "Ask the assistant about this session."));
    }
    panel.append(turnsBox);
    turnsBox.scrollTop = turnsBox.scrollHeight;

    if (ready) {
      const input = el("input", { type: "text", placeholder: "Ask about this session…",
        maxlength: "2000" });
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          ask(input.value);
          input.value = "";
        }
      });
      panel.append(el("div.ask-row", input,
        el("button.primary", "Ask", {
          disabled: busy,
          onclick: () => {
            ask(input.value);
            input.value = "";
          },
        })));
      if (state.health?.active_session_id === sessionId) {
        panel.append(el("div.hint",
          "Live meeting — answers use the transcript captured so far."));
      }
    }
    if (error) panel.append(el("div.error-line", error));
  }

  await loadConversations();
  await loadDetail();
  render();

  let readyBefore = !!state.assistant?.ready;
  return {
    destroy() {
      destroyed = true;
      stream?.close();
    },
    async onPoll() {
      // Multi-tab: pick up turns asked elsewhere; readiness flips update
      // the affordances (R8, FR-010).
      const readyNow = !!state.assistant?.ready;
      if (openId && !stream) {
        const before = detail?.turns?.length ?? -1;
        const stateSig = detail?.turns?.map((t) => t.state).join();
        await loadDetail();
        if (destroyed) return;
        if ((detail?.turns?.length ?? -1) !== before ||
            detail?.turns?.map((t) => t.state).join() !== stateSig ||
            readyNow !== readyBefore) {
          render();
        }
      } else if (readyNow !== readyBefore) {
        render();
      }
      readyBefore = readyNow;
    },
  };
}
