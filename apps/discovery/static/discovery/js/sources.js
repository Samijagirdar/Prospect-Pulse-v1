let quotaAlertTimeout = null;

function triggerQuotaAlert(msg) {
  const banner = document.getElementById("quota-alert-banner");
  const messageEl = document.getElementById("quota-alert-message");
  if (!banner || !messageEl) return;

  messageEl.innerText = msg;
  banner.style.display = "flex";
  banner.style.opacity = "1";
  banner.style.transform = "translateX(0)";

  if (quotaAlertTimeout) {
    clearTimeout(quotaAlertTimeout);
  }

  quotaAlertTimeout = setTimeout(function () {
    banner.style.opacity = "0";
    banner.style.transform = "translateX(120%)";
    setTimeout(function () {
      banner.style.display = "none";
    }, 600);
  }, 5000);
}

function switchSubView(viewName) {
  document.querySelectorAll(".sub-nav-btn").forEach((btn) => {
    btn.classList.remove("active");
  });
  const activeBtn = document.getElementById(`btn-${viewName}`);
  if (activeBtn) activeBtn.classList.add("active");

  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.remove("active");
  });
  const activePanel = document.getElementById(`panel-${viewName}`);
  if (activePanel) activePanel.classList.add("active");

  // Apply sorting to the newly opened tab
  sortActivePanel();
}

function sortActivePanel() {
  const activePanel = document.querySelector(".view-panel.active");
  if (!activePanel) return;
  const tbody = activePanel.querySelector(".article-tbody");
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll(".article-row"));
  const sortVal = document.getElementById("sortArticles").value;

  rows.sort((a, b) => {
    let valA, valB;

    if (sortVal.startsWith("pub")) {
      const dateStrA = a.getAttribute("data-published") || "";
      const dateStrB = b.getAttribute("data-published") || "";
      valA = dateStrA ? Date.parse(dateStrA) : 0;
      valB = dateStrB ? Date.parse(dateStrB) : 0;
      if (isNaN(valA)) valA = 0;
      if (isNaN(valB)) valB = 0;
    } else {
      valA = parseInt(a.getAttribute("data-scraped") || "0", 10);
      valB = parseInt(b.getAttribute("data-scraped") || "0", 10);
    }

    if (sortVal.endsWith("desc")) {
      return valB - valA;
    } else {
      return valA - valB;
    }
  });

  // Re-append sorted rows
  rows.forEach((row) => tbody.appendChild(row));
}

document.addEventListener("DOMContentLoaded", function () {
  // If run_error is present on load, trigger the fade out timeout
  const banner = document.getElementById("quota-alert-banner");
  if (banner && banner.style.display === "flex") {
    banner.style.opacity = "1";
    banner.style.transform = "translateX(0)";
    quotaAlertTimeout = setTimeout(function () {
      banner.style.opacity = "0";
      banner.style.transform = "translateX(120%)";
      setTimeout(function () {
        banner.style.display = "none";
      }, 600);
    }, 5000);
  }

  document.querySelectorAll(".btn-view-summary").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const summary = this.getAttribute("data-summary");
      document.getElementById("summary-modal-content").innerText = summary;
      document.getElementById("summaryModal").style.display = "flex";
    });
  });

  document.querySelectorAll(".btn-summarize-manual").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const articleId = this.getAttribute("data-id");
      const originalHtml = this.innerHTML;
      this.disabled = true;
      this.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin-icon" style="width:12px;height:12px;display:inline-block;animation:spin 1.2s linear infinite;vertical-align:middle;margin-right:4px;">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 2a10 10 0 0 1 10 10" />
          </svg>
          Summarizing...
        `;
      this.style.opacity = "0.7";

      fetch(`/articles/${articleId}/summarize/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": "{{ csrf_token }}",
        },
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.success) {
            // Trigger refresh so new contacts / targets / summaries load
            location.reload();
          } else {
            let errMsg = data.error || "";
            if (
              errMsg.includes("RESOURCE_EXHAUSTED") ||
              errMsg.toLowerCase().includes("quota") ||
              errMsg.includes("spending cap")
            ) {
              errMsg = "You have exceeded your AI quota";
            } else {
              errMsg = errMsg || "Failed to generate AI summary.";
            }
            triggerQuotaAlert(errMsg);

            this.disabled = false;
            this.innerHTML = originalHtml;
            this.style.opacity = "1";
          }
        })
        .catch((err) => {
          console.error(err);
          let errMsg = err.message || "";
          if (
            errMsg.includes("RESOURCE_EXHAUSTED") ||
            errMsg.toLowerCase().includes("quota") ||
            errMsg.includes("spending cap")
          ) {
            errMsg = "You have exceeded your monthly quota";
          } else {
            errMsg = "Error executing manual AI summarization: " + errMsg;
          }
          triggerQuotaAlert(errMsg);

          this.disabled = false;
          this.innerHTML = originalHtml;
          this.style.opacity = "1";
        });
    });
  });

  document.querySelectorAll(".btn-move-intent").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const articleId = this.getAttribute("data-id");
      const originalHtml = this.innerHTML;
      this.disabled = true;
      this.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin-icon" style="width:12px;height:12px;display:inline-block;animation:spin 1.2s linear infinite;vertical-align:middle;margin-right:4px;">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 2a10 10 0 0 1 10 10" />
          </svg>
          Moving...
        `;
      this.style.opacity = "0.7";

      fetch(`/articles/${articleId}/summarize/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": "{{ csrf_token }}",
        },
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.success) {
            // Reload page to reflect dynamic state update
            location.reload();
          } else {
            let errMsg = data.error || "";
            if (
              errMsg.includes("RESOURCE_EXHAUSTED") ||
              errMsg.toLowerCase().includes("quota") ||
              errMsg.includes("spending cap")
            ) {
              errMsg = "You have exceeded your AI quota";
            } else {
              errMsg = errMsg || "Failed to move article to High Intent.";
            }
            triggerQuotaAlert(errMsg);

            this.disabled = false;
            this.innerHTML = originalHtml;
            this.style.opacity = "1";
          }
        })
        .catch((err) => {
          console.error(err);
          let errMsg = err.message || "";
          if (
            errMsg.includes("RESOURCE_EXHAUSTED") ||
            errMsg.toLowerCase().includes("quota") ||
            errMsg.includes("spending cap")
          ) {
            errMsg = "You have exceeded your monthly quota";
          } else {
            errMsg = "Error moving article: " + errMsg;
          }
          triggerQuotaAlert(errMsg);

          this.disabled = false;
          this.innerHTML = originalHtml;
          this.style.opacity = "1";
        });
    });
  });

  // Run initial sort on page load
  sortActivePanel();
});
