let quotaAlertTimeout = null;

function getCsrfToken() {
  const meta = document.querySelector('input[name=csrfmiddlewaretoken]');
  if (meta && meta.value) return meta.value;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

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

  // Universal Unicode Decoder: Converts \uXXXX escape sequences into real characters
  function decodeUnicodeEscapes(str) {
    if (!str) return "";
    return str.replace(/\\u([0-9a-fA-F]{4})/g, function (_, hex) {
      return String.fromCharCode(parseInt(hex, 16));
    });
  }

  // Smart Bullet-Point Formatter: Transforms raw paragraphs or multiline summaries into modern bullet points
  function formatSummaryToBulletHTML(rawText) {
    if (!rawText || !rawText.trim()) {
      return '<div style="color: var(--muted); font-style: italic;">No summary available.</div>';
    }

    let text = rawText.trim();
    let lines = text.split(/[\r\n]+/).map((s) => s.trim()).filter(Boolean);
    let bullets = [];

    if (lines.length > 1) {
      bullets = lines
        .map((line) => line.replace(/^[•\-\*\d\.\)\s]+/, "").trim())
        .filter(Boolean);
    } else {
      // Single paragraph: Protect common abbreviations before sentence boundary split
      const abbrevs = [
        [/\bU\.S\./gi, "U_DOT_S_DOT_"],
        [/\bU\.K\./gi, "U_DOT_K_DOT_"],
        [/\be\.g\./gi, "E_DOT_G_DOT_"],
        [/\bi\.e\./gi, "I_DOT_E_DOT_"],
        [/\bvs\./gi, "VS_DOT_"],
        [/\bInc\./gi, "INC_DOT_"],
        [/\bCorp\./gi, "CORP_DOT_"],
        [/\bCo\./gi, "CO_DOT_"],
        [/\bLtd\./gi, "LTD_DOT_"],
        [/\bDr\./gi, "DR_DOT_"],
        [/\bMr\./gi, "MR_DOT_"],
        [/\bMs\./gi, "MS_DOT_"],
      ];

      let protectedText = text;
      abbrevs.forEach(([pat, rep]) => {
        protectedText = protectedText.replace(pat, rep);
      });

      // Split sentences on [.!?] followed by whitespace and a capital letter, digit, or quote
      const sentences = protectedText.split(/(?<=[.!?])\s+(?=[A-Z0-9"“'\(])/);

      bullets = sentences
        .map((s) => {
          let restored = s.trim();
          abbrevs.forEach(([pat, rep]) => {
            const original = pat.source.replace(/\\b/g, "").replace(/\\\./g, ".");
            restored = restored.split(rep).join(original);
          });
          return restored.replace(/^[•\-\*\d\.\)\s]+/, "").trim();
        })
        .filter((s) => s.length > 5);

      if (bullets.length === 0) {
        bullets = [text];
      }
    }

    // Build modern styled HTML list
    const itemsHtml = bullets
      .map((b) => {
        const escaped = b
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");

        return `
        <li style="display: flex; align-items: flex-start; gap: 10px; line-height: 1.6; color: var(--text); font-size: 13.5px;">
          <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); margin-top: 7px; flex-shrink: 0;"></span>
          <span style="flex: 1;">${escaped}</span>
        </li>
      `;
      })
      .join("");

    return `<ul style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 12px;">${itemsHtml}</ul>`;
  }

  document.querySelectorAll(".btn-view-summary").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const hiddenSummary = this.closest("td")?.querySelector(".article-summary-data");
      let summary = hiddenSummary ? hiddenSummary.textContent : (this.getAttribute("data-summary") || "");
      summary = decodeUnicodeEscapes(summary.trim());
      document.getElementById("summary-modal-content").innerHTML = formatSummaryToBulletHTML(summary);
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
          "X-CSRFToken": getCsrfToken(),
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

      fetch(`/articles/${articleId}/move-intent/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCsrfToken(),
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
