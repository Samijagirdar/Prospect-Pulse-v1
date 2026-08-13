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

  function toggleCustomDays() {
    var freqEl = document.getElementById("{{ form.frequency.id_for_label }}");
    if (!freqEl) return;
    var container = document.getElementById("custom-days-container");
    var input = document.getElementById("custom_days");
    if (freqEl.value === "custom") {
      container.style.display = "block";
      input.disabled = false;
    } else {
      container.style.display = "none";
      input.disabled = true;
    }
  }

  var freqEl = document.getElementById("{{ form.frequency.id_for_label }}");
  if (freqEl) {
    toggleCustomDays();
    freqEl.addEventListener("change", toggleCustomDays);
  }

  document.getElementById("pulseForm").addEventListener("submit", function (e) {
    var startInput = document.getElementById(
      "{{ form.start_date.id_for_label }}",
    );
    var endInput = document.getElementById("{{ form.end_date.id_for_label }}");
    var wasStartDisabled = startInput ? startInput.disabled : false;

    // Re-enable disabled fields before submit
    this.querySelectorAll(
      "input[disabled], select[disabled], textarea[disabled]",
    ).forEach(function (el) {
      el.disabled = false;
    });

    var today = new Date();
    today.setHours(0, 0, 0, 0);

    if (startInput && startInput.value) {
      var startDate = new Date(startInput.value);
      if (!wasStartDisabled && startDate < today) {
        alert("Start date cannot be in the past");
        startInput.focus();
        e.preventDefault();
        return;
      }
      if (endInput && endInput.value) {
        var endDate = new Date(endInput.value);
        if (endDate < startDate) {
          alert("End date cannot be before start date");
          endInput.focus();
          e.preventDefault();
          return;
        }
      }
    }

    if (freqEl && freqEl.value === "custom") {
      var customDays = parseInt(document.getElementById("custom_days").value);
      if (isNaN(customDays) || customDays < 1) {
        alert("Please enter a valid number of days (1 or more)");
        document.getElementById("custom_days").focus();
        e.preventDefault();
      }
    }
  });
})();
