const agentGrid = document.querySelector("#agent-grid");
const sharedGrid = document.querySelector("#shared-grid");
const blockedPanel = document.querySelector("#blocked-panel");
const stream = document.querySelector("#publication-stream");
const connection = document.querySelector("#connection-status");
const sharedEvidence = document.querySelector("#shared-evidence");
let currentView = null;

function text(value) {
  if (value === null || value === undefined) return "UNKNOWN";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function setBadge(node, value) {
  node.className = `badge ${value}`;
  node.textContent = value;
}

function metric(label, value) {
  const item = document.createElement("div");
  item.className = "metric";
  item.innerHTML = `<div class="metric-label"></div><div class="metric-value"></div>`;
  item.querySelector(".metric-label").textContent = label;
  item.querySelector(".metric-value").textContent = text(value);
  return item;
}

function eventValue(event, field = "created_at") {
  return event ? event[field] || event.event_type || "UNKNOWN" : "UNKNOWN";
}

function renderShared(shared) {
  sharedGrid.replaceChildren(
    metric("Active session", shared.active_session),
    metric("Environment", shared.testnet_environment),
    metric("Portfolio", shared.portfolio_state),
    metric("Open orders", shared.open_orders),
    metric("Open positions", shared.open_positions),
    metric("Pending commands", shared.pending_commands),
    metric("Symbol ownership", shared.symbol_ownership),
    metric("Kill switch", shared.kill_switch_state),
    metric("Last reconciliation", shared.last_reconciliation),
    metric("Integration SHA", shared.current_integration_sha),
  );
  setBadge(sharedEvidence, shared.exchange_evidence);
  stream.replaceChildren();
  if (!shared.collective_publication_stream.length) {
    stream.innerHTML = '<p class="empty">No collective publications recorded.</p>';
  } else {
    shared.collective_publication_stream.forEach((publication) => {
      const row = document.createElement("div");
      row.className = "stream-item";
      row.textContent = `${publication.created_at || "UNKNOWN"} · ${publication.event_type || "PUBLICATION"}`;
      stream.append(row);
    });
  }
}

function addDetail(list, label, value) {
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = text(value);
  list.append(term, detail);
}

function renderAgents(agents, shared) {
  agentGrid.replaceChildren();
  const template = document.querySelector("#agent-card-template");
  agents.forEach((agent, index) => {
    const card = template.content.firstElementChild.cloneNode(true);
    card.style.animationDelay = `${index * 80}ms`;
    card.dataset.agentId = agent.agent_id;
    card.querySelector(".agent-kind").textContent = `${agent.runtime_kind} AGENT · #${agent.agent_number}`;
    card.querySelector(".agent-id").textContent = agent.agent_id;
    card.querySelector(".agent-state").textContent = agent.current_state;
    card.querySelector(".heartbeat").textContent = `${agent.heartbeat_freshness} · ${agent.last_heartbeat || "never"}`;
    setBadge(card.querySelector(".agent-evidence"), agent.exchange_evidence);
    agent.owned_symbols.forEach((symbol) => {
      const chip = document.createElement("span");
      chip.className = "symbol";
      chip.textContent = symbol;
      card.querySelector(".symbols").append(chip);
    });
    const details = card.querySelector(".agent-details");
    addDetail(details, "Instruction ACK", eventValue(agent.last_instruction_ack, "instruction_version"));
    addDetail(details, "Last analysis", agent.last_analysis_time);
    addDetail(details, "Publication", eventValue(agent.last_publication));
    addDetail(details, "Command request", eventValue(agent.last_command_request, "command_id"));
    addDetail(details, "FSM result", eventValue(agent.last_fsm_result));
    addDetail(details, "Exchange response", agent.last_exchange_response);
    addDetail(details, "Timeout / degraded", agent.timeout_degraded_state);
    const controlsReady = Boolean(shared.active_session && agent.last_instruction_ack?.instruction_version);
    card.querySelectorAll("[data-action]").forEach((button) => {
      button.disabled = !controlsReady;
      button.addEventListener("click", () => submitControl(button.dataset.action, agent, card));
    });
    agentGrid.append(card);
  });

  const firstReadyAgent = agents.find((agent) => agent.last_instruction_ack?.instruction_version);
  document.querySelectorAll("[data-shared-action]").forEach((button) => {
    button.disabled = !(shared.active_session && firstReadyAgent);
    button.onclick = () => submitControl(button.dataset.sharedAction, firstReadyAgent, document.body, "ALL");
  });
}

async function submitControl(action, agent, scope, symbolOverride = null) {
  const rationale = window.prompt(`Rationale for ${action}:`);
  if (!rationale?.trim()) return;
  const payload = {
    session_id: currentView.shared.active_session,
    agent_id: agent.agent_id,
    agent_number: agent.agent_number,
    command_id: `command-${crypto.randomUUID()}`,
    event_id: `event-${crypto.randomUUID()}`,
    symbol: symbolOverride || agent.owned_symbols[0],
    created_at: new Date().toISOString(),
    rationale: rationale.trim(),
    instruction_version: agent.last_instruction_ack.instruction_version,
    collective_state_version: agent.last_publication?.collective_state_version || null,
  };
  const response = await fetch(`/arena/commands/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  const output = scope.querySelector?.(".control-result");
  if (output) output.textContent = response.ok ? `${result.status}: ${result.command_id}` : result.error;
  await loadView();
}

async function loadView() {
  try {
    const response = await fetch("/arena/runtime", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    currentView = await response.json();
    setBadge(connection, currentView.blocked_reasons.length ? "BLOCKED" : "TEST");
    if (currentView.blocked_reasons.length) {
      blockedPanel.classList.remove("hidden");
      blockedPanel.textContent = currentView.blocked_reasons.join(" · ");
    } else {
      blockedPanel.classList.add("hidden");
    }
    renderShared(currentView.shared);
    renderAgents(currentView.agents, currentView.shared);
  } catch (error) {
    setBadge(connection, "BLOCKED");
    blockedPanel.classList.remove("hidden");
    blockedPanel.textContent = `Cockpit runtime view unavailable: ${error.message}`;
  }
}

document.querySelector("#refresh-view").addEventListener("click", loadView);
loadView();
setInterval(loadView, 5000);
