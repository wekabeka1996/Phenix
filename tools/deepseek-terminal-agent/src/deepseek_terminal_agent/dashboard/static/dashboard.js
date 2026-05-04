// DeepSeek Terminal Agent Dashboard — polling UI with live status and activity feed

(function () {
  const bootstrapNode = document.getElementById("dashboard-bootstrap");
  const bootstrap = bootstrapNode ? JSON.parse(bootstrapNode.textContent || "{}") : {};
  const MAX_CHARS = bootstrap.maxPromptChars || 12000;
  const TERMINAL_STATUSES = ["succeeded", "failed", "cancelled"];
  const POLL_INTERVAL_MS = 1000;

  const textarea = document.getElementById("prompt");
  const form = document.getElementById("run-form");
  const charCount = document.getElementById("char-count");
  const runBtn = document.getElementById("run-btn");
  const cancelBtn = document.getElementById("cancel-btn");
  const refreshBtn = document.getElementById("refresh-btn");
  const copyOutputBtn = document.getElementById("copy-output-btn");
  const autoScrollToggle = document.getElementById("autoscroll-toggle");
  const connectionWarning = document.getElementById("connection-warning");
  const statusBadge = document.getElementById("status-badge");
  const statusPhase = document.getElementById("status-phase");
  const statusDuration = document.getElementById("status-duration");
  const statusRunId = document.getElementById("status-run-id");
  const statusExitCode = document.getElementById("status-exit-code");
  const statusLatestEvent = document.getElementById("status-latest-event");
  const statusRunDir = document.getElementById("status-run-dir");
  const activityCount = document.getElementById("activity-count");
  const activityFeed = document.getElementById("activity-feed");
  const outputView = document.getElementById("output-view");
  const outputWarning = document.getElementById("output-warning");
  const outputTabs = Array.from(document.querySelectorAll("[data-output-tab]"));
  const recentRunsBody = document.getElementById("recent-runs-body");

  const state = {
    currentRunId: null,
    pollHandle: null,
    selectedOutputTab: "combined",
    lastStatus: null,
    lastOutput: { combined: "", stdout: "", stderr: "" },
    lastEvents: [],
    recentRuns: Array.isArray(bootstrap.recentRuns) ? bootstrap.recentRuns : [],
  };

  function isTerminalStatus(status) {
    return TERMINAL_STATUSES.includes(status);
  }

  function updateCounter() {
    const length = textarea ? textarea.value.length : 0;
    if (!charCount) {
      return;
    }
    charCount.textContent = String(length) + " / " + String(MAX_CHARS);
    charCount.style.color = length > MAX_CHARS * 0.9 ? "#ff9d72" : "";
  }

  function showConnectionWarning(message) {
    if (!connectionWarning) {
      return;
    }
    connectionWarning.textContent = message;
    connectionWarning.classList.remove("hidden");
  }

  function hideConnectionWarning() {
    if (!connectionWarning) {
      return;
    }
    connectionWarning.textContent = "";
    connectionWarning.classList.add("hidden");
  }

  function setRunControls(isRunning) {
    if (runBtn) {
      runBtn.disabled = isRunning;
      runBtn.textContent = isRunning ? "Running..." : "Run";
      runBtn.classList.toggle("is-running", isRunning);
    }
    if (cancelBtn) {
      cancelBtn.classList.toggle("hidden", !isRunning);
      cancelBtn.disabled = !isRunning;
    }
  }

  function formatDuration(value) {
    const duration = Number(value || 0);
    if (duration < 1000) {
      return String(duration) + " ms";
    }
    return (duration / 1000).toFixed(1) + " s";
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function statusBadgeClass(status) {
    if (status === "succeeded") {
      return "badge-ok";
    }
    if (status === "failed" || status === "cancelled") {
      return "badge-error";
    }
    if (status === "queued" || status === "waiting_model" || status === "finalizing") {
      return "badge-warn";
    }
    return "badge-info";
  }

  function setStatusView(status) {
    state.lastStatus = status;
    const currentStatus = status && status.status ? status.status : "idle";
    if (statusBadge) {
      statusBadge.textContent = currentStatus;
      statusBadge.className = "badge " + statusBadgeClass(currentStatus);
    }
    if (statusPhase) {
      statusPhase.textContent = status && status.current_phase ? status.current_phase : "idle";
    }
    if (statusDuration) {
      statusDuration.textContent = formatDuration(status && status.duration_ms ? status.duration_ms : 0);
    }
    if (statusRunId) {
      statusRunId.textContent = status && status.run_id ? status.run_id : "-";
    }
    if (statusExitCode) {
      statusExitCode.textContent = status && status.exit_code !== null && status.exit_code !== undefined ? String(status.exit_code) : "-";
    }
    if (statusLatestEvent) {
      statusLatestEvent.textContent = status && status.latest_event ? status.latest_event : "No active run.";
    }
    if (statusRunDir) {
      statusRunDir.textContent = status && status.run_dir ? status.run_dir : "Not available";
    }

    if (isTerminalStatus(currentStatus)) {
      stopPolling();
      setRunControls(false);
    }
  }

  function renderEvents(events) {
    state.lastEvents = events;
    if (activityCount) {
      activityCount.textContent = String(events.length) + " events";
    }
    if (!activityFeed) {
      return;
    }
    if (!events.length) {
      activityFeed.innerHTML = '<li class="activity-empty">No events yet.</li>';
      return;
    }
    activityFeed.innerHTML = events
      .slice()
      .reverse()
      .map(function (event) {
        const meta = event.metadata || {};
        const metaText = meta.cmd || meta.final_answer || meta.content_preview || meta.excerpt || "";
        return [
          '<li class="activity-item activity-' + escapeHtml(event.type) + '">',
          '<div class="activity-top">',
          '<span class="activity-type">' + escapeHtml(event.type) + '</span>',
          '<span class="activity-phase mono">' + escapeHtml(event.phase || "") + '</span>',
          '</div>',
          '<p class="activity-message">' + escapeHtml(event.message || "") + '</p>',
          metaText ? '<p class="activity-meta mono">' + escapeHtml(metaText) + '</p>' : "",
          '</li>'
        ].join("");
      })
      .join("");
  }

  function currentOutputText() {
    if (state.selectedOutputTab === "stdout") {
      return state.lastOutput.stdout || "";
    }
    if (state.selectedOutputTab === "stderr") {
      return state.lastOutput.stderr || "";
    }
    return state.lastOutput.combined || "";
  }

  function renderOutput(output) {
    state.lastOutput = {
      combined: output && output.output ? output.output : "",
      stdout: output && output.stdout ? output.stdout : "",
      stderr: output && output.stderr ? output.stderr : "",
      truncated: Boolean(output && output.truncated),
    };
    if (outputWarning) {
      outputWarning.classList.toggle("hidden", !state.lastOutput.truncated);
    }
    if (outputView) {
      const text = currentOutputText();
      outputView.textContent = text || "No output yet.";
      if (autoScrollToggle && autoScrollToggle.checked) {
        outputView.scrollTop = outputView.scrollHeight;
      }
    }
  }

  function renderRecentRuns(runs) {
    state.recentRuns = runs;
    if (!recentRunsBody) {
      return;
    }
    if (!runs.length) {
      recentRunsBody.innerHTML = '<tr><td colspan="6" class="muted">No runs yet. Submit a prompt above.</td></tr>';
      return;
    }
    recentRunsBody.innerHTML = runs
      .map(function (run) {
        const status = run.status || (run.exit_code === 0 ? "succeeded" : "failed");
        const prompt = run.prompt || "";
        return [
          '<tr class="runs-row ' + escapeHtml(status) + '">',
          '<td class="mono">' + escapeHtml((run.created_at || "").replace("T", " ").slice(0, 19)) + '</td>',
          '<td class="prompt-cell">' + escapeHtml(prompt.length > 80 ? prompt.slice(0, 80) + "..." : prompt) + '</td>',
          '<td><span class="badge ' + statusBadgeClass(status) + '">' + escapeHtml(status) + '</span></td>',
          '<td class="mono">' + escapeHtml(formatDuration(run.duration_ms || 0)) + '</td>',
          '<td class="mono small">' + escapeHtml(run.run_id || "") + '</td>',
          '<td><button type="button" class="btn-link open-run-btn" data-run-id="' + escapeHtml(run.run_id || "") + '" data-run-status="' + escapeHtml(status) + '">Open</button></td>',
          '</tr>'
        ].join("");
      })
      .join("");
  }

  function stopPolling() {
    if (state.pollHandle) {
      window.clearInterval(state.pollHandle);
      state.pollHandle = null;
    }
  }

  function startPolling(runId) {
    stopPolling();
    state.currentRunId = runId;
    setRunControls(true);
    state.pollHandle = window.setInterval(refreshCurrentRun, POLL_INTERVAL_MS);
    refreshCurrentRun();
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options || {});
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data && data.error ? data.error : "Request failed.");
    }
    return data;
  }

  async function refreshRecentRuns() {
    const runs = await fetchJson("/runs");
    renderRecentRuns(runs);
  }

  async function refreshCurrentRun() {
    if (!state.currentRunId) {
      await refreshRecentRuns();
      return;
    }

    try {
      const runId = state.currentRunId;
      const results = await Promise.all([
        fetchJson("/runs/" + encodeURIComponent(runId) + "/status"),
        fetchJson("/runs/" + encodeURIComponent(runId) + "/output"),
        fetchJson("/runs/" + encodeURIComponent(runId) + "/events"),
        fetchJson("/runs"),
      ]);
      hideConnectionWarning();
      setStatusView(results[0]);
      renderOutput(results[1]);
      renderEvents(results[2].events || []);
      renderRecentRuns(results[3]);
    } catch (error) {
      showConnectionWarning(String(error.message || error) + " Retrying...");
    }
  }

  function resetRunViewForNewRun() {
    state.lastEvents = [];
    state.lastOutput = { combined: "", stdout: "", stderr: "", truncated: false };
    renderEvents([]);
    renderOutput({ output: "", stdout: "", stderr: "", truncated: false });
    setStatusView({
      run_id: "-",
      status: "queued",
      current_phase: "queued",
      duration_ms: 0,
      exit_code: null,
      latest_event: "Queued",
      run_dir: null,
    });
  }

  async function submitRun(event) {
    event.preventDefault();
    if (!textarea) {
      return;
    }
    const prompt = textarea.value.trim();
    if (!prompt) {
      showConnectionWarning("Prompt is required.");
      return;
    }
    hideConnectionWarning();
    resetRunViewForNewRun();
    setRunControls(true);
    try {
      const created = await fetchJson("/runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({ prompt: prompt }),
      });
      state.currentRunId = created.run_id;
      setStatusView(created);
      startPolling(created.run_id);
    } catch (error) {
      setRunControls(false);
      showConnectionWarning(String(error.message || error));
    }
  }

  async function cancelCurrentRun() {
    if (!state.currentRunId) {
      return;
    }
    try {
      await fetchJson("/runs/" + encodeURIComponent(state.currentRunId) + "/cancel", {
        method: "POST",
        headers: { "Accept": "application/json" },
      });
      refreshCurrentRun();
    } catch (error) {
      showConnectionWarning(String(error.message || error));
    }
  }

  async function copyCurrentOutput() {
    const text = currentOutputText();
    if (!text) {
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const fallback = document.createElement("textarea");
    fallback.value = text;
    document.body.appendChild(fallback);
    fallback.select();
    document.execCommand("copy");
    document.body.removeChild(fallback);
  }

  function selectOutputTab(nextTab) {
    state.selectedOutputTab = nextTab;
    outputTabs.forEach(function (button) {
      button.classList.toggle("is-active", button.getAttribute("data-output-tab") === nextTab);
    });
    renderOutput(state.lastOutput);
  }

  function openRun(runId, runStatus) {
    state.currentRunId = runId;
    hideConnectionWarning();
    if (isTerminalStatus(runStatus)) {
      stopPolling();
      setRunControls(false);
      refreshCurrentRun();
      return;
    }
    startPolling(runId);
  }

  if (textarea) {
    textarea.addEventListener("input", updateCounter);
    updateCounter();
  }

  window.setPrompt = function (text) {
    if (!textarea) {
      return;
    }
    textarea.value = text;
    textarea.focus();
    updateCounter();
  };

  if (form) {
    form.addEventListener("submit", submitRun);
  }
  if (cancelBtn) {
    cancelBtn.addEventListener("click", cancelCurrentRun);
  }
  if (refreshBtn) {
    refreshBtn.addEventListener("click", refreshCurrentRun);
  }
  if (copyOutputBtn) {
    copyOutputBtn.addEventListener("click", function () {
      copyCurrentOutput().catch(function () {
        showConnectionWarning("Could not copy output.");
      });
    });
  }
  outputTabs.forEach(function (button) {
    button.addEventListener("click", function () {
      selectOutputTab(button.getAttribute("data-output-tab") || "combined");
    });
  });
  if (recentRunsBody) {
    recentRunsBody.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (target.classList.contains("open-run-btn")) {
        openRun(target.getAttribute("data-run-id"), target.getAttribute("data-run-status") || "");
      }
    });
  }

  renderRecentRuns(state.recentRuns);
  renderEvents([]);
  renderOutput({ output: "", stdout: "", stderr: "", truncated: false });
  setRunControls(false);
  setStatusView({
    run_id: "-",
    status: "idle",
    current_phase: "idle",
    duration_ms: 0,
    exit_code: null,
    latest_event: "No active run.",
    run_dir: null,
  });
})();
