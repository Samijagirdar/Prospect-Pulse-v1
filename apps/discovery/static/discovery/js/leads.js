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
}

document.addEventListener("DOMContentLoaded", function () {
  // Checkbox and selection toolbar logic
  const checkAll = document.getElementById("check-all-leads");
  const toolbar = document.getElementById("selection-toolbar");
  const selectedCountSpan = document.getElementById("selected-count");
  const btnClear = document.getElementById("btn-clear-selection");
  const leadsTbody = document.getElementById("leads-tbody");

  // Gmail-style promotional multi-page elements
  const selectAllPagesWrapper = document.getElementById("select-all-pages-wrapper");
  const btnSelectAllPages = document.getElementById("btn-select-all-pages");
  const selectAllTotalCount = document.getElementById("select-all-total-count");
  const allPagesSelectedNotice = document.getElementById("all-pages-selected-notice");
  const allPagesTotalCount = document.getElementById("all-pages-total-count");

  // --- Leads Pagination Controller ---
  const paginationBar = document.getElementById("leads-pagination-bar");
  const countStartEl = document.getElementById("leads-count-start");
  const countEndEl = document.getElementById("leads-count-end");
  const countTotalEl = document.getElementById("leads-count-total");
  const perPageSelect = document.getElementById("leads-per-page-select");
  const prevBtn = document.getElementById("leads-page-prev");
  const nextBtn = document.getElementById("leads-page-next");
  const pageNumbersEl = document.getElementById("leads-page-numbers");

  let currentPage = 1;
  let pageSize = perPageSelect ? parseInt(perPageSelect.value, 10) || 25 : 25;

  function getLeadRows() {
    return Array.from(
      document.querySelectorAll("#leads-tbody tr.lead-row-item, #leads-tbody tr[id^='lead-row-']")
    ).filter((r) => !r.classList.contains("empty-placeholder-row"));
  }

  function syncCheckAllState() {
    if (!checkAll) return;
    const visibleBoxes = Array.from(
      document.querySelectorAll("#leads-tbody tr.lead-row-item:not([style*='display: none']) .lead-checkbox")
    );
    const checkedBoxes = visibleBoxes.filter((cb) => cb.checked);

    if (visibleBoxes.length > 0 && checkedBoxes.length === visibleBoxes.length) {
      checkAll.checked = true;
      checkAll.indeterminate = false;
    } else if (checkedBoxes.length === 0) {
      checkAll.checked = false;
      checkAll.indeterminate = false;
    } else {
      checkAll.checked = false;
      checkAll.indeterminate = true;
    }
  }

  function updateSelectionToolbar() {
    const allRowBoxes = Array.from(document.querySelectorAll("#leads-tbody tr.lead-row-item .lead-checkbox"));
    const checkedBoxes = Array.from(document.querySelectorAll(".lead-checkbox:checked"));
    const count = checkedBoxes.length;

    if (count > 0) {
      if (selectedCountSpan) selectedCountSpan.innerText = count;
      if (toolbar) toolbar.style.display = "flex";
    } else {
      if (toolbar) toolbar.style.display = "none";
    }

    // Gmail-style promotional banner state
    const visibleBoxes = Array.from(
      document.querySelectorAll("#leads-tbody tr.lead-row-item:not([style*='display: none']) .lead-checkbox")
    );
    const visibleChecked = visibleBoxes.filter((cb) => cb.checked);
    const totalLeads = allRowBoxes.length;

    if (totalLeads > 0 && count === totalLeads && totalLeads > visibleBoxes.length) {
      // All leads across all pages are selected
      if (selectAllPagesWrapper) selectAllPagesWrapper.style.display = "none";
      if (allPagesSelectedNotice) {
        if (allPagesTotalCount) allPagesTotalCount.innerText = totalLeads;
        allPagesSelectedNotice.style.display = "inline";
      }
    } else if (visibleBoxes.length > 0 && visibleChecked.length === visibleBoxes.length && totalLeads > visibleBoxes.length) {
      // Exactly this page is fully selected, but not all pages yet -> show promo link
      if (selectAllPagesWrapper) {
        if (selectAllTotalCount) selectAllTotalCount.innerText = totalLeads;
        selectAllPagesWrapper.style.display = "inline";
      }
      if (allPagesSelectedNotice) allPagesSelectedNotice.style.display = "none";
    } else {
      // Partial selection or single page
      if (selectAllPagesWrapper) selectAllPagesWrapper.style.display = "none";
      if (allPagesSelectedNotice) allPagesSelectedNotice.style.display = "none";
    }

    syncCheckAllState();
  }

  function renderLeadsPagination() {
    if (!paginationBar) return;
    const rows = getLeadRows();
    const total = rows.length;

    if (total === 0) {
      paginationBar.style.display = "none";
      return;
    }
    paginationBar.style.display = "flex";

    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIdx = (currentPage - 1) * pageSize;
    const endIdx = Math.min(startIdx + pageSize, total);

    rows.forEach((row, idx) => {
      if (idx >= startIdx && idx < endIdx) {
        row.style.display = "";
      } else {
        row.style.display = "none";
      }
    });

    if (countStartEl) countStartEl.innerText = total === 0 ? 0 : startIdx + 1;
    if (countEndEl) countEndEl.innerText = endIdx;
    if (countTotalEl) countTotalEl.innerText = total;

    // Update Previous and Next buttons
    if (prevBtn) {
      prevBtn.disabled = currentPage <= 1;
      prevBtn.style.opacity = currentPage <= 1 ? "0.45" : "1";
      prevBtn.style.cursor = currentPage <= 1 ? "not-allowed" : "pointer";
    }
    if (nextBtn) {
      nextBtn.disabled = currentPage >= totalPages;
      nextBtn.style.opacity = currentPage >= totalPages ? "0.45" : "1";
      nextBtn.style.cursor = currentPage >= totalPages ? "not-allowed" : "pointer";
    }

    // Build page number pills
    if (pageNumbersEl) {
      pageNumbersEl.innerHTML = "";
      for (let p = 1; p <= totalPages; p++) {
        if (
          totalPages <= 7 ||
          p === 1 ||
          p === totalPages ||
          (p >= currentPage - 1 && p <= currentPage + 1)
        ) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "btn btn-sm btn-page-number" + (p === currentPage ? " active" : "");
          btn.innerText = p;
          btn.style.cssText =
            p === currentPage
              ? "padding: 4px 10px; font-size: 12px; font-weight: 700; border-radius: 6px; background: var(--accent); color: #fff; border: 1px solid var(--accent); min-width: 30px; cursor: default;"
              : "padding: 4px 10px; font-size: 12px; font-weight: 600; border-radius: 6px; background: var(--surface); color: var(--text); border: 1px solid var(--border); min-width: 30px; cursor: pointer;";
          btn.onclick = () => {
            if (currentPage !== p) {
              currentPage = p;
              renderLeadsPagination();
            }
          };
          pageNumbersEl.appendChild(btn);
        } else if (
          (p === 2 && currentPage > 3) ||
          (p === totalPages - 1 && currentPage < totalPages - 2)
        ) {
          if (!pageNumbersEl.querySelector(`.ellipsis-${p}`)) {
            const span = document.createElement("span");
            span.className = `ellipsis-${p}`;
            span.innerText = "…";
            span.style.cssText = "padding: 0 4px; color: var(--muted); font-size: 12px;";
            pageNumbersEl.appendChild(span);
          }
        }
      }
    }

    syncCheckAllState();
  }

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        renderLeadsPagination();
      }
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      const rows = getLeadRows();
      const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
      if (currentPage < totalPages) {
        currentPage++;
        renderLeadsPagination();
      }
    });
  }

  if (perPageSelect) {
    perPageSelect.addEventListener("change", function () {
      pageSize = parseInt(this.value, 10) || 25;
      currentPage = 1;
      renderLeadsPagination();
    });
  }

  window.refreshLeadsPagination = renderLeadsPagination;

  // Initialize pagination immediately
  renderLeadsPagination();

  // Check-all listener (checks/unchecks visible rows on current page)
  if (checkAll) {
    checkAll.addEventListener("change", function () {
      if (checkAll.checked) {
        const visibleCheckboxes = document.querySelectorAll(
          "#leads-tbody tr.lead-row-item:not([style*='display: none']) .lead-checkbox"
        );
        visibleCheckboxes.forEach((cb) => {
          cb.checked = true;
        });
      } else {
        // Unchecking check-all deselects ALL leads (both visible and hidden)
        document.querySelectorAll(".lead-checkbox").forEach((cb) => {
          cb.checked = false;
        });
        if (selectAllPagesWrapper) selectAllPagesWrapper.style.display = "none";
        if (allPagesSelectedNotice) allPagesSelectedNotice.style.display = "none";
      }
      updateSelectionToolbar();
    });
  }

  // Multi-page promotional link listener: promotes selection to ALL leads across all pages
  if (btnSelectAllPages) {
    btnSelectAllPages.addEventListener("click", function (e) {
      e.preventDefault();
      const allRowBoxes = document.querySelectorAll("#leads-tbody tr.lead-row-item .lead-checkbox");
      allRowBoxes.forEach((cb) => {
        cb.checked = true;
      });
      updateSelectionToolbar();
    });
  }

  // Delegated listener for individual checkboxes
  if (leadsTbody) {
    leadsTbody.addEventListener("change", function (e) {
      if (e.target && e.target.classList.contains("lead-checkbox")) {
        updateSelectionToolbar();
      }
    });
  }

  // Direct listeners for initial checkboxes
  document.querySelectorAll(".lead-checkbox").forEach((cb) => {
    cb.addEventListener("change", updateSelectionToolbar);
  });

  if (btnClear) {
    btnClear.addEventListener("click", function () {
      document.querySelectorAll(".lead-checkbox").forEach((cb) => {
        cb.checked = false;
      });
      if (checkAll) {
        checkAll.checked = false;
        checkAll.indeterminate = false;
      }
      if (selectAllPagesWrapper) selectAllPagesWrapper.style.display = "none";
      if (allPagesSelectedNotice) allPagesSelectedNotice.style.display = "none";
      updateSelectionToolbar();
    });
  }

  let activeModalLeads = [];

  function openCampaignModal(ids, singleLeadData = null) {
    const modal = document.getElementById("campaignModal");
    const hiddenInput = document.getElementById("campaign-modal-lead-ids");
    const countSpan = document.getElementById("campaign-modal-count");
    const modalError = document.getElementById("campaign-modal-error");
    const modalErrorText = document.getElementById("campaign-modal-error-text");

    if (!modal || !hiddenInput) return;

    if (modalError) modalError.style.display = "none";
    if (modalErrorText) modalErrorText.innerText = "";

    hiddenInput.value = ids.join(",");
    if (countSpan) {
      countSpan.innerText = ids.length;
    }

    if (singleLeadData) {
      activeModalLeads = [singleLeadData];
    } else {
      activeModalLeads = [];
      ids.forEach((id) => {
        const el = document.querySelector(`.lead-checkbox[data-id="${id}"]`) || document.querySelector(`.btn-row-add-campaign[data-id="${id}"]`);
        if (el) {
          activeModalLeads.push({
            id: id,
            name: el.getAttribute("data-name") || `Lead #${id}`,
            email: (el.getAttribute("data-email") || "").trim(),
            phone: (el.getAttribute("data-phone") || "").trim(),
          });
        }
      });
    }

    modal.style.display = "flex";
  }
  window.openCampaignModal = openCampaignModal;

  document.querySelectorAll(".btn-row-add-campaign").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const leadId = this.getAttribute("data-id");
      const leadData = {
        id: leadId,
        name: this.getAttribute("data-name") || `Lead #${leadId}`,
        email: (this.getAttribute("data-email") || "").trim(),
        phone: (this.getAttribute("data-phone") || "").trim(),
      };
      openCampaignModal([leadId], leadData);
    });
  });

  const btnBulkAdd = document.getElementById("btn-bulk-add-campaign");
  if (btnBulkAdd) {
    btnBulkAdd.addEventListener("click", function (e) {
      e.preventDefault();
      const checkedBoxes = document.querySelectorAll(".lead-checkbox:checked");
      const ids = Array.from(checkedBoxes).map((cb) =>
        cb.getAttribute("data-id"),
      );
      openCampaignModal(ids);
    });
  }

  const campaignForm = document.getElementById("campaign-modal-form");
  if (campaignForm) {
    campaignForm.addEventListener("submit", function (e) {
      e.preventDefault();
      const submitBtn = campaignForm.querySelector("button[type='submit']");
      const originalText = submitBtn ? submitBtn.innerHTML : "Add to Campaign";

      const leadIds = document.getElementById("campaign-modal-lead-ids").value;
      const callCampaignSelect = document.getElementById(
        "call-campaign-select",
      );
      const emailCampaignSelect = document.getElementById(
        "email-campaign-select",
      );
      const callCampaignId = callCampaignSelect ? callCampaignSelect.value : "";
      const emailCampaignId = emailCampaignSelect
        ? emailCampaignSelect.value
        : "";
      const modalError = document.getElementById("campaign-modal-error");
      const modalErrorText = document.getElementById("campaign-modal-error-text");

      // Reset modal error display
      if (modalError) modalError.style.display = "none";
      if (modalErrorText) modalErrorText.innerText = "";

      if (!callCampaignId && !emailCampaignId) {
        if (modalError && modalErrorText) {
          modalErrorText.innerText = "Please select at least one campaign (Call or Email).";
          modalError.style.display = "flex";
        }
        return;
      }

      // Fast Client-Side Contact Verification
      function isValidPhone(p) {
        return Boolean(p && !["—", "-", "None", "null", "N/A", "n/a"].includes(p));
      }

      function isValidEmail(em) {
        return Boolean(em && !["—", "-", "None", "null", "N/A", "n/a"].includes(em) && em.includes("@"));
      }

      let clientErrors = [];

      if (callCampaignId && activeModalLeads.length > 0) {
        const missingPhone = activeModalLeads.filter((l) => !isValidPhone(l.phone));
        if (missingPhone.length === 1) {
          clientErrors.push(`Cannot add to Call Campaign: '${missingPhone[0].name}' does not have a phone number.`);
        } else if (missingPhone.length > 1) {
          const names = missingPhone.slice(0, 3).map((l) => l.name).join(", ");
          const suffix = missingPhone.length > 3 ? ` and ${missingPhone.length - 3} more` : "";
          clientErrors.push(`Cannot add to Call Campaign: ${missingPhone.length} lead(s) (${names}${suffix}) do not have a phone number.`);
        }
      }

      if (emailCampaignId && activeModalLeads.length > 0) {
        const missingEmail = activeModalLeads.filter((l) => !isValidEmail(l.email));
        if (missingEmail.length === 1) {
          clientErrors.push(`Cannot add to Email Campaign: '${missingEmail[0].name}' does not have an email address.`);
        } else if (missingEmail.length > 1) {
          const names = missingEmail.slice(0, 3).map((l) => l.name).join(", ");
          const suffix = missingEmail.length > 3 ? ` and ${missingEmail.length - 3} more` : "";
          clientErrors.push(`Cannot add to Email Campaign: ${missingEmail.length} lead(s) (${names}${suffix}) do not have an email address.`);
        }
      }

      if (clientErrors.length > 0) {
        if (modalError && modalErrorText) {
          modalErrorText.innerText = clientErrors.join(" ");
          modalError.style.display = "flex";
        }
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = "Adding...";
      }

      const csrfTokenEl = document.querySelector("[name=csrfmiddlewaretoken]");
      const csrfToken = csrfTokenEl ? csrfTokenEl.value : "";

      fetch("/leads/add-to-campaign/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({
          lead_ids: leadIds,
          call_campaign_id: callCampaignId,
          email_campaign_id: emailCampaignId,
        }),
      })
        .then((res) => res.json().then(data => ({ status: res.status, ok: res.ok, body: data })))
        .then(({ status, ok, body }) => {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
          }
          if (ok && body.status === "success") {
            document.getElementById("campaignModal").style.display = "none";
            checkboxes.forEach((cb) => (cb.checked = false));
            if (checkAll) {
              checkAll.checked = false;
              checkAll.indeterminate = false;
            }
            updateSelectionToolbar();

            const alertBanner = document.getElementById("quota-alert-banner");
            const alertMessage = document.getElementById("quota-alert-message");
            if (alertBanner && alertMessage) {
              alertMessage.innerText =
                body.message || "Successfully added leads to campaign!";
              alertBanner.style.borderColor = "rgba(34, 197, 94, 0.45)";
              alertBanner.style.color = "#4ade80";
              alertBanner.style.display = "flex";
              setTimeout(() => {
                alertBanner.style.display = "none";
              }, 5000);
            }
          } else {
            // Validation error or server failure - display in modal
            if (modalError && modalErrorText) {
              modalErrorText.innerText =
                body.message || "Failed to add leads to campaign.";
              modalError.style.display = "flex";
            }
            const alertBanner = document.getElementById("quota-alert-banner");
            const alertMessage = document.getElementById("quota-alert-message");
            if (alertBanner && alertMessage) {
              alertMessage.innerText =
                body.message || "Failed to add leads to campaign.";
              alertBanner.style.borderColor = "rgba(220, 38, 38, 0.45)";
              alertBanner.style.color = "#f87171";
              alertBanner.style.display = "flex";
            }
          }
        })
        .catch((err) => {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
          }
          if (modalError && modalErrorText) {
            modalErrorText.innerText = "Network error while adding leads to campaign.";
            modalError.style.display = "flex";
          }
          const alertBanner = document.getElementById("quota-alert-banner");
          const alertMessage = document.getElementById("quota-alert-message");
          if (alertBanner && alertMessage) {
            alertMessage.innerText = "Failed to add leads to campaign.";
            alertBanner.style.borderColor = "rgba(220, 38, 38, 0.45)";
            alertBanner.style.color = "#f87171";
            alertBanner.style.display = "flex";
          }
        });
    });
  }

  function performEnrichment(leadIds, triggerBtn) {
    if (!leadIds || leadIds.length === 0) return;

    const originalHTML = triggerBtn ? triggerBtn.innerHTML : "";
    if (triggerBtn) {
      triggerBtn.disabled = true;
      triggerBtn.innerText = "Enriching...";
    }

    const csrfTokenEl = document.querySelector("[name=csrfmiddlewaretoken]");
    const csrfToken = csrfTokenEl ? csrfTokenEl.value : "";

    fetch("/discovery/leads/enrich/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({ lead_ids: leadIds }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (triggerBtn) {
          triggerBtn.disabled = false;
          triggerBtn.innerHTML = originalHTML;
        }

        const alertBanner = document.getElementById("quota-alert-banner");
        const alertMessage = document.getElementById("quota-alert-message");

        if (data.status === "success") {
          checkboxes.forEach((cb) => (cb.checked = false));
          if (checkAll) {
            checkAll.checked = false;
            checkAll.indeterminate = false;
          }
          updateSelectionToolbar();

          if (alertBanner && alertMessage) {
            alertMessage.innerText =
              data.message || "Successfully enriched lead(s)!";
            alertBanner.style.borderColor = "rgba(34, 197, 94, 0.45)";
            alertBanner.style.color = "#4ade80";
            alertBanner.style.display = "flex";
            setTimeout(() => {
              alertBanner.style.display = "none";
            }, 5000);
          }
        } else {
          if (alertBanner && alertMessage) {
            alertMessage.innerText =
              data.message || "Failed to enrich lead(s).";
            alertBanner.style.borderColor = "rgba(220, 38, 38, 0.45)";
            alertBanner.style.color = "#f87171";
            alertBanner.style.display = "flex";
          }
        }
      })
      .catch((err) => {
        if (triggerBtn) {
          triggerBtn.disabled = false;
          triggerBtn.innerHTML = originalHTML;
        }
        const alertBanner = document.getElementById("quota-alert-banner");
        const alertMessage = document.getElementById("quota-alert-message");
        if (alertBanner && alertMessage) {
          alertMessage.innerText = "Failed to enrich lead(s).";
          alertBanner.style.borderColor = "rgba(220, 38, 38, 0.45)";
          alertBanner.style.color = "#f87171";
          alertBanner.style.display = "flex";
        }
      });
  }
  window.performEnrichment = performEnrichment;

  document.querySelectorAll(".btn-row-enrich").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const leadId = this.getAttribute("data-id");
      performEnrichment([leadId], this);
    });
  });

  const btnBulkEnrich = document.getElementById("btn-bulk-enrich");
  if (btnBulkEnrich) {
    btnBulkEnrich.addEventListener("click", function (e) {
      e.preventDefault();
      const checkedBoxes = document.querySelectorAll(".lead-checkbox:checked");
      const ids = Array.from(checkedBoxes).map((cb) =>
        cb.getAttribute("data-id"),
      );
      performEnrichment(ids, this);
    });
  }

  function performMoveToCRM(leadIds, triggerBtn) {
    if (!leadIds || leadIds.length === 0) return;

    const originalHTML = triggerBtn ? triggerBtn.innerHTML : "";
    if (triggerBtn) {
      triggerBtn.disabled = true;
      triggerBtn.innerText = "Moving...";
    }

    const csrfTokenEl = document.querySelector("[name=csrfmiddlewaretoken]");
    const csrfToken = csrfTokenEl ? csrfTokenEl.value : "";

    fetch("/discovery/leads/move-to-crm/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({ lead_ids: leadIds }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (triggerBtn) {
          triggerBtn.disabled = false;
          triggerBtn.innerHTML = originalHTML;
        }

        const alertBanner = document.getElementById("quota-alert-banner");
        const alertMessage = document.getElementById("quota-alert-message");

        if (data.status === "success") {
          checkboxes.forEach((cb) => (cb.checked = false));
          if (checkAll) {
            checkAll.checked = false;
            checkAll.indeterminate = false;
          }
          updateSelectionToolbar();

          if (alertBanner && alertMessage) {
            alertMessage.innerText =
              data.message || "Successfully moved lead(s) to Agentyne CRM!";
            alertBanner.style.borderColor = "rgba(34, 197, 94, 0.45)";
            alertBanner.style.color = "#4ade80";
            alertBanner.style.display = "flex";
            setTimeout(() => {
              alertBanner.style.display = "none";
            }, 5000);
          }
        } else {
          if (alertBanner && alertMessage) {
            alertMessage.innerText =
              data.message || "Failed to move leads to CRM.";
            alertBanner.style.borderColor = "rgba(220, 38, 38, 0.45)";
            alertBanner.style.color = "#f87171";
            alertBanner.style.display = "flex";
          }
        }
      })
      .catch((err) => {
        if (triggerBtn) {
          triggerBtn.disabled = false;
          triggerBtn.innerHTML = originalHTML;
        }
        const alertBanner = document.getElementById("quota-alert-banner");
        const alertMessage = document.getElementById("quota-alert-message");
        if (alertBanner && alertMessage) {
          alertMessage.innerText = "Failed to move leads to CRM.";
          alertBanner.style.borderColor = "rgba(220, 38, 38, 0.45)";
          alertBanner.style.color = "#f87171";
          alertBanner.style.display = "flex";
        }
      });
  }

  document.querySelectorAll(".btn-row-crm").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const leadId = this.getAttribute("data-id");
      performMoveToCRM([leadId], this);
    });
  });

  const btnBulkCRM = document.getElementById("btn-bulk-crm");
  if (btnBulkCRM) {
    btnBulkCRM.addEventListener("click", function (e) {
      e.preventDefault();
      const checkedBoxes = document.querySelectorAll(".lead-checkbox:checked");
      const ids = Array.from(checkedBoxes).map((cb) =>
        cb.getAttribute("data-id"),
      );
      performMoveToCRM(ids, this);
    });
  }

  function performBulkExport(triggerBtn) {
    const checkedBoxes = document.querySelectorAll(".lead-checkbox:checked");
    const ids = Array.from(checkedBoxes).map((cb) => cb.getAttribute("data-id")).filter(Boolean);

    if (!ids || ids.length === 0) {
      alert("Please select at least one lead to export.");
      return;
    }

    const formatSelect = document.getElementById("bulk-export-format");
    const format = formatSelect ? formatSelect.value : "excel";
    const pulseName = triggerBtn ? (triggerBtn.getAttribute("data-pulse-name") || "").trim() : "";

    const originalHTML = triggerBtn ? triggerBtn.innerHTML : "Export";
    if (triggerBtn) {
      triggerBtn.disabled = true;
      triggerBtn.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation: spin 1s linear infinite; display: inline-block;">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-opacity="0.25"></circle>
          <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor"></path>
        </svg>
        Exporting...
      `;
    }

    const csrfTokenEl = document.querySelector("[name=csrfmiddlewaretoken]");
    const csrfToken = csrfTokenEl ? csrfTokenEl.value : "";

    fetch("/leads/export/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({
        lead_ids: ids,
        format: format,
        pulse_name: pulseName,
      }),
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().then((err) => {
            throw new Error(err.message || "Export failed.");
          });
        }
        const cleanPulse = pulseName.replace(/[^\w\-]+/g, '_').replace(/^_+|_+$/g, '').toLowerCase();
        let fallbackPrefix = cleanPulse ? `prospectpulse_leads_${cleanPulse}` : 'prospectpulse_leads';
        let filename = `${fallbackPrefix}.${format === 'doc' ? 'docx' : format === 'pdf' ? 'pdf' : 'xlsx'}`;
        const disposition = res.headers.get("Content-Disposition");
        if (disposition && disposition.includes("filename=")) {
          const match = disposition.match(/filename="?([^";]+)"?/);
          if (match && match[1]) {
            filename = match[1];
          }
        }
        return res.blob().then((blob) => ({ blob, filename }));
      })
      .then(({ blob, filename }) => {
        if (triggerBtn) {
          triggerBtn.disabled = false;
          triggerBtn.innerHTML = originalHTML;
        }

        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);

        const alertBanner = document.getElementById("quota-alert-banner");
        const alertMessage = document.getElementById("quota-alert-message");
        if (alertBanner && alertMessage) {
          alertMessage.innerText = `Successfully exported ${ids.length} lead(s) as ${format.toUpperCase()}!`;
          alertBanner.style.borderColor = "rgba(34, 197, 94, 0.45)";
          alertBanner.style.color = "#4ade80";
          alertBanner.style.display = "flex";
          setTimeout(() => {
            alertBanner.style.display = "none";
          }, 4000);
        }
      })
      .catch((err) => {
        if (triggerBtn) {
          triggerBtn.disabled = false;
          triggerBtn.innerHTML = originalHTML;
        }
        const alertBanner = document.getElementById("quota-alert-banner");
        const alertMessage = document.getElementById("quota-alert-message");
        if (alertBanner && alertMessage) {
          alertMessage.innerText = err.message || "Failed to export leads.";
          alertBanner.style.borderColor = "rgba(220, 38, 38, 0.45)";
          alertBanner.style.color = "#f87171";
          alertBanner.style.display = "flex";
        }
      });
  }

  const btnBulkExport = document.getElementById("btn-bulk-export");
  if (btnBulkExport) {
    btnBulkExport.addEventListener("click", function (e) {
      e.preventDefault();
      performBulkExport(this);
    });
  }

  // Universal Unicode Decoder: Converts \uXXXX escape sequences into real characters
  function decodeUnicodeEscapes(str) {
    if (!str) return "";
    return str.replace(/\\u([0-9a-fA-F]{4})/g, function (_, hex) {
      return String.fromCharCode(parseInt(hex, 16));
    });
  }

  document.querySelectorAll(".btn-view-article").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const title = decodeUnicodeEscapes(this.getAttribute("data-title") || "Source Article");
      const source = decodeUnicodeEscapes(this.getAttribute("data-source") || "Verified Source");
      const url = this.getAttribute("data-url") || "#";

      document.getElementById("article-modal-title").innerText = title;
      document.getElementById("article-modal-source").innerText = source;
      const linkEl = document.getElementById("article-modal-link");
      if (linkEl) {
        if (url && url !== "#") {
          linkEl.setAttribute("href", url);
          linkEl.style.display = "inline-flex";
        } else {
          linkEl.removeAttribute("href");
          linkEl.style.display = "none";
        }
      }

      document.getElementById("articleModal").style.display = "flex";
    });
  });

  // ==========================================
  // LEAD INFORMATION CARD MODAL LOGIC
  // ==========================================
  let activeLeadCardData = null;

  function getLeadInitials(name) {
    if (!name) return "LD";
    const clean = name.trim();
    if (!clean) return "LD";
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length === 1) {
      return parts[0].substring(0, 2).toUpperCase();
    }
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function openLeadCardModal(leadData) {
    activeLeadCardData = leadData;
    const modal = document.getElementById("leadDetailModal");
    if (!modal) return;

    // Avatar and Initials
    const avatarEl = document.getElementById("lead-card-avatar");
    if (avatarEl) {
      avatarEl.innerText = getLeadInitials(leadData.name);
    }

    // Name
    const nameEl = document.getElementById("lead-card-name");
    if (nameEl) {
      nameEl.innerText = decodeUnicodeEscapes(leadData.name || "Lead Details");
    }

    // Score Badge
    const scoreBadgeEl = document.getElementById("lead-card-score-badge");
    if (scoreBadgeEl) {
      const scoreVal = leadData.score ? leadData.score : "50";
      scoreBadgeEl.innerText = `${scoreVal} Intent Score`;
    }

    // Designation / Role
    const desigEl = document.getElementById("lead-card-designation");
    if (desigEl) {
      desigEl.innerText = decodeUnicodeEscapes(leadData.designation || "Decision Maker / Key Contact");
    }

    // Account / Company
    const accountEl = document.getElementById("lead-card-account");
    if (accountEl) {
      accountEl.innerText = decodeUnicodeEscapes(leadData.account || "—");
    }

    // Phone
    const phoneEl = document.getElementById("lead-card-phone");
    const phoneStatusEl = document.getElementById("lead-card-phone-status");
    const hasPhone = Boolean(
      leadData.phone &&
      !["—", "-", "None", "null", "N/A", "n/a"].includes(leadData.phone.trim())
    );

    if (phoneEl) {
      if (hasPhone) {
        phoneEl.innerText = leadData.phone;
        phoneEl.setAttribute("href", `tel:${leadData.phone}`);
        phoneEl.style.color = "var(--accent)";
        phoneEl.style.textDecoration = "underline";
      } else {
        phoneEl.innerText = "Not Available";
        phoneEl.removeAttribute("href");
        phoneEl.style.color = "var(--muted)";
        phoneEl.style.textDecoration = "none";
      }
    }

    if (phoneStatusEl) {
      if (hasPhone) {
        phoneStatusEl.innerText = "Verified";
        phoneStatusEl.style.background = "rgba(22, 163, 74, 0.1)";
        phoneStatusEl.style.color = "#16a34a";
        phoneStatusEl.style.border = "1px solid rgba(22, 163, 74, 0.25)";
      } else {
        phoneStatusEl.innerText = "Missing";
        phoneStatusEl.style.background = "rgba(220, 38, 38, 0.1)";
        phoneStatusEl.style.color = "#ef4444";
        phoneStatusEl.style.border = "1px solid rgba(220, 38, 38, 0.25)";
      }
    }

    // Email
    const emailEl = document.getElementById("lead-card-email");
    const emailStatusEl = document.getElementById("lead-card-email-status");
    const hasEmail = Boolean(
      leadData.email &&
      !["—", "-", "None", "null", "N/A", "n/a"].includes(leadData.email.trim()) &&
      leadData.email.includes("@")
    );

    if (emailEl) {
      if (hasEmail) {
        emailEl.innerText = leadData.email;
        emailEl.setAttribute("href", `mailto:${leadData.email}`);
        emailEl.style.color = "var(--accent)";
        emailEl.style.textDecoration = "underline";
      } else {
        emailEl.innerText = "Not Available";
        emailEl.removeAttribute("href");
        emailEl.style.color = "var(--muted)";
        emailEl.style.textDecoration = "none";
      }
    }

    if (emailStatusEl) {
      if (hasEmail) {
        emailStatusEl.innerText = "Verified";
        emailStatusEl.style.background = "rgba(22, 163, 74, 0.1)";
        emailStatusEl.style.color = "#16a34a";
        emailStatusEl.style.border = "1px solid rgba(22, 163, 74, 0.25)";
      } else {
        emailStatusEl.innerText = "Missing";
        emailStatusEl.style.background = "rgba(220, 38, 38, 0.1)";
        emailStatusEl.style.color = "#ef4444";
        emailStatusEl.style.border = "1px solid rgba(220, 38, 38, 0.25)";
      }
    }

    // Intent Signal & Rationale
    const signalEl = document.getElementById("lead-card-signal");
    if (signalEl) {
      signalEl.innerText = decodeUnicodeEscapes(leadData.signal || "General B2B Intent");
    }
    const reasonEl = document.getElementById("lead-card-reason");
    if (reasonEl) {
      reasonEl.innerText = leadData.reason
        ? `“${decodeUnicodeEscapes(leadData.reason)}”`
        : "Extracted automatically by AI Prospect Pulse engine based on ICP buying signals.";
    }

    // Source Extracted From
    const sourceTitleEl = document.getElementById("lead-card-source-title");
    if (sourceTitleEl) {
      sourceTitleEl.innerText = decodeUnicodeEscapes(leadData.sourceTitle || "Intelligence Source Article");
    }
    const sourcePublisherEl = document.getElementById("lead-card-source-publisher");
    if (sourcePublisherEl) {
      sourcePublisherEl.innerText = decodeUnicodeEscapes(leadData.sourcePublisher || "Verified Publisher");
    }
    const sourceDateEl = document.getElementById("lead-card-source-date");
    if (sourceDateEl) {
      sourceDateEl.innerText = leadData.sourceDate ? `• ${leadData.sourceDate}` : "";
    }
    const sourceLinkEl = document.getElementById("lead-card-source-link");
    if (sourceLinkEl) {
      if (leadData.sourceUrl) {
        sourceLinkEl.setAttribute("href", leadData.sourceUrl);
        sourceLinkEl.style.display = "inline-flex";
      } else {
        sourceLinkEl.removeAttribute("href");
        sourceLinkEl.style.display = "none";
      }
    }

    modal.style.display = "flex";
  }
  window.openLeadCardModal = openLeadCardModal;

  // Bind click on lead card triggers (both table row lead names & actions icon buttons)
  document.querySelectorAll(".btn-lead-card-trigger").forEach((trigger) => {
    trigger.addEventListener("click", function (e) {
      e.preventDefault();
      const leadData = {
        id: this.getAttribute("data-id"),
        name: this.getAttribute("data-name") || "Lead Details",
        designation: this.getAttribute("data-designation") || "",
        account: this.getAttribute("data-account") || "",
        email: (this.getAttribute("data-email") || "").trim(),
        phone: (this.getAttribute("data-phone") || "").trim(),
        score: this.getAttribute("data-score") || "50",
        signal: this.getAttribute("data-signal") || "General B2B Intent",
        reason: this.getAttribute("data-reason") || "",
        sourceTitle: this.getAttribute("data-source-title") || "",
        sourceUrl: this.getAttribute("data-source-url") || "",
        sourcePublisher: this.getAttribute("data-source-publisher") || "",
        sourceDate: this.getAttribute("data-source-date") || "",
        assignedCampaign: this.getAttribute("data-assigned-campaign") || "",
      };
      openLeadCardModal(leadData);
    });
  });

  // Action: Add to Campaign from Lead Detail Modal
  const leadCardBtnCampaign = document.getElementById("lead-card-btn-campaign");
  if (leadCardBtnCampaign) {
    leadCardBtnCampaign.addEventListener("click", function (e) {
      e.preventDefault();
      if (!activeLeadCardData) return;
      const modal = document.getElementById("leadDetailModal");
      if (modal) modal.style.display = "none";
      openCampaignModal([activeLeadCardData.id], activeLeadCardData);
    });
  }

  // Action: Enrich from Lead Detail Modal
  const leadCardBtnEnrich = document.getElementById("lead-card-btn-enrich");
  if (leadCardBtnEnrich) {
    leadCardBtnEnrich.addEventListener("click", function (e) {
      e.preventDefault();
      if (!activeLeadCardData) return;
      performEnrichment([activeLeadCardData.id], this);
    });
  }

  // Backdrop click dismiss for modals
  window.addEventListener("click", function (e) {
    const leadModal = document.getElementById("leadDetailModal");
    if (leadModal && e.target === leadModal) {
      leadModal.style.display = "none";
    }
    const campModal = document.getElementById("campaignModal");
    if (campModal && e.target === campModal) {
      campModal.style.display = "none";
    }
    const artModal = document.getElementById("articleModal");
    if (artModal && e.target === artModal) {
      artModal.style.display = "none";
    }
  });

  // Escape key to dismiss modals
  window.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      const leadModal = document.getElementById("leadDetailModal");
      if (leadModal && leadModal.style.display === "flex") {
        leadModal.style.display = "none";
      }
      const campModal = document.getElementById("campaignModal");
      if (campModal && campModal.style.display === "flex") {
        campModal.style.display = "none";
      }
      const artModal = document.getElementById("articleModal");
      if (artModal && artModal.style.display === "flex") {
        artModal.style.display = "none";
      }
    }
  });
});
