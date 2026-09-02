// Summary pane (FR-007, FR-013): structured render (overview, key
// points, decisions, action items with owner/deadline), generate and
// re-summarize where the API allows, pending progress that never hides
// the readable current summary (the API's currency rule, mirrored).

import { api, friendly } from "../api.js";
import { clear, el } from "../dom.js";

export async function renderSummaryPane(panel, sessionId, state, ctx) {
  let current = null; // GET /summary result (may be pending or failed)
  let readable = null; // the completed SummaryResponse to render
  let readableIsPrevious = false;
  let versions = [];
  let error = null;
  let destroyed = false;
  let busy = false;

  async function load() {
    try {
      current = await api.getSummary(sessionId);
    } catch (e) {
      if (e.code === "summary_not_found") current = null;
    }
    try {
      versions = (await api.listSummaries(sessionId)).summaries;
    } catch {
      versions = [];
    }
    readable = current?.state === "completed" ? current : null;
    readableIsPrevious = false;
    if (!readable) {
      const done = versions
        .filter((v) => v.state === "completed")
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
      if (done) {
        try {
          readable = await api.getSummaryVersion(sessionId, done.id);
          readableIsPrevious = current != null; // pending/failed run on top
        } catch { /* keep empty */ }
      }
    }
    if (!destroyed) renderIfChanged();
  }

  function pendingRun() {
    if (current?.state === "pending") return current;
    return versions.find((v) => v.state === "pending") || null;
  }

  // Re-render only when displayed state actually changed — a needless
  // redraw destroys the reader's text selection mid-copy.
  let lastKey = null;

  function renderKey() {
    const session = ctx.getSession();
    const transcript = ctx.getTranscript();
    const p = pendingRun();
    return [
      current?.id, current?.state, current?.failure_reason,
      p ? p.task_state || p.state || "pending" : "",
      readable?.id, readableIsPrevious, error, busy,
      state.assistant?.ready, state.assistant?.status, state.assistant?.reason,
      session.status, transcript?.state, transcript?.final,
    ].join("|");
  }

  function renderIfChanged() {
    if (renderKey() !== lastKey) render();
  }

  async function request() {
    busy = true;
    error = null;
    render();
    try {
      await api.summarize(sessionId);
    } catch (e) {
      error = friendly(e);
    }
    busy = false;
    await load();
  }

  // ---- copy (plain text of the whole summary) ---------------------------

  function summaryText(c) {
    const lines = ["Overview", c.overview, ""];
    if (c.key_points?.length) {
      lines.push("Key points", ...c.key_points.map((i) => `- ${i.text}`), "");
    }
    if (c.decisions?.length) {
      lines.push("Decisions", ...c.decisions.map((i) => `- ${i.text}`), "");
    }
    if (c.action_items?.length) {
      lines.push("Action items", ...c.action_items.map((i) =>
        `- [${i.owner}] ${i.text}${i.deadline_text ? ` (${i.deadline_text})` : ""}`));
    }
    return lines.join("\n").trim() + "\n";
  }

  async function copySummary(btn) {
    const text = summaryText(readable.content);
    try {
      // writeText can hang (not just reject) in an unfocused document —
      // race it so the fallback and the feedback always happen.
      await Promise.race([
        navigator.clipboard.writeText(text),
        new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 800)),
      ]);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.append(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    btn.textContent = "✓";
    setTimeout(() => {
      btn.textContent = "⧉";
    }, 1500);
  }

  // ---- structured render ------------------------------------------------

  function citationChips(citations, counter) {
    return (citations || []).map((c) => {
      counter.n += 1;
      return el("button.cite", `[${counter.n}]`, {
        title: "jump to the cited transcript moment",
        onclick: () => ctx.onCitation(c),
      });
    });
  }

  function itemList(items, counter, extra) {
    return el("ul", items.map((it) =>
      el("li", it.text, " ", citationChips(it.citations, counter),
        extra ? extra(it) : null)));
  }

  function renderContent(content) {
    const counter = { n: 0 };
    const box = el("div.summary");
    box.append(el("h3", "Overview"), el("p", content.overview));
    if (content.key_points?.length) {
      box.append(el("h3", "Key points"), itemList(content.key_points, counter));
    }
    if (content.decisions?.length) {
      box.append(el("h3", "Decisions"), itemList(content.decisions, counter));
    }
    if (content.action_items?.length) {
      box.append(el("h3", "Action items"),
        el("ul", content.action_items.map((it) =>
          el("li",
            el("span.owner." + it.owner, it.owner), " ", it.text, " ",
            it.deadline_text ? el("span.deadline", `(${it.deadline_text})`) : null,
            " ", citationChips(it.citations, counter)))));
    }
    return box;
  }

  function render() {
    lastKey = renderKey();
    clear(panel);
    const head = el("div.panel-head", el("h2", "Summary"));
    panel.append(head);

    const pending = pendingRun();
    const session = ctx.getSession();
    const transcript = ctx.getTranscript();
    const assistantReady = !!state.assistant?.ready;
    const transcriptFinal = !!transcript && transcript.final &&
      transcript.state === "completed" && session.status !== "active";

    if (pending) {
      head.append(el("span.chip.warn", el("span.dot"),
        `generating (${pending.task_state || pending.state || "queued"})`));
      panel.append(el("div.progress-track", el("div.progress-fill.indeterminate")));
    } else if (assistantReady && transcriptFinal) {
      head.append(el("button" + (readable ? "" : ".primary"),
        readable ? "Re-summarize" : "Generate summary",
        { disabled: busy, onclick: request }));
    }
    if (readable?.content) {
      head.append(el("button.icon-btn", "⧉", {
        title: "Copy summary",
        "aria-label": "Copy summary",
        onclick: (ev) => copySummary(ev.currentTarget),
      }));
    }

    if (current?.state === "failed" && !pending) {
      panel.append(el("div.error-line",
        el("span.state-tag.critical", "failed"),
        ` ${current.failure_reason || "summary generation failed"} `,
        assistantReady && transcriptFinal
          ? el("button", "Retry", { disabled: busy, onclick: request })
          : null));
    }
    if (error) panel.append(el("div.error-line", error));

    if (state.assistant && !state.assistant.ready) {
      panel.append(el("div.remedy-line",
        `Assistant ${state.assistant.status === "not_installed" ? "not installed" : "not ready"}` +
        (state.assistant.reason ? ` — ${state.assistant.reason}` : "") +
        ". Summaries are unavailable until it is."));
    }

    if (readable?.content) {
      if (readableIsPrevious && pending) {
        panel.append(el("div.hint", "Previous summary — kept readable while the new one generates:"));
      } else if (readableIsPrevious) {
        panel.append(el("div.hint", "Showing the most recent completed summary."));
      }
      panel.append(renderContent(readable.content));
      if (readable.model) {
        panel.append(el("div.hint", `model: ${readable.model}`));
      }
    } else if (!pending && !current) {
      if (!assistantReady) {
        // remedy line above already explains
      } else if (!transcriptFinal) {
        panel.append(el("div.empty",
          session.status === "active"
            ? "Summary becomes available after the session ends."
            : "Summary needs a completed transcript first."));
      } else {
        panel.append(el("div.empty", "No summary yet."));
      }
    }
  }

  await load();

  return {
    destroy() {
      destroyed = true;
    },
    onPoll() {
      // Session/transcript state gates the buttons; a pending run needs
      // progress; both ride the 3 s poll — but only redraw on change,
      // so reading (and selecting text to copy) isn't disturbed.
      if (pendingRun()) load();
      else renderIfChanged();
    },
  };
}
