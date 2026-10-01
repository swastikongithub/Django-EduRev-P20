// In-app QR scanner. Uses the native BarcodeDetector when available, jsQR otherwise.
// Only same-site check-in URLs are followed; anything else is shown, never opened.
(function () {
  "use strict";
  const root = document.querySelector("[data-scanner]");
  if (!root) return;
  const video = root.querySelector("video");
  const status = root.querySelector("[data-status]");
  const idle = root.querySelector("[data-idle]");
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  let stream = null, detector = null, stopped = false;

  const say = (msg) => { status.textContent = msg; };

  function accept(text) {
    let url;
    try { url = new URL(text, location.origin); } catch (e) { return false; }
    if (url.origin !== location.origin || !/^\/(c|here)\//.test(url.pathname)) {
      say("That QR isn't an LPU Reserve check-in code.");
      return false;
    }
    stop();
    say("Found it — opening…");
    if (navigator.vibrate) navigator.vibrate(60);
    location.href = url.pathname;
    return true;
  }

  async function tick() {
    if (stopped || !video.videoWidth) { if (!stopped) requestAnimationFrame(tick); return; }
    try {
      if (detector) {
        const codes = await detector.detect(video);
        if (codes.length && accept(codes[0].rawValue)) return;
      } else if (window.jsQR) {
        const w = (canvas.width = Math.min(640, video.videoWidth));
        const h = (canvas.height = Math.round(video.videoHeight * (w / video.videoWidth)));
        ctx.drawImage(video, 0, 0, w, h);
        const res = window.jsQR(ctx.getImageData(0, 0, w, h).data, w, h, { inversionAttempts: "dontInvert" });
        if (res && accept(res.data)) return;
      }
    } catch (e) { /* keep scanning */ }
    setTimeout(() => requestAnimationFrame(tick), 120);
  }

  async function start() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      say("This browser can't open the camera here. Type the code below instead.");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
    } catch (e) {
      say(e.name === "NotAllowedError" ? "Camera permission was declined. Allow it in your browser settings, or type the code below." : "Couldn't start the camera. Type the code below instead.");
      return;
    }
    if ("BarcodeDetector" in window) {
      try { detector = new window.BarcodeDetector({ formats: ["qr_code"] }); } catch (e) { detector = null; }
    }
    video.srcObject = stream;
    await video.play();
    idle.hidden = true;
    root.classList.add("is-live");
    say("Scanning… hold the QR inside the frame.");
    stopped = false;
    requestAnimationFrame(tick);
  }

  function stop() {
    stopped = true;
    if (stream) stream.getTracks().forEach((t) => t.stop());
  }

  root.querySelector("[data-start]").addEventListener("click", start);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });

  const manual = document.querySelector("[data-manual]");
  manual?.addEventListener("submit", (e) => {
    e.preventDefault();
    const code = manual.querySelector("input").value.trim();
    if (code) location.href = "/here/" + encodeURIComponent(code) + "/";
  });
})();
