// Runs before first paint: apply the saved theme so there is no flash.
(function () {
  try {
    var t = localStorage.getItem("lpr-theme");
    if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* storage unavailable: follow the OS */ }
})();
