/* Prefill the only things a new entry gets for free: the day, the
   clock, and the timezone. Everything else is said, not filled in. */

(function () {
  "use strict";

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
})();
