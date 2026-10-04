// LPU Reserve — public landing page. Progressive enhancement only: the page is complete without it.
//
// Without GSAP (or under prefers-reduced-motion) only the essentials run: the reading-progress rule,
// the current-section link, the state legend and the board's time readout. With GSAP: the hero
// intro, word-by-word headings, chapter choreography and Lenis smooth scrolling (the one scroll
// engine, driven by GSAP's ticker and feeding ScrollTrigger).
(function () {
  "use strict";
  const root = document.documentElement;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ── Reading progress and the sticky bar's rule ──────────────────────
  const bar = $(".lp-progress span");
  const nav = $(".lp-nav");
  let ticking = false;
  function paintScroll() {
    ticking = false;
    const max = root.scrollHeight - window.innerHeight;
    if (bar) bar.style.setProperty("--p", max > 0 ? Math.min(1, window.scrollY / max).toFixed(4) : 0);
    if (nav) nav.classList.toggle("is-stuck", window.scrollY > 8);
  }
  window.addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(paintScroll); } }, { passive: true });
  paintScroll();

  // ── Current section in the nav ──────────────────────────────────────
  const links = new Map($$(".lp-nav__links a").map((a) => [a.getAttribute("href").slice(1), a]));
  if ("IntersectionObserver" in window && links.size) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        const a = links.get(e.target.id);
        if (a && e.isIntersecting) {
          links.forEach((l) => l.removeAttribute("aria-current"));
          a.setAttribute("aria-current", "true");
        }
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    $$("main section[id]").forEach((s) => io.observe(s));
  }

  // ── Availability legend: pick a state, see it in the strip ──────────
  const anatomy = $("[data-anatomy]");
  if (anatomy) {
    const buttons = $$("[data-show]", anatomy);
    const segs = $$(".lp-seg[data-state]", anatomy);
    let pinned = null;
    const show = (state) => {
      anatomy.classList.toggle("is-focus", !!state);
      segs.forEach((s) => s.classList.toggle("is-on", s.dataset.state === state));
    };
    buttons.forEach((b) => {
      b.addEventListener("click", () => {
        pinned = pinned === b.dataset.show ? null : b.dataset.show;
        buttons.forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.show === pinned)));
        show(pinned);
      });
      b.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") show(b.dataset.show); });
      b.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") show(pinned); });
    });
  }

  // ── Board: read the ledger under the pointer ────────────────────────
  const board = $("[data-board]");
  if (board && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    const tip = document.createElement("div");
    tip.className = "lp-tip";
    tip.setAttribute("aria-hidden", "true");
    board.appendChild(tip);
    const start = 8, hours = 12;
    const fmt = (m) => String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
    board.addEventListener("pointermove", (e) => {
      const track = e.target.closest(".lp-track");
      if (!track) { tip.classList.remove("is-on"); return; }
      const r = track.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width;
      const seg = $$(".lp-seg", track).find((s) => {
        const b = s.getBoundingClientRect();
        return e.clientX >= b.left && e.clientX <= b.right;
      });
      const minutes = Math.round((start * 60 + x * hours * 60) / 30) * 30;
      tip.textContent = seg ? seg.title : fmt(Math.min(minutes, (start + hours) * 60)) + " Available";
      const br = board.getBoundingClientRect();
      tip.style.transform = `translate(${Math.round(e.clientX - br.left)}px, ${Math.round(r.top - br.top - 8)}px)`;
      tip.classList.add("is-on");
    });
    board.addEventListener("pointerleave", () => tip.classList.remove("is-on"));
  }

  // ── Motion ──────────────────────────────────────────────────────────
  const gsap = window.gsap;
  const ST = window.ScrollTrigger;
  if (reduce || !gsap || !ST) {
    root.classList.remove("lp-anim");
    return;
  }
  gsap.registerPlugin(ST);
  gsap.defaults({ ease: "expo.out", duration: 1 });

  // One smooth-scroll engine: Lenis, on GSAP's clock, feeding ScrollTrigger. Touch scrolls natively.
  let lenis = null;
  if (window.Lenis) {
    lenis = new window.Lenis({ lerp: 0.11, smoothWheel: true });
    lenis.on("scroll", ST.update);
    const raf = (t) => lenis.raf(t * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);
    window.addEventListener("pagehide", (e) => { if (!e.persisted) { gsap.ticker.remove(raf); lenis.destroy(); } });
  }
  // In-page links: scroll under the sticky bar, then move keyboard focus to the target.
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#"]');
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey) return;
    const id = a.getAttribute("href");
    const target = id.length > 1 ? document.getElementById(id.slice(1)) : null;
    if (!target) return;
    e.preventDefault();
    const done = () => {
      if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
      target.focus({ preventScroll: true });
    };
    if (lenis) lenis.scrollTo(target, { duration: 1.1, onComplete: done }); // Lenis honours scroll-margin-top
    else { target.scrollIntoView(); done(); }
    history.replaceState(null, "", id === "#top" ? location.pathname : id);
  });

  // Headline words: the sentence stays whole for assistive tech in an sr-only span.
  function split(el) {
    const sr = document.createElement("span");
    sr.className = "sr-only";
    sr.textContent = el.textContent.replace(/\s+/g, " ").trim();
    const vis = document.createElement("span");
    vis.setAttribute("aria-hidden", "true");
    Array.from(el.childNodes).forEach((node) => {
      const holder = node.nodeType === 1 ? node.cloneNode(false) : null; // keeps <em>
      const into = holder || vis;
      node.textContent.split(/(\s+)/).forEach((w) => {
        if (!w) return;
        if (/^\s+$/.test(w)) { into.appendChild(document.createTextNode(" ")); return; }
        const outer = document.createElement("span");
        outer.className = "lp-wl";
        const inner = document.createElement("span");
        inner.className = "lp-w";
        inner.textContent = w;
        outer.appendChild(inner);
        into.appendChild(outer);
      });
      if (holder) vis.appendChild(holder);
    });
    el.textContent = "";
    el.append(sr, vis);
    return $$(".lp-w", vis);
  }

  // ── Hero intro ──────────────────────────────────────────────────────
  const intro = gsap.timeline({ onComplete: () => root.classList.remove("lp-anim") });
  const title = $(".lp-hero__title");
  if (title) {
    const words = split(title);
    gsap.set(title, { opacity: 1 });
    intro.from(words, { yPercent: 110, duration: 1.15, stagger: 0.06 }, 0.15);
  }
  intro
    .fromTo(".lp-nav", { opacity: 0, y: -10 }, { opacity: 1, y: 0, duration: 0.9 }, 0)
    .fromTo(".lp-eyebrow", { opacity: 0, y: 12 }, { opacity: 1, y: 0 }, 0.05)
    .fromTo([".lp-hero__lede", ".lp-hero__copy .lp-cta", ".lp-facts"], { opacity: 0, y: 18 }, { opacity: 1, y: 0, stagger: 0.09 }, 0.55);

  if (board) {
    const parts = $$("[data-intro]", board);
    const rows = $$("[data-row]", board);
    intro.fromTo(board, { opacity: 0, y: 28 }, { opacity: 1, y: 0, duration: 1.2 }, 0.35);
    intro.fromTo(parts, { opacity: 0 }, { opacity: 1, duration: 0.8, stagger: 0.08 }, 0.6);
    intro.from(rows, { opacity: 0, y: 8, stagger: 0.06, duration: 0.8 }, 0.65);
    const list = $(".lp-board__rows", board);
    if (list && rows.length) {
      // the ledger being read: a hairline sweeps the day and each claim lands as it passes
      const sweep = document.createElement("span");
      sweep.className = "lp-sweep";
      sweep.setAttribute("aria-hidden", "true");
      sweep.innerHTML = "<i></i>";
      list.appendChild(sweep);
      const SWEEP = 1.5, AT = 0.9;
      intro.fromTo(sweep.firstChild, { left: "0%" }, { left: "100%", duration: SWEEP, ease: "power2.inOut" }, AT)
        .fromTo(sweep, { opacity: 1 }, { opacity: 0, duration: 0.4, ease: "none" }, AT + SWEEP - 0.1);
      $$(".lp-seg", list).forEach((s) => {
        const at = AT + (parseFloat(s.style.left) / 100) * SWEEP * 0.85;
        intro.from(s, { scaleX: 0, duration: 0.7, ease: "power3.out" }, at);
      });
      const now = $(".lp-track__now", list);
      if (now) intro.from($$(".lp-track__now", list), { opacity: 0, duration: 0.6 }, AT + SWEEP);
    }
  }

  // ── Headings and reveals as the story scrolls ───────────────────────
  $$("main [data-split]").forEach((h) => {
    if (h === title) return;
    const words = split(h);
    gsap.from(words, {
      yPercent: 110, duration: 1.1, stagger: 0.045,
      scrollTrigger: { trigger: h, start: "top 88%", once: true },
    });
  });
  $$(".lp-section .lp-head").forEach((head) => {
    const bits = $$(".lp-index, .lp-lede", head);
    gsap.from(bits, { opacity: 0, y: 16, stagger: 0.12, delay: 0.15, scrollTrigger: { trigger: head, start: "top 85%", once: true } });
  });
  const reveals = $$("[data-reveal]");
  gsap.set(reveals, { opacity: 0, y: 24 });
  ST.batch(reveals, {
    start: "top 90%", once: true,
    onEnter: (els) => gsap.to(els, { opacity: 1, y: 0, stagger: 0.08, duration: 1 }),
  });

  // 01 · four registers, then one ledger
  const merge = $("[data-merge]");
  if (merge) {
    const tl = gsap.timeline({ scrollTrigger: { trigger: merge, start: "top 72%", once: true } });
    tl.from($$("[data-lane]", merge), { opacity: 0, x: -16, stagger: 0.1, duration: 0.8 })
      .from($$(".lp-lanes .lp-seg", merge), { scaleX: 0, stagger: 0.05, duration: 0.7, ease: "power3.out" }, 0.25)
      .from($$("[data-clash]", merge), { opacity: 0, scaleY: 0.4, stagger: 0.15, duration: 0.5, ease: "back.out(2)" }, 0.9)
      .from(".lp-merge__note", { opacity: 0, y: 10, duration: 0.6 }, 1.3)
      .from(".lp-merge__after", { opacity: 0, y: 18, duration: 0.9 }, 1.1)
      .from($$("[data-one] .lp-seg", merge), { scaleX: 0, stagger: 0.09, duration: 0.6, ease: "power3.out" }, 1.4)
      .from($$(".lp-ticks li", merge), { opacity: 0, y: 10, stagger: 0.1, duration: 0.7 }, 1.7);
  }

  // 02 · the strip assembles itself
  if (anatomy) {
    gsap.from($$(".lp-track--xl .lp-seg", anatomy), {
      scaleX: 0, stagger: 0.07, duration: 0.8, ease: "power3.out",
      scrollTrigger: { trigger: anatomy, start: "top 75%", once: true },
    });
    gsap.from($$(".lp-states li", anatomy), {
      opacity: 0, y: 14, stagger: 0.05, duration: 0.8,
      scrollTrigger: { trigger: ".lp-states", start: "top 88%", once: true },
    });
  }

  // 03 · the journey's rule fills as you read down it
  const steps = $("[data-steps]");
  if (steps) {
    gsap.fromTo(steps, { "--lp-steps": 0 }, {
      "--lp-steps": 1, ease: "none",
      scrollTrigger: { trigger: steps, start: "top 80%", end: "bottom 65%", scrub: 0.6 },
    });
    gsap.from($$(".lp-step", steps), {
      opacity: 0, y: 26, stagger: 0.1, duration: 1,
      scrollTrigger: { trigger: steps, start: "top 82%", once: true },
    });
  }

  // 04 · tiles open like shutters; large photos drift a little against the scroll
  const tiles = $$("[data-tile]");
  if (tiles.length) {
    gsap.set(tiles, { clipPath: "inset(100% 0% 0% 0%)" });
    ST.batch(tiles, {
      start: "top 92%", once: true,
      onEnter: (els) => gsap.to(els, { clipPath: "inset(0% 0% 0% 0%)", duration: 1.2, ease: "expo.inOut", stagger: 0.07 }),
    });
    gsap.matchMedia().add("(min-width: 921px)", () => {
      tiles.forEach((t) => {
        const media = $(".lp-tile__media", t);
        if (media) gsap.fromTo(media, { yPercent: -5 }, { yPercent: 5, ease: "none", scrollTrigger: { trigger: t, start: "top bottom", end: "bottom top", scrub: true } });
      });
    });
  }

  // 05 · the race
  const race = $("[data-race]");
  if (race) {
    const a = $('[data-req="a"]', race), b = $('[data-req="b"]', race);
    const slot = $("[data-slot]", race);
    const replay = $("[data-replay]", race);
    const outs = $$("[data-out]", race);
    gsap.set(outs, { opacity: 0, y: 6 }); // the outcome is unknown until the race is run
    const tl = gsap.timeline({ paused: true });
    tl.call(() => { a.classList.remove("is-won"); b.classList.remove("is-refused"); }, null, 0)
      .set(outs, { opacity: 0, y: 6 }, 0)
      .from([a, b], { opacity: 0, y: 22, duration: 0.8, stagger: 0.08 }, 0)
      .from(".lp-ledger", { opacity: 0, y: 16, duration: 0.8 }, 0.1)
      .to([a, b], { y: 10, duration: 0.45, ease: "power2.in" }, 1.0)
      .to([a, b], { y: 0, duration: 0.6, ease: "expo.out" }, 1.45)
      .from(slot, { scaleX: 0, duration: 0.7, ease: "expo.out" }, 1.45)
      .call(() => a.classList.add("is-won"), null, 1.5)
      .to('[data-out="a"]', { opacity: 1, y: 0, duration: 0.6 }, 1.55)
      .to(b, { x: 7, duration: 0.07, repeat: 5, yoyo: true, ease: "power1.inOut" }, 1.62)
      .set(b, { x: 0 }, 2.05)
      .call(() => b.classList.add("is-refused"), null, 1.65)
      .to('[data-out="b"]', { opacity: 1, y: 0, duration: 0.6 }, 1.75)
      .from(".lp-proof", { opacity: 0, y: 18, duration: 1 }, 1.9);
    ST.create({ trigger: race, start: "top 65%", once: true, onEnter: () => tl.play(0) });
    if (replay) {
      replay.hidden = false;
      replay.addEventListener("click", () => tl.restart());
    }
  }

  // Closing chapter
  const close = $(".lp-close__side");
  if (close) gsap.from(close.children, { opacity: 0, y: 18, stagger: 0.1, scrollTrigger: { trigger: close, start: "top 88%", once: true } });

  // Fonts change line breaks: measure again once they are in.
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => ST.refresh());
  window.addEventListener("load", () => ST.refresh());
})();
