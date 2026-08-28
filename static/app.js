/* Prefill the only things a new entry gets for free (day, clock,
   timezone), run the account menu, and drive the audio recorder. */

(function () {
  "use strict";

  // ----- Date, clock, timezone prefill ------------------------------------

  var tz = "UTC";
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch (e) { /* UTC it is */ }

  var tzInput = document.getElementById("tz");
  if (tzInput) tzInput.value = tz;

  var dateInput = document.getElementById("log-date");
  if (dateInput && !dateInput.value) {
    var now = new Date();
    var pad = function (n) { return String(n).padStart(2, "0"); };
    dateInput.value =
      now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
  }

  var clock = document.getElementById("log-clock");
  if (clock) {
    var tick = function () {
      clock.textContent = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
    };
    tick();
    setInterval(tick, 30 * 1000);
  }

  // ----- Account menu ------------------------------------------------------

  var whoBtn = document.getElementById("who-btn");
  var whoMenu = document.getElementById("who-menu");
  if (whoBtn && whoMenu) {
    var setMenu = function (open) {
      whoMenu.hidden = !open;
      whoBtn.setAttribute("aria-expanded", String(open));
    };
    whoBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      setMenu(whoMenu.hidden);
    });
    document.addEventListener("click", function (e) {
      if (!whoMenu.hidden && !whoMenu.contains(e.target)) setMenu(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setMenu(false);
    });
  }

  // ----- Audio recorder ----------------------------------------------------

  var recBtn = document.getElementById("rec");
  var status = document.getElementById("rec-status");
  var discard = document.getElementById("rec-discard");
  var audioInput = document.getElementById("audio-input");

  if (recBtn && audioInput && navigator.mediaDevices && window.MediaRecorder) {
    recBtn.hidden = false;

    var recorder = null;
    var chunks = [];
    var startedAt = 0;
    var timer = null;

    var mimeType = "";
    ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].some(function (t) {
      if (MediaRecorder.isTypeSupported(t)) { mimeType = t; return true; }
      return false;
    });

    var fmt = function (seconds) {
      var m = Math.floor(seconds / 60);
      var s = String(Math.floor(seconds % 60)).padStart(2, "0");
      return m + ":" + s;
    };

    var setIdle = function (message) {
      recBtn.removeAttribute("data-recording");
      recBtn.setAttribute("aria-label", "Record audio");
      status.textContent = message || "";
      status.removeAttribute("data-attached");
      discard.hidden = true;
    };

    var setAttached = function (seconds) {
      setIdle("");
      status.textContent = "audio attached, " + fmt(seconds);
      status.setAttribute("data-attached", "");
      discard.hidden = false;
    };

    var start = function () {
      navigator.mediaDevices.getUserMedia({ audio: true }).then(
        function (stream) {
          chunks = [];
          recorder = new MediaRecorder(
            stream, mimeType ? { mimeType: mimeType } : undefined
          );
          recorder.ondataavailable = function (e) { chunks.push(e.data); };
          recorder.onstop = function () {
            stream.getTracks().forEach(function (t) { t.stop(); });
            var seconds = (Date.now() - startedAt) / 1000;
            var type = (recorder.mimeType || "audio/webm").split(";")[0];
            var ext = type === "audio/mp4" ? "m4a" : type.split("/")[1];
            var file = new File(chunks, "recording." + ext, { type: type });
            var dt = new DataTransfer();
            dt.items.add(file);
            audioInput.files = dt.files;
            setAttached(seconds);
          };
          recorder.start();
          startedAt = Date.now();
          recBtn.setAttribute("data-recording", "");
          recBtn.setAttribute("aria-label", "Stop recording");
          timer = setInterval(function () {
            status.textContent = "recording " + fmt((Date.now() - startedAt) / 1000);
          }, 500);
          status.textContent = "recording 0:00";
        },
        function () { setIdle("microphone unavailable"); }
      );
    };

    var stop = function () {
      clearInterval(timer);
      if (recorder && recorder.state !== "inactive") recorder.stop();
    };

    recBtn.addEventListener("click", function () {
      if (recBtn.hasAttribute("data-recording")) stop();
      else start();
    });

    discard.addEventListener("click", function () {
      audioInput.value = "";
      setIdle("");
    });
  }
})();
