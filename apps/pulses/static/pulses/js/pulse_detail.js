// Prospect Pulse Detail View Dynamic JS Handlers

document.addEventListener("DOMContentLoaded", function () {
  // If active run is already executing on load, poll it
  const config = window.PULSE_CONFIG || {};
  if (config.activeRunId) {
    pollRunStatus(config.activeRunId);
  }

  const discoveryForm = document.getElementById("run-discovery-form");
  if (discoveryForm) {
    discoveryForm.addEventListener("submit", function (e) {
      e.preventDefault();

      // Show track progress button, but keep modal hidden
      const trackBtn = document.getElementById("btn-track-progress");
      if (trackBtn) trackBtn.style.display = "inline-flex";

      // Alert user
      const progressBar = document.getElementById("progress-bar-indicator");
      if (progressBar) progressBar.style.width = "10%";

      // Hide run form and show loading indicator
      const runForm = document.getElementById("run-discovery-form");
      const loadingIndicator = document.getElementById(
        "discovery-loading-indicator",
      );
      if (runForm) runForm.style.display = "none";
      if (loadingIndicator) loadingIndicator.style.display = "inline-flex";

      addStatusStep("Launching crawler queries in background...");

      fetch(discoveryForm.action, {
        method: "POST",
        headers: {
          "X-CSRFToken": config.csrfToken || "",
        },
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.success && data.run_id) {
            addStatusStep(`Job spawned in background (Run ID: ${data.run_id})`);

            // Show temporary alert banner
            const alertBox = document.createElement("div");
            alertBox.style.cssText =
              "position: fixed; bottom: 20px; right: 20px; background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--accent); padding: 16px 20px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 10000; font-size: 13px; color: var(--text); display: flex; align-items: center; gap: 10px;";
            alertBox.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
            <span>Discovery started in background. Click <strong>Track Progress</strong> to view live logs.</span>
          `;
            document.body.appendChild(alertBox);
            setTimeout(() => {
              alertBox.remove();
            }, 5000);

            pollRunStatus(data.run_id);
          } else {
            // Restore Run button and hide loading indicator
            if (runForm) runForm.style.display = "inline-block";
            if (loadingIndicator) loadingIndicator.style.display = "none";
            addStatusStep(
              `[Error] Failed to trigger discovery: ${data.error || "Setup failure"}`,
            );
            alert(data.error || "Failed to trigger discovery run");
          }
        })
        .catch((err) => {
          // Restore Run button and hide loading indicator
          if (runForm) runForm.style.display = "inline-block";
          if (loadingIndicator) loadingIndicator.style.display = "none";
          addStatusStep("[Error] Request failed or timed out.");
          alert("Error initializing discovery run");
        });
    });
  }
});

// Helper to add status steps beautifully to the user
function addStatusStep(message) {
  const consoleLog = document.getElementById("progress-log-console");
  if (!consoleLog) return;

  // Clear placeholder text on first message
  if (consoleLog.querySelector(".placeholder-text")) {
    consoleLog.innerHTML = "";
  }

  const timestamp = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const stepEl = document.createElement("div");
  stepEl.style.cssText =
    "display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 13.5px; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 10px; animation: fadeIn 0.3s ease;";

  let dotColor = "var(--accent)";
  if (
    message.toLowerCase().includes("completed") ||
    message.toLowerCase().includes("successfully") ||
    message.toLowerCase().includes("success")
  ) {
    dotColor = "var(--success)";
  } else if (
    message.toLowerCase().includes("failed") ||
    message.toLowerCase().includes("error")
  ) {
    dotColor = "var(--danger)";
  }

  stepEl.innerHTML = `
    <div style="width: 8px; height: 8px; border-radius: 50%; background: ${dotColor}; flex-shrink: 0;"></div>
    <div style="flex: 1; font-weight: 600;">${message}</div>
    <div style="font-size: 11px; color: var(--muted); font-weight: 700; white-space: nowrap;">${timestamp}</div>
  `;

  consoleLog.appendChild(stepEl);
  consoleLog.scrollTop = consoleLog.scrollHeight;
}

function pollRunStatus(runId) {
  const progressBar = document.getElementById("progress-bar-indicator");
  const trackBtn = document.getElementById("btn-track-progress");
  const runForm = document.getElementById("run-discovery-form");
  const loadingIndicator = document.getElementById(
    "discovery-loading-indicator",
  );
  const statusUrl = `/runs/${runId}/status/`;
  let lastStatus = "";

  // Ensure button is visible if it is polling
  if (trackBtn) trackBtn.style.display = "inline-flex";

  // Ensure form is hidden and loading indicator is shown during active polling
  if (runForm) runForm.style.display = "none";
  if (loadingIndicator) loadingIndicator.style.display = "inline-flex";

  const interval = setInterval(() => {
    fetch(statusUrl)
      .then((res) => res.json())
      .then((data) => {
        const cleanStatus = data.status || "running";

        if (cleanStatus !== lastStatus) {
          addStatusStep(cleanStatus);
          lastStatus = cleanStatus;
        }

        // Move progress bar
        if (progressBar) {
          if (cleanStatus.includes("Scraping")) {
            progressBar.style.width = "40%";
          } else if (cleanStatus.includes("Deduplicating")) {
            progressBar.style.width = "70%";
          } else if (cleanStatus.includes("Summarizing")) {
            progressBar.style.width = "90%";
          }
        }

        if (cleanStatus === "completed") {
          if (progressBar) progressBar.style.width = "100%";
          addStatusStep("Completed successfully! Fetching fresh data...");
          clearInterval(interval);
          setTimeout(() => {
            location.reload();
          }, 1000);
        } else if (cleanStatus === "failed") {
          addStatusStep(
            `Run failed: ${data.error_message || "Pipeline crashed"}`,
          );

          // Restore Run button and hide loading indicator
          if (runForm) runForm.style.display = "inline-block";
          if (loadingIndicator) loadingIndicator.style.display = "none";

          clearInterval(interval);
          setTimeout(() => {
            const modal = document.getElementById("progressModal");
            if (modal) modal.style.display = "none";
          }, 5000);
        }
      })
      .catch((err) => {
        console.error("Polling error:", err);
      });
  }, 1500);
}

function showAddInput(type) {
  const box = document.getElementById(`add-${type}-box`);
  if (!box) return;
  box.classList.toggle("d-none");
  if (!box.classList.contains("d-none")) {
    const input = document.getElementById(`add-${type}-input`);
    if (input) input.focus();
  }
}

function removeItem(type, val, btnEl) {
  if (!confirm(`Are you sure you want to remove "${val}"?`)) return;

  const config = window.PULSE_CONFIG || {};

  fetch(config.manageItemUrl || "", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": config.csrfToken || "",
    },
    body: JSON.stringify({ item_type: type, action: "remove", value: val }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.success) {
        const badge = btnEl.closest("span");
        if (badge) badge.remove();
      } else {
        alert(data.error || "Failed to remove item");
      }
    })
    .catch((err) => {
      console.error(err);
      alert("Error removing item");
    });
}

function addItem(type) {
  const input = document.getElementById(`add-${type}-input`);
  if (!input) return;
  const val = input.value.trim();
  if (!val) return;

  const config = window.PULSE_CONFIG || {};

  fetch(config.manageItemUrl || "", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": config.csrfToken || "",
    },
    body: JSON.stringify({ item_type: type, action: "add", value: val }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.success) {
        location.reload();
      } else {
        alert(data.error || "Failed to add item");
      }
    })
    .catch((err) => {
      console.error(err);
      alert("Error adding item");
    });
}

function performDelete() {
  const config = window.PULSE_CONFIG || {};

  fetch(config.deleteUrl || "", {
    method: "POST",
    headers: {
      "X-CSRFToken": config.csrfToken || "",
    },
  })
    .then((res) => {
      if (res.ok) {
        window.location.href = config.listUrl || "/pulses/";
      } else {
        alert("Failed to delete the pulse configuration. Please try again.");
      }
    })
    .catch((err) => {
      console.error(err);
      alert("An error occurred. Please try again.");
    });
}
