// Prospect Pulse Detail View Dynamic JS Handlers

document.addEventListener('DOMContentLoaded', function() {
  // If active run is already executing on load, poll it
  const config = window.PULSE_CONFIG || {};
  if (config.activeRunId) {
    window.currentActiveRunId = config.activeRunId;
    pollRunStatus(config.activeRunId);
  }

  function showExpiredPulseModal(msg, editUrl) {
    const modal = document.getElementById('pulseExpiredModal');
    const msgEl = document.getElementById('pulseExpiredModalMsg');
    const editBtn = document.getElementById('pulseExpiredModalEditBtn');
    
    if (msgEl && msg) msgEl.innerText = msg;
    if (editBtn && editUrl) editBtn.href = editUrl;
    
    if (modal) {
      modal.style.display = 'flex';
    } else {
      triggerToastAlert(msg, 'warning');
    }
  }
  window.showExpiredPulseModal = showExpiredPulseModal;

  const discoveryForm = document.getElementById('run-discovery-form');
  if (discoveryForm) {
    discoveryForm.addEventListener('submit', function(e) {
      e.preventDefault();

      const config = window.PULSE_CONFIG || {};
      const isExpired = Boolean(config.isExpired || discoveryForm.dataset.isExpired === 'true');

      if (isExpired) {
        const endDate = config.endDateFormatted || discoveryForm.dataset.endDate || 'the configured date';
        const editUrl = config.editUrl || discoveryForm.dataset.editUrl || '#';
        const msg = `This pulse reached its end date on ${endDate}. Please edit your pulse and extend the end date to run discovery.`;
        showExpiredPulseModal(msg, editUrl);
        return false;
      }

      // Show track progress button, but keep modal hidden
      const trackBtn = document.getElementById('btn-track-progress');
      if (trackBtn) trackBtn.style.display = 'inline-flex';

      // Alert user
      const progressBar = document.getElementById('progress-bar-indicator');
      if (progressBar) progressBar.style.width = '10%';

      // Hide run form and show loading indicator
      const runForm = document.getElementById('run-discovery-form');
      const loadingIndicator = document.getElementById('discovery-loading-indicator');
      if (runForm) runForm.style.display = 'none';
      if (loadingIndicator) loadingIndicator.style.display = 'inline-flex';

      addStatusStep('Launching crawler queries in background...');

      fetch(discoveryForm.action, {
        method: 'POST',
        headers: {
          'X-CSRFToken': config.csrfToken || ''
        }
      })
      .then(res => res.json())
      .then(data => {
        if (data.success && data.run_id) {
          window.currentActiveRunId = data.run_id;
          addStatusStep(`Job spawned in background (Run ID: ${data.run_id})`);

          // Show temporary alert banner
          const alertBox = document.createElement('div');
          alertBox.style.cssText = "position: fixed; bottom: 20px; right: 20px; background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--accent); padding: 16px 20px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 10000; font-size: 13px; color: var(--text); display: flex; align-items: center; gap: 10px;";
          alertBox.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
            <span>Discovery started in background. Click <strong>Track Progress</strong> to view live logs.</span>
          `;
          document.body.appendChild(alertBox);
          setTimeout(() => { alertBox.remove(); }, 5000);

          pollRunStatus(data.run_id);
        } else {
          // Restore Run button and hide loading indicator
          if (runForm) runForm.style.display = 'inline-block';
          if (loadingIndicator) loadingIndicator.style.display = 'none';
          const errMsg = data.message || data.error || 'Failed to trigger discovery run';
          addStatusStep(`[Error] Failed to trigger discovery: ${errMsg}`);
          triggerToastAlert(errMsg, 'error');
          if (data.is_expired) {
            showExpiredPulseModal(errMsg, data.edit_url || config.editUrl);
          }
        }
      })
      .catch(err => {
        // Restore Run button and hide loading indicator
        if (runForm) runForm.style.display = 'inline-block';
        if (loadingIndicator) loadingIndicator.style.display = 'none';
        addStatusStep('[Error] Request failed or timed out.');
        triggerToastAlert('Error initializing discovery run', 'error');
      });
    });
  }

  // Real-time metric preview listeners
  ['metric-rev-min', 'metric-rev-max', 'metric-rev-min-unit', 'metric-rev-max-unit', 'metric-emp-min', 'metric-emp-max', 'metric-comp-min', 'metric-comp-max'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', updateMetricLivePreview);
      el.addEventListener('change', updateMetricLivePreview);
    }
  });
});

// Helper to add status steps beautifully to the user
function addStatusStep(message) {
  const consoleLog = document.getElementById('progress-log-console');
  if (!consoleLog) return;

  // Clear placeholder text on first message
  if (consoleLog.querySelector('.placeholder-text')) {
    consoleLog.innerHTML = '';
  }

  const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const stepEl = document.createElement('div');
  stepEl.style.cssText = "display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 13.5px; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 10px; animation: fadeIn 0.3s ease;";

  let dotColor = "var(--accent)";
  if (message.toLowerCase().includes('completed') || message.toLowerCase().includes('successfully') || message.toLowerCase().includes('success')) {
    dotColor = "var(--success)";
  } else if (message.toLowerCase().includes('failed') || message.toLowerCase().includes('error')) {
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
  window.currentActiveRunId = runId;
  const progressBar = document.getElementById('progress-bar-indicator');
  const trackBtn = document.getElementById('btn-track-progress');
  const runForm = document.getElementById('run-discovery-form');
  const loadingIndicator = document.getElementById('discovery-loading-indicator');
  const stopBtn = document.getElementById('btn-stop-discovery');
  const statusUrl = `/runs/${runId}/status/`;
  let lastStatus = '';

  // Ensure button is visible if it is polling
  if (trackBtn) trackBtn.style.display = 'inline-flex';

  // Ensure stop button is visible and active
  if (stopBtn) {
    stopBtn.style.display = 'inline-flex';
    stopBtn.disabled = false;
    stopBtn.innerHTML = `
      <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="none">
        <rect x="4" y="4" width="16" height="16" rx="2" />
      </svg>
      <span>Stop Discovery</span>
    `;
  }

  // Ensure form is hidden and loading indicator is shown during active polling
  if (runForm) runForm.style.display = 'none';
  if (loadingIndicator) loadingIndicator.style.display = 'inline-flex';

  const interval = setInterval(() => {
    fetch(statusUrl)
      .then(res => res.json())
      .then(data => {
        const cleanStatus = data.status || 'running';

        if (['completed', 'failed', 'stopped'].includes(cleanStatus)) {
          if (stopBtn) stopBtn.style.display = 'none';
        }

        if (cleanStatus !== lastStatus) {
          addStatusStep(cleanStatus);
          lastStatus = cleanStatus;
        }

        // Move progress bar
        if (progressBar) {
          if (cleanStatus.includes('Scraping')) {
            progressBar.style.width = '35%';
          } else if (cleanStatus.includes('Deduplicating')) {
            progressBar.style.width = '65%';
          } else if (cleanStatus.includes('Summarizing')) {
            progressBar.style.width = '85%';
          } else if (cleanStatus.includes('Discovering') || cleanStatus.includes('leads')) {
            progressBar.style.width = '95%';
          }
        }

        if (cleanStatus === 'completed') {
          if (progressBar) progressBar.style.width = '100%';
          addStatusStep('Completed successfully! Fetching fresh data...');
          clearInterval(interval);
          setTimeout(() => {
            location.reload();
          }, 1000);
        } else if (cleanStatus === 'stopped') {
          if (progressBar) {
            progressBar.style.width = '100%';
            progressBar.style.background = '#f59e0b';
          }
          addStatusStep('Discovery was stopped by user. Refreshing to show partial results...');
          clearInterval(interval);
          if (runForm) runForm.style.display = 'inline-block';
          if (loadingIndicator) loadingIndicator.style.display = 'none';
          setTimeout(() => {
            location.reload();
          }, 1200);
        } else if (cleanStatus === 'failed') {
          addStatusStep(`Run failed: ${data.error_message || 'Pipeline crashed'}`);

          // Restore Run button and hide loading indicator
          if (runForm) runForm.style.display = 'inline-block';
          if (loadingIndicator) loadingIndicator.style.display = 'none';

          clearInterval(interval);
          setTimeout(() => {
            const modal = document.getElementById('progressModal');
            if (modal) modal.style.display = 'none';
          }, 5000);
        }
      })
      .catch(err => {
        console.error("Polling error:", err);
      });
  }, 1500);
}

function stopActiveDiscovery() {
  const runId = window.currentActiveRunId || (window.PULSE_CONFIG && window.PULSE_CONFIG.activeRunId);
  if (!runId) {
    alert("No active discovery run detected to stop.");
    return;
  }

  const stopBtn = document.getElementById('btn-stop-discovery');
  if (stopBtn) {
    stopBtn.disabled = true;
    stopBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin-icon" style="width: 13px; height: 13px;">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 2a10 10 0 0 1 10 10" />
      </svg>
      <span>Stopping...</span>
    `;
  }

  addStatusStep('Stopping discovery... Saving all extracted results so far.');

  const csrfToken = (window.PULSE_CONFIG && window.PULSE_CONFIG.csrfToken) || 
                    document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

  fetch(`/runs/${runId}/stop/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    }
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) {
      addStatusStep('Stop signal acknowledged. Preserving partial results...');
    } else {
      addStatusStep(`Notice: ${data.message || 'Run already finished or stopped.'}`);
    }
  })
  .catch(err => {
    console.error("Error stopping discovery run:", err);
    addStatusStep(`Error communicating stop command: ${err.message}`);
    if (stopBtn) {
      stopBtn.disabled = false;
      stopBtn.innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="none">
          <rect x="4" y="4" width="16" height="16" rx="2" />
        </svg>
        <span>Stop Discovery</span>
      `;
    }
  });
}

let toastAlertTimeout = null;

function triggerToastAlert(msg, type = 'error') {
  const banner = document.getElementById("quota-alert-banner");
  const messageEl = document.getElementById("quota-alert-message");
  if (!banner || !messageEl) {
    // Fallback if banner element is absent
    alert(msg);
    return;
  }

  messageEl.innerText = msg;

  if (type === 'success') {
    banner.style.borderColor = "rgba(34, 197, 94, 0.45)";
    banner.style.color = "#4ade80";
  } else if (type === 'warning') {
    banner.style.borderColor = "rgba(245, 158, 11, 0.45)";
    banner.style.color = "#fbbf24";
  } else {
    // Default error
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

function dismissToastAlert() {
  const banner = document.getElementById("quota-alert-banner");
  if (!banner) return;
  banner.style.opacity = "0";
  banner.style.transform = "translateX(120%)";
  setTimeout(function () {
    banner.style.display = "none";
  }, 600);
}

function showAddInput(type) {
  if (type === 'keyword') {
    const badge = document.getElementById('keywords-count-badge');
    if (badge) {
      const match = badge.innerText.match(/\((\d+)\/15\)/);
      if (match && parseInt(match[1], 10) >= 15) {
        triggerToastAlert('You cannot add more than 15 keywords.', 'warning');
        return;
      }
    }
  } else if (type === 'buying_signal') {
    const badge = document.getElementById('signals-count-badge');
    if (badge) {
      const match = badge.innerText.match(/\((\d+)\/15\)/);
      if (match && parseInt(match[1], 10) >= 15) {
        triggerToastAlert('You cannot add more than 15 buying signals.', 'warning');
        return;
      }
    }
  } else if (type === 'persona') {
    const badge = document.getElementById('personas-count-badge');
    if (badge) {
      const match = badge.innerText.match(/\((\d+)\/8\)/);
      if (match && parseInt(match[1], 10) >= 8) {
        triggerToastAlert('You cannot add more than 8 personas.', 'warning');
        return;
      }
    }
  } else if (type === 'focus') {
    const badge = document.getElementById('focus-count-badge');
    if (badge) {
      const match = badge.innerText.match(/\((\d+)\/8\)/);
      if (match && parseInt(match[1], 10) >= 8) {
        triggerToastAlert('You cannot add more than 8 target focus areas.', 'warning');
        return;
      }
    }
  }

  const box = document.getElementById(`add-${type}-box`);
  if (!box) return;
  box.classList.toggle('d-none');
  if (!box.classList.contains('d-none')) {
    const input = document.getElementById(`add-${type}-input`);
    if (input) input.focus();
  }
}

// In-page item deletion confirmation modal state
let pendingDeleteItem = null;

function removeItem(type, val, btnEl) {
  pendingDeleteItem = { type: type, val: val, btnEl: btnEl };

  const modal = document.getElementById('customItemDeleteModal');
  const titleEl = document.getElementById('itemDeleteModalTitle');
  const textEl = document.getElementById('itemDeleteModalText');

  let typeLabel = 'item';
  if (type === 'keyword') typeLabel = 'Keyword';
  else if (type === 'buying_signal') typeLabel = 'Buying Signal';
  else if (type === 'persona') typeLabel = 'Persona';
  else if (type === 'competitor') typeLabel = 'Competitor';
  else if (type === 'focus') typeLabel = 'Focus Area';
  else if (type === 'geography') typeLabel = 'Target Geography';

  if (titleEl) {
    titleEl.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2" style="width: 18px; height: 18px">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      Remove ${typeLabel}
    `;
  }

  if (textEl) {
    const safeSpan = document.createElement('span');
    safeSpan.textContent = val;
    textEl.innerHTML = `Are you sure you want to remove <strong>${safeSpan.innerHTML}</strong> from this pulse?`;
  }

  if (modal) {
    modal.style.display = 'flex';
  } else {
    if (!confirm(`Are you sure you want to remove "${val}"?`)) return;
    confirmItemDelete();
  }
}

function closeItemDeleteModal() {
  const modal = document.getElementById('customItemDeleteModal');
  if (modal) modal.style.display = 'none';
  pendingDeleteItem = null;
}

function confirmItemDelete() {
  if (!pendingDeleteItem) return;
  const { type, val, btnEl } = pendingDeleteItem;
  closeItemDeleteModal();

  const config = window.PULSE_CONFIG || {};

  fetch(config.manageItemUrl || '', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': config.csrfToken || ''
    },
    body: JSON.stringify({ item_type: type, action: 'remove', value: val })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) {
      const badge = btnEl ? (btnEl.closest('.persona-badge') || btnEl.closest('span') || btnEl.closest('.badge-item')) : null;
      if (badge) {
        badge.remove();
        // Update count badge if present
        if (type === 'keyword') {
          const countBadge = document.getElementById('keywords-count-badge');
          if (countBadge) {
            const current = document.querySelectorAll('#add-keyword-box').length ? document.querySelectorAll('.detail-card:has(#add-keyword-box) .badge-item').length : 0;
            countBadge.innerText = `(${current}/15)`;
          }
        } else if (type === 'buying_signal') {
          const countBadge = document.getElementById('signals-count-badge');
          if (countBadge) {
            const current = document.querySelectorAll('#add-buying_signal-box').length ? document.querySelectorAll('.detail-card:has(#add-buying_signal-box) .badge-item').length : 0;
            countBadge.innerText = `(${current}/15)`;
          }
        } else if (type === 'focus') {
          const countBadge = document.getElementById('focus-count-badge');
          if (countBadge) {
            const box = document.getElementById('add-focus-box');
            const current = box && box.parentElement ? box.parentElement.querySelectorAll('.persona-badge').length : 0;
            countBadge.innerText = `(${current}/8)`;
          }
        } else if (type === 'persona') {
          const countBadge = document.getElementById('personas-count-badge');
          if (countBadge) {
            const box = document.getElementById('add-persona-box');
            const current = box && box.parentElement ? box.parentElement.querySelectorAll('.persona-badge').length : 0;
            countBadge.innerText = `(${current}/8)`;
          }
        }
      } else {
        location.reload();
      }
    } else {
      triggerToastAlert(data.error || 'Failed to remove item', 'error');
    }
  })
  .catch(err => {
    console.error(err);
    triggerToastAlert('Error removing item', 'error');
  });
}

function addItem(type) {
  if (type === 'keyword') {
    const badge = document.getElementById('keywords-count-badge');
    if (badge) {
      const match = badge.innerText.match(/\((\d+)\/15\)/);
      if (match && parseInt(match[1], 10) >= 15) {
        triggerToastAlert('You cannot add more than 15 keywords.', 'warning');
        return;
      }
    }
  } else if (type === 'buying_signal') {
    const badge = document.getElementById('signals-count-badge');
    if (badge) {
      const match = badge.innerText.match(/\((\d+)\/15\)/);
      if (match && parseInt(match[1], 10) >= 15) {
        triggerToastAlert('You cannot add more than 15 buying signals.', 'warning');
        return;
      }
    }
  } else if (type === 'persona') {
    const badge = document.getElementById('personas-count-badge');
    if (badge) {
      const match = badge.innerText.match(/\((\d+)\/8\)/);
      if (match && parseInt(match[1], 10) >= 8) {
        triggerToastAlert('You cannot add more than 8 personas.', 'warning');
        return;
      }
    }
  } else if (type === 'focus') {
    const badge = document.getElementById('focus-count-badge');
    if (badge) {
      const match = badge.innerText.match(/\((\d+)\/8\)/);
      if (match && parseInt(match[1], 10) >= 8) {
        triggerToastAlert('You cannot add more than 8 target focus areas.', 'warning');
        return;
      }
    }
  }

  const input = document.getElementById(`add-${type}-input`);
  if (!input) return;
  const val = input.value.trim();
  if (!val) return;

  const payload = { item_type: type, action: 'add', value: val };

  // If a category dropdown exists for this item type, include the selected value
  const categorySelect = document.getElementById(`add-${type}-category`);
  if (categorySelect && categorySelect.value) {
    payload.category = categorySelect.value;
  }

  const config = window.PULSE_CONFIG || {};

  fetch(config.manageItemUrl || '', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': config.csrfToken || ''
    },
    body: JSON.stringify(payload)
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) {
      location.reload();
    } else {
      triggerToastAlert(data.error || 'Failed to add item', 'error');
    }
  })
  .catch(err => {
    console.error(err);
    triggerToastAlert('Error adding item', 'error');
  });
}

// ==========================================
// ICP METRIC EDIT MODAL HANDLERS
// ==========================================
// ICP METRIC EDIT MODAL HANDLERS
// ==========================================
let currentEditingMetricField = null;

function parseRevenueString(val) {
  if (!val) return { min: '', minUnit: 'M', max: '', maxUnit: 'M' };
  const matches = [...val.matchAll(/(\d+(?:\.\d+)?)\s*([KkMmBb])?/g)];
  let min = '', minUnit = 'M', max = '', maxUnit = 'M';
  if (matches.length >= 2) {
    min = matches[0][1] || '';
    minUnit = (matches[0][2] || 'M').toUpperCase();
    max = matches[1][1] || '';
    maxUnit = (matches[1][2] || minUnit).toUpperCase();
  } else if (matches.length === 1) {
    min = matches[0][1] || '';
    minUnit = (matches[0][2] || 'M').toUpperCase();
    maxUnit = minUnit;
  }
  minUnit = ['K', 'M', 'B'].includes(minUnit) ? minUnit : 'M';
  maxUnit = ['K', 'M', 'B'].includes(maxUnit) ? maxUnit : 'M';
  return { min, minUnit, max, maxUnit };
}

function parseRangeNumbers(val) {
  if (!val) return { min: '', max: '' };
  const cleaned = val.replace(/,/g, '');
  const matches = [...cleaned.matchAll(/\d+/g)];
  let min = '', max = '';
  if (matches.length >= 2) {
    min = matches[0][0] || '';
    max = matches[1][0] || '';
  } else if (matches.length === 1) {
    min = matches[0][0] || '';
  }
  return { min, max };
}

function openIcpMetricModal(field, currentVal) {
  currentEditingMetricField = field;
  const modal = document.getElementById('icpMetricModal');
  if (!modal) return;

  // Hide all metric panels
  document.querySelectorAll('.metric-form-panel').forEach(p => p.style.display = 'none');

  const titleEl = document.getElementById('icp-metric-title-text');
  const subtextEl = document.getElementById('icp-metric-subtext');

  if (field === 'revenue_range') {
    if (titleEl) titleEl.innerText = 'Edit Revenue Range';
    if (subtextEl) subtextEl.innerText = 'Set minimum and maximum revenue amounts and their scale units (K, M, or B).';
    const panel = document.getElementById('metric-form-revenue');
    if (panel) panel.style.display = 'block';

    const parsed = parseRevenueString(currentVal);
    const minInput = document.getElementById('metric-rev-min');
    const minUnitSelect = document.getElementById('metric-rev-min-unit');
    const maxInput = document.getElementById('metric-rev-max');
    const maxUnitSelect = document.getElementById('metric-rev-max-unit');
    if (minInput) minInput.value = parsed.min;
    if (minUnitSelect) minUnitSelect.value = parsed.minUnit;
    if (maxInput) maxInput.value = parsed.max;
    if (maxUnitSelect) maxUnitSelect.value = parsed.maxUnit;

  } else if (field === 'company_size') {
    if (titleEl) titleEl.innerText = 'Edit Company Size';
    if (subtextEl) subtextEl.innerText = 'Enter headcount numbers only. "Employees" suffix is automated.';
    const panel = document.getElementById('metric-form-company-size');
    if (panel) panel.style.display = 'block';

    const parsed = parseRangeNumbers(currentVal);
    const minInput = document.getElementById('metric-comp-min');
    const maxInput = document.getElementById('metric-comp-max');
    if (minInput) minInput.value = parsed.min;
    if (maxInput) maxInput.value = parsed.max;

  } else if (field === 'employee_count') {
    if (titleEl) titleEl.innerText = 'Edit Employee Count';
    if (subtextEl) subtextEl.innerText = 'Enter headcount number range (e.g. 100 - 400).';
    const panel = document.getElementById('metric-form-employees');
    if (panel) panel.style.display = 'block';

    const parsed = parseRangeNumbers(currentVal);
    const minInput = document.getElementById('metric-emp-min');
    const maxInput = document.getElementById('metric-emp-max');
    if (minInput) minInput.value = parsed.min;
    if (maxInput) maxInput.value = parsed.max;
  }

  // Clear previous error state when opening modal
  const errorContainer = document.getElementById('metric-validation-error');
  if (errorContainer) errorContainer.style.display = 'none';
  ['metric-rev-max', 'metric-comp-max', 'metric-emp-max'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.style.borderColor = '';
      el.style.boxShadow = '';
    }
  });

  updateMetricLivePreview();
  modal.style.display = 'flex';
}

function closeIcpMetricModal() {
  const modal = document.getElementById('icpMetricModal');
  if (modal) modal.style.display = 'none';
  currentEditingMetricField = null;
}

function setRevPreset(min, minUnit, max, maxUnit) {
  const minInput = document.getElementById('metric-rev-min');
  const minUnitSelect = document.getElementById('metric-rev-min-unit');
  const maxInput = document.getElementById('metric-rev-max');
  const maxUnitSelect = document.getElementById('metric-rev-max-unit');

  if (minInput) minInput.value = min;
  if (minUnitSelect) minUnitSelect.value = minUnit;
  if (maxInput) maxInput.value = max;
  if (maxUnitSelect) maxUnitSelect.value = maxUnit;
  updateMetricLivePreview();
}

function setEmpPreset(min, max) {
  const minInput = document.getElementById('metric-emp-min');
  const maxInput = document.getElementById('metric-emp-max');
  if (minInput) minInput.value = min;
  if (maxInput) maxInput.value = max;
  updateMetricLivePreview();
}

function setCompSizePreset(min, max) {
  const minInput = document.getElementById('metric-comp-min');
  const maxInput = document.getElementById('metric-comp-max');
  if (minInput) minInput.value = min;
  if (maxInput) maxInput.value = max;
  updateMetricLivePreview();
}

function validateMetricRange() {
  const errorContainer = document.getElementById('metric-validation-error');
  const errorText = document.getElementById('metric-validation-error-text');
  const saveBtn = document.getElementById('save-icp-metric-btn');
  const previewEl = document.getElementById('metric-live-preview');

  let errorMsg = null;
  let invalidInput = null;

  if (currentEditingMetricField === 'revenue_range') {
    const minInput = document.getElementById('metric-rev-min');
    const minUnitSelect = document.getElementById('metric-rev-min-unit');
    const maxInput = document.getElementById('metric-rev-max');
    const maxUnitSelect = document.getElementById('metric-rev-max-unit');

    const minStr = (minInput?.value || '').trim();
    const maxStr = (maxInput?.value || '').trim();
    const minVal = parseFloat(minStr);
    const maxVal = parseFloat(maxStr);
    const minUnit = minUnitSelect?.value || 'M';
    const maxUnit = maxUnitSelect?.value || minUnit;
    const unitMultipliers = { 'K': 1e3, 'M': 1e6, 'B': 1e9 };

    if (minStr && maxStr && !isNaN(minVal) && !isNaN(maxVal)) {
      const minDollars = minVal * (unitMultipliers[minUnit] || 1e6);
      const maxDollars = maxVal * (unitMultipliers[maxUnit] || 1e6);
      if (maxDollars <= minDollars) {
        errorMsg = `Max revenue ($${maxStr}${maxUnit}) must be greater than min revenue ($${minStr}${minUnit}).`;
        invalidInput = maxInput;
      }
    }
  } else if (currentEditingMetricField === 'company_size') {
    const minInput = document.getElementById('metric-comp-min');
    const maxInput = document.getElementById('metric-comp-max');
    const minStr = (minInput?.value || '').trim();
    const maxStr = (maxInput?.value || '').trim();
    const minVal = parseInt(minStr, 10);
    const maxVal = parseInt(maxStr, 10);

    if (minStr && maxStr && !isNaN(minVal) && !isNaN(maxVal)) {
      if (maxVal <= minVal) {
        errorMsg = `Max company size (${maxVal}) must be greater than min company size (${minVal}).`;
        invalidInput = maxInput;
      }
    }
  } else if (currentEditingMetricField === 'employee_count') {
    const minInput = document.getElementById('metric-emp-min');
    const maxInput = document.getElementById('metric-emp-max');
    const minStr = (minInput?.value || '').trim();
    const maxStr = (maxInput?.value || '').trim();
    const minVal = parseInt(minStr, 10);
    const maxVal = parseInt(maxStr, 10);

    if (minStr && maxStr && !isNaN(minVal) && !isNaN(maxVal)) {
      if (maxVal <= minVal) {
        errorMsg = `Max employee count (${maxVal}) must be greater than min employee count (${minVal}).`;
        invalidInput = maxInput;
      }
    }
  }

  // Clear previous input error highlights
  ['metric-rev-max', 'metric-comp-max', 'metric-emp-max'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.style.borderColor = '';
      el.style.boxShadow = '';
    }
  });

  if (errorMsg) {
    if (errorContainer) {
      errorContainer.style.display = 'flex';
      if (errorText) errorText.innerText = errorMsg;
    }
    if (invalidInput) {
      invalidInput.style.borderColor = '#ef4444';
      invalidInput.style.boxShadow = '0 0 0 2px rgba(239, 68, 68, 0.2)';
    }
    if (previewEl) {
      previewEl.innerText = '⚠️ Max must be greater than Min';
      previewEl.style.color = '#ef4444';
    }
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.style.opacity = '0.5';
      saveBtn.style.cursor = 'not-allowed';
    }
    return false;
  } else {
    if (errorContainer) {
      errorContainer.style.display = 'none';
    }
    if (previewEl) {
      previewEl.style.color = '#6366f1';
    }
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.style.opacity = '1';
      saveBtn.style.cursor = 'pointer';
    }
    return true;
  }
}

function computeMetricValue() {
  if (currentEditingMetricField === 'revenue_range') {
    const min = (document.getElementById('metric-rev-min')?.value || '').trim();
    const minUnit = document.getElementById('metric-rev-min-unit')?.value || 'M';
    const max = (document.getElementById('metric-rev-max')?.value || '').trim();
    const maxUnit = document.getElementById('metric-rev-max-unit')?.value || minUnit;

    if (min && max) return `$${min}${minUnit} - $${max}${maxUnit}`;
    if (min && !max) return `$${min}${minUnit}+`;
    if (!min && max) return `Up to $${max}${maxUnit}`;
    return `$10M - $50M`;

  } else if (currentEditingMetricField === 'company_size') {
    const min = (document.getElementById('metric-comp-min')?.value || '').trim();
    const max = (document.getElementById('metric-comp-max')?.value || '').trim();

    if (min && max) return `${min} - ${max} Employees`;
    if (min && !max) return `${min}+ Employees`;
    if (!min && max) return `Up to ${max} Employees`;
    return `51 - 200 Employees`;

  } else if (currentEditingMetricField === 'employee_count') {
    const min = (document.getElementById('metric-emp-min')?.value || '').trim();
    const max = (document.getElementById('metric-emp-max')?.value || '').trim();

    if (min && max) return `${min} - ${max}`;
    if (min && !max) return `${min}+`;
    if (!min && max) return `Up to ${max}`;
    return `100 - 400`;
  }
  return '';
}

function updateMetricLivePreview() {
  const isValid = validateMetricRange();
  if (!isValid) return;

  const previewEl = document.getElementById('metric-live-preview');
  if (!previewEl) return;
  previewEl.innerText = computeMetricValue();
}

function saveIcpMetricModal() {
  if (!currentEditingMetricField) return;
  if (!validateMetricRange()) return;

  const val = computeMetricValue();
  const field = currentEditingMetricField;

  const btn = document.getElementById('save-icp-metric-btn');
  const originalHtml = btn ? btn.innerHTML : 'Save Changes';
  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Saving...';
  }

  const config = window.PULSE_CONFIG || {};

  fetch(config.manageItemUrl || '', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': config.csrfToken || ''
    },
    body: JSON.stringify({ item_type: 'icp_metric', field: field, value: val })
  })
  .then(res => res.json())
  .then(data => {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
    if (data.success) {
      // In-place DOM update
      const displayEl = document.getElementById('display-' + field);
      if (displayEl) displayEl.innerText = val;

      const editBtn = document.getElementById('btn-edit-' + field);
      if (editBtn) {
        editBtn.setAttribute('onclick', `openIcpMetricModal('${field}', '${val.replace(/'/g, "\\'")}')`);
      }

      closeIcpMetricModal();
    } else {
      triggerToastAlert(data.error || 'Failed to update ICP metric', 'error');
    }
  })
  .catch(err => {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
    console.error(err);
    triggerToastAlert('Error updating ICP metric', 'error');
  });
}

// Backward-compatibility wrapper
function editIcpMetric(field, currentVal) {
  openIcpMetricModal(field, currentVal);
}

function performDelete() {
  const config = window.PULSE_CONFIG || {};

  fetch(config.deleteUrl || '', {
    method: 'POST',
    headers: {
      'X-CSRFToken': config.csrfToken || ''
    }
  })
  .then(res => {
    if (res.ok) {
      window.location.href = config.listUrl || '/pulses/';
    } else {
      triggerToastAlert("Failed to delete the pulse configuration. Please try again.", 'error');
    }
  })
  .catch(err => {
    console.error(err);
    triggerToastAlert("An error occurred while deleting the pulse. Please try again.", 'error');
  });
}
