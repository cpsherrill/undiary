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

  // ----- Popover menus (account, per-entry) --------------------------------
  // One document listener runs every [data-menu-button] / [data-menu] pair.
  // Buttons with data-confirm arm on the first click and act on the second.

  var closeMenus = function () {
    document.querySelectorAll("[data-menu]").forEach(function (menu) {
      menu.hidden = true;
    });
    document.querySelectorAll("[data-menu-button]").forEach(function (btn) {
      btn.setAttribute("aria-expanded", "false");
    });
    document.querySelectorAll("[data-confirm][data-armed]").forEach(function (btn) {
      btn.textContent = btn.dataset.label;
      btn.removeAttribute("data-armed");
    });
  };

  document.addEventListener("click", function (e) {
    var confirmBtn = e.target.closest("[data-confirm]");
    if (confirmBtn && !confirmBtn.hasAttribute("data-armed")) {
      e.preventDefault();
      confirmBtn.dataset.label = confirmBtn.textContent;
      confirmBtn.textContent = confirmBtn.dataset.confirm;
      confirmBtn.setAttribute("data-armed", "");
      return;
    }
    if (confirmBtn) {
      // Armed: this click submits. Disable after the submit event has
      // fired so a double-click cannot post twice.
      setTimeout(function () { confirmBtn.disabled = true; }, 0);
    }
    var menuBtn = e.target.closest("[data-menu-button]");
    if (menuBtn) {
      var menu = menuBtn.parentElement.querySelector("[data-menu]");
      var wasClosed = menu.hidden;
      closeMenus();
      if (wasClosed) {
        menu.hidden = false;
        menuBtn.setAttribute("aria-expanded", "true");
      }
      return;
    }
    if (!e.target.closest("[data-menu]")) closeMenus();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeMenus();
  });

  // ----- The log form: one submit only, and a keyboard shortcut -----------

  var logForm = document.querySelector(".log-form");
  if (logForm) {
    var logBtn = logForm.querySelector('button[type="submit"]');

    logForm.addEventListener("submit", function (e) {
      if (logForm.hasAttribute("data-submitting")) {
        e.preventDefault();
        return;
      }
      logForm.setAttribute("data-submitting", "");
      if (logBtn) {
        logBtn.disabled = true;
        logBtn.textContent = "Logging…";
      }
    });

    // Cmd+Enter (Ctrl+Enter off Mac) logs the entry. While a recording
    // is running it stops the recording instead, so nothing half-said
    // gets submitted.
    logForm.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" || !(e.metaKey || e.ctrlKey)) return;
      e.preventDefault();
      var rec = document.getElementById("rec");
      if (rec && rec.hasAttribute("data-recording")) {
        rec.click();
        return;
      }
      logForm.requestSubmit();
    });

    // Back-forward cache restores the page mid-"Logging"; reset it.
    window.addEventListener("pageshow", function (e) {
      if (e.persisted) {
        logForm.removeAttribute("data-submitting");
        if (logBtn) {
          logBtn.disabled = false;
          logBtn.textContent = "Log";
        }
      }
    });
  }

  // ----- Audio recorder ----------------------------------------------------

  var recBtn = document.getElementById("rec");
  var status = document.getElementById("rec-status");
  var discard = document.getElementById("rec-discard");
  var audioInput = document.getElementById("audio-input");
  var preview = document.getElementById("rec-preview");
  var previewUrl = null;

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

    var clearPreview = function () {
      preview.pause();
      preview.hidden = true;
      preview.removeAttribute("src");
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }
    };

    var setIdle = function (message) {
      recBtn.removeAttribute("data-recording");
      recBtn.setAttribute("aria-label", "Record audio");
      status.textContent = message || "";
      status.removeAttribute("data-attached");
      discard.hidden = true;
      clearPreview();
    };

    var setAttached = function (seconds, file) {
      setIdle("");
      status.textContent = "audio attached, " + fmt(seconds);
      status.setAttribute("data-attached", "");
      discard.hidden = false;
      previewUrl = URL.createObjectURL(file);
      preview.src = previewUrl;
      preview.hidden = false;
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
            setAttached(seconds, file);
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
