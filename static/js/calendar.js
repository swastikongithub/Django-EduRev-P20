// Resource calendar: select free time by dragging (pointer) or tapping start then end (touch),
// keep the booking form and the grid in sync, and explain unavailable blocks on demand.
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const hm = (iso) => iso.slice(11, 16);
  const minutes = (a, b) => Math.round((new Date(b) - new Date(a)) / 60000);
  const fmtDur = (m) => (m >= 60 ? Math.floor(m / 60) + " h" + (m % 60 ? " " + (m % 60) + " min" : "") : m + " min");
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  document.documentElement.classList.toggle("is-touch", coarse);

  let anchor = null; // first chosen cell
  let dragging = false;

  function cellsOf(col) { return $$(".cal__cell", col); }

  // Contiguous free cells between two cells of the same column, or null if anything blocks.
  function range(a, b) {
    if (!a || !b || a.parentElement !== b.parentElement) return null;
    const col = a.parentElement;
    const kids = Array.from(col.children);
    let i = kids.indexOf(a), j = kids.indexOf(b);
    if (i > j) [i, j] = [j, i];
    const span = kids.slice(i, j + 1);
    if (span.some((el) => !el.classList.contains("cal__cell"))) return null;
    return span;
  }

  function clear() { $$(".cal__cell.is-selected").forEach((c) => c.classList.remove("is-selected", "is-first", "is-last")); }

  function paint(span) {
    clear();
    if (!span || !span.length) return;
    span.forEach((c) => c.classList.add("is-selected"));
    span[0].classList.add("is-first");
    span[span.length - 1].classList.add("is-last");
  }

  function toForm(span) {
    const form = $("[data-bookform]");
    if (!form || !span || !span.length) return;
    const start = span[0].dataset.start, end = span[span.length - 1].dataset.end;
    const day = span[0].parentElement.dataset.day;
    form.querySelector("[data-bind=date]").value = day;
    setSelect(form.querySelector("[data-bind=start]"), hm(start));
    setSelect(form.querySelector("[data-bind=end]"), hm(end));
    summary(day, hm(start), hm(end), minutes(start, end));
  }

  function setSelect(sel, value) {
    if (!sel) return;
    if (![...sel.options].some((o) => o.value === value || o.text === value)) sel.add(new Option(value, value));
    sel.value = value;
  }

  function summary(day, s, e, mins) {
    const box = $("[data-selection]");
    if (!box) return;
    $(".selection__empty", box).hidden = true;
    $(".selection__chosen", box).hidden = false;
    const d = new Date(day + "T00:00:00");
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const diff = Math.round((d - today) / 86400000);
    $("[data-sel-day]", box).textContent = diff === 0 ? "Today" : diff === 1 ? "Tomorrow" : d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
    $("[data-sel-time]", box).textContent = s + "–" + e;
    $("[data-sel-dur]", box).textContent = mins > 0 ? fmtDur(mins) : "";
    box.classList.remove("is-pulse"); void box.offsetWidth; box.classList.add("is-pulse");
    const label = $("[data-submit-label] span");
    if (label) label.textContent = label.textContent.replace(/\s\d{2}:\d{2}–\d{2}:\d{2}$/, "") + " " + s + "–" + e;
    const repeat = $("[data-repeat-link]");
    if (repeat) {
      const u = new URL(repeat.href, location.href);
      u.searchParams.set("date", day); u.searchParams.set("from", s); u.searchParams.set("to", e);
      repeat.href = u.pathname + u.search;
    }
  }

  // Form -> grid: highlight what the selects describe (if it is all free).
  function fromForm() {
    const form = $("[data-bookform]");
    if (!form) return;
    const day = form.querySelector("[data-bind=date]").value;
    const s = form.querySelector("[data-bind=start]").value;
    const e = form.querySelector("[data-bind=end]").value;
    const col = $(`.cal__col[data-day="${day}"]`);
    if (!col || !s || !e) { clear(); return; }
    const cells = cellsOf(col).filter((c) => c.dataset.hm >= s && c.dataset.hmEnd <= e);
    const span = cells.length ? range(cells[0], cells[cells.length - 1]) : null;
    paint(span);
    if (s && e) summary(day, s, e, (parseInt(e) * 60 + +e.slice(3)) - (parseInt(s) * 60 + +s.slice(3)));
  }

  function why(text) {
    const panel = $("#book-panel");
    let box = $("#why");
    if (!box && panel) {
      box = document.createElement("div");
      box.id = "why";
      box.className = "notice notice--warn why";
      box.setAttribute("role", "status");
      panel.querySelector(".bookpanel__head").after(box);
    }
    if (box) {
      box.innerHTML = "";
      const strong = document.createElement("strong");
      strong.textContent = "That time isn't available";
      const span = document.createElement("span");
      span.textContent = text;
      box.append(strong, span);
    }
  }

  function bind(root) {
    const cal = $("[data-calendar]", root);
    if (!cal || cal.dataset.bound) return;
    cal.dataset.bound = "1";

    cal.addEventListener("pointerdown", (e) => {
      const cell = e.target.closest(".cal__cell");
      if (!cell) return;
      if (coarse) return; // touch uses taps (click) so scrolling still works
      e.preventDefault();
      dragging = true;
      anchor = cell;
      paint([cell]);
    });
    cal.addEventListener("pointerover", (e) => {
      if (!dragging) return;
      const cell = e.target.closest(".cal__cell");
      const span = range(anchor, cell);
      if (span) paint(span);
    });
    window.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = false;
      const span = $$(".cal__cell.is-selected");
      if (span.length) { toForm(span); $("#why")?.remove(); }
    });

    cal.addEventListener("click", (e) => {
      const cell = e.target.closest(".cal__cell");
      const block = e.target.closest(".cal__block");
      if (block) { why(block.dataset.why); return; }
      if (!cell) return;
      if (!coarse && !e.shiftKey && e.detail !== 0) return; // pointer drag already handled it
      // Touch (or keyboard): first tap = start; second tap later in the same day = end.
      if (anchor && anchor !== cell && (e.shiftKey || coarse) && range(anchor, cell)) {
        const span = range(anchor, cell);
        paint(span); toForm(span); anchor = null;
      } else {
        anchor = cell; paint([cell]); toForm([cell]);
      }
      $("#why")?.remove();
    });
    cal.addEventListener("keydown", (e) => {
      const block = e.target.closest(".cal__block");
      if (block && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); why(block.dataset.why); }
    });

    // The red "now" line on today's column.
    const nowEl = $("[data-now]", cal);
    if (nowEl) {
      const first = parseInt(cal.dataset.firstHour, 10), hours = parseInt(cal.dataset.hours, 10);
      const place = () => {
        const d = new Date();
        const pos = ((d.getHours() + d.getMinutes() / 60) - first) / hours;
        nowEl.hidden = pos < 0 || pos > 1;
        nowEl.style.top = (pos * 100).toFixed(2) + "%";
      };
      place(); setInterval(place, 60000);
    }
    fromForm();
  }

  document.addEventListener("change", (e) => { if (e.target.closest("[data-bookform]") && e.target.dataset.bind) fromForm(); });

  // Phones get the day view by default — a 7-column week is unreadable at 360 px.
  const wrap = $("#calendar");
  if (wrap && wrap.dataset.view === "week" && window.innerWidth < 700 && !/[?&]view=/.test(location.search) && window.htmx) {
    window.htmx.ajax("GET", location.pathname + "?view=day&date=" + (new URLSearchParams(location.search).get("date") || ""), { target: "#calendar", swap: "outerHTML" });
  }

  bind(document);
  document.addEventListener("htmx:afterSwap", (e) => {
    bind(document);
    if (e.detail.target && e.detail.target.id === "book-panel") fromForm();
  });
  document.addEventListener("htmx:afterSettle", () => bind(document));
})();
