/* Prefill the only things a new entry gets for free (day, clock,
   timezone), run the account menu, and drive the audio recorder. */

(function () {
  "use strict";

  // ----- Service worker (installability, offline shell) --------------------

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {
      /* no worker, no harm */
    });
  }

  // An installed app resumes the page it fell asleep on, sometimes days
  // old. On waking stale, reload; never while a draft is in progress.
  var loadedAt = Date.now();
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible") return;
    if (Date.now() - loadedAt < 5 * 60 * 1000) return;
    var ta = document.querySelector(".log-form textarea");
    var fileInput = document.getElementById("audio-input");
    var drafting =
      (ta && ta.value.trim()) ||
      (fileInput && fileInput.files.length > 0) ||
      document.querySelector(".rec-btn[data-recording]");
    if (!drafting) location.reload();
  });

  // ----- Arrival flash: a fresh entry announces itself ---------------------

  var newPk = new URLSearchParams(location.search).get("new");
  if (newPk) {
    var fresh = document.getElementById("entry-" + newPk);
    if (fresh) fresh.classList.add("flash-new");
    var params = new URLSearchParams(location.search);
    params.delete("new");
    var qs = params.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
  }

  // ----- Todos page: keep your place, flash new arrivals -------------------

  if (location.pathname === "/todos") {
    try {
      var savedScroll = sessionStorage.getItem("undiary-todos-scroll");
      if (savedScroll !== null) {
        window.scrollTo(0, parseInt(savedScroll, 10) || 0);
        sessionStorage.removeItem("undiary-todos-scroll");
      }
    } catch (e) { /* no storage, no memory */ }

    document.addEventListener("submit", function () {
      try {
        sessionStorage.setItem("undiary-todos-scroll", String(window.scrollY));
      } catch (e) { /* fine */ }
    });

    try {
      var SEEN_KEY = "undiary-todos-seen";
      var seen = Date.parse(localStorage.getItem(SEEN_KEY) || "") || 0;
      if (seen) {
        document.querySelectorAll(".todo[data-created]").forEach(function (el) {
          if (Date.parse(el.getAttribute("data-created")) > seen) {
            el.classList.add("flash-new");
          }
        });
      }
      localStorage.setItem(SEEN_KEY, new Date().toISOString());
    } catch (e) { /* fine */ }

    document.querySelectorAll("details.todo-fold").forEach(function (fold) {
      var key = "undiary-fold-" + fold.getAttribute("data-fold");
      try {
        var stored = localStorage.getItem(key);
        if (stored === "1") fold.open = true;
        else if (stored === "0") fold.open = false;
      } catch (e) { /* defaults stand */ }
      fold.addEventListener("toggle", function () {
        try {
          localStorage.setItem(key, fold.open ? "1" : "0");
        } catch (e) { /* fine */ }
      });
    });
  }

  // ----- Date, clock, timezone prefill ------------------------------------

  var tz = "UTC";
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch (e) { /* UTC it is */ }

  document.querySelectorAll('input[name="tz"]').forEach(function (el) {
    el.value = tz;
  });

  var now = new Date();
  var pad = function (n) { return String(n).padStart(2, "0"); };
  var localDate =
    now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());

  var dateInput = document.getElementById("log-date");
  if (dateInput && !dateInput.value) dateInput.value = localDate;
  document.querySelectorAll("input.js-local-date").forEach(function (el) {
    if (!el.value) el.value = localDate;
  });

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
    document.querySelectorAll("[data-copy-link]").forEach(function (btn) {
      if (btn.dataset.label) {
        btn.textContent = btn.dataset.label;
        delete btn.dataset.label;
      }
    });
  };

  // Copy that works everywhere: a synchronous execCommand attempt runs
  // inside the tap gesture (WebKit is strict about that), the async
  // clipboard API backs it up, and the share sheet is the last resort.
  var legacyCopy = function (text) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.focus();
      ta.setSelectionRange(0, text.length);
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (err) {
      return false;
    }
  };

  // On touch devices the share sheet is the only reliable path (its
  // Copy button is the real clipboard on iOS), and it must be called
  // synchronously in the tap: WebKit's gesture budget does not survive
  // a rejected promise. Desktops keep the clipboard with its flashes.
  var shareFirst = !!(
    navigator.share &&
    window.matchMedia &&
    matchMedia("(any-pointer: coarse)").matches
  );
  if (shareFirst) {
    document.querySelectorAll("[data-copy-link]").forEach(function (btn) {
      btn.textContent = "Share link";
    });
  }

  document.addEventListener("click", function (e) {
    var copyBtn = e.target.closest("[data-copy-link]");
    if (copyBtn) {
      var link = location.origin + copyBtn.getAttribute("data-copy-link");
      if (!copyBtn.dataset.label) copyBtn.dataset.label = copyBtn.textContent;
      var flash = function (message) {
        copyBtn.textContent = message;
        setTimeout(closeMenus, 900);
      };
      if (shareFirst) {
        navigator.share({ url: link }).catch(function () {});
        closeMenus();
      } else if (legacyCopy(link)) {
        flash("Copied");
      } else if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(
          function () { flash("Copied"); },
          function () { flash("Copy failed"); }
        );
      } else {
        flash("Copy failed");
      }
      return;
    }
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

  // ----- The log form: fetch submits, an offline outbox, a shortcut -------
  // Entries post via fetch so a dead network can be caught; caught
  // entries wait in IndexedDB and flush, in order, when the network
  // returns. The captain does not check for signal.

  var logForm = document.querySelector(".log-form");
  if (logForm) {
    var logBtn = logForm.querySelector('button[type="submit"]');
    var textArea = logForm.querySelector("textarea");
    var outboxEl = document.getElementById("outbox");

    var resetLogForm = function () {
      logForm.removeAttribute("data-submitting");
      if (logBtn) {
        logBtn.disabled = false;
        logBtn.textContent = "Log";
      }
    };

    var clearLogForm = function () {
      if (textArea) textArea.value = "";
      var discardBtn = document.getElementById("rec-discard");
      if (discardBtn && !discardBtn.hidden) discardBtn.click();
      var fileInput = document.getElementById("audio-input");
      if (fileInput) fileInput.value = "";
    };

    var openOutbox = function () {
      return new Promise(function (resolve, reject) {
        var req = indexedDB.open("undiary", 1);
        req.onupgradeneeded = function () {
          req.result.createObjectStore("outbox", { autoIncrement: true });
        };
        req.onsuccess = function () { resolve(req.result); };
        req.onerror = function () { reject(req.error); };
      });
    };

    var outboxAll = function () {
      return openOutbox().then(function (db) {
        return new Promise(function (resolve, reject) {
          var rows = [];
          var tx = db.transaction("outbox", "readonly");
          tx.objectStore("outbox").openCursor().onsuccess = function (e) {
            var cursor = e.target.result;
            if (cursor) {
              rows.push({ key: cursor.key, value: cursor.value });
              cursor.continue();
            } else {
              resolve(rows);
            }
          };
          tx.onerror = function () { reject(tx.error); };
        });
      });
    };

    var outboxAdd = function (record) {
      return openOutbox().then(function (db) {
        return new Promise(function (resolve, reject) {
          var tx = db.transaction("outbox", "readwrite");
          tx.objectStore("outbox").add(record);
          tx.oncomplete = resolve;
          tx.onerror = function () { reject(tx.error); };
        });
      });
    };

    var outboxRemove = function (key) {
      return openOutbox().then(function (db) {
        return new Promise(function (resolve, reject) {
          var tx = db.transaction("outbox", "readwrite");
          tx.objectStore("outbox").delete(key);
          tx.oncomplete = resolve;
          tx.onerror = function () { reject(tx.error); };
        });
      });
    };

    var renderOutbox = function () {
      if (!outboxEl) return;
      outboxAll().then(function (rows) {
        outboxEl.innerHTML = "";
        if (!rows.length) {
          outboxEl.hidden = true;
          return;
        }
        var note = document.createElement("p");
        note.className = "outbox-note";
        note.textContent =
          rows.length === 1
            ? "1 entry waits for the network."
            : rows.length + " entries wait for the network.";
        outboxEl.appendChild(note);
        rows.forEach(function (row) {
          var ghost = document.createElement("article");
          ghost.className = "entry";
          var meta = document.createElement("p");
          meta.className = "entry-meta";
          meta.textContent = (row.value.log_date || "") + " · queued";
          var body = document.createElement("div");
          body.className = "entry-body";
          var p = document.createElement("p");
          p.textContent = row.value.text || "(audio)";
          body.appendChild(p);
          ghost.appendChild(meta);
          ghost.appendChild(body);
          outboxEl.appendChild(ghost);
        });
        outboxEl.hidden = false;
      }).catch(function () { /* no IndexedDB, no outbox UI */ });
    };

    var csrfToken = function () {
      var input = logForm.querySelector('[name="csrfmiddlewaretoken"]');
      return input ? input.value : "";
    };

    var postable = function (res) {
      return res.ok && res.url.indexOf("/accounts/") === -1;
    };

    var flushing = false;
    var flushOutbox = function () {
      if (flushing || !navigator.onLine) return;
      flushing = true;
      outboxAll().then(function (rows) {
        var i = 0;
        var sent = 0;
        var finish = function () {
          flushing = false;
          if (sent && i >= rows.length) {
            location.reload();
          } else {
            renderOutbox();
          }
        };
        var next = function () {
          if (i >= rows.length) { finish(); return; }
          var row = rows[i++];
          var fd = new FormData();
          fd.append("csrfmiddlewaretoken", csrfToken());
          fd.append("text", row.value.text || "");
          fd.append("tz", row.value.tz || "UTC");
          fd.append("log_date", row.value.log_date || "");
          fd.append("spoken_at", row.value.spoken_at || "");
          if (row.value.audio) {
            fd.append("audio", row.value.audio, row.value.audio_name || "recording.webm");
          }
          fetch("/", { method: "POST", body: fd, credentials: "same-origin" })
            .then(function (res) {
              if (postable(res)) {
                outboxRemove(row.key).then(function () {
                  sent++;
                  next();
                });
              } else {
                i = rows.length + 1;
                finish();
              }
            })
            .catch(function () {
              i = rows.length + 1;
              finish();
            });
        };
        next();
      }).catch(function () { flushing = false; });
    };

    logForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (logForm.hasAttribute("data-submitting")) return;

      var text = textArea ? textArea.value.trim() : "";
      var fileInput = document.getElementById("audio-input");
      var hasAudio = fileInput && fileInput.files.length > 0;
      if (!text && !hasAudio) return;

      logForm.setAttribute("data-submitting", "");
      if (logBtn) {
        logBtn.disabled = true;
        logBtn.textContent = "Logging…";
      }

      var record = {
        text: text,
        tz: (document.getElementById("tz") || {}).value || "UTC",
        log_date: (document.getElementById("log-date") || {}).value || "",
        spoken_at: new Date().toISOString(),
        audio: hasAudio ? fileInput.files[0] : null,
        audio_name: hasAudio ? fileInput.files[0].name : "",
        queued_at: new Date().toISOString(),
      };

      var queueIt = function () {
        outboxAdd(record).then(
          function () {
            clearLogForm();
            resetLogForm();
            renderOutbox();
          },
          function () { resetLogForm(); }
        );
      };

      if (!navigator.onLine) {
        queueIt();
        return;
      }

      var fd = new FormData(logForm);
      fd.append("spoken_at", record.spoken_at);
      fetch(location.href, { method: "POST", body: fd, credentials: "same-origin" })
        .then(function (res) {
          if (postable(res)) {
            // The redirect carries ?new=<id> so the arrival can flash.
            location.assign(res.url || "/");
          } else {
            resetLogForm();
          }
        })
        .catch(queueIt);
    });

    window.addEventListener("online", flushOutbox);
    renderOutbox();
    flushOutbox();

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

    // ----- Microphone picker, for browsers that guess wrong ---------------

    var micSelect = document.getElementById("mic-select");
    var MIC_KEY = "undiary-mic";

    var savedMic = function () {
      try {
        return localStorage.getItem(MIC_KEY) || "";
      } catch (e) {
        return "";
      }
    };

    var refreshMics = function () {
      if (!micSelect || !navigator.mediaDevices.enumerateDevices) return;
      navigator.mediaDevices.enumerateDevices().then(function (devices) {
        var mics = devices.filter(function (d) {
          return d.kind === "audioinput" && d.deviceId;
        });
        if (mics.length < 2) {
          micSelect.hidden = true;
          return;
        }
        micSelect.innerHTML = "";
        mics.forEach(function (mic, i) {
          var option = document.createElement("option");
          option.value = mic.deviceId;
          option.textContent = mic.label || "microphone " + (i + 1);
          micSelect.appendChild(option);
        });
        var saved = savedMic();
        for (var i = 0; i < micSelect.options.length; i++) {
          if (micSelect.options[i].value === saved) micSelect.value = saved;
        }
        micSelect.hidden = false;
      });
    };

    if (micSelect) {
      micSelect.addEventListener("change", function () {
        try {
          localStorage.setItem(MIC_KEY, micSelect.value);
        } catch (e) { /* private mode */ }
      });
    }
    refreshMics();
    if (navigator.mediaDevices.addEventListener) {
      navigator.mediaDevices.addEventListener("devicechange", refreshMics);
    }

    var micConstraint = function () {
      var chosen =
        micSelect && !micSelect.hidden && micSelect.value
          ? micSelect.value
          : savedMic();
      return chosen ? { deviceId: { exact: chosen } } : true;
    };

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

    // ----- Level meter: bars that move only for an actual voice ----------

    var levelEl = document.getElementById("rec-level");
    var levelBars = levelEl ? [].slice.call(levelEl.children) : [];
    var HEARING_RMS = 0.012;
    var audioCtx = null;
    var levelTimer = null;
    var heardPeak = 0;

    var startLevelMeter = function (stream) {
      if (!levelEl || !(window.AudioContext || window.webkitAudioContext)) return;
      try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === "suspended") audioCtx.resume();
        var analyser = audioCtx.createAnalyser();
        analyser.fftSize = 512;
        audioCtx.createMediaStreamSource(stream).connect(analyser);
        var buf = new Uint8Array(analyser.fftSize);
        var levels = [0, 0, 0, 0, 0];
        heardPeak = 0;
        levelEl.hidden = false;
        levelTimer = setInterval(function () {
          analyser.getByteTimeDomainData(buf);
          var sum = 0;
          for (var i = 0; i < buf.length; i++) {
            var v = (buf[i] - 128) / 128;
            sum += v * v;
          }
          var rms = Math.sqrt(sum / buf.length);
          if (rms > heardPeak) heardPeak = rms;
          levels.shift();
          levels.push(rms);
          levelEl.toggleAttribute("data-hearing", rms > HEARING_RMS);
          levelBars.forEach(function (bar, idx) {
            var scale = Math.max(0.18, Math.min(1, levels[idx] * 9));
            bar.style.transform = "scaleY(" + scale + ")";
          });
        }, 90);
      } catch (err) { /* no meter, the recording is unaffected */ }
    };

    var stopLevelMeter = function () {
      clearInterval(levelTimer);
      levelTimer = null;
      if (audioCtx) {
        audioCtx.close().catch(function () {});
        audioCtx = null;
      }
      if (levelEl) {
        levelEl.hidden = true;
        levelEl.removeAttribute("data-hearing");
      }
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
      var verdict = heardPeak > 0 && heardPeak <= HEARING_RMS ? ", heard nothing" : "";
      status.textContent = "audio attached, " + fmt(seconds) + verdict;
      status.setAttribute("data-attached", "");
      discard.hidden = false;
      previewUrl = URL.createObjectURL(file);
      preview.src = previewUrl;
      preview.hidden = false;
    };

    var start = function () {
      navigator.mediaDevices
        .getUserMedia({ audio: micConstraint() })
        .catch(function () {
          // The chosen device may be unplugged; fall back to default.
          return navigator.mediaDevices.getUserMedia({ audio: true });
        })
        .then(
        function (stream) {
          refreshMics();
          chunks = [];
          recorder = new MediaRecorder(
            stream, mimeType ? { mimeType: mimeType } : undefined
          );
          recorder.ondataavailable = function (e) { chunks.push(e.data); };
          recorder.onstop = function () {
            stopLevelMeter();
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
          startLevelMeter(stream);
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
      stopLevelMeter();
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
