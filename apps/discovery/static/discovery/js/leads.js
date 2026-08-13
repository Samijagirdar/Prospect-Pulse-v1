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
  const checkboxes = document.querySelectorAll(".lead-checkbox");
  const toolbar = document.getElementById("selection-toolbar");
  const selectedCountSpan = document.getElementById("selected-count");
  const btnClear = document.getElementById("btn-clear-selection");

  function updateSelectionToolbar() {
    const checkedBoxes = document.querySelectorAll(".lead-checkbox:checked");
    const count = checkedBoxes.length;

    if (count > 0) {
      selectedCountSpan.innerText = count;
      toolbar.style.display = "flex";
    } else {
      toolbar.style.display = "none";
    }

    // Sync the Check-All checkbox state
    if (checkAll) {
      if (count === checkboxes.length && checkboxes.length > 0) {
        checkAll.checked = true;
        checkAll.indeterminate = false;
      } else if (count === 0) {
        checkAll.checked = false;
        checkAll.indeterminate = false;
      } else {
        checkAll.checked = false;
        checkAll.indeterminate = true;
      }
    }
  }

  if (checkAll) {
    checkAll.addEventListener("change", function () {
      checkboxes.forEach((cb) => {
        cb.checked = checkAll.checked;
      });
      updateSelectionToolbar();
    });
  }

  checkboxes.forEach((cb) => {
    cb.addEventListener("change", updateSelectionToolbar);
  });

  if (btnClear) {
    btnClear.addEventListener("click", function () {
      checkboxes.forEach((cb) => {
        cb.checked = false;
      });
      if (checkAll) {
        checkAll.checked = false;
        checkAll.indeterminate = false;
      }
      updateSelectionToolbar();
    });
  }

  function openCampaignModal(ids) {
    const modal = document.getElementById("campaignModal");
    const hiddenInput = document.getElementById("campaign-modal-lead-ids");
    const countSpan = document.getElementById("campaign-modal-count");

    if (!modal || !hiddenInput) return;

    hiddenInput.value = ids.join(",");
    if (countSpan) {
      countSpan.innerText = ids.length;
    }

    modal.style.display = "flex";
  }

  document.querySelectorAll(".btn-row-add-campaign").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const leadId = this.getAttribute("data-id");
      openCampaignModal([leadId]);
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
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = "Adding...";
      }

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

      const csrfTokenEl = document.querySelector("[name=csrfmiddlewaretoken]");
      const csrfToken = csrfTokenEl ? csrfTokenEl.value : "";

      fetch("/discovery/leads/add-to-campaign/", {
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
        .then((res) => res.json())
        .then((data) => {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
          }
          if (data.status === "success") {
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
                data.message || "Successfully added leads to campaign!";
              alertBanner.style.borderColor = "rgba(34, 197, 94, 0.45)";
              alertBanner.style.color = "#4ade80";
              alertBanner.style.display = "flex";
              setTimeout(() => {
                alertBanner.style.display = "none";
              }, 5000);
            }
          } else {
            const alertBanner = document.getElementById("quota-alert-banner");
            const alertMessage = document.getElementById("quota-alert-message");
            if (alertBanner && alertMessage) {
              alertMessage.innerText =
                data.message || "Failed to add leads to campaign.";
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

  document.querySelectorAll(".btn-view-article").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const title = this.getAttribute("data-title");
      const source = this.getAttribute("data-source");
      const url = this.getAttribute("data-url");

      document.getElementById("article-modal-title").innerText = title;
      document.getElementById("article-modal-source").innerText = source;
      document.getElementById("article-modal-link").setAttribute("href", url);

      document.getElementById("articleModal").style.display = "flex";
    });
  });
});
