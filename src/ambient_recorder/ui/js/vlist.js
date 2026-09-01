// Hand-rolled windowed list (research R3, NFR-003): only the visible
// rows ± overscan exist in the DOM, absolutely positioned inside a
// spacer sized from estimated-then-measured row heights. Serves stored
// and live transcripts alike: append() extends the tail, and auto-follow
// sticks to the bottom until the user scrolls up (re-engaging when they
// scroll back down).

export function createVList(scroller, { render, overscan = 100, estimate = 30 }) {
  const spacer = document.createElement("div");
  spacer.className = "vlist-spacer";
  scroller.appendChild(spacer);

  let items = [];
  let heights = []; // per-row: measured once rendered, `estimate` before
  let offsets = [0]; // prefix sums; offsets[i] = top of row i
  let followMode = false; // live views enable; stored views leave off
  let following = false;
  let highlightIndex = -1;
  let raf = 0;
  let destroyed = false;
  let onFollowChange = null;
  let suppressScroll = false;

  function rebuildOffsets(from = 0) {
    offsets.length = items.length + 1;
    if (from === 0) offsets[0] = 0;
    for (let i = from; i < items.length; i++) offsets[i + 1] = offsets[i] + heights[i];
    spacer.style.height = `${offsets[items.length]}px`;
  }

  function indexAt(y) {
    let lo = 0;
    let hi = items.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (offsets[mid + 1] <= y) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  function renderWindow() {
    raf = 0;
    if (destroyed) return;
    spacer.textContent = "";
    if (!items.length) return;
    const top = scroller.scrollTop;
    const bottom = top + scroller.clientHeight;
    const s = Math.max(0, indexAt(top) - overscan);
    const e = Math.min(items.length, indexAt(Math.max(0, bottom - 1)) + overscan + 1);

    const nodes = [];
    for (let i = s; i < e; i++) {
      const node = render(items[i], i);
      node.style.position = "absolute";
      node.style.top = `${offsets[i]}px`;
      node.style.left = "0";
      node.style.right = "0";
      if (i === highlightIndex) node.classList.add("cited");
      spacer.appendChild(node);
      nodes.push(node);
    }
    // Measure after all appends (one reflow), then correct estimates.
    let changed = false;
    for (let i = s; i < e; i++) {
      const h = nodes[i - s].offsetHeight;
      if (h && Math.abs(h - heights[i]) > 0.5) {
        heights[i] = h;
        changed = true;
      }
    }
    if (changed) {
      rebuildOffsets(s);
      for (let i = s; i < e; i++) nodes[i - s].style.top = `${offsets[i]}px`;
    }
  }

  function schedule() {
    if (!raf) raf = requestAnimationFrame(renderWindow);
  }

  function nearBottom() {
    return scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 40;
  }

  function scrollToBottom() {
    suppressScroll = true;
    scroller.scrollTop = scroller.scrollHeight;
    schedule();
  }

  function setFollowing(v) {
    if (following === v) return;
    following = v;
    if (onFollowChange) onFollowChange(v);
  }

  function onScroll() {
    if (suppressScroll) {
      suppressScroll = false;
    } else if (followMode) {
      // User-driven scroll: disengage when they scroll up, re-engage at bottom.
      setFollowing(nearBottom());
    }
    schedule();
  }

  scroller.addEventListener("scroll", onScroll);
  const ro = new ResizeObserver(schedule);
  ro.observe(scroller);

  return {
    setItems(next) {
      items = next.slice();
      heights = items.map((_, i) => heights[i] && i < heights.length ? heights[i] : estimate);
      heights.length = items.length;
      for (let i = 0; i < items.length; i++) if (!heights[i]) heights[i] = estimate;
      rebuildOffsets(0);
      schedule();
      if (followMode && following) scrollToBottom();
    },
    append(newItems) {
      if (!newItems.length) return;
      const from = items.length;
      items.push(...newItems);
      for (let i = 0; i < newItems.length; i++) heights.push(estimate);
      rebuildOffsets(from);
      schedule();
      if (followMode && following) scrollToBottom();
    },
    get length() {
      return items.length;
    },
    setFollowMode(enabled) {
      followMode = enabled;
      if (enabled) {
        setFollowing(true);
        scrollToBottom();
      } else {
        setFollowing(false);
      }
    },
    isFollowing() {
      return followMode && following;
    },
    set onFollow(cb) {
      onFollowChange = cb;
    },
    refollow() {
      if (followMode) {
        setFollowing(true);
        scrollToBottom();
      }
    },
    scrollToIndex(i, { highlight = true } = {}) {
      if (i < 0 || i >= items.length) return;
      if (followMode) setFollowing(false);
      if (highlight) highlightIndex = i;
      // Estimates may be off for far targets: position, measure, correct once.
      suppressScroll = true;
      scroller.scrollTop = Math.max(0, offsets[i] - scroller.clientHeight / 3);
      renderWindow();
      suppressScroll = true;
      scroller.scrollTop = Math.max(0, offsets[i] - scroller.clientHeight / 3);
      schedule();
    },
    redraw: schedule,
    destroy() {
      destroyed = true;
      if (raf) cancelAnimationFrame(raf);
      ro.disconnect();
      scroller.removeEventListener("scroll", onScroll);
      spacer.remove();
    },
  };
}
