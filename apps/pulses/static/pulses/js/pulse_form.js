(function () {
  function toggleInputFields() {
    var inputType = document.querySelector('input[name="input_type"]:checked');
    var val = inputType ? inputType.value : "";
    document.getElementById("pdf-upload").style.display =
      val === "pdf" ? "block" : "none";
    document.getElementById("url-input").style.display =
      val === "url" ? "block" : "none";

    // Toggle ICP select dropdown visibility
    document.getElementById("icp-select").style.display =
      val === "icp" ? "block" : "none";

    // Show text content only for manual text
    document.getElementById("text-content").style.display =
      val === "text" ? "block" : "none";
  }

  var initialInputType =
    document.getElementById("pulseForm").dataset.initialInputType;
  if (initialInputType) {
    var radio = document.querySelector(
      'input[name="input_type"][value="' + initialInputType + '"]',
    );
    if (radio) radio.checked = true;
  }
  toggleInputFields();

  document.querySelectorAll('input[name="input_type"]').forEach(function (r) {
    r.addEventListener("change", toggleInputFields);
  });

  // Target Geography Quick-Add helpers
  function addGeographyTag(geo) {
    var input = document.getElementById("target_geography") || document.getElementById("id_target_geography") || document.querySelector('input[name="target_geography"]');
    if (!input || !geo) return;
    var current = input.value.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
    if (!current.some(function(s) { return s.toLowerCase() === geo.toLowerCase(); })) {
      current.push(geo);
      input.value = current.join(', ');
      input.focus();
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }
  window.addGeographyTag = addGeographyTag;

  document.querySelectorAll('.geo-quick-add, .geo-pill-btn').forEach(function(el) {
    el.addEventListener('click', function(e) {
      e.preventDefault();
      var geo = this.getAttribute('data-geo');
      if (geo) {
        addGeographyTag(geo);
      }
    });
  });

  var toastAlertTimeout = null;
  function triggerToastAlert(msg, type) {
    type = type || 'error';
    var banner = document.getElementById("quota-alert-banner");
    var messageEl = document.getElementById("quota-alert-message");
    if (!banner || !messageEl) {
      alert(msg);
      return;
    }

    messageEl.innerText = msg;

    if (type === 'warning') {
      banner.style.borderColor = "rgba(245, 158, 11, 0.45)";
      banner.style.color = "#fbbf24";
    } else {
      banner.style.borderColor = "rgba(220, 38, 38, 0.45)";
      banner.style.color = "#f87171";
    }

    banner.style.display = "flex";
    banner.style.opacity = "1";
    banner.style.transform = "translateX(0)";

    if (toastAlertTimeout) {
      clearTimeout(toastAlertTimeout);
    }

    toastAlertTimeout = setTimeout(function () {
      dismissToastAlert();
    }, 5000);
  }
  window.triggerToastAlert = triggerToastAlert;

  function dismissToastAlert() {
    var banner = document.getElementById("quota-alert-banner");
    if (!banner) return;
    banner.style.opacity = "0";
    banner.style.transform = "translateX(120%)";
    setTimeout(function () {
      banner.style.display = "none";
    }, 600);
  }
  window.dismissToastAlert = dismissToastAlert;

  function isValidDate(d) {
    return d instanceof Date && !isNaN(d.getTime());
  }

  function formatDate(d) {
    if (!isValidDate(d)) return "";
    var year = d.getFullYear();
    var month = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
  }

  function updateDateRules() {
    var freqSelect = document.getElementById("id_frequency") || document.querySelector('select[name="frequency"]');
    var frequency = freqSelect ? freqSelect.value : "daily";
    var startInput = document.getElementById("id_start_date") || document.querySelector('input[name="start_date"]');
    var endInput = document.getElementById("id_end_date") || document.querySelector('input[name="end_date"]');
    var endHelp = document.getElementById("end_date_help_text");
    var endStar = document.getElementById("end_date_star");

    if (!endInput) return;

    var sDate = (startInput && startInput.value) ? new Date(startInput.value + "T00:00:00") : null;
    var hasValidStartDate = sDate && isValidDate(sDate);

    if (frequency === "weekly") {
      if (endStar) endStar.style.display = "inline";
      if (hasValidStartDate) {
        var minDate = new Date(sDate.getTime() + 7 * 24 * 60 * 60 * 1000);
        var minStr = formatDate(minDate);
        endInput.min = minStr;
        if (endHelp) {
          endHelp.innerText = "Weekly pulses require an end date at least 7 days after the start date (minimum: " + minStr + ").";
        }
      } else {
        endInput.removeAttribute("min");
        if (endHelp) {
          endHelp.innerText = "Weekly pulses require an end date at least 7 days after the start date.";
        }
      }
    } else if (frequency === "monthly") {
      if (endStar) endStar.style.display = "inline";
      if (hasValidStartDate) {
        var minDate = new Date(sDate.getTime() + 30 * 24 * 60 * 60 * 1000);
        var minStr = formatDate(minDate);
        endInput.min = minStr;
        if (endHelp) {
          endHelp.innerText = "Monthly pulses require an end date at least 30 days after the start date (minimum: " + minStr + ").";
        }
      } else {
        endInput.removeAttribute("min");
        if (endHelp) {
          endHelp.innerText = "Monthly pulses require an end date at least 30 days after the start date.";
        }
      }
    } else {
      // Daily or others
      if (endStar) endStar.style.display = "none";
      if (hasValidStartDate) {
        endInput.min = startInput.value;
        if (endHelp) {
          endHelp.innerText = "Optional end date. If specified, must be on or after " + startInput.value + ".";
        }
      } else {
        endInput.removeAttribute("min");
        if (endHelp) {
          endHelp.innerText = "Optional end date. If specified, must be on or after start date.";
        }
      }
    }
  }

  var freqSelect = document.getElementById("id_frequency") || document.querySelector('select[name="frequency"]');
  if (freqSelect) {
    freqSelect.addEventListener("change", updateDateRules);
  }
  var startInputEl = document.getElementById("id_start_date") || document.querySelector('input[name="start_date"]');
  if (startInputEl) {
    startInputEl.addEventListener("change", updateDateRules);
    startInputEl.addEventListener("input", updateDateRules);
  }
  updateDateRules();

  var form = document.getElementById("pulseForm");
  if (form) {
    form.addEventListener("submit", function (e) {
      var nameInput = document.getElementById("id_name") || document.querySelector('input[name="name"]');
      if (nameInput && !nameInput.value.trim()) {
        triggerToastAlert("Pulse name is required", "warning");
        nameInput.focus();
        e.preventDefault();
        return;
      }

      var startInput = document.getElementById("id_start_date") || document.querySelector('input[name="start_date"]');
      var endInput = document.getElementById("id_end_date") || document.querySelector('input[name="end_date"]');
      var freqSelect = document.getElementById("id_frequency") || document.querySelector('select[name="frequency"]');
      var frequency = freqSelect ? freqSelect.value : "daily";
      var isEdit = form.dataset.isEdit === "true" || (startInput && startInput.hasAttribute("data-locked"));

      var today = new Date();
      today.setHours(0, 0, 0, 0);

      if (startInput && startInput.value) {
        var startDate = new Date(startInput.value + "T00:00:00");
        if (!isEdit && startDate < today) {
          triggerToastAlert("Start date cannot be in the past", "warning");
          startInput.focus();
          e.preventDefault();
          return;
        }

        var endVal = endInput ? endInput.value : "";
        if (frequency === "weekly") {
          if (!endVal) {
            triggerToastAlert("An end date is required for weekly pulses (minimum 7 days)", "warning");
            endInput.focus();
            e.preventDefault();
            return;
          }
          var endDate = new Date(endVal + "T00:00:00");
          var diffDays = Math.round((endDate - startDate) / (1000 * 60 * 60 * 24));
          if (diffDays < 0) {
            triggerToastAlert("End date cannot be before start date", "warning");
            endInput.focus();
            e.preventDefault();
            return;
          }
          if (diffDays < 7) {
            triggerToastAlert("Weekly pulses require an end date at least 7 days after the start date (currently " + diffDays + " day" + (diffDays === 1 ? "" : "s") + ")", "warning");
            endInput.focus();
            e.preventDefault();
            return;
          }
        } else if (frequency === "monthly") {
          if (!endVal) {
            triggerToastAlert("An end date is required for monthly pulses (minimum 30 days)", "warning");
            endInput.focus();
            e.preventDefault();
            return;
          }
          var endDate = new Date(endVal + "T00:00:00");
          var diffDays = Math.round((endDate - startDate) / (1000 * 60 * 60 * 24));
          if (diffDays < 0) {
            triggerToastAlert("End date cannot be before start date", "warning");
            endInput.focus();
            e.preventDefault();
            return;
          }
          if (diffDays < 30) {
            triggerToastAlert("Monthly pulses require an end date at least 30 days after the start date (currently " + diffDays + " day" + (diffDays === 1 ? "" : "s") + ")", "warning");
            endInput.focus();
            e.preventDefault();
            return;
          }
        } else {
          // Daily or others
          if (endVal) {
            var endDate = new Date(endVal + "T00:00:00");
            var diffDays = Math.round((endDate - startDate) / (1000 * 60 * 60 * 24));
            if (diffDays < 0) {
              triggerToastAlert("End date cannot be before start date", "warning");
              endInput.focus();
              e.preventDefault();
              return;
            }
          }
        }
      }

      // Re-enable temporary disabled fields before submit, but leave locked fields alone
      form.querySelectorAll(
        "input[disabled]:not([data-locked]), select[disabled]:not([data-locked]), textarea[disabled]:not([data-locked])"
      ).forEach(function (el) {
        el.disabled = false;
      });
    });
  }
})();
