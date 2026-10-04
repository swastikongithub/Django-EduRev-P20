// Landing page, before first paint: when motion is welcome, hold the hero's intro elements back so
// landing.js can bring them in. landing.css shows them after 2.6 s whatever happens to the scripts.
(function () {
  try {
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      document.documentElement.classList.add("lp-anim");
    }
  } catch (e) { /* no matchMedia: leave everything visible */ }
})();
