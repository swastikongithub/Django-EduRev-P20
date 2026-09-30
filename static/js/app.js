// LPU Reserve — small progressive-enhancement runtime. Every page works without it.
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  // ── Theme toggle ──────────────────────────────────────────────────────
  function currentTheme() {
    const set = document.documentElement.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-theme-toggle]");
    if (!btn) return;
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("lpr-theme", next); } catch (err) { /* ignore */ }
  });

  // ── "/" focuses search (like the UMS command search, but instant) ────
  document.addEventListener("keydown", (e) => {
    if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (/INPUT|TEXTAREA|SELECT/.test(tag) || document.activeElement.isContentEditable) return;
    const box = $("[data-cmdk]");
    if (box && box.offsetParent !== null) { e.preventDefault(); box.focus(); box.select(); }
  });

  // ── Toasts ───────────────────────────────────────────────────────────
  const ICON = { success: "circle-check", error: "circle-x", warning: "triangle-alert", info: "info" };
  const spriteUrl = document.body.dataset.sprite || "/static/img/icons.svg";
  window.toast = function (message, tone = "info") {
    const wrap = $("#toasts");
    if (!wrap) return;
    const el = document.createElement("div");
    el.className = "toast toast--" + tone;
    el.setAttribute("role", "status");
    el.innerHTML = '<svg class="ic" aria-hidden="true"><use href="' + spriteUrl + "#i-" + (ICON[tone] || "info") + '"></use></svg><div></div>' +
      '<button type="button" data-dismiss aria-label="Dismiss"><svg class="ic" aria-hidden="true"><use href="' + spriteUrl + '#i-x"></use></svg></button>';
    el.children[1].textContent = message;
    wrap.appendChild(el);
    setTimeout(() => el.remove(), 6500);
  };
  document.addEventListener("click", (e) => {
    const d = e.target.closest("[data-dismiss]");
    if (d) d.closest(".toast")?.remove();
  });
  $$("#toasts .toast").forEach((t) => setTimeout(() => t.remove(), 7000));

  // ── Page-load bar for navigations and htmx requests ──────────────────
  const body = document.body;
  window.addEventListener("beforeunload", () => body.classList.add("is-loading"));
  window.addEventListener("pageshow", () => body.classList.remove("is-loading"));
  document.addEventListener("htmx:beforeRequest", () => body.classList.add("is-loading"));
  document.addEventListener("htmx:afterRequest", () => body.classList.remove("is-loading"));
  document.addEventListener("htmx:responseError", (e) => {
    const xhr = e.detail.xhr;
    let msg = "Something went wrong. Try again.";
    try { const j = JSON.parse(xhr.responseText); msg = (j.error && j.error.message) || msg; } catch (err) { /* html */ }
    if (xhr.status === 0) msg = "You appear to be offline. Check your connection.";
    window.toast(msg, "error");
  });
  document.addEventListener("htmx:sendError", () => window.toast("You appear to be offline. Check your connection.", "error"));

  // ── Dialogs: [data-open="id"] opens <dialog id>, [data-close] closes ──
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-open]");
    if (opener) {
      const dlg = document.getElementById(opener.dataset.open);
      if (dlg && dlg.showModal) { e.preventDefault(); dlg.showModal(); $("[autofocus]", dlg)?.focus(); }
    }
    const closer = e.target.closest("[data-close]");
    if (closer) closer.closest("dialog")?.close();
  });
  document.addEventListener("click", (e) => {
    if (e.target.tagName === "DIALOG" && e.target.open) {
      const r = e.target.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) e.target.close();
    }
  });

  // ── Confirm before destructive submits (no inline JS: data-confirm) ──
  document.addEventListener("submit", (e) => {
    const form = e.target;
    const msg = form.dataset.confirm || (e.submitter && e.submitter.dataset.confirm);
    if (msg && !form.dataset.confirmed) {
      e.preventDefault();
      const dlg = $("#confirm-dialog");
      if (!dlg) { if (window.confirm(msg)) { form.dataset.confirmed = "1"; form.requestSubmit(e.submitter); } return; }
      $("[data-confirm-text]", dlg).textContent = msg;
      dlg.showModal();
      $("[data-confirm-yes]", dlg).onclick = () => { dlg.close(); form.dataset.confirmed = "1"; form.requestSubmit(e.submitter); };
    }
  });

  // ── Auto-submit filter forms ──────────────────────────────────────────
  document.addEventListener("change", (e) => {
    const f = e.target.closest("form[data-autosubmit]");
    if (f && !e.target.matches("[data-no-autosubmit]")) {
      if (window.htmx && f.getAttribute("hx-get")) window.htmx.trigger(f, "submit");
      else f.requestSubmit();
    }
  });

  // ── Live countdowns: <time data-countdown="ISO"> ──────────────────────
  function tick() {
    $$("[data-countdown]").forEach((el) => {
      const end = new Date(el.dataset.countdown).getTime();
      let s = Math.max(0, Math.round((end - Date.now()) / 1000));
      if (s === 0 && el.dataset.expired) { el.textContent = el.dataset.expired; return; }
      const h = Math.floor(s / 3600); s -= h * 3600;
      const m = Math.floor(s / 60); s -= m * 60;
      el.textContent = (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0");
    });
  }
  if ($("[data-countdown]")) { tick(); setInterval(tick, 1000); }
  document.addEventListener("htmx:afterSwap", tick);

  // ── Copy to clipboard ────────────────────────────────────────────────
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    try { await navigator.clipboard.writeText(b.dataset.copy); window.toast("Copied", "success"); } catch (err) { /* ignore */ }
  });
})();
