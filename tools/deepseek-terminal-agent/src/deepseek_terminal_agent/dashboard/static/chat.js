(function () {
  const bootstrapNode = document.getElementById("chat-bootstrap");
  const bootstrap = bootstrapNode ? JSON.parse(bootstrapNode.textContent || "{}") : {};

  const sessionList = document.getElementById("session-list");
  const newSessionBtn = document.getElementById("new-session-btn");
  const newSessionTitle = document.getElementById("new-session-title");
  const newSessionProfile = document.getElementById("new-session-profile");
  const sessionTitle = document.getElementById("session-title");
  const sessionMeta = document.getElementById("session-meta");
  const workspaceSessionPill = document.getElementById("workspace-session-pill");
  const profileSelect = document.getElementById("profile-select");
  const simpleChatModelSelect = document.getElementById("simple-chat-model");
  const centralWorkspace = document.getElementById("central-workspace");
  const centralWorkspaceStack = document.getElementById("central-workspace-stack");
  const workspacePresetSelect = document.getElementById("workspace-preset-select");
  const workspaceResetBtn = document.getElementById("workspace-reset-btn");
  const chatThread = document.getElementById("chat-thread");
  const chatStreamStatus = document.getElementById("chat-stream-status");
  const chatSubagentEmpty = document.getElementById("chat-subagent-empty");
  const chatInput = document.getElementById("chat-input");
  const outputStatusBadge = document.getElementById("output-status-badge");
  const outputStatusLine = document.getElementById("output-status-line");
  const outputResultBox = document.getElementById("output-result-box");
  const resultSectionStatus = document.getElementById("result-section-status");
  const resultArtifactLinks = document.getElementById("result-artifact-links");
  const resultCopyBtn = document.getElementById("result-copy-btn");
  const resultAddMemoryBtn = document.getElementById("result-add-memory-btn");
  const resultFocusTraceBtn = document.getElementById("result-focus-trace-btn");
  const resultFocusArtifactsBtn = document.getElementById("result-focus-artifacts-btn");
  const capsulePhaseStatus = document.getElementById("capsule-phase-status");
  const capsuleProjectName = document.getElementById("capsule-project-name");
  const capsuleProjectMode = document.getElementById("capsule-project-mode");
  const capsuleProjectPhase = document.getElementById("capsule-project-phase");
  const capsuleRiskCount = document.getElementById("capsule-risk-count");
  const capsuleSearchMode = document.getElementById("capsule-search-mode");
  const capsuleRulesList = document.getElementById("capsule-rules-list");
  const capsuleRisksList = document.getElementById("capsule-risks-list");
  const capsuleNextStepsList = document.getElementById("capsule-next-steps-list");
  const chatCharCount = document.getElementById("chat-char-count");
  const composer = document.getElementById("composer");
  const composerBody = document.getElementById("composer-body");
  const composerClearBtn = document.getElementById("composer-clear-btn");
  const composerExpandBtn = document.getElementById("composer-expand-btn");
  const composerUseScenarioBtn = document.getElementById("composer-use-scenario-btn");
  const sendBtn = document.getElementById("send-btn");
  const refreshSessionBtn = document.getElementById("refresh-session-btn");
  const inspectContextBtn = document.getElementById("inspect-context-btn");
  const compressBtn = document.getElementById("compress-btn");
  const spawnScoutBtn = document.getElementById("spawn-scout-btn");
  const cancelSubagentBtn = document.getElementById("cancel-subagent-btn");
  const chatWarning = document.getElementById("chat-warning");
  const chatStatusBadge = document.getElementById("chat-status-badge");
  const contextUsage = document.getElementById("context-usage");
  const contextWarningCount = document.getElementById("context-warning-count");
  const contextTurnCount = document.getElementById("context-turn-count");
  const contextMemoryCount = document.getElementById("context-memory-count");
  const contextArtifactCount = document.getElementById("context-artifact-count");
  const contextPackView = document.getElementById("context-pack-view");
  const routerRoute = document.getElementById("router-route");
  const routerTaskType = document.getElementById("router-task-type");
  const routerAttachStatus = document.getElementById("router-attach-status");
  const routerReason = document.getElementById("router-reason");
  const routerSuggestedList = document.getElementById("router-suggested-list");
  const memoryCount = document.getElementById("memory-count");
  const memoryText = document.getElementById("memory-text");
  const memoryKind = document.getElementById("memory-kind");
  const memorySearchText = document.getElementById("memory-search-text");
  const searchMemoryBtn = document.getElementById("search-memory-btn");
  const memorySearchResults = document.getElementById("memory-search-results");
  const addMemoryBtn = document.getElementById("add-memory-btn");
  const memoryList = document.getElementById("memory-list");
  const subagentCount = document.getElementById("subagent-count");
  const subagentList = document.getElementById("subagent-list");
  const artifactList = document.getElementById("artifact-list");
  const currentRunStatus = document.getElementById("current-run-status");
  const currentRunTask = document.getElementById("current-run-task");
  const currentRunAgent = document.getElementById("current-run-agent");
  const currentRunModel = document.getElementById("current-run-model");
  const currentRunElapsed = document.getElementById("current-run-elapsed");
  const recentRunsBody = document.getElementById("recent-runs-body");
  const eventLogView = document.getElementById("event-log-view");
  const drawerArtifactsView = document.getElementById("drawer-artifacts-view");
  const testResultView = document.getElementById("test-result-view");
  const traceView = document.getElementById("trace-view");
  const scenarioSectionStatus = document.getElementById("scenario-section-status");
  const scenarioPreviewEmpty = document.getElementById("scenario-preview-empty");
  const scenarioPreviewCard = document.getElementById("scenario-preview-card");
  const scenarioPreviewTitle = document.getElementById("scenario-preview-title");
  const scenarioPreviewDescription = document.getElementById("scenario-preview-description");
  const scenarioPreviewGroup = document.getElementById("scenario-preview-group");
  const scenarioPreviewMode = document.getElementById("scenario-preview-mode");
  const scenarioPreviewRisk = document.getElementById("scenario-preview-risk");
  const scenarioPreviewTemplate = document.getElementById("scenario-preview-template");
  const scenarioPreviewSource = document.getElementById("scenario-preview-source");
  const scenarioPreviewWarning = document.getElementById("scenario-preview-warning");
  const scenarioApplyBtn = document.getElementById("scenario-apply-btn");
  const scenarioRunBtn = document.getElementById("scenario-run-btn");
  const scenarioOpenSourceBtn = document.getElementById("scenario-open-source-btn");
  const traceModeSwitcher = document.getElementById("trace-mode-switcher");
  const reasoningTree = document.getElementById("reasoning-tree");
  const reasoningEmptyState = document.getElementById("reasoning-empty-state");
  const reasoningCoverageBadge = document.getElementById("reasoning-coverage-badge");
  const workspaceModeSwitch = document.getElementById("workspace-mode-switch");
  const layoutModeCockpitBtn = document.getElementById("layout-mode-cockpit");
  const layoutModeBoardBtn = document.getElementById("layout-mode-board");
  const boardResetBtn = document.getElementById("board-reset-btn");
  const boardCanvasShell = document.getElementById("board-canvas-shell");
  const boardCanvas = document.getElementById("board-canvas");

  const state = {
    sessions: Array.isArray(bootstrap.sessions) ? bootstrap.sessions : [],
    profiles: Array.isArray(bootstrap.profiles) ? bootstrap.profiles : [],
    projectCapsule: bootstrap.projectCapsule || null,
    playbooks: [],
    recentRuns: [],
    selectedRunId: null,
    currentSessionId: null,
    currentSession: null,
    currentSessionDetail: null,
    selectedSubagentId: null,
    selectedScenarioId: null,
    selectedScenarioText: "",
    scenarioStates: {},
    traceMode: "compact",
    layoutMode: "cockpit",
    layoutPreset: "balanced",
    composerExpanded: false,
    layoutState: null,
    boardLayoutState: null,
    activeBoardPanelId: null,
    boardScrollHandle: null,
    isApplyingLayout: false,
    subagentPollHandle: null,
    simpleChatQueue: [],
  };

  const STORAGE_KEYS = {
    mode: "deepseekAgentOS.layout.mode.v1",
    sections: "dashboard.chat.workspace.sections",
    traceMode: "dashboard.chat.workspace.traceMode",
    layoutPreset: "dashboard.chat.workspace.layoutPreset",
    composerExpanded: "dashboard.chat.workspace.composerExpanded",
    drawerOpen: "dashboard.chat.workspace.drawerOpen",
    layoutState: "deepseekAgentOS.layout.cockpit.v1",
    layoutStateLegacy: "deepseekAgentOS.layout.v1",
    boardLayoutState: "deepseekAgentOS.layout.board.v1"
  };

  const LAYOUT_SECTION_KEYS = ["scenarios", "chat", "workTrace", "result", "composer"];
  const LAYOUT_PRESET_ORDERS = {
    balanced: ["scenarios", "chat", "workTrace", "result", "composer"],
    compact: ["scenarios", "result", "composer", "workTrace", "chat"],
    debug: ["scenarios", "workTrace", "chat", "result", "composer"]
  };
  const LAYOUT_SECTION_TARGETS = {
    scenarios: "scenario-rail-body",
    chat: "chat-thread-panel",
    workTrace: "reasoning-body",
    result: "output-panel-body",
    composer: "composer-body"
  };
  const LAYOUT_SECTION_CONFIG = {
    scenarios: { role: "scenarios", min: 44, max: 160, defaultHeight: 140 },
    chat: { role: "chat", min: 120, max: 600, defaultHeight: 280 },
    workTrace: { role: "trace", min: 100, max: 600, defaultHeight: 220 },
    result: { role: "result", min: 90, max: 400, defaultHeight: 180 },
    composer: { role: "composer", min: 118, max: 520, defaultHeight: 160 }
  };
  const PANEL_LIMITS = {
    leftNav: { min: 72, max: 280, defaultSize: 220, cssVar: "--left-nav-width" },
    sessionPanel: { min: 220, max: 420, defaultSize: 300, cssVar: "--session-panel-width" },
    rightInspector: { min: 280, max: 520, defaultSize: 360, cssVar: "--right-inspector-width" },
    bottomDrawer: { min: 120, max: 420, defaultSize: 220, cssVar: "--bottom-drawer-height" }
  };
  const BOARD_CANVAS_LIMITS = {
    minWidth: 3200,
    maxWidth: 5000,
    defaultWidth: 4200,
    minHeight: 2400,
    maxHeight: 4000,
    defaultHeight: 3200,
    padding: 40
  };
  const BOARD_PANEL_LIMITS = {
    sessions: { minWidth: 280, maxWidth: 680, minHeight: 340, maxHeight: 1400 },
    scenarios: { minWidth: 420, maxWidth: 980, minHeight: 220, maxHeight: 520 },
    workTrace: { minWidth: 520, maxWidth: 1200, minHeight: 260, maxHeight: 1100 },
    result: { minWidth: 420, maxWidth: 980, minHeight: 190, maxHeight: 640 },
    composer: { minWidth: 420, maxWidth: 760, minHeight: 180, maxHeight: 520 },
    chat: { minWidth: 420, maxWidth: 760, minHeight: 420, maxHeight: 1400 },
    inspector: { minWidth: 340, maxWidth: 520, minHeight: 360, maxHeight: 1400 },
    artifacts: { minWidth: 520, maxWidth: 980, minHeight: 220, maxHeight: 640 }
  };
  const BOARD_PANEL_KEYS = Object.keys(BOARD_PANEL_LIMITS);
  const BOARD_SECTION_PANEL_KEYS = ["scenarios", "chat", "workTrace", "result", "composer"];

  const SCENARIO_FALLBACKS = {
    scout_context: {
      description: "Зібрати безпечний context pack, session state та nearby evidence перед першим edit slice.",
      group: "Код",
      mode: "prepare",
      riskLevel: "safe",
      quickRun: true,
      sourceFile: "playbooks/scout_context.md"
    },
    build_plan: {
      description: "Скласти короткий реалізаційний план з локальними гіпотезами та дешевого validation check.",
      group: "Код",
      mode: "prepare",
      riskLevel: "safe",
      quickRun: true,
      sourceFile: "playbooks/build_plan.md"
    },
    audit_patch: {
      description: "Провести code review по локальному patch slice з фокусом на regression risks та missing tests.",
      group: "Код",
      mode: "review",
      riskLevel: "guarded",
      quickRun: false,
      sourceFile: "playbooks/audit_patch.md"
    },
    run_focused_tests: {
      description: "Запустити вузький pytest slice або targeted validation command по зміненому фрагменту.",
      group: "Тести",
      mode: "validate",
      riskLevel: "guarded",
      quickRun: false,
      sourceFile: "playbooks/run_focused_tests.md"
    },
    triage_failures: {
      description: "Розібрати test failure, локалізувати контролюючий код та дати repair loop без broad exploration.",
      group: "Тести",
      mode: "triage",
      riskLevel: "guarded",
      quickRun: false,
      sourceFile: "playbooks/triage_failures.md"
    },
    analyze_logs: {
      description: "Зібрати operator-facing зведення по логах, не змішуючи їх з raw reasoning або hidden content.",
      group: "Логи",
      mode: "observe",
      riskLevel: "safe",
      quickRun: true,
      sourceFile: "playbooks/analyze_logs.md"
    },
    trace_failure_path: {
      description: "Відтрасувати failure path по events, reports та subagent artifacts без запуску mutating actions.",
      group: "Логи",
      mode: "observe",
      riskLevel: "safe",
      quickRun: true,
      sourceFile: "playbooks/trace_failure_path.md"
    },
    generate_report: {
      description: "Сформувати компактний report із висновками, ризиками та next steps для operator handoff.",
      group: "Звіти",
      mode: "summarize",
      riskLevel: "safe",
      quickRun: true,
      sourceFile: "playbooks/generate_report.md"
    },
    memory_patch: {
      description: "Підготувати memory patch proposal з чітким reason/risk surface перед підтвердженням.",
      group: "Звіти",
      mode: "patch",
      riskLevel: "guarded",
      quickRun: false,
      sourceFile: "playbooks/memory_patch.md"
    }
  };

  function formatTimestamp(value) {
    if (!value) {
      return "—";
    }
    return String(value).replace("T", " ").replace("Z", "").slice(0, 19) || "—";
  }

  function formatDuration(value) {
    const ms = Number(value);
    if (!Number.isFinite(ms) || ms <= 0) {
      return "—";
    }
    if (ms < 1000) {
      return String(ms) + " ms";
    }
    return (ms / 1000).toFixed(ms >= 10000 ? 0 : 1) + " s";
  }

  function badgeToneClass(tone) {
    switch (tone) {
      case "ok":
      case "success":
      case "done":
      case "completed":
        return "badge-ok";
      case "warn":
      case "warning":
      case "queued":
        return "badge-warn";
      case "error":
      case "failed":
      case "stopped":
      case "cancelled":
      case "canceled":
      case "blocked":
        return "badge-error";
      case "running":
      case "active":
      case "processing":
        return "badge-running";
      default:
        return "badge-muted";
    }
  }

  function applyBadgeTone(node, tone) {
    if (!node) {
      return;
    }
    ["badge-ok", "badge-warn", "badge-error", "badge-muted", "badge-running", "badge-blocked", "badge-approved"].forEach(function (name) {
      node.classList.remove(name);
    });
    node.classList.add("badge", badgeToneClass(String(tone || "").toLowerCase()));
  }

  function readStoredValue(key, fallback) {
    try {
      const raw = window.localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch (error) {
      return fallback;
    }
  }

  function writeStoredValue(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      // Ignore storage failures in constrained environments.
    }
  }

  function removeStoredValue(key) {
    try {
      window.localStorage.removeItem(key);
    } catch (error) {
      // Ignore storage failures in constrained environments.
    }
  }

  function clampNumber(value, min, max, fallback) {
    var number = Number(value);
    if (!Number.isFinite(number)) {
      return fallback;
    }
    return Math.min(max, Math.max(min, Math.round(number)));
  }

  function normalizePreset(value) {
    var preset = String(value || '').toLowerCase();
    if (preset === 'delivery') {
      return 'debug';
    }
    if (preset === 'balanced' || preset === 'compact' || preset === 'debug' || preset === 'custom') {
      return preset;
    }
    return 'balanced';
  }

  function getLayoutSectionKeyFromTarget(targetId) {
    return Object.keys(LAYOUT_SECTION_TARGETS).find(function (sectionKey) {
      return LAYOUT_SECTION_TARGETS[sectionKey] === targetId;
    }) || null;
  }

  function createDefaultLayoutState() {
    return {
      version: 1,
      layoutPreset: 'balanced',
      centralSectionHeights: {
        scenarios: LAYOUT_SECTION_CONFIG.scenarios.defaultHeight,
        chat: LAYOUT_SECTION_CONFIG.chat.defaultHeight,
        workTrace: LAYOUT_SECTION_CONFIG.workTrace.defaultHeight,
        result: LAYOUT_SECTION_CONFIG.result.defaultHeight,
        composer: LAYOUT_SECTION_CONFIG.composer.defaultHeight
      },
      centralSectionOrder: LAYOUT_PRESET_ORDERS.balanced.slice(),
      collapsedSections: {
        scenarios: false,
        chat: false,
        workTrace: false,
        result: false,
        composer: false
      },
      panelWidths: {
        leftNav: PANEL_LIMITS.leftNav.defaultSize,
        sessionPanel: PANEL_LIMITS.sessionPanel.defaultSize,
        rightInspector: PANEL_LIMITS.rightInspector.defaultSize
      },
      bottomDrawerHeight: PANEL_LIMITS.bottomDrawer.defaultSize,
      bottomDrawerCollapsed: true,
      composerExpanded: false,
      navCollapsed: false,
      inspectorCollapsed: false
    };
  }

  function normalizeSectionOrder(order) {
    var unique = [];
    (Array.isArray(order) ? order : []).forEach(function (value) {
      var normalized = String(value || '');
      if (normalized === 'trace') {
        normalized = 'workTrace';
      }
      if (LAYOUT_SECTION_KEYS.indexOf(normalized) >= 0 && unique.indexOf(normalized) < 0) {
        unique.push(normalized);
      }
    });
    LAYOUT_SECTION_KEYS.forEach(function (sectionKey) {
      if (unique.indexOf(sectionKey) < 0) {
        unique.push(sectionKey);
      }
    });
    return unique;
  }

  function readLegacyCollapsedSections() {
    var legacy = readStoredValue(STORAGE_KEYS.sections, {});
    var collapsed = {};
    Object.keys(LAYOUT_SECTION_TARGETS).forEach(function (sectionKey) {
      var targetId = LAYOUT_SECTION_TARGETS[sectionKey];
      if (typeof legacy[targetId] === 'boolean') {
        collapsed[sectionKey] = !legacy[targetId];
      }
    });
    return collapsed;
  }

  function normalizeLayoutState(raw) {
    var defaults = createDefaultLayoutState();
    var source = raw && typeof raw === 'object' ? raw : {};
    var legacyCollapsed = readLegacyCollapsedSections();
    var layout = createDefaultLayoutState();
    layout.layoutPreset = normalizePreset(source.layoutPreset || readStoredValue(STORAGE_KEYS.layoutPreset, defaults.layoutPreset));
    layout.centralSectionOrder = normalizeSectionOrder(source.centralSectionOrder || LAYOUT_PRESET_ORDERS[layout.layoutPreset] || defaults.centralSectionOrder);
    Object.keys(layout.centralSectionHeights).forEach(function (sectionKey) {
      var config = LAYOUT_SECTION_CONFIG[sectionKey];
      layout.centralSectionHeights[sectionKey] = clampNumber(
        source.centralSectionHeights && source.centralSectionHeights[sectionKey],
        config.min,
        config.max,
        defaults.centralSectionHeights[sectionKey]
      );
    });
    Object.keys(layout.collapsedSections).forEach(function (sectionKey) {
      if (source.collapsedSections && typeof source.collapsedSections[sectionKey] === 'boolean') {
        layout.collapsedSections[sectionKey] = source.collapsedSections[sectionKey];
      } else if (typeof legacyCollapsed[sectionKey] === 'boolean') {
        layout.collapsedSections[sectionKey] = legacyCollapsed[sectionKey];
      }
    });
    Object.keys(layout.panelWidths).forEach(function (panelKey) {
      var limits = PANEL_LIMITS[panelKey];
      layout.panelWidths[panelKey] = clampNumber(
        source.panelWidths && source.panelWidths[panelKey],
        limits.min,
        limits.max,
        defaults.panelWidths[panelKey]
      );
    });
    layout.bottomDrawerHeight = clampNumber(
      source.bottomDrawerHeight,
      PANEL_LIMITS.bottomDrawer.min,
      PANEL_LIMITS.bottomDrawer.max,
      defaults.bottomDrawerHeight
    );
    layout.bottomDrawerCollapsed = typeof source.bottomDrawerCollapsed === 'boolean'
      ? source.bottomDrawerCollapsed
      : !readStoredValue(STORAGE_KEYS.drawerOpen, !defaults.bottomDrawerCollapsed);
    layout.composerExpanded = typeof source.composerExpanded === 'boolean'
      ? source.composerExpanded
      : !!readStoredValue(STORAGE_KEYS.composerExpanded, defaults.composerExpanded);
    layout.navCollapsed = !!source.navCollapsed;
    layout.inspectorCollapsed = !!source.inspectorCollapsed;
    return layout;
  }

  function ensureLayoutState() {
    if (!state.layoutState) {
      state.layoutState = createDefaultLayoutState();
    }
    return state.layoutState;
  }

  function loadLayoutState() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEYS.layoutState);
      if (raw == null) {
        raw = window.localStorage.getItem(STORAGE_KEYS.layoutStateLegacy);
      }
      return normalizeLayoutState(raw ? JSON.parse(raw) : null);
    } catch (error) {
      removeStoredValue(STORAGE_KEYS.layoutState);
      removeStoredValue(STORAGE_KEYS.layoutStateLegacy);
      return createDefaultLayoutState();
    }
  }

  function saveLayoutState() {
    if (state.isApplyingLayout || !state.layoutState) {
      return;
    }
    writeStoredValue(STORAGE_KEYS.layoutState, state.layoutState);
  }

  function getSectionElementByKey(sectionKey) {
    return centralWorkspaceStack
      ? centralWorkspaceStack.querySelector('[data-layout-section="' + sectionKey + '"]')
      : null;
  }

  function getSectionBodyByKey(sectionKey) {
    var targetId = LAYOUT_SECTION_TARGETS[sectionKey];
    return targetId ? document.getElementById(targetId) : null;
  }

  function findMatchingPreset(order) {
    var normalized = normalizeSectionOrder(order);
    var matched = null;
    Object.keys(LAYOUT_PRESET_ORDERS).some(function (preset) {
      var presetOrder = normalizeSectionOrder(LAYOUT_PRESET_ORDERS[preset]);
      var same = presetOrder.length === normalized.length && presetOrder.every(function (sectionKey, index) {
        return normalized[index] === sectionKey;
      });
      if (same) {
        matched = preset;
        return true;
      }
      return false;
    });
    return matched;
  }

  function syncWorkspacePresetControl(order) {
    var layout = ensureLayoutState();
    var presetValue = layout.layoutPreset || findMatchingPreset(order || layout.centralSectionOrder) || 'custom';
    if (centralWorkspace) {
      centralWorkspace.setAttribute('data-layout-preset', presetValue);
    }
    if (workspacePresetSelect && workspacePresetSelect.value !== presetValue) {
      workspacePresetSelect.value = presetValue;
    }
  }

  function syncMoveControls() {
    var order = normalizeSectionOrder(ensureLayoutState().centralSectionOrder);
    order.forEach(function (sectionKey, index) {
      var section = getSectionElementByKey(sectionKey);
      if (!section) {
        return;
      }
      section.querySelectorAll('[data-section-move="up"]').forEach(function (button) {
        button.disabled = index === 0;
      });
      section.querySelectorAll('[data-section-move="down"]').forEach(function (button) {
        button.disabled = index === order.length - 1;
      });
    });
  }

  function applySectionOrder(order, options) {
    options = options || {};
    var layout = ensureLayoutState();
    var normalized = normalizeSectionOrder(order);
    layout.centralSectionOrder = normalized.slice();
    normalized.forEach(function (sectionKey, index) {
      var section = getSectionElementByKey(sectionKey);
      if (section) {
        section.style.order = String(index);
      }
    });
    if (!options.preservePreset) {
      layout.layoutPreset = findMatchingPreset(normalized) || 'custom';
    }
    syncWorkspacePresetControl(normalized);
    syncMoveControls();
    if (!options.skipSave) {
      saveLayoutState();
    }
  }

  function clampSectionHeight(sectionKey, height) {
    var config = LAYOUT_SECTION_CONFIG[sectionKey] || LAYOUT_SECTION_CONFIG.chat;
    return clampNumber(height, config.min, config.max, config.defaultHeight);
  }

  function setSectionHeight(sectionKey, height, options) {
    options = options || {};
    var body = getSectionBodyByKey(sectionKey);
    var section = getSectionElementByKey(sectionKey);
    if (!body || !section) {
      return 0;
    }
    var clamped = clampSectionHeight(sectionKey, height);
    body.style.height = clamped + 'px';
    section.setAttribute('data-section-height', String(clamped));
    ensureLayoutState().centralSectionHeights[sectionKey] = clamped;
    if (!options.skipSave) {
      saveLayoutState();
    }
    return clamped;
  }

  function setPanelWidth(panelKey, width, options) {
    options = options || {};
    var limits = PANEL_LIMITS[panelKey];
    if (!limits) {
      return 0;
    }
    var clamped = clampNumber(width, limits.min, limits.max, limits.defaultSize);
    document.documentElement.style.setProperty(limits.cssVar, clamped + 'px');
    ensureLayoutState().panelWidths[panelKey] = clamped;
    if (!options.skipSave) {
      saveLayoutState();
    }
    return clamped;
  }

  function setBottomDrawerHeight(height, options) {
    options = options || {};
    var clamped = clampNumber(height, PANEL_LIMITS.bottomDrawer.min, PANEL_LIMITS.bottomDrawer.max, PANEL_LIMITS.bottomDrawer.defaultSize);
    document.documentElement.style.setProperty(PANEL_LIMITS.bottomDrawer.cssVar, clamped + 'px');
    ensureLayoutState().bottomDrawerHeight = clamped;
    if (!options.skipSave) {
      saveLayoutState();
    }
    return clamped;
  }

  function applyLayoutState(layout, options) {
    options = options || {};
    state.isApplyingLayout = true;
    state.layoutState = normalizeLayoutState(layout);
    setPanelWidth('leftNav', state.layoutState.panelWidths.leftNav, { skipSave: true });
    setPanelWidth('sessionPanel', state.layoutState.panelWidths.sessionPanel, { skipSave: true });
    setPanelWidth('rightInspector', state.layoutState.panelWidths.rightInspector, { skipSave: true });
    setBottomDrawerHeight(state.layoutState.bottomDrawerHeight, { skipSave: true });
    setNavCollapsed(state.layoutState.navCollapsed, { skipSave: true });
    setInspectorCollapsed(state.layoutState.inspectorCollapsed, { skipSave: true });
    setDrawerOpen(!state.layoutState.bottomDrawerCollapsed, { skipSave: true, skipLegacyStorage: true });
    setWorkspacePreset(state.layoutState.layoutPreset, { skipSave: true, preserveOrder: true, skipLegacyStorage: true });
    applySectionOrder(state.layoutState.centralSectionOrder, { skipSave: true, preservePreset: true });
    Object.keys(state.layoutState.centralSectionHeights).forEach(function (sectionKey) {
      setSectionHeight(sectionKey, state.layoutState.centralSectionHeights[sectionKey], { skipSave: true });
    });
    Object.keys(state.layoutState.collapsedSections).forEach(function (sectionKey) {
      setCollapsedState(LAYOUT_SECTION_TARGETS[sectionKey], !state.layoutState.collapsedSections[sectionKey], { skipSave: true, skipLegacyStorage: true });
    });
    setComposerExpanded(state.layoutState.composerExpanded, { skipSave: true, skipLegacyStorage: true, skipHeightChange: true });
    state.isApplyingLayout = false;
    if (!options.skipSave) {
      saveLayoutState();
    }
  }

  function resetLayoutState() {
    state.layoutState = createDefaultLayoutState();
    removeStoredValue(STORAGE_KEYS.layoutState);
    removeStoredValue(STORAGE_KEYS.layoutStateLegacy);
    removeStoredValue(STORAGE_KEYS.layoutPreset);
    removeStoredValue(STORAGE_KEYS.composerExpanded);
    removeStoredValue(STORAGE_KEYS.drawerOpen);
    writeStoredValue(STORAGE_KEYS.sections, {});
    applyLayoutState(state.layoutState);
    return state.layoutState;
  }

  function loadLayoutMode() {
    var mode = readStoredValue(STORAGE_KEYS.mode, 'cockpit');
    return mode === 'board' ? 'board' : (mode === 'simple' ? 'simple' : 'cockpit');
  }

  function measureBoardCanvas() {
    var viewportWidth = boardCanvasShell && boardCanvasShell.clientWidth
      ? boardCanvasShell.clientWidth
      : Math.max(window.innerWidth - 120, 1080);
    var viewportHeight = boardCanvasShell && boardCanvasShell.clientHeight
      ? boardCanvasShell.clientHeight
      : Math.max(window.innerHeight - 220, 760);
    return {
      viewportWidth: viewportWidth,
      viewportHeight: viewportHeight,
      width: clampNumber(Math.round(viewportWidth * 4.6), BOARD_CANVAS_LIMITS.minWidth, BOARD_CANVAS_LIMITS.maxWidth, BOARD_CANVAS_LIMITS.defaultWidth),
      height: clampNumber(Math.round(viewportHeight * 4.1), BOARD_CANVAS_LIMITS.minHeight, BOARD_CANVAS_LIMITS.maxHeight, BOARD_CANVAS_LIMITS.defaultHeight)
    };
  }

  function getDefaultBoardPanels(canvasMetrics) {
    var padding = BOARD_CANVAS_LIMITS.padding;
    var viewportWidth = canvasMetrics.viewportWidth;
    var viewportHeight = canvasMetrics.viewportHeight;
    var sessionsWidth = 320;
    var sessionsHeight = clampNumber(Math.round(viewportHeight * 0.82), BOARD_PANEL_LIMITS.sessions.minHeight, BOARD_PANEL_LIMITS.sessions.maxHeight, 720);
    var chatWidth = clampNumber(Math.round(viewportWidth * 0.3), BOARD_PANEL_LIMITS.chat.minWidth, BOARD_PANEL_LIMITS.chat.maxWidth, 520);
    var chatHeight = clampNumber(Math.round(viewportHeight * 0.76), BOARD_PANEL_LIMITS.chat.minHeight, BOARD_PANEL_LIMITS.chat.maxHeight, 780);
    var composerWidth = clampNumber(chatWidth, BOARD_PANEL_LIMITS.composer.minWidth, BOARD_PANEL_LIMITS.composer.maxWidth, 520);
    var composerHeight = clampNumber(Math.round(viewportHeight * 0.26), BOARD_PANEL_LIMITS.composer.minHeight, BOARD_PANEL_LIMITS.composer.maxHeight, 260);
    var chatX = Math.max(padding + sessionsWidth + 720, viewportWidth - chatWidth - padding);
    var inspectorWidth = clampNumber(Math.round(viewportWidth * 0.24), BOARD_PANEL_LIMITS.inspector.minWidth, BOARD_PANEL_LIMITS.inspector.maxWidth, 400);
    var inspectorHeight = clampNumber(Math.round(viewportHeight * 0.66), BOARD_PANEL_LIMITS.inspector.minHeight, BOARD_PANEL_LIMITS.inspector.maxHeight, 660);
    var inspectorX = Math.max(padding + sessionsWidth + 260, chatX - inspectorWidth - 28);
    var workAreaX = padding + sessionsWidth + 28;
    var workAreaWidth = clampNumber(inspectorX - workAreaX - 28, BOARD_PANEL_LIMITS.workTrace.minWidth, BOARD_PANEL_LIMITS.workTrace.maxWidth, 760);
    var scenariosWidth = clampNumber(workAreaWidth - 120, BOARD_PANEL_LIMITS.scenarios.minWidth, BOARD_PANEL_LIMITS.scenarios.maxWidth, 640);
    var workTraceHeight = clampNumber(Math.round(viewportHeight * 0.48), BOARD_PANEL_LIMITS.workTrace.minHeight, BOARD_PANEL_LIMITS.workTrace.maxHeight, 520);
    var resultWidth = clampNumber(workAreaWidth - 40, BOARD_PANEL_LIMITS.result.minWidth, BOARD_PANEL_LIMITS.result.maxWidth, 720);
    var resultHeight = clampNumber(Math.round(viewportHeight * 0.24), BOARD_PANEL_LIMITS.result.minHeight, BOARD_PANEL_LIMITS.result.maxHeight, 260);
    var artifactsWidth = clampNumber(chatWidth + inspectorWidth - 40, BOARD_PANEL_LIMITS.artifacts.minWidth, BOARD_PANEL_LIMITS.artifacts.maxWidth, 760);
    var artifactsHeight = clampNumber(Math.round(viewportHeight * 0.26), BOARD_PANEL_LIMITS.artifacts.minHeight, BOARD_PANEL_LIMITS.artifacts.maxHeight, 280);

    return {
      sessions: { x: padding, y: 48, width: sessionsWidth, height: sessionsHeight, zIndex: 1, minimized: false, collapsed: false, visible: true, pinned: false },
      scenarios: { x: workAreaX, y: 48, width: scenariosWidth, height: 252, zIndex: 2, minimized: false, collapsed: false, visible: true, pinned: false },
      workTrace: { x: workAreaX, y: 328, width: workAreaWidth, height: workTraceHeight, zIndex: 3, minimized: false, collapsed: false, visible: true, pinned: false },
      result: { x: workAreaX, y: 48 + 252 + 28 + workTraceHeight + 28, width: resultWidth, height: resultHeight, zIndex: 4, minimized: false, collapsed: false, visible: true, pinned: false },
      composer: { x: chatX, y: 48 + chatHeight + 28, width: composerWidth, height: composerHeight, zIndex: 5, minimized: false, collapsed: false, visible: true, pinned: false },
      chat: { x: chatX, y: 48, width: chatWidth, height: chatHeight, zIndex: 6, minimized: false, collapsed: false, visible: true, pinned: false },
      inspector: { x: inspectorX, y: 48, width: inspectorWidth, height: inspectorHeight, zIndex: 7, minimized: false, collapsed: false, visible: true, pinned: false },
      artifacts: { x: Math.max(inspectorX, chatX - 120), y: 48 + Math.max(inspectorHeight, chatHeight) + 36, width: artifactsWidth, height: artifactsHeight, zIndex: 8, minimized: false, collapsed: false, visible: true, pinned: false }
    };
  }

  function clampBoardPanelState(panelKey, rawPanel, defaults, canvasMetrics) {
    var limits = BOARD_PANEL_LIMITS[panelKey];
    var source = rawPanel && typeof rawPanel === 'object' ? rawPanel : {};
    var fallback = defaults[panelKey];
    var width = clampNumber(source.width, limits.minWidth, limits.maxWidth, fallback.width);
    var height = clampNumber(source.height, limits.minHeight, limits.maxHeight, fallback.height);
    var maxX = Math.max(0, canvasMetrics.width - width - BOARD_CANVAS_LIMITS.padding);
    var maxY = Math.max(0, canvasMetrics.height - height - BOARD_CANVAS_LIMITS.padding);
    return {
      x: clampNumber(source.x, 0, maxX, fallback.x),
      y: clampNumber(source.y, 0, maxY, fallback.y),
      width: width,
      height: height,
      zIndex: clampNumber(source.zIndex, 1, 999, fallback.zIndex),
      minimized: !!source.minimized,
      collapsed: typeof source.collapsed === 'boolean' ? source.collapsed : !!fallback.collapsed,
      visible: typeof source.visible === 'boolean' ? source.visible : true,
      pinned: !!source.pinned
    };
  }

  function createDefaultBoardLayoutState() {
    var canvasMetrics = measureBoardCanvas();
    return {
      version: 1,
      canvas: {
        width: canvasMetrics.width,
        height: canvasMetrics.height
      },
      scroll: { left: 0, top: 0 },
      nextZIndex: BOARD_PANEL_KEYS.length + 2,
      panels: getDefaultBoardPanels(canvasMetrics)
    };
  }

  function normalizeBoardLayoutState(raw) {
    var source = raw && typeof raw === 'object' ? raw : {};
    var measured = measureBoardCanvas();
    var canvasMetrics = {
      viewportWidth: measured.viewportWidth,
      viewportHeight: measured.viewportHeight,
      width: clampNumber(source.canvas && source.canvas.width, BOARD_CANVAS_LIMITS.minWidth, BOARD_CANVAS_LIMITS.maxWidth, measured.width),
      height: clampNumber(source.canvas && source.canvas.height, BOARD_CANVAS_LIMITS.minHeight, BOARD_CANVAS_LIMITS.maxHeight, measured.height)
    };
    var defaults = getDefaultBoardPanels(canvasMetrics);
    var panels = {};
    var highestZ = 0;
    BOARD_PANEL_KEYS.forEach(function (panelKey) {
      panels[panelKey] = clampBoardPanelState(panelKey, source.panels && source.panels[panelKey], defaults, canvasMetrics);
      highestZ = Math.max(highestZ, panels[panelKey].zIndex);
    });
    return {
      version: 1,
      canvas: {
        width: canvasMetrics.width,
        height: canvasMetrics.height
      },
      scroll: {
        left: clampNumber(source.scroll && source.scroll.left, 0, Math.max(0, canvasMetrics.width - measured.viewportWidth), 0),
        top: clampNumber(source.scroll && source.scroll.top, 0, Math.max(0, canvasMetrics.height - measured.viewportHeight), 0)
      },
      nextZIndex: clampNumber(source.nextZIndex, highestZ || 1, 999, highestZ || (BOARD_PANEL_KEYS.length + 2)),
      panels: panels
    };
  }

  function ensureBoardLayoutState() {
    if (!state.boardLayoutState) {
      state.boardLayoutState = createDefaultBoardLayoutState();
    }
    return state.boardLayoutState;
  }

  function loadBoardLayoutState() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEYS.boardLayoutState);
      return normalizeBoardLayoutState(raw ? JSON.parse(raw) : null);
    } catch (error) {
      removeStoredValue(STORAGE_KEYS.boardLayoutState);
      return createDefaultBoardLayoutState();
    }
  }

  function saveBoardLayoutState() {
    if (!state.boardLayoutState) {
      return;
    }
    writeStoredValue(STORAGE_KEYS.boardLayoutState, state.boardLayoutState);
  }

  function getBoardPanelElement(panelKey) {
    return document.querySelector('[data-board-panel="' + panelKey + '"]');
  }

  function syncLayoutModeControls() {
    var mode = state.layoutMode || 'simple';
    document.body.classList.toggle('layout-mode--board', mode === 'board');
    document.body.classList.toggle('layout-mode--cockpit', mode === 'cockpit');
    document.body.classList.toggle('layout-mode--simple', mode === 'simple');
    
    if (workspaceModeSwitch) {
      workspaceModeSwitch.setAttribute('data-active-mode', mode);
    }
    
    var btns = [
      document.getElementById('layout-mode-cockpit'),
      document.getElementById('layout-mode-board'),
      document.getElementById('layout-mode-simple')
    ];
    btns.forEach(function (button) {
      if (!button) return;
      var active = button.getAttribute('data-layout-mode') === mode;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    var select = document.getElementById('simple-chat-mode-switch');
    if (select) select.value = mode;
}

function applyBoardPanelState(panelKey, panelState) {
    var panel = getBoardPanelElement(panelKey);
    if (!panel || !panelState) {
      return;
    }
    panel.style.left = panelState.x + 'px';
    panel.style.top = panelState.y + 'px';
    panel.style.width = panelState.width + 'px';
    panel.style.height = panelState.height + 'px';
    panel.style.zIndex = String(panelState.zIndex);
    panel.setAttribute('data-board-collapsed', panelState.collapsed ? 'true' : 'false');
    panel.classList.toggle('board-panel--focused', panelKey === state.activeBoardPanelId);
    panel.classList.toggle('board-panel--collapsed', !!panelState.collapsed);
    panel.classList.toggle('board-panel--hidden', panelState.visible === false);
    if (BOARD_SECTION_PANEL_KEYS.indexOf(panelKey) >= 0) {
      setCollapsedState(LAYOUT_SECTION_TARGETS[panelKey], !panelState.collapsed, { skipSave: true, skipLegacyStorage: true });
    }
    if (panelKey === 'artifacts') {
      setDrawerOpen(!panelState.collapsed, { skipSave: true, skipLegacyStorage: true });
    }
  }

  function applyBoardLayoutState(layout, options) {
    options = options || {};
    state.boardLayoutState = normalizeBoardLayoutState(layout);
    if (boardCanvas) {
      boardCanvas.style.setProperty('--board-canvas-width', state.boardLayoutState.canvas.width + 'px');
      boardCanvas.style.setProperty('--board-canvas-height', state.boardLayoutState.canvas.height + 'px');
    }
    BOARD_PANEL_KEYS.forEach(function (panelKey) {
      applyBoardPanelState(panelKey, state.boardLayoutState.panels[panelKey]);
    });
    if (!state.activeBoardPanelId) {
      state.activeBoardPanelId = 'chat';
    }
    if (!options.skipScroll && state.layoutMode === 'board') {
      window.requestAnimationFrame(function () {
        window.scrollTo(state.boardLayoutState.scroll.left, state.boardLayoutState.scroll.top);
      });
    }
    if (!options.skipSave) {
      saveBoardLayoutState();
    }
  }

  function focusBoardPanel(panelKey, options) {
    options = options || {};
    var layout = ensureBoardLayoutState();
    var panelState = layout.panels[panelKey];
    if (!panelState) {
      return;
    }
    if (!options.skipRaise) {
      layout.nextZIndex = Math.max(layout.nextZIndex || 1, panelState.zIndex || 1) + 1;
      panelState.zIndex = layout.nextZIndex;
    }
    state.activeBoardPanelId = panelKey;
    BOARD_PANEL_KEYS.forEach(function (key) {
      applyBoardPanelState(key, layout.panels[key]);
    });
    if (!options.skipSave) {
      saveBoardLayoutState();
    }
  }

  function moveBoardPanel(panelKey, x, y, options) {
    options = options || {};
    var layout = ensureBoardLayoutState();
    var panelState = layout.panels[panelKey];
    if (!panelState) {
      return;
    }
    var maxX = Math.max(0, layout.canvas.width - panelState.width - BOARD_CANVAS_LIMITS.padding);
    var maxY = Math.max(0, layout.canvas.height - panelState.height - BOARD_CANVAS_LIMITS.padding);
    panelState.x = clampNumber(x, 0, maxX, panelState.x);
    panelState.y = clampNumber(y, 0, maxY, panelState.y);
    applyBoardPanelState(panelKey, panelState);
    if (!options.skipSave) {
      saveBoardLayoutState();
    }
  }

  function resizeBoardPanel(panelKey, direction, deltaX, deltaY, options) {
    options = options || {};
    var layout = ensureBoardLayoutState();
    var panelState = layout.panels[panelKey];
    var limits = BOARD_PANEL_LIMITS[panelKey];
    if (!panelState || !limits) {
      return;
    }
    var next = {
      x: panelState.x,
      y: panelState.y,
      width: panelState.width,
      height: panelState.height
    };
    if (direction.indexOf('e') >= 0) {
      next.width = clampNumber(panelState.width + deltaX, limits.minWidth, limits.maxWidth, panelState.width);
    }
    if (direction.indexOf('s') >= 0) {
      next.height = clampNumber(panelState.height + deltaY, limits.minHeight, limits.maxHeight, panelState.height);
    }
    if (direction.indexOf('w') >= 0) {
      var nextWidth = clampNumber(panelState.width - deltaX, limits.minWidth, limits.maxWidth, panelState.width);
      next.x = panelState.x + (panelState.width - nextWidth);
      next.width = nextWidth;
    }
    if (direction.indexOf('n') >= 0) {
      var nextHeight = clampNumber(panelState.height - deltaY, limits.minHeight, limits.maxHeight, panelState.height);
      next.y = panelState.y + (panelState.height - nextHeight);
      next.height = nextHeight;
    }
    panelState.width = next.width;
    panelState.height = next.height;
    moveBoardPanel(panelKey, next.x, next.y, { skipSave: true });
    applyBoardPanelState(panelKey, panelState);
    if (!options.skipSave) {
      saveBoardLayoutState();
    }
  }

  function resetBoardLayoutState() {
    state.boardLayoutState = createDefaultBoardLayoutState();
    removeStoredValue(STORAGE_KEYS.boardLayoutState);
    applyBoardLayoutState(state.boardLayoutState, { skipSave: false, skipScroll: false });
    return state.boardLayoutState;
  }

  function scrollBoardPanelIntoView(panelKey) {
    if (state.layoutMode !== 'board') {
      return;
    }
    var layout = ensureBoardLayoutState();
    var panelState = layout.panels[panelKey];
    if (!panelState) {
      return;
    }
    window.scrollTo({
      left: Math.max(0, panelState.x - 32),
      top: Math.max(0, panelState.y - 32),
      behavior: 'smooth'
    });
  }

  function persistBoardScrollPosition() {
    if (state.layoutMode !== 'board' || !state.boardLayoutState) {
      return;
    }
    state.boardLayoutState.scroll.left = Math.max(0, Math.round(window.scrollX || window.pageXOffset || 0));
    state.boardLayoutState.scroll.top = Math.max(0, Math.round(window.scrollY || window.pageYOffset || 0));
    if (state.boardScrollHandle) {
      window.clearTimeout(state.boardScrollHandle);
    }
    state.boardScrollHandle = window.setTimeout(function () {
      saveBoardLayoutState();
    }, 80);
  }

  function isBoardDragTargetInteractive(target) {
    return !!(target && target.closest('button, a, input, select, textarea, summary, [role="button"], .section-menu__btn, .section-toggle'));
  }

  
  var navCollapseBtn = document.getElementById('nav-collapse-btn');
  var inspectorToggleBtn = document.getElementById('inspector-toggle-btn');
  var leftNav = document.getElementById('left-nav');
  var inspectorColumn = document.getElementById('inspector-column');

  if (navCollapseBtn && leftNav) {
    navCollapseBtn.addEventListener('click', function() {
      state.layoutState.navCollapsed = !state.layoutState.navCollapsed;
      leftNav.classList.toggle('nav-collapsed', state.layoutState.navCollapsed);
      saveLayoutState();
    });
  }

  if (inspectorToggleBtn && inspectorColumn) {
    inspectorToggleBtn.addEventListener('click', function() {
      state.layoutState.inspectorCollapsed = !state.layoutState.inspectorCollapsed;
      inspectorColumn.classList.toggle('inspector-collapsed', state.layoutState.inspectorCollapsed);
      saveLayoutState();
    });
  }

  
  var simpleModeBtn = document.getElementById('layout-mode-simple');
  if (simpleModeBtn) {
    simpleModeBtn.addEventListener('click', function() { setLayoutMode('simple'); });
  }
  var simpleModeSelect = document.getElementById('simple-chat-mode-switch');
  if (simpleModeSelect) {
    simpleModeSelect.addEventListener('change', function() { setLayoutMode(this.value); });
    
    if (simpleChatModelSelect) {
      simpleChatModelSelect.addEventListener('change', function() {
        if (profileSelect) profileSelect.value = simpleChatModelSelect.value;
        updateProfile().catch(function (error) { setWarning(error.message || 'Profile update failed.'); });
      });
    }
  }
  
  var menuNew = document.getElementById('simple-menu-new');
  if (menuNew) {
      menuNew.addEventListener('click', function() {
          if (newSessionBtn) newSessionBtn.click();
      });
  }
  var menuCopyId = document.getElementById('simple-menu-copy-id');
  if (menuCopyId) {
      menuCopyId.addEventListener('click', function() {
          if (state.currentSessionId) {
              navigator.clipboard.writeText(state.currentSessionId);
              setWarning('ID copied to clipboard.');
          } else {
              setWarning('No active session.');
          }
      });
  }
  var menuDrawerBtn = document.getElementById('simple-menu-drawer');
  var advancedDrawer = document.getElementById('simple-chat-advanced-drawer');
  var menuLeftDrawerBtn = document.getElementById('simple-menu-left-drawer');
  var leftDrawer = document.getElementById('simple-chat-left-drawer');
  
  function closeAllSimpleDrawers() {
      if (advancedDrawer) advancedDrawer.classList.remove('is-open');
      if (leftDrawer) leftDrawer.classList.remove('is-open');
  }

  if (menuDrawerBtn && advancedDrawer) {
      menuDrawerBtn.addEventListener('click', function() {
          var wasOpen = advancedDrawer.classList.contains('is-open');
          closeAllSimpleDrawers();
          if (!wasOpen) advancedDrawer.classList.add('is-open');
      });
      var drawerCloseBtn = document.getElementById('simple-chat-drawer-close');
      if (drawerCloseBtn) {
          drawerCloseBtn.addEventListener('click', function() {
              advancedDrawer.classList.remove('is-open');
          });
      }
      var rightCollapseBtn = document.getElementById('simple-chat-right-drawer-collapse');
      if (rightCollapseBtn) {
          rightCollapseBtn.addEventListener('click', function() {
              advancedDrawer.classList.remove('is-open');
          });
      }
  }

  if (menuLeftDrawerBtn && leftDrawer) {
      menuLeftDrawerBtn.addEventListener('click', function() {
          var wasOpen = leftDrawer.classList.contains('is-open');
          closeAllSimpleDrawers();
          if (!wasOpen) leftDrawer.classList.add('is-open');
      });
      var leftDrawerCloseBtn = document.getElementById('simple-chat-left-drawer-close');
      if (leftDrawerCloseBtn) {
          leftDrawerCloseBtn.addEventListener('click', function() {
              leftDrawer.classList.remove('is-open');
          });
      }
      var leftCollapseBtn = document.getElementById('simple-chat-left-drawer-collapse');
      if (leftCollapseBtn) {
          leftCollapseBtn.addEventListener('click', function() {
              leftDrawer.classList.remove('is-open');
          });
      }
  }
  var simpleInput = document.getElementById('simple-chat-input');
  var simpleSendBtn = document.getElementById('simple-chat-send-btn');
  
  function updateSimpleChatComposer() {
    if (!simpleSendBtn || !simpleInput) return;
    var isRunning = state.currentSession && state.currentSession.session && state.currentSession.session.status && state.currentSession.session.status.match(/running|active/i);
    var hasText = simpleInput.value.trim().length > 0;
    
    if (isRunning) {
        if (hasText) {
            simpleSendBtn.textContent = 'У чергу';
            simpleSendBtn.className = 'simple-chat-composer__send-btn simple-chat-send--queue';
        } else {
            simpleSendBtn.textContent = 'Stop';
            simpleSendBtn.className = 'simple-chat-composer__send-btn simple-chat-send--running simple-chat-stop';
        }
    } else {
        simpleSendBtn.textContent = '➤';
        simpleSendBtn.className = 'simple-chat-composer__send-btn simple-chat-send--idle';
    }
    
    // Also update queue pill if there is a queue
    var composerWrap = document.querySelector('.simple-chat-composer');
    if (composerWrap) {
        var pill = document.getElementById('simple-chat-queue-pill');
        if (state.simpleChatQueue.length > 0) {
            if (!pill) {
                pill = document.createElement('div');
                pill.id = 'simple-chat-queue-pill';
                pill.className = 'simple-chat-queue-pill';
                composerWrap.insertBefore(pill, composerWrap.firstChild);
            }
            pill.textContent = state.simpleChatQueue.length + ' у черзі';
        } else if (pill) {
            pill.remove();
        }
    }
  }

  if (simpleSendBtn && simpleInput) {
    simpleInput.addEventListener('input', updateSimpleChatComposer);
    simpleSendBtn.addEventListener('click', function() {
       var isRunning = state.currentSession && state.currentSession.session && state.currentSession.session.status && state.currentSession.session.status.match(/running|active/i);
       var text = simpleInput.value.trim();
       
       if (isRunning) {
           if (text) {
               state.simpleChatQueue.push(text);
               simpleInput.value = '';
               updateSimpleChatComposer();
               if (state.currentSessionDetail) renderSimpleChatThread(state.currentSessionDetail);
           } else {
               // Stop functionality
               if (state.selectedSubagentId) {
                   cancelSelectedSubagent().catch(function (error) { setWarning(error.message || 'Stop failed.'); });
               } else {
                   setWarning('Top-level run cancel is deferred if no subagent selected.');
                   // Or call cancel top-level run if available. Since it's a UX patch, just show warning or call API.
               }
           }
           return;
       }
       
       if (!text) return;
       if (chatInput) chatInput.value = text;
       simpleInput.value = '';
       sendMessage().catch(function (error) { setWarning(error.message || 'Send failed.'); });
       updateSimpleChatComposer();
    });
    simpleInput.addEventListener('keydown', function(e) {
       if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          simpleSendBtn.click();
       }
    });
  }

  function initBoardInteractions() {
    document.querySelectorAll('[data-board-panel]').forEach(function (panel) {
      if (panel.dataset.boardInit === 'true') {
        return;
      }
      panel.dataset.boardInit = 'true';
      var panelKey = panel.getAttribute('data-board-panel');
      panel.addEventListener('pointerdown', function () {
        if (state.layoutMode === 'board') {
          focusBoardPanel(panelKey, { skipSave: true });
        }
      });
      panel.querySelectorAll('[data-board-drag-handle]').forEach(function (handle) {
        handle.addEventListener('pointerdown', function (event) {
          if (state.layoutMode !== 'board' || event.button !== 0 || isBoardDragTargetInteractive(event.target)) {
            return;
          }
          event.preventDefault();
          focusBoardPanel(panelKey, { skipSave: true });
          var startX = event.clientX;
          var startY = event.clientY;
          var layout = ensureBoardLayoutState();
          var panelState = layout.panels[panelKey];
          var originX = panelState.x;
          var originY = panelState.y;
          panel.classList.add('board-panel--dragging');
          document.body.classList.add('layout-resizing');
          function onPointerMove(moveEvent) {
            moveBoardPanel(panelKey, originX + (moveEvent.clientX - startX), originY + (moveEvent.clientY - startY), { skipSave: true });
          }
          function onPointerUp() {
            panel.classList.remove('board-panel--dragging');
            document.body.classList.remove('layout-resizing');
            document.removeEventListener('pointermove', onPointerMove);
            document.removeEventListener('pointerup', onPointerUp);
            document.removeEventListener('pointercancel', onPointerUp);
            saveBoardLayoutState();
          }
          document.addEventListener('pointermove', onPointerMove);
          document.addEventListener('pointerup', onPointerUp);
          document.addEventListener('pointercancel', onPointerUp);
        });
      });
      panel.querySelectorAll('[data-board-resize]').forEach(function (handle) {
        handle.addEventListener('pointerdown', function (event) {
          if (state.layoutMode !== 'board' || event.button !== 0) {
            return;
          }
          event.preventDefault();
          focusBoardPanel(panelKey, { skipSave: true });
          var direction = handle.getAttribute('data-board-resize') || 'se';
          var startX = event.clientX;
          var startY = event.clientY;
          panel.classList.add('workspace-section--resizing');
          document.body.classList.add('layout-resizing');
          function onPointerMove(moveEvent) {
            resizeBoardPanel(panelKey, direction, moveEvent.clientX - startX, moveEvent.clientY - startY, { skipSave: true });
          }
          function onPointerUp() {
            panel.classList.remove('workspace-section--resizing');
            document.body.classList.remove('layout-resizing');
            document.removeEventListener('pointermove', onPointerMove);
            document.removeEventListener('pointerup', onPointerUp);
            document.removeEventListener('pointercancel', onPointerUp);
            saveBoardLayoutState();
          }
          document.addEventListener('pointermove', onPointerMove);
          document.addEventListener('pointerup', onPointerUp);
          document.addEventListener('pointercancel', onPointerUp);
        });
      });
    });
    if (!window.__deepseekBoardScrollBound) {
      window.__deepseekBoardScrollBound = true;
      window.addEventListener('scroll', function () {
        persistBoardScrollPosition();
      }, { passive: true });
    }
  }

  function setLayoutMode(mode, options) {
    options = options || {};
    state.layoutMode = (mode === 'board') ? 'board' : (mode === 'simple' ? 'simple' : 'cockpit');
    syncLayoutModeControls();
    if (!options.skipPersist) {
      writeStoredValue(STORAGE_KEYS.mode, state.layoutMode);
    }
    if (state.layoutMode === 'board') {
      applyBoardLayoutState(state.boardLayoutState || loadBoardLayoutState(), { skipSave: !!options.skipSave, skipScroll: !!options.skipScroll });
      setDrawerOpen(true, { skipSave: true, skipLegacyStorage: true });
    } else {
      
      BOARD_PANEL_KEYS.forEach(function(key) {
        var p = getBoardPanelElement(key);
        if (p) {
          p.style.width = '';
          p.style.height = '';
          p.style.left = '';
          p.style.top = '';
          p.style.position = '';
          p.style.zIndex = '';
        }
      });
      applyLayoutState(state.layoutState || loadLayoutState(), { skipSave: !!options.skipSave });
    }
  }

  function normalizeStatus(value) {
    return String(value || "").toLowerCase();
  }

  function excerptText(value, maxChars) {
    const clean = String(value || "").replace(/\s+/g, " ").trim();
    if (!clean) {
      return "—";
    }
    if (!maxChars || clean.length <= maxChars) {
      return clean;
    }
    return clean.slice(0, Math.max(1, maxChars - 1)) + "…";
  }

  function timestampMs(value) {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function prettifyEventType(value) {
    const text = String(value || "event").replace(/[_.-]+/g, " ").trim();
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Event";
  }

  function formatTraceModeLabel(mode) {
    switch (mode) {
      case "working":
        return "Робочий";
      case "detailed":
        return "Детальний trace";
      default:
        return "Компактний";
    }
  }

  function summarizeMetadata(metadata, maxPairs) {
    if (!metadata || typeof metadata !== "object") {
      return "";
    }
    const pairs = Object.entries(metadata).slice(0, maxPairs || 2);
    return pairs.map(function (entry) {
      return String(entry[0]) + ": " + excerptText(entry[1], 48);
    }).join(" · ");
  }

  function stringifySurface(value) {
    if (value == null || value === "") {
      return "Немає результатів.";
    }
    if (typeof value === "string") {
      return value;
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch (error) {
      return String(value);
    }
  }

  function setOutputSurface(tone, summary, detail) {
    if (outputStatusBadge) {
      outputStatusBadge.textContent = String(tone || "idle").toUpperCase();
      applyBadgeTone(outputStatusBadge, tone || "idle");
    }
    if (resultSectionStatus) {
      resultSectionStatus.textContent = String(tone || "idle");
      applyBadgeTone(resultSectionStatus, tone || "idle");
    }
    if (outputStatusLine) {
      outputStatusLine.textContent = summary || "Публічний результат з'явиться після першої дії.";
    }
    if (outputResultBox && detail !== undefined) {
      outputResultBox.textContent = stringifySurface(detail);
    }
  }

  function syncOutputFromTurns(turns) {
    const items = Array.isArray(turns) ? turns : [];
    const latestAssistant = items.slice().reverse().find(function (turn) {
      return turn && turn.role === "assistant" && turn.visible_content;
    });
    if (!latestAssistant) {
      if (!items.length) {
        setOutputSurface("idle", "Публічний результат з'явиться після першої дії.", "Немає результатів.");
      }
      return;
    }
    setOutputSurface("success", "Остання відповідь агента завантажена.", latestAssistant.visible_content);
  }

  function renderProjectCapsule(capsule) {
    const project = capsule && capsule.project ? capsule.project : {};
    const phase = capsule && capsule.current_phase ? capsule.current_phase : {};
    const counts = capsule && capsule.counts ? capsule.counts : {};
    const rules = capsule && capsule.ssot_rules ? capsule.ssot_rules : {};
    const permissions = capsule && capsule.permissions ? capsule.permissions : {};
    const memory = capsule && capsule.memory ? capsule.memory : {};

    if (capsulePhaseStatus) {
      capsulePhaseStatus.textContent = phase.status || 'missing';
    }
    if (capsuleProjectName) {
      capsuleProjectName.textContent = project.name || '-';
    }
    if (capsuleProjectMode) {
      capsuleProjectMode.textContent = project.mode || '-';
    }
    if (capsuleProjectPhase) {
      capsuleProjectPhase.textContent = project.current_phase || '-';
    }
    if (capsuleRiskCount) {
      capsuleRiskCount.textContent = String(counts.risks || 0);
    }
    if (capsuleSearchMode) {
      capsuleSearchMode.textContent = memory.default_agent_search_mode
        ? 'Memory mode: ' + String(memory.default_agent_search_mode)
        : 'No capsule loaded.';
    }

    if (!capsule) {
      if (capsuleRulesList) {
        capsuleRulesList.innerHTML = '<div class="mini-empty">No project capsule loaded.</div>';
      }
      if (capsuleRisksList) {
        capsuleRisksList.innerHTML = '';
      }
      if (capsuleNextStepsList) {
        capsuleNextStepsList.innerHTML = '';
      }
      return;
    }

    if (capsuleRulesList) {
      capsuleRulesList.innerHTML = [
        '<article class="mini-card">',
        '<div class="mini-card-head"><span class="badge badge-info">Rules</span><span class="badge badge-muted">' + escapeHtml(String((counts.config_rules || 0) + (counts.development_rules || 0) + (counts.runtime_rules || 0))) + ' total</span></div>',
        '<p class="mini-card-text small">config: ' + escapeHtml((rules.config || []).slice(0, 2).join('; ') || 'n/a') + '</p>',
        '<p class="mini-card-text small">development: ' + escapeHtml((rules.development || []).slice(0, 2).join('; ') || 'n/a') + '</p>',
        '<p class="mini-card-text small">runtime: ' + escapeHtml((rules.runtime || []).slice(0, 2).join('; ') || 'n/a') + '</p>',
        '<p class="mini-card-text small">permissions: prod=' + escapeHtml(permissions.production_changes || 'n/a') + ' · config=' + escapeHtml(permissions.config_changes || 'n/a') + '</p>',
        '</article>'
      ].join('');
    }

    if (capsuleRisksList) {
      const riskItems = [];
      (phase.risks || []).slice(0, 2).forEach(function (item) {
        riskItems.push('<p class="mini-card-text small">risk: ' + escapeHtml(item) + '</p>');
      });
      (phase.blockers || []).slice(0, 2).forEach(function (item) {
        riskItems.push('<p class="mini-card-text small">blocker: ' + escapeHtml(item) + '</p>');
      });
      capsuleRisksList.innerHTML = [
        '<article class="mini-card">',
        '<div class="mini-card-head"><span class="badge badge-warn">Risk View</span><span class="badge badge-muted">' + escapeHtml(String((counts.risks || 0) + (counts.blockers || 0))) + ' items</span></div>',
        riskItems.join('') || '<p class="mini-card-text small">No active risks.</p>',
        '</article>'
      ].join('');
    }

    if (capsuleNextStepsList) {
      const nextItems = (phase.next_best_step || []).slice(0, 3).map(function (item) {
        return '<p class="mini-card-text small">next: ' + escapeHtml(item) + '</p>';
      }).join('');
      capsuleNextStepsList.innerHTML = [
        '<article class="mini-card">',
        '<div class="mini-card-head"><span class="badge badge-ok">Next Steps</span><span class="badge badge-muted">' + escapeHtml(String(counts.next_steps || 0)) + ' queued</span></div>',
        nextItems || '<p class="mini-card-text small">No next steps recorded.</p>',
        '</article>'
      ].join('');
    }
  }

  function renderRouter(session, artifacts, subagents) {
    const metadata = session && session.metadata ? session.metadata : {};
    const route = metadata.last_task_route || {};
    const attachedIds = Array.isArray(metadata.attached_artifact_ids) ? metadata.attached_artifact_ids : [];
    const artifactItems = Array.isArray(artifacts) ? artifacts : [];
    const runs = Array.isArray(subagents) ? subagents : [];
    if (routerRoute) {
      routerRoute.textContent = route.route || 'direct';
    }
    if (routerTaskType) {
      routerTaskType.textContent = route.task_type || 'direct_answer';
    }
    if (routerAttachStatus) {
      routerAttachStatus.textContent = String(attachedIds.length) + ' / ' + String(artifactItems.length);
    }
    if (routerReason) {
      routerReason.textContent = route.reason || 'No routed task yet.';
    }
    if (!routerSuggestedList) {
      return;
    }
    const suggested = Array.isArray(route.suggested_subagents) ? route.suggested_subagents : [];
    if (!suggested.length) {
      routerSuggestedList.innerHTML = '<div class="mini-empty">No suggested subagents.</div>';
      return;
    }
    routerSuggestedList.innerHTML = suggested.map(function (item) {
      const matchingRun = runs.find(function (run) { return run.role === item.role; });
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">' + escapeHtml(item.role || '') + '</span>',
        matchingRun ? '<span class="badge badge-muted">' + escapeHtml(matchingRun.status || '') + '</span>' : '',
        '</div>',
        '<p class="mini-card-text">' + escapeHtml(item.reason || '') + '</p>',
        '<p class="mini-card-text small">' + escapeHtml(item.task || '') + '</p>',
        '<p class="mini-card-text small">policy=' + escapeHtml(item.tool_policy || '') + ' · profile=' + escapeHtml(item.profile_strategy || '') + '</p>',
        '</article>'
      ].join('');
    }).join('');
  }

  function setWarning(message) {
    if (!chatWarning) {
      return;
    }
    if (!message) {
      chatWarning.textContent = "";
      chatWarning.classList.add("hidden");
      return;
    }
    chatWarning.textContent = message;
    chatWarning.classList.remove("hidden");
    setOutputSurface("warn", message, outputResultBox ? outputResultBox.textContent : undefined);
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options || {});
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data && data.error ? data.error : "Request failed.");
    }
    return data;
  }

  function updateCharCount() {
    if (chatCharCount) {
      chatCharCount.textContent = String((chatInput && chatInput.value ? chatInput.value.length : 0)) + " chars";
    }
  }

  function populateProfileSelects() {
    const options = state.profiles
      .map(function (profile) {
        return '<option value="' + escapeHtml(profile.profile_id) + '">' + escapeHtml(profile.name) + ' · ' + escapeHtml(profile.model_id) + '</option>';
      })
      .join("");
    if (newSessionProfile) {
      newSessionProfile.innerHTML = options;
    }
    if (profileSelect) {
      profileSelect.innerHTML = options;
    }
    if (simpleChatModelSelect) {
      simpleChatModelSelect.innerHTML = options;
    }
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function roleLabel(role) {
    switch (normalizeStatus(role)) {
      case "assistant":
        return "Агент";
      case "user":
        return "Оператор";
      case "system":
        return "System";
      case "subagent":
        return "Subagent";
      default:
        return role || "Повідомлення";
    }
  }

  function renderMessageDetailSections(sections) {
    var items = Array.isArray(sections) ? sections.filter(Boolean) : [];
    if (!items.length) {
      return '';
    }
    return '<div class="chat-message__details">' + items.map(function (section, index) {
      return [
        '<details class="chat-message__detail"' + (index === 0 && section.open ? ' open' : '') + '>',
        '<summary class="chat-message__detail-summary">' + escapeHtml(section.label || 'Показати деталі') + '</summary>',
        '<div class="chat-message__detail-body">' + escapeHtml(section.content || '—') + '</div>',
        '</details>'
      ].join('');
    }).join('') + '</div>';
  }

  function buildTimelineTraceSummary(item) {
    if (!item) {
      return '';
    }
    if (item.kind === 'subagent') {
      return [item.meta || 'bounded child run', 'trace згорнуто'].filter(Boolean).join(' · ');
    }
    if (item.kind === 'event') {
      return [item.meta || 'system event', 'operator-facing trace'].filter(Boolean).join(' · ');
    }
    if (normalizeStatus(item.role) === 'assistant') {
      return [item.meta || 'assistant response', 'деталі роботи згорнуті'].filter(Boolean).join(' · ');
    }
    if (normalizeStatus(item.role) === 'system') {
      return item.meta || 'system surface';
    }
    return '';
  }

  function buildTimelineDetailSections(item) {
    if (!item) {
      return [];
    }
    if (item.kind === 'subagent') {
      return [
        { label: 'Показати кроки', content: item.body || 'Задача субагента не зафіксована.' },
        { label: 'Показати інструменти', content: item.meta || 'Tool policy відсутня.' },
        item.artifactId ? { label: 'Показати артефакти', content: 'artifact_id: ' + item.artifactId } : null
      ];
    }
    if (item.kind === 'event') {
      return [
        { label: 'Показати деталі', content: item.body || 'Системна подія без повідомлення.' },
        item.meta ? { label: 'Показати інструменти', content: item.meta } : null
      ];
    }
    if (normalizeStatus(item.role) === 'assistant') {
      return [
        { label: 'Показати кроки', content: 'Головна відповідь показана вище. Для tool traces використовуйте Work Trace та Artifacts.' },
        item.meta ? { label: 'Показати деталі', content: 'model: ' + item.meta } : null
      ];
    }
    return [];
  }

  function getScenarioButtons() {
    return Array.from((scenarioBar || document).querySelectorAll('.scenario-btn[data-playbook]'));
  }

  function getScenarioButtonById(playbookId) {
    return getScenarioButtons().find(function (button) {
      return button.getAttribute('data-playbook') === playbookId;
    }) || null;
  }

  function getPlaybookById(playbookId) {
    return state.playbooks.find(function (playbook) {
      return playbook && playbook.playbook_id === playbookId;
    }) || null;
  }

  function getScenarioMeta(playbookId) {
    const button = getScenarioButtonById(playbookId);
    const fallback = SCENARIO_FALLBACKS[playbookId] || {};
    const playbook = getPlaybookById(playbookId) || {};
    return {
      playbookId: playbookId,
      title: playbook.title || (button ? button.textContent.trim() : playbookId),
      description: playbook.description || fallback.description || "Сценарій без опису.",
      templateId: (button && button.getAttribute('data-template-id')) || playbook.template_id || playbookId,
      sourceFile: (button && button.getAttribute('data-source-file')) || playbook.source_file || fallback.sourceFile || "—",
      group: (button && button.getAttribute('data-group')) || playbook.group || fallback.group || "Інше",
      mode: (button && button.getAttribute('data-mode')) || playbook.mode || fallback.mode || "prepare",
      riskLevel: normalizeStatus((button && button.getAttribute('data-risk-level')) || playbook.risk_level || fallback.riskLevel || "safe") || "safe",
      quickRun: ((button && button.getAttribute('data-quick-run')) || String(playbook.quick_run || fallback.quickRun || false)) === 'true'
    };
  }

  function getScenarioPrompt(meta) {
    return [meta.title, meta.description].filter(Boolean).join('\n\n').trim();
  }

  function isGuardedScenario(meta) {
    return ['guarded', 'high', 'critical', 'risky'].indexOf(normalizeStatus(meta && meta.riskLevel)) >= 0;
  }

  function updateScenarioButtons() {
    const buttons = getScenarioButtons();
    if (scenarioSectionStatus) {
      scenarioSectionStatus.textContent = String(buttons.length) + ' templates';
    }
    buttons.forEach(function (button) {
      const playbookId = button.getAttribute('data-playbook');
      const scenarioState = normalizeStatus(state.scenarioStates[playbookId] || '');
      const isSelected = playbookId === state.selectedScenarioId;
      button.classList.toggle('scenario-button--selected', isSelected);
      button.classList.toggle('scenario-button--running', scenarioState === 'running');
      button.classList.toggle('scenario-button--success', scenarioState === 'success');
      button.classList.toggle('scenario-button--failed', scenarioState === 'failed');
      button.classList.toggle('scenario-button--guarded', isGuardedScenario(getScenarioMeta(playbookId)));
      button.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
    });
  }

  function renderScenarioPreview(playbookId) {
    if (!playbookId) {
      if (scenarioPreviewEmpty) {
        scenarioPreviewEmpty.classList.remove('hidden');
      }
      if (scenarioPreviewCard) {
        scenarioPreviewCard.classList.add('hidden');
      }
      return;
    }
    const meta = getScenarioMeta(playbookId);
    if (scenarioPreviewEmpty) {
      scenarioPreviewEmpty.classList.add('hidden');
    }
    if (scenarioPreviewCard) {
      scenarioPreviewCard.classList.remove('hidden');
    }
    if (scenarioPreviewTitle) {
      scenarioPreviewTitle.textContent = meta.title;
    }
    if (scenarioPreviewDescription) {
      scenarioPreviewDescription.textContent = meta.description;
    }
    if (scenarioPreviewGroup) {
      scenarioPreviewGroup.textContent = meta.group;
    }
    if (scenarioPreviewMode) {
      scenarioPreviewMode.textContent = meta.mode;
    }
    if (scenarioPreviewRisk) {
      scenarioPreviewRisk.textContent = meta.riskLevel;
      applyBadgeTone(scenarioPreviewRisk, meta.riskLevel === 'safe' ? 'success' : meta.riskLevel);
    }
    if (scenarioPreviewTemplate) {
      scenarioPreviewTemplate.textContent = meta.templateId;
    }
    if (scenarioPreviewSource) {
      scenarioPreviewSource.textContent = meta.sourceFile;
    }
    if (scenarioPreviewWarning) {
      scenarioPreviewWarning.textContent = isGuardedScenario(meta)
        ? 'Цей сценарій не запускається одразу. Перевірте template та підтвердіть запуск вручну з composer.'
        : 'Safe read-only сценарій можна вставити в composer або запустити Alt+click / quick-run.';
      scenarioPreviewWarning.classList.remove('hidden');
    }
    if (scenarioRunBtn) {
      scenarioRunBtn.textContent = meta.quickRun && !isGuardedScenario(meta) ? 'Швидкий запуск' : 'Підготувати до запуску';
    }
    updateScenarioButtons();
  }

  function applyScenarioToComposer(meta, summary) {
    const prompt = getScenarioPrompt(meta);
    state.selectedScenarioId = meta.playbookId;
    state.selectedScenarioText = prompt;
    if (chatInput) {
      chatInput.value = prompt;
      chatInput.focus();
      updateCharCount();
    }
    renderScenarioPreview(meta.playbookId);
    updateScenarioButtons();
    setOutputSurface(isGuardedScenario(meta) ? 'warn' : 'success', summary || 'Composer заповнено зі сценарію.', prompt);
  }

  async function runScenario(meta) {
    if (!meta) {
      return;
    }
    applyScenarioToComposer(meta, isGuardedScenario(meta)
      ? 'Guarded сценарій підготовлено в composer. Потрібен ручний review перед run.'
      : 'Сценарій підготовлено для запуску.');
    if (isGuardedScenario(meta) || !meta.quickRun) {
      return;
    }
    await sendMessage();
  }

  function buildTimelineItems(detail) {
    const turns = detail && Array.isArray(detail.turns) ? detail.turns : [];
    const events = detail && Array.isArray(detail.events) ? detail.events : [];
    const subagents = detail && Array.isArray(detail.subagents) ? detail.subagents : [];
    const eventLimit = state.traceMode === 'detailed' ? 10 : (state.traceMode === 'working' ? 6 : 3);
    const items = [];

    turns.forEach(function (turn, index) {
      const turnRole = normalizeStatus(turn.role) || 'assistant';
      items.push({
        kind: 'turn',
        order: index,
        role: turnRole,
        status: turnRole,
        createdAt: turn.created_at,
        timestamp: timestampMs(turn.created_at),
        title: roleLabel(turn.role),
        body: turn.visible_content || '',
        meta: turn.model_id || '',
        traceSummary: turnRole === 'assistant' ? [turn.model_id || 'assistant', 'деталі роботи згорнуті'].filter(Boolean).join(' · ') : '',
        detailSections: turnRole === 'assistant'
          ? [
            { label: 'Показати кроки', content: 'Головна відповідь показана вище. Для tool traces використовуйте Work Trace та Artifacts.' },
            turn.model_id ? { label: 'Показати деталі', content: 'model: ' + turn.model_id } : null
          ]
          : [],
        actions: normalizeStatus(turn.role) === 'user'
          ? [{ id: 'reuse', label: 'Reuse prompt', payload: turn.visible_content || '' }]
          : [{ id: 'copy', label: 'Copy', payload: turn.visible_content || '' }]
      });
    });

    events.slice(-eventLimit).forEach(function (event, index) {
      items.push({
        kind: 'event',
        order: 1000 + index,
        role: 'system',
        status: /error|fail|blocked/.test(normalizeStatus(event.event_type + ' ' + event.message)) ? 'failed' : 'running',
        createdAt: event.created_at,
        timestamp: timestampMs(event.created_at),
        title: prettifyEventType(event.event_type),
        body: event.message || prettifyEventType(event.event_type),
        meta: summarizeMetadata(event.metadata, state.traceMode === 'detailed' ? 3 : 2),
        traceSummary: [summarizeMetadata(event.metadata, 2) || 'system event', 'operator-facing trace'].filter(Boolean).join(' · '),
        detailSections: [
          { label: 'Показати деталі', content: event.message || prettifyEventType(event.event_type) },
          summarizeMetadata(event.metadata, state.traceMode === 'detailed' ? 3 : 2)
            ? { label: 'Показати інструменти', content: summarizeMetadata(event.metadata, state.traceMode === 'detailed' ? 3 : 2) }
            : null
        ],
        actions: [{ id: 'focus-trace', label: 'To trace', payload: event.event_type || '' }]
      });
    });

    subagents.forEach(function (run, index) {
      const badgeMeta = [run.status || 'queued', run.tool_policy || ''].filter(Boolean).join(' · ');
      items.push({
        kind: 'subagent',
        order: 2000 + index,
        role: 'subagent',
        status: normalizeStatus(run.status) || 'queued',
        createdAt: run.finished_at || run.started_at || run.created_at,
        timestamp: timestampMs(run.finished_at || run.started_at || run.created_at),
        title: run.role || 'Subagent',
        body: run.task || run.child_run_id || 'Subagent work item',
        meta: badgeMeta,
        subagentId: run.child_run_id,
        artifactId: run.artifact_id,
        traceSummary: [badgeMeta || 'subagent run', 'trace згорнуто'].filter(Boolean).join(' · '),
        detailSections: [
          { label: 'Показати кроки', content: run.task || run.child_run_id || 'Subagent work item' },
          badgeMeta ? { label: 'Показати інструменти', content: badgeMeta } : null,
          run.artifact_id ? { label: 'Показати артефакти', content: 'artifact_id: ' + run.artifact_id } : null
        ],
        actions: [
          { id: 'select-subagent', label: 'Inspect', payload: run.child_run_id || '' }
        ].concat(run.artifact_id ? [{ id: 'focus-artifact', label: 'Artifact', payload: run.artifact_id }] : [])
      });
    });

    return items.sort(function (left, right) {
      if (left.timestamp === right.timestamp) {
        return left.order - right.order;
      }
      return left.timestamp - right.timestamp;
    });
  }

  function bindTimelineActions(detail) {
    Array.from((chatThread || document).querySelectorAll('[data-chat-action]')).forEach(function (button) {
      button.addEventListener('click', function () {
        const action = button.getAttribute('data-chat-action');
        const payload = button.getAttribute('data-chat-payload') || '';
        if (action === 'reuse' && chatInput) {
          chatInput.value = payload;
          updateCharCount();
          chatInput.focus();
          setOutputSurface('success', 'Prompt повернуто в composer.', payload);
          return;
        }
        if (action === 'copy') {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(payload).catch(function () {});
          }
          setOutputSurface('success', 'Текст підготовлено для копіювання.', payload);
          return;
        }
        if (action === 'focus-trace') {
          setCollapsedState('reasoning-body', true);
          if (state.layoutMode === 'board') {
            focusBoardPanel('workTrace');
            scrollBoardPanelIntoView('workTrace');
          }
          if (reasoningBody && reasoningBody.scrollIntoView) {
            reasoningBody.scrollIntoView({ block: 'nearest' });
          }
          return;
        }
        if (action === 'select-subagent') {
          state.selectedSubagentId = payload;
          if (cancelSubagentBtn) {
            cancelSubagentBtn.classList.remove('hidden');
          }
          renderSubagents(detail.subagents || [], detail.artifacts || [], detail.session || detail.sessionData || state.currentSession || {});
          return;
        }
        if (action === 'focus-artifact') {
          const artifact = (detail.artifacts || []).find(function (item) {
            return item && item.artifact_id === payload;
          });
          if (state.layoutMode === 'board') {
            focusBoardPanel('artifacts');
            scrollBoardPanelIntoView('artifacts');
          }
          setOutputSurface('success', 'Artifact selected.', artifact ? artifact.summary || payload : payload);
        }
      });
    });
  }

  function renderTraceNodes(nodes) {
    if (!reasoningTree) {
      return;
    }
    if (!nodes.length) {
      reasoningTree.innerHTML = '';
      if (reasoningEmptyState) {
        reasoningEmptyState.classList.remove('hidden');
      }
      return;
    }
    if (reasoningEmptyState) {
      reasoningEmptyState.classList.add('hidden');
    }
    reasoningTree.innerHTML = nodes.map(function renderNode(node) {
      const children = Array.isArray(node.children) && node.children.length
        ? '<ol class="reasoning-step__children">' + node.children.map(renderNode).join('') + '</ol>'
        : '';
      return [
        '<li class="reasoning-step reasoning-step--' + escapeHtml(badgeToneClass(node.status || 'muted').replace('badge-', '')) + '">',
        '<div class="reasoning-step__row">',
        '<span class="reasoning-step__marker"></span>',
        '<div class="reasoning-step__content">',
        '<div class="reasoning-step__header">',
        '<strong>' + escapeHtml(node.title || 'Trace node') + '</strong>',
        '<span class="badge ' + badgeToneClass(node.status || 'muted') + '">' + escapeHtml(node.status || 'info') + '</span>',
        node.createdAt ? '<span class="mono small">' + escapeHtml(formatTimestamp(node.createdAt)) + '</span>' : '',
        '</div>',
        '<p class="reasoning-step__summary">' + escapeHtml(node.summary || '—') + '</p>',
        node.meta ? '<p class="reasoning-step__meta mono small">' + escapeHtml(node.meta) + '</p>' : '',
        children,
        '</div>',
        '</div>',
        '</li>'
      ].join('');
    }).join('');
  }

  function buildTraceNodes(detail) {
    const turns = detail && Array.isArray(detail.turns) ? detail.turns : [];
    const events = detail && Array.isArray(detail.events) ? detail.events : [];
    const subagents = detail && Array.isArray(detail.subagents) ? detail.subagents : [];
    const artifacts = detail && Array.isArray(detail.artifacts) ? detail.artifacts : [];
    const latestUser = turns.slice().reverse().find(function (turn) { return normalizeStatus(turn.role) === 'user'; });
    const latestAssistant = turns.slice().reverse().find(function (turn) { return normalizeStatus(turn.role) === 'assistant'; });
    const eventLimit = state.traceMode === 'detailed' ? 8 : (state.traceMode === 'working' ? 5 : 3);
    const nodes = [];

    if (latestUser) {
      nodes.push({
        title: 'Запит оператора',
        status: 'completed',
        summary: excerptText(latestUser.visible_content, state.traceMode === 'compact' ? 96 : 180),
        createdAt: latestUser.created_at,
        meta: latestUser.model_id || ''
      });
    }

    events.slice(-eventLimit).forEach(function (event) {
      nodes.push({
        title: prettifyEventType(event.event_type),
        status: /error|fail|blocked/.test(normalizeStatus(event.event_type + ' ' + event.message)) ? 'failed' : 'running',
        summary: excerptText(event.message || prettifyEventType(event.event_type), state.traceMode === 'compact' ? 96 : 180),
        createdAt: event.created_at,
        meta: summarizeMetadata(event.metadata, state.traceMode === 'detailed' ? 3 : 2)
      });
    });

    subagents.forEach(function (run) {
      const children = [];
      if (state.traceMode !== 'compact' && Array.isArray(run.events)) {
        run.events.slice(state.traceMode === 'detailed' ? -4 : -2).forEach(function (event) {
          children.push({
            title: prettifyEventType(event.type || 'subagent event'),
            status: normalizeStatus(event.type) === 'error' ? 'failed' : 'completed',
            summary: excerptText(event.message, 120),
            createdAt: event.ts,
            meta: ''
          });
        });
      }
      const artifact = artifacts.find(function (item) { return item && item.artifact_id === run.artifact_id; });
      if (artifact) {
        children.push({
          title: 'Artifact',
          status: artifact.trusted ? 'success' : 'completed',
          summary: excerptText(artifact.summary, 120),
          createdAt: artifact.created_at,
          meta: artifact.artifact_type || ''
        });
      }
      nodes.push({
        title: (run.role || 'Subagent') + ' · ' + (run.status || 'queued'),
        status: run.status || 'queued',
        summary: excerptText(run.task || run.child_run_id, state.traceMode === 'compact' ? 92 : 180),
        createdAt: run.finished_at || run.started_at || run.created_at,
        meta: [run.tool_policy, run.child_run_id ? run.child_run_id.slice(0, 8) : ''].filter(Boolean).join(' · '),
        children: children
      });
    });

    if (latestAssistant) {
      nodes.push({
        title: 'Публічний результат',
        status: 'completed',
        summary: excerptText(latestAssistant.visible_content, state.traceMode === 'compact' ? 96 : 180),
        createdAt: latestAssistant.created_at,
        meta: latestAssistant.model_id || ''
      });
    }

    return nodes.sort(function (left, right) {
      return timestampMs(left.createdAt) - timestampMs(right.createdAt);
    });
  }

  function renderWorkTrace(detail) {
    const nodes = buildTraceNodes(detail);
    if (reasoningCoverageBadge) {
      const eventCount = detail && Array.isArray(detail.events) ? detail.events.length : 0;
      const subagentCount = detail && Array.isArray(detail.subagents) ? detail.subagents.length : 0;
      const artifactCount = detail && Array.isArray(detail.artifacts) ? detail.artifacts.length : 0;
      reasoningCoverageBadge.textContent = [
        String(eventCount) + ' events',
        String(subagentCount) + ' subagents',
        String(artifactCount) + ' artifacts'
      ].join(' · ');
    }
    renderTraceNodes(nodes);
  }

  function renderResultArtifacts(artifacts, subagents) {
    const items = [];
    (Array.isArray(artifacts) ? artifacts : []).forEach(function (artifact) {
      items.push([
        '<article class="mini-card result-artifact-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">artifact</span>',
        '<span class="badge badge-muted">' + escapeHtml(artifact.artifact_type || '') + '</span>',
        '</div>',
        '<p class="mini-card-text">' + escapeHtml(artifact.summary || '') + '</p>',
        '<button type="button" class="btn-link" data-chat-action="focus-artifact" data-chat-payload="' + escapeHtml(artifact.artifact_id || '') + '">Відкрити</button>',
        '</article>'
      ].join(''));
    });
    (Array.isArray(subagents) ? subagents : []).forEach(function (run) {
      items.push([
        '<article class="mini-card result-artifact-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">subagent</span>',
        '<span class="badge ' + badgeToneClass(run.status || '') + '">' + escapeHtml(run.status || 'queued') + '</span>',
        '</div>',
        '<p class="mini-card-text">' + escapeHtml(run.role || 'Subagent') + ': ' + escapeHtml(excerptText(run.task || run.child_run_id, 120)) + '</p>',
        '</article>'
      ].join(''));
    });
    if (resultArtifactLinks) {
      resultArtifactLinks.innerHTML = items.length
        ? items.join('')
        : '<div class="mini-empty">Артефакти та підсумки subagent runs з\'являться після першого результату.</div>';
      Array.from(resultArtifactLinks.querySelectorAll('[data-chat-action]')).forEach(function (button) {
        button.addEventListener('click', function () {
          const payload = button.getAttribute('data-chat-payload') || '';
          const artifact = (Array.isArray(artifacts) ? artifacts : []).find(function (item) {
            return item && item.artifact_id === payload;
          });
          setOutputSurface('success', 'Artifact selected.', artifact ? artifact.summary || payload : payload);
        });
      });
    }
  }

  function renderSessions() {
    if (!sessionList) {
      return;
    }
    if (!state.sessions.length) {
      sessionList.innerHTML = '<div class="mini-empty">No sessions yet.</div>';
      return;
    }
    sessionList.innerHTML = state.sessions.map(function (session) {
      const active = session.session_id === state.currentSessionId ? " is-active" : "";
      return [
        '<button type="button" class="session-row' + active + '" data-session-id="' + escapeHtml(session.session_id) + '">',
        '<span class="session-row-title">' + escapeHtml(session.title || "New Session") + '</span>',
        '<span class="session-row-meta mono">' + escapeHtml(session.active_profile ? session.active_profile.model_id : "") + '</span>',
        '</button>'
      ].join("");
    }).join("");
    Array.from(sessionList.querySelectorAll("[data-session-id]")).forEach(function (button) {
      button.addEventListener("click", function () {
        loadSession(button.getAttribute("data-session-id"));
      });
    });
  }

  function normalizeSimpleTraceEvent(item) {
      var out = {
          label: "Агент",
          summary: "Виконується поточний запит",
          status: "running"
      };

      if (item.kind === 'subagent') {
          out.label = "Сабагент";
          out.summary = item.title || item.task || item.role || "Виконує задачу...";
          if (item.status === 'success' || item.status === 'completed') out.status = 'success';
          else if (item.status === 'failed' || item.status === 'error') out.status = 'failed';
      } else if (item.kind === 'event') {
          var type = (item.title || item.source || '').toLowerCase();
          if (type.indexOf('tool') > -1 || type.indexOf('terminal') > -1 || (item.body || '').indexOf('tool') > -1) {
              out.label = "Інструмент";
              var bodyStr = item.body || '';
              var firstLine = bodyStr.split('\n')[0].trim();
              out.summary = firstLine.substring(0, 60) || "Виконується команда...";
              if (item.status === 'success' || item.status === 'completed') out.status = 'success';
              else if (item.status === 'failed' || item.status === 'error') out.status = 'failed';
          } else if (type.indexOf('artifact') > -1) {
              out.label = "Артефакт";
              out.summary = item.title || "Оновлено артефакт";
          } else {
              out.label = "Агент";
              if (item.status === 'running') out.summary = "Очікування відповіді моделі...";
              else if (item.status === 'success') { out.summary = "Дію завершено"; out.status = 'success'; }
              else if (item.status === 'failed') { out.summary = "Не вдалося виконати дію"; out.status = 'failed'; }
              else out.summary = item.title || item.status || "Обробка...";
          }
      }
      
      if (item.traceSummary) {
          out.summary = item.traceSummary;
      }
      return out;
  }

  function renderSimpleChatThread(detail) {
    var simpleThread = document.getElementById('simple-chat-thread');
    if (!simpleThread) return;
    
    var items = buildTimelineItems(detail || {});
    if (!items.length) {
      simpleThread.innerHTML = '<div class="chat-empty">No messages yet. Write a prompt below to start.</div>';
      return;
    }
    
    var html = [];
    var currentGroup = [];
    
    var isRunning = state.currentSession && state.currentSession.session && state.currentSession.session.status && state.currentSession.session.status.match(/running|active/i);

    function flushGroup(isLastGroup) {
       if (currentGroup.length === 0) return;
       var isOpen = (isLastGroup && isRunning) ? ' open="open"' : '';
       html.push('<div class="simple-chat-details"><details' + isOpen + '><summary>▸ Деталі роботи агента (' + currentGroup.length + ' подій)</summary><div class="simple-chat-details__body">');
       currentGroup.forEach(function(ev) {
          var norm = normalizeSimpleTraceEvent(ev);
          html.push('<div class="simple-chat-trace-row simple-chat-trace--' + norm.status + '">');
          html.push('<span class="simple-chat-trace-label">' + escapeHtml(norm.label) + '</span>');
          html.push('<span class="simple-chat-trace-summary">' + escapeHtml(norm.summary) + '</span>');
          html.push('</div>');
       });
       html.push('</div></details></div>');
       currentGroup = [];
    }

    items.forEach(function(item, idx) {
        if (item.kind === 'message' || item.kind === 'turn') {
            flushGroup(false);
            var isUser = item.role === 'user';
            var roleClass = isUser ? 'simple-chat-message--user' : 'simple-chat-message--assistant';
            html.push('<div class="simple-chat-message ' + roleClass + '">');
            html.push('<div class="simple-chat-message__content">' + escapeHtml(item.body || '') + '</div>');
            html.push('</div>');
        } else {
            currentGroup.push(item);
        }
    });
    flushGroup(true);
    
    if (isRunning) {
        html.push('<div class="simple-chat-message simple-chat-message--assistant simple-chat-assistant-placeholder">');
        html.push('<div class="simple-chat-spinner"></div>');
        html.push('<div class="simple-chat-message__content">Агент працює…</div>');
        html.push('</div>');
    }
    
    state.simpleChatQueue.forEach(function(qMsg) {
        html.push('<div class="simple-chat-message simple-chat-message--user simple-chat-queued-message">');
        html.push('<div class="simple-chat-message__content">' + escapeHtml(qMsg) + '</div>');
        html.push('<div class="simple-chat-message__badge">У черзі</div>');
        html.push('</div>');
    });
    
    simpleThread.innerHTML = html.join('');
    
    // Smart auto-scroll: if user is not near bottom, show "New events" button.
    // For V1, always scroll to bottom.
    simpleThread.scrollTop = simpleThread.scrollHeight;
    
    // Auto-dispatch queue if not running anymore
    if (!isRunning && state.simpleChatQueue.length > 0 && !state.isDispatchingQueue) {
        state.isDispatchingQueue = true;
        setTimeout(function() {
            var nextMsg = state.simpleChatQueue.shift();
            if (chatInput) chatInput.value = nextMsg;
            sendMessage().catch(function (error) { setWarning(error.message || 'Send failed.'); }).finally(function() {
                state.isDispatchingQueue = false;
            });
            updateSimpleChatComposer();
        }, 500);
    }
    
    // Call update composer to sync state if it changed externally
    if (typeof updateSimpleChatComposer === 'function') updateSimpleChatComposer();
}

function renderThread(detail) {
    if (!chatThread) {
      return;
    }
    renderSimpleChatThread(detail);
    const items = buildTimelineItems(detail || {});
    if (chatStreamStatus) {
      chatStreamStatus.textContent = String(items.length) + ' items';
    }
    if (!items.length) {
      chatThread.innerHTML = '<div class="chat-empty">No turns yet.</div>';
      if (chatSubagentEmpty) {
        chatSubagentEmpty.classList.remove('hidden');
      }
      return;
    }
    if (chatSubagentEmpty) {
      chatSubagentEmpty.classList.toggle('hidden', items.some(function (item) {
        return item.kind === 'event' || item.kind === 'subagent';
      }));
    }
    chatThread.innerHTML = items.map(function (item) {
      const role = normalizeStatus(item.role || item.kind || 'assistant');
      const tone = item.status || role;
      return [
        '<article class="chat-message chat-message--' + escapeHtml(role) + '">',
        '<div class="chat-message__header">',
        '<span class="badge ' + badgeToneClass(tone) + '">' + escapeHtml(roleLabel(item.role || item.kind)) + '</span>',
        '<strong>' + escapeHtml(item.title || roleLabel(item.role || item.kind)) + '</strong>',
        item.createdAt ? '<span class="mono small">' + escapeHtml(formatTimestamp(item.createdAt)) + '</span>' : '',
        '</div>',
        '<pre class="chat-message__body">' + escapeHtml(item.body || '') + '</pre>',
        item.traceSummary ? '<p class="chat-message__trace-summary">' + escapeHtml(item.traceSummary || buildTimelineTraceSummary(item)) + '</p>' : '',
        item.meta ? '<p class="chat-message__meta mono small">' + escapeHtml(item.meta) + '</p>' : '',
        renderMessageDetailSections(item.detailSections || buildTimelineDetailSections(item)),
        item.actions && item.actions.length
          ? '<div class="chat-message__actions">' + item.actions.map(function (action) {
            return '<button type="button" class="btn-link" data-chat-action="' + escapeHtml(action.id) + '" data-chat-payload="' + escapeHtml(action.payload || '') + '">' + escapeHtml(action.label) + '</button>';
          }).join('') + '</div>'
          : '',
        '</article>'
      ].join("");
    }).join("");
    bindTimelineActions(detail || {});
    chatThread.scrollTop = chatThread.scrollHeight;
  }

  function renderMemory(memoryAtoms, pinnedIds) {
    const atoms = Array.isArray(memoryAtoms) ? memoryAtoms : [];
    if (memoryCount) {
      memoryCount.textContent = String(atoms.length) + ' atoms';
    }
    if (!memoryList) {
      return;
    }
    if (!atoms.length) {
      memoryList.innerHTML = '<div class="mini-empty">No memory atoms yet.</div>';
      return;
    }
    memoryList.innerHTML = atoms.map(function (atom) {
      const pinned = Array.isArray(pinnedIds) && pinnedIds.indexOf(atom.atom_id) >= 0;
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">' + escapeHtml(atom.kind) + '</span>',
        pinned ? '<span class="badge badge-ok">pinned</span>' : '',
        '</div>',
        '<p class="mini-card-text">' + escapeHtml(atom.text || '') + '</p>',
        '<div class="quick-buttons">',
        '<button type="button" class="btn-link memory-pin-btn" data-atom-id="' + escapeHtml(atom.atom_id) + '" data-pin-action="' + (pinned ? 'unpin' : 'pin') + '">' + (pinned ? 'Unpin' : 'Pin') + '</button>',
        '<button type="button" class="btn-link memory-disable-btn" data-atom-id="' + escapeHtml(atom.atom_id) + '">Disable</button>',
        '</div>',
        '</article>'
      ].join('');
    }).join('');

    Array.from(memoryList.querySelectorAll('.memory-pin-btn')).forEach(function (button) {
      button.addEventListener('click', async function () {
        const atomId = button.getAttribute('data-atom-id');
        const action = button.getAttribute('data-pin-action');
        await fetchJson('/chat/sessions/' + state.currentSessionId + '/memory/' + atomId + '/' + action, { method: 'POST' });
        await loadSession(state.currentSessionId);
      });
    });
    Array.from(memoryList.querySelectorAll('.memory-disable-btn')).forEach(function (button) {
      button.addEventListener('click', async function () {
        const atomId = button.getAttribute('data-atom-id');
        await fetchJson('/chat/sessions/' + state.currentSessionId + '/memory/' + atomId + '/disable', { method: 'POST' });
        await loadSession(state.currentSessionId);
      });
    });
  }

  function renderMemorySearch(memoryAtoms, query) {
    if (!memorySearchResults) {
      return;
    }
    const atoms = Array.isArray(memoryAtoms) ? memoryAtoms : [];
    if (!query) {
      memorySearchResults.innerHTML = '';
      return;
    }
    if (!atoms.length) {
      memorySearchResults.innerHTML = '<div class="mini-empty">No memory hits for this query.</div>';
      return;
    }
    memorySearchResults.innerHTML = atoms.map(function (atom) {
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">' + escapeHtml(atom.kind || '') + '</span>',
        '<span class="badge badge-muted">search hit</span>',
        '</div>',
        '<p class="mini-card-text">' + escapeHtml(atom.text || '') + '</p>',
        '</article>'
      ].join('');
    }).join('');
  }

  function renderSubagents(subagents, artifacts, session) {
    const runs = Array.isArray(subagents) ? subagents : [];
    const metadata = session && session.metadata ? session.metadata : {};
    const attachedIds = Array.isArray(metadata.attached_artifact_ids) ? metadata.attached_artifact_ids : [];
    if (subagentCount) {
      subagentCount.textContent = String(runs.length) + ' runs';
    }
    if (subagentList) {
      if (!runs.length) {
        subagentList.innerHTML = '<div class="mini-empty">No subagent runs yet.</div>';
      } else {
        subagentList.innerHTML = runs.map(function (run) {
          const selected = run.child_run_id === state.selectedSubagentId ? ' is-active' : '';
          return [
            '<article class="mini-card mini-selectable' + selected + '" data-subagent-id="' + escapeHtml(run.child_run_id) + '">',
            '<div class="mini-card-head">',
            '<span class="badge badge-info">' + escapeHtml(run.role) + '</span>',
            '<span class="badge badge-muted">' + escapeHtml(run.status) + '</span>',
            '</div>',
            '<p class="mini-card-text">' + escapeHtml(run.task || '') + '</p>',
            run.artifact_id && attachedIds.indexOf(run.artifact_id) === -1 ? '<button type="button" class="btn-link attach-artifact-btn" data-artifact-id="' + escapeHtml(run.artifact_id) + '">Attach artifact</button>' : '',
            run.artifact_id && attachedIds.indexOf(run.artifact_id) >= 0 ? '<span class="badge badge-ok">attached</span>' : '',
            '</article>'
          ].join('');
        }).join('');
      }
    }
    if (artifactList) {
      const items = Array.isArray(artifacts) ? artifacts : [];
      artifactList.innerHTML = items.length ? items.map(function (artifact) {
        const attached = attachedIds.indexOf(artifact.artifact_id) >= 0;
        const findings = Array.isArray(artifact.findings) ? artifact.findings.slice(0, 3) : [];
        return [
          '<article class="mini-card">',
          '<div class="mini-card-head"><span class="badge badge-info">artifact</span><span class="badge badge-muted">' + escapeHtml(artifact.artifact_type || '') + '</span>' + (attached ? '<span class="badge badge-ok">attached</span>' : '') + '</div>',
          '<p class="mini-card-text">' + escapeHtml(artifact.summary || '') + '</p>',
          findings.map(function (finding) {
            return '<p class="mini-card-text small">- ' + escapeHtml(finding.claim || '') + '</p>';
          }).join(''),
          artifact.risks && artifact.risks.length ? '<p class="mini-card-text small">risks: ' + escapeHtml(artifact.risks.slice(0, 2).join('; ')) + '</p>' : '',
          artifact.open_questions && artifact.open_questions.length ? '<p class="mini-card-text small">open: ' + escapeHtml(artifact.open_questions.slice(0, 2).join('; ')) + '</p>' : '',
          '</article>'
        ].join('');
      }).join('') : '';
    }
    Array.from((subagentList || document).querySelectorAll('[data-subagent-id]')).forEach(function (card) {
      card.addEventListener('click', function () {
        state.selectedSubagentId = card.getAttribute('data-subagent-id');
        if (cancelSubagentBtn) {
          cancelSubagentBtn.classList.remove('hidden');
        }
        renderSubagents(runs, artifacts, session);
      });
    });
    Array.from((subagentList || document).querySelectorAll('.attach-artifact-btn')).forEach(function (button) {
      button.addEventListener('click', async function (event) {
        event.stopPropagation();
        await fetchJson('/chat/sessions/' + state.currentSessionId + '/artifacts/attach', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ artifact_id: button.getAttribute('data-artifact-id') })
        });
        await loadSession(state.currentSessionId);
      });
    });
  }

  function renderCurrentRun(session, subagents) {
    const runs = Array.isArray(subagents) ? subagents : [];
    const activeRun = runs.find(function (run) {
      return ["running", "queued", "active"].indexOf(String(run.status || "").toLowerCase()) >= 0;
    }) || runs[0] || null;
    const profile = session && session.active_profile ? session.active_profile : null;
    const tone = activeRun ? activeRun.status : (session && session.status ? session.status : "idle");

    if (currentRunStatus) {
      currentRunStatus.textContent = activeRun ? (activeRun.status || "idle") : (session && session.status ? session.status : "idle");
      applyBadgeTone(currentRunStatus, tone);
    }
    if (currentRunTask) {
      currentRunTask.textContent = activeRun ? (activeRun.task || "—") : "—";
    }
    if (currentRunAgent) {
      currentRunAgent.textContent = activeRun ? (activeRun.role || "—") : "—";
    }
    if (currentRunModel) {
      currentRunModel.textContent = activeRun ? (activeRun.profile_id || (profile && profile.model_id) || "—") : ((profile && profile.model_id) || "—");
    }
    if (currentRunElapsed) {
      currentRunElapsed.textContent = activeRun ? formatDuration(activeRun.elapsed_ms || activeRun.duration_ms) : "—";
    }
  }

  function renderDrawerArtifacts(artifacts) {
    const items = Array.isArray(artifacts) ? artifacts : [];
    if (!drawerArtifactsView) {
      return;
    }
    if (!items.length) {
      drawerArtifactsView.textContent = "Артефактів немає.";
      return;
    }
    drawerArtifactsView.textContent = items.map(function (artifact) {
      return [
        "artifact_id: " + String(artifact.artifact_id || "—"),
        "type: " + String(artifact.artifact_type || "—"),
        "summary: " + String(artifact.summary || "—"),
      ].join("\n");
    }).join("\n\n---\n\n");
  }

  function renderContext(report) {
    const data = report || {};
    if (contextUsage) {
      const usage = data.estimated_context_usage || data.context_report || {};
      contextUsage.textContent = String(usage.chars || usage.approximate_chars || 0) + ' chars';
    }
    const contextReport = data.context_report || data;
    if (contextWarningCount) {
      contextWarningCount.textContent = String((contextReport.warnings || []).length);
    }
    if (contextTurnCount) {
      contextTurnCount.textContent = String((contextReport.recent_turns_included || []).length);
    }
    if (contextMemoryCount) {
      contextMemoryCount.textContent = String((contextReport.memory_atoms_included || []).length);
    }
    if (contextArtifactCount) {
      contextArtifactCount.textContent = String((contextReport.artifacts_included || []).length);
    }
    if (contextPackView) {
      contextPackView.textContent = data.context_pack || JSON.stringify(contextReport, null, 2);
    }
  }

  async function loadSession(sessionId) {
    if (!sessionId) {
      return;
    }
    const detail = await fetchJson('/chat/sessions/' + sessionId);
    state.currentSessionId = sessionId;
    state.currentSession = detail;
    state.currentSessionDetail = detail;
    const session = detail.session || {};
    if (sessionTitle) {
      sessionTitle.textContent = session.title || 'Conversation';
    }
    if (sessionMeta) {
      sessionMeta.textContent = (session.active_profile ? session.active_profile.name + ' · ' + session.active_profile.model_id : 'No active profile');
    }
    if (profileSelect && session.active_profile) {
      profileSelect.value = session.active_profile.profile_id;
    }
    if (simpleChatModelSelect && session.active_profile) {
      simpleChatModelSelect.value = session.active_profile.profile_id;
    }
    if (chatStatusBadge) {
      chatStatusBadge.textContent = session.status || 'idle';
      applyBadgeTone(chatStatusBadge, session.status || 'idle');
    }
    if (workspaceSessionPill) {
      workspaceSessionPill.textContent = session.title || 'Поточна сесія';
    }
    updateHeaderFromSession(session);
    renderSessions();
    renderThread(detail);
    syncOutputFromTurns(detail.turns || []);
    renderWorkTrace(detail);
    renderResultArtifacts(detail.artifacts || [], detail.subagents || []);
    renderMemory(detail.memory_atoms || [], session.pinned_memory_atom_ids || []);
    renderRouter(session, detail.artifacts || [], detail.subagents || []);
    renderSubagents(detail.subagents || [], detail.artifacts || [], session);
    renderCurrentRun(session, detail.subagents || []);
    renderDrawerArtifacts(detail.artifacts || []);
  }

  async function refreshSessions() {
    state.sessions = await fetchJson('/chat/sessions');
    renderSessions();
    if (!state.sessions.length && workspaceSessionPill) {
      workspaceSessionPill.textContent = 'Немає сесій';
    }
    if (!state.currentSessionId && state.sessions.length) {
      await loadSession(state.sessions[0].session_id);
    }
  }

  async function createSession() {
    const payload = {
      title: newSessionTitle && newSessionTitle.value ? newSessionTitle.value : 'New Session',
      profile_id: newSessionProfile && newSessionProfile.value ? newSessionProfile.value : undefined,
    };
    const detail = await fetchJson('/chat/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    state.sessions.unshift(detail.session);
    setOutputSurface('success', 'Сесію створено.', detail.session ? detail.session.title || 'Нова сесія' : 'Нова сесія');
    await loadSession(detail.session.session_id);
  }

  async function sendMessage() {
    if (!state.currentSessionId) {
      setWarning('Create a session first.');
      return;
    }
    const message = chatInput && chatInput.value ? chatInput.value.trim() : '';
    if (!message) {
      setWarning('Message is required.');
      return;
    }
    setWarning('');
    if (state.selectedScenarioId) {
      state.scenarioStates[state.selectedScenarioId] = 'running';
      updateScenarioButtons();
    }
    sendBtn.disabled = true;
    sendBtn.classList.add('is-running');
    chatInput.value = '';
    updateCharCount();
    
    // Optimistically update UI
    if (state.currentSessionDetail && Array.isArray(state.currentSessionDetail.turns)) {
      state.currentSessionDetail.turns.push({
        role: 'user',
        created_at: new Date().toISOString(),
        visible_content: message
      });
      if (state.currentSessionDetail.session) {
        state.currentSessionDetail.session.status = 'running';
      }
      renderThread(state.currentSessionDetail);
    }
    
    setOutputSurface('running', 'Агент обробляє запит.', message);
    try {
      const result = await fetchJson('/chat/sessions/' + state.currentSessionId + '/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message }),
      });
      renderContext(result);
      setOutputSurface('success', 'Відповідь агента готова.', result.assistant_turn ? result.assistant_turn.visible_content || result.assistant_turn : result.context_report || 'Відповідь отримана.');
      if (state.selectedScenarioId) {
        state.scenarioStates[state.selectedScenarioId] = 'success';
        updateScenarioButtons();
      }
      await refreshSessions();
      await loadSession(state.currentSessionId);
    } catch (error) {
      if (state.selectedScenarioId) {
        state.scenarioStates[state.selectedScenarioId] = 'failed';
        updateScenarioButtons();
      }
      setWarning(error.message || 'Send failed.');
    } finally {
      sendBtn.disabled = false;
      sendBtn.classList.remove('is-running');
    }
  }

  async function updateProfile() {
    const val = simpleChatModelSelect ? simpleChatModelSelect.value : (profileSelect ? profileSelect.value : null);
    if (!state.currentSessionId || !val) {
      return;
    }
    await fetchJson('/chat/sessions/' + state.currentSessionId + '/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: val }),
    });
    setOutputSurface('success', 'Активний профіль оновлено.', profileSelect.value || 'profile');
    await refreshSessions();
    await loadSession(state.currentSessionId);
  }

  async function inspectContext() {
    if (!state.currentSessionId) {
      setWarning('Select a session first.');
      return;
    }
    const report = await fetchJson('/chat/sessions/' + state.currentSessionId + '/context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: chatInput && chatInput.value ? chatInput.value : '' }),
    });
    renderContext(report);
    setOutputSurface('success', 'Контекст зібрано.', report.context_pack || report.context_report || report);
  }

  async function compressSession() {
    if (!state.currentSessionId) {
      return;
    }
    const result = await fetchJson('/chat/sessions/' + state.currentSessionId + '/compress', { method: 'POST' });
    if (result.compressed) {
      setWarning('Compression completed.');
      setOutputSurface('success', 'Стиснення контексту завершено.', result);
    } else {
      setWarning('Compression skipped: ' + String(result.reason || 'unknown'));
    }
    await loadSession(state.currentSessionId);
  }

  async function addMemory() {
    if (!state.currentSessionId) {
      setWarning('Select a session first.');
      return;
    }
    const text = memoryText && memoryText.value ? memoryText.value.trim() : '';
    if (!text) {
      setWarning('Memory text is required.');
      return;
    }
    await fetchJson('/chat/sessions/' + state.currentSessionId + '/memory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, kind: memoryKind ? memoryKind.value : 'fact' }),
    });
    memoryText.value = '';
    setOutputSurface('success', 'Атом пам’яті додано.', text);
    await loadSession(state.currentSessionId);
  }

  async function searchMemory() {
    if (!state.currentSessionId) {
      setWarning('Select a session first.');
      return;
    }
    const query = memorySearchText && memorySearchText.value ? memorySearchText.value.trim() : '';
    if (!query) {
      renderMemorySearch([], '');
      return;
    }
    const result = await fetchJson('/chat/sessions/' + state.currentSessionId + '/memory/search?q=' + encodeURIComponent(query));
    renderMemorySearch(result.memory_atoms || [], query);
  }

  async function spawnScout() {
    if (!state.currentSessionId) {
      setWarning('Select a session first.');
      return;
    }
    await fetchJson('/chat/sessions/' + state.currentSessionId + '/subagents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        role: 'ScoutAgent',
        task: (chatInput && chatInput.value ? chatInput.value.trim() : '') || 'Inspect repository state',
        profile_id: 'flash-scout',
        tool_policy: 'read_only'
      }),
    });
    setOutputSurface('running', 'Субагента поставлено в чергу.', chatInput && chatInput.value ? chatInput.value.trim() : 'Inspect repository state');
    startSubagentPolling();
    await loadSession(state.currentSessionId);
  }

  async function cancelSelectedSubagent() {
    if (!state.selectedSubagentId) {
      setWarning('Select a subagent first.');
      return;
    }
    await fetchJson('/chat/subagents/' + state.selectedSubagentId + '/cancel', { method: 'POST' });
    setOutputSurface('warn', 'Субагента зупинено.', state.selectedSubagentId);
    await loadSession(state.currentSessionId);
  }

  function startSubagentPolling() {
    if (state.subagentPollHandle) {
      window.clearInterval(state.subagentPollHandle);
    }
    state.subagentPollHandle = window.setInterval(function () {
      if (state.currentSessionId) {
        loadSession(state.currentSessionId).catch(function () {});
      }
    }, 2000);
  }

  if (chatInput) {
    chatInput.addEventListener('input', updateCharCount);
  }
  if (newSessionBtn) {
    newSessionBtn.addEventListener('click', function () { createSession().catch(function (error) { setWarning(error.message || 'Failed to create session.'); }); });
  }
  if (sendBtn) {
    sendBtn.addEventListener('click', function () { sendMessage().catch(function (error) { setWarning(error.message || 'Send failed.'); }); });
  }
  if (profileSelect) {
    profileSelect.addEventListener('change', function () { updateProfile().catch(function (error) { setWarning(error.message || 'Profile update failed.'); }); });
  }
  if (refreshSessionBtn) {
    refreshSessionBtn.addEventListener('click', function () { if (state.currentSessionId) { loadSession(state.currentSessionId).catch(function (error) { setWarning(error.message || 'Refresh failed.'); }); } });
  }
  if (inspectContextBtn) {
    inspectContextBtn.addEventListener('click', function () { inspectContext().catch(function (error) { setWarning(error.message || 'Context inspect failed.'); }); });
  }
  if (compressBtn) {
    compressBtn.addEventListener('click', function () { compressSession().catch(function (error) { setWarning(error.message || 'Compression failed.'); }); });
  }
  if (addMemoryBtn) {
    addMemoryBtn.addEventListener('click', function () { addMemory().catch(function (error) { setWarning(error.message || 'Memory add failed.'); }); });
  }
  if (searchMemoryBtn) {
    searchMemoryBtn.addEventListener('click', function () { searchMemory().catch(function (error) { setWarning(error.message || 'Memory search failed.'); }); });
  }
  if (spawnScoutBtn) {
    spawnScoutBtn.addEventListener('click', function () { spawnScout().catch(function (error) { setWarning(error.message || 'Subagent spawn failed.'); }); });
  }
  if (cancelSubagentBtn) {
    cancelSubagentBtn.addEventListener('click', function () { cancelSelectedSubagent().catch(function (error) { setWarning(error.message || 'Subagent cancel failed.'); }); });
  }

  // ── Agent OS Panel wiring ────────────────────────────────────────────────────

  var playbooksEnabledOnly = document.getElementById('playbooks-enabled-only');
  var playbooksReloadBtn = document.getElementById('playbooks-reload-btn');
  var playbooksList = document.getElementById('playbooks-list');
  var playbooksCount = document.getElementById('playbooks-count');
  var toolsReloadBtn = document.getElementById('tools-reload-btn');
  var toolsList = document.getElementById('tools-list');
  var toolsCount = document.getElementById('tools-count');
  var approvalCreateBtn = document.getElementById('approval-create-btn');
  var approvalAction = document.getElementById('approval-action');
  var approvalReason = document.getElementById('approval-reason');
  var approvalRisk = document.getElementById('approval-risk');
  var approvalsReloadBtn = document.getElementById('approvals-reload-btn');
  var approvalsList = document.getElementById('approvals-list');
  var approvalsCount = document.getElementById('approvals-count');
  var reportsScanBtn = document.getElementById('reports-scan-btn');
  var reportsReloadBtn = document.getElementById('reports-reload-btn');
  var reportsList = document.getElementById('reports-list');
  var reportsCount = document.getElementById('reports-count');
  var decisionAddBtn = document.getElementById('decision-add-btn');
  var decisionText = document.getElementById('decision-text');
  var decisionScope = document.getElementById('decision-scope');
  var decisionsReloadBtn = document.getElementById('decisions-reload-btn');
  var decisionsActiveOnly = document.getElementById('decisions-active-only');
  var decisionsList = document.getElementById('decisions-list');
  var decisionsCount = document.getElementById('decisions-count');
  var patchCreateBtn = document.getElementById('patch-create-btn');
  var patchChange = document.getElementById('patch-change');
  var patchSection = document.getElementById('patch-section');
  var patchReason = document.getElementById('patch-reason');
  var patchRisk = document.getElementById('patch-risk');
  var patchesReloadBtn = document.getElementById('patches-reload-btn');
  var patchesList = document.getElementById('patches-list');
  var patchesCount = document.getElementById('patches-count');
  var bundlesScanBtn = document.getElementById('bundles-scan-btn');
  var bundlesReloadBtn = document.getElementById('bundles-reload-btn');
  var bundlesList = document.getElementById('bundles-list');
  var bundlesCount = document.getElementById('bundles-count');

  // ── Playbooks ─────────────────────────────────────────────────────────────────

  function renderPlaybooks(items) {
    if (!playbooksList) return;
    state.playbooks = Array.isArray(items) ? items : [];
    updateScenarioButtons();
    if (state.selectedScenarioId) {
      renderScenarioPreview(state.selectedScenarioId);
    }
    if (!items || !items.length) {
      playbooksList.innerHTML = '<div class="mini-empty">No playbooks found.</div>';
      if (playbooksCount) playbooksCount.textContent = '0';
      return;
    }
    if (playbooksCount) playbooksCount.textContent = String(items.length);
    playbooksList.innerHTML = items.map(function (pb) {
      var riskBadge = pb.risk_level === 'critical' ? 'badge-error' : pb.risk_level === 'high' ? 'badge-warn' : 'badge-ok';
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">' + escapeHtml(pb.playbook_id || '') + '</span>',
        '<span class="badge ' + riskBadge + '">' + escapeHtml(pb.risk_level || '') + '</span>',
        pb.enabled ? '<span class="badge badge-ok">enabled</span>' : '<span class="badge badge-muted">disabled</span>',
        '</div>',
        '<p class="mini-card-text">' + escapeHtml(pb.title || '') + '</p>',
        pb.hotkey ? '<p class="mini-card-text small">hotkey: ' + escapeHtml(pb.hotkey) + '</p>' : '',
        pb.trigger_button ? '<p class="mini-card-text small">trigger: ' + escapeHtml(pb.trigger_button) + '</p>' : '',
        pb.done_criteria && pb.done_criteria.length ? '<p class="mini-card-text small">done: ' + escapeHtml(pb.done_criteria.slice(0, 2).join('; ')) + '</p>' : '',
        '</article>'
      ].join('');
    }).join('');
  }

  async function loadPlaybooks() {
    try {
      var enabledOnly = playbooksEnabledOnly && playbooksEnabledOnly.checked;
      var items = await fetchJson('/chat/playbooks');
      if (enabledOnly) items = items.filter(function (pb) { return pb.enabled; });
      renderPlaybooks(items);
    } catch (err) {
      if (playbooksList) playbooksList.innerHTML = '<div class="mini-empty">Failed: ' + escapeHtml(err.message || 'error') + '</div>';
    }
  }

  if (playbooksReloadBtn) playbooksReloadBtn.addEventListener('click', function () { loadPlaybooks().catch(function () {}); });
  if (playbooksEnabledOnly) playbooksEnabledOnly.addEventListener('change', function () { loadPlaybooks().catch(function () {}); });

  // ── Tool Registry ─────────────────────────────────────────────────────────────

  function renderTools(items) {
    if (!toolsList) return;
    if (!items || !items.length) {
      toolsList.innerHTML = '<div class="mini-empty">No tools found.</div>';
      if (toolsCount) toolsCount.textContent = '0';
      return;
    }
    if (toolsCount) toolsCount.textContent = String(items.length);
    toolsList.innerHTML = items.map(function (t) {
      var riskBadge = t.risk_level === 'critical' ? 'badge-error' : t.risk_level === 'high' ? 'badge-warn' : t.risk_level === 'medium' ? 'badge-muted' : 'badge-ok';
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">' + escapeHtml(t.tool_id || '') + '</span>',
        '<span class="badge ' + riskBadge + '">' + escapeHtml(t.risk_level || '') + '</span>',
        t.manual_only ? '<span class="badge badge-error">manual-only</span>' : '',
        t.approval_required ? '<span class="badge badge-warn">approval-req</span>' : '',
        '</div>',
        '<p class="mini-card-text small">agents: ' + escapeHtml((t.allowed_agents || []).join(', ') || 'none') + '</p>',
        '</article>'
      ].join('');
    }).join('');
  }

  async function loadTools() {
    try {
      var items = await fetchJson('/chat/tools');
      renderTools(items);
    } catch (err) {
      if (toolsList) toolsList.innerHTML = '<div class="mini-empty">Failed: ' + escapeHtml(err.message || 'error') + '</div>';
    }
  }

  if (toolsReloadBtn) toolsReloadBtn.addEventListener('click', function () { loadTools().catch(function () {}); });

  // ── Approval Queue ────────────────────────────────────────────────────────────

  function renderApprovals(items) {
    if (!approvalsList) return;
    var pending = (items || []).filter(function (r) { return r.status === 'pending'; });
    if (approvalsCount) approvalsCount.textContent = String(pending.length) + ' pending';
    if (!items || !items.length) {
      approvalsList.innerHTML = '<div class="mini-empty">No approval requests.</div>';
      return;
    }
    approvalsList.innerHTML = items.map(function (req) {
      var statusBadge = req.status === 'approved' ? 'badge-ok' : req.status === 'rejected' ? 'badge-error' : 'badge-warn';
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">' + escapeHtml((req.approval_id || '').slice(0, 8)) + '</span>',
        '<span class="badge ' + statusBadge + '">' + escapeHtml(req.status || '') + '</span>',
        '<span class="badge badge-muted">' + escapeHtml(req.risk_level || '') + '</span>',
        '</div>',
        '<p class="mini-card-text">' + escapeHtml(req.requested_action || '') + '</p>',
        '<p class="mini-card-text small">' + escapeHtml(req.reason || '') + '</p>',
        req.status === 'pending' ? [
          '<div class="quick-buttons">',
          '<button type="button" class="btn-link approval-approve-btn" data-approval-id="' + escapeHtml(req.approval_id) + '">Approve</button>',
          '<button type="button" class="btn-link approval-reject-btn" data-approval-id="' + escapeHtml(req.approval_id) + '">Reject</button>',
          '</div>'
        ].join('') : '',
        '</article>'
      ].join('');
    }).join('');

    approvalsList.querySelectorAll('.approval-approve-btn').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        await fetchJson('/chat/approvals/' + btn.getAttribute('data-approval-id') + '/approve', { method: 'POST' });
        await loadApprovals();
      });
    });
    approvalsList.querySelectorAll('.approval-reject-btn').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        await fetchJson('/chat/approvals/' + btn.getAttribute('data-approval-id') + '/reject', { method: 'POST' });
        await loadApprovals();
      });
    });
  }

  async function loadApprovals() {
    try {
      var items = await fetchJson('/chat/approvals');
      renderApprovals(items);
    } catch (err) {
      if (approvalsList) approvalsList.innerHTML = '<div class="mini-empty">Failed: ' + escapeHtml(err.message || 'error') + '</div>';
    }
  }

  async function createApproval() {
    var action = approvalAction && approvalAction.value ? approvalAction.value.trim() : '';
    if (!action) { setWarning('Requested action is required.'); return; }
    await fetchJson('/chat/approvals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.currentSessionId || '',
        requested_action: action,
        reason: approvalReason && approvalReason.value ? approvalReason.value.trim() : '',
        risk_level: approvalRisk && approvalRisk.value ? approvalRisk.value : 'medium',
        requested_by: 'user',
        rollback_plan: 'manual revert',
        files_or_scopes: [],
        expected_behavior_change: true,
      })
    });
    if (approvalAction) approvalAction.value = '';
    if (approvalReason) approvalReason.value = '';
    await loadApprovals();
  }

  if (approvalCreateBtn) approvalCreateBtn.addEventListener('click', function () { createApproval().catch(function (e) { setWarning(e.message || 'Approval create failed.'); }); });
  if (approvalsReloadBtn) approvalsReloadBtn.addEventListener('click', function () { loadApprovals().catch(function () {}); });

  // ── Reports Panel ─────────────────────────────────────────────────────────────

  function renderReports(items) {
    if (!reportsList) return;
    if (reportsCount) reportsCount.textContent = String((items || []).length);
    if (!items || !items.length) {
      reportsList.innerHTML = '<div class="mini-empty">No reports indexed. Click Scan Reports.</div>';
      return;
    }
    reportsList.innerHTML = items.map(function (r) {
      var statusBadge = r.status === 'accepted' ? 'badge-ok' : r.status === 'rejected' ? 'badge-error' : r.status === 'stale' ? 'badge-muted' : 'badge-info';
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">' + escapeHtml(r.report_type || 'UNKNOWN') + '</span>',
        '<span class="badge ' + statusBadge + '">' + escapeHtml(r.status || '') + '</span>',
        r.verdict ? '<span class="badge badge-muted">' + escapeHtml(r.verdict) + '</span>' : '',
        '</div>',
        '<p class="mini-card-text small">' + escapeHtml(r.source_path || '') + '</p>',
        r.summary ? '<p class="mini-card-text small">' + escapeHtml((r.summary || '').slice(0, 80)) + '</p>' : '',
        r.status === 'draft' ? [
          '<div class="quick-buttons">',
          '<button type="button" class="btn-link report-accept-btn" data-report-id="' + escapeHtml(r.report_id) + '">Accept</button>',
          '<button type="button" class="btn-link report-reject-btn" data-report-id="' + escapeHtml(r.report_id) + '">Reject</button>',
          '</div>'
        ].join('') : '',
        '</article>'
      ].join('');
    }).join('');

    reportsList.querySelectorAll('.report-accept-btn').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        await fetchJson('/chat/reports/' + btn.getAttribute('data-report-id') + '/status', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'accepted' })
        });
        await loadReports();
      });
    });
    reportsList.querySelectorAll('.report-reject-btn').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        await fetchJson('/chat/reports/' + btn.getAttribute('data-report-id') + '/status', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'rejected' })
        });
        await loadReports();
      });
    });
  }

  async function loadReports() {
    try {
      var items = await fetchJson('/chat/reports');
      renderReports(items);
    } catch (err) {
      if (reportsList) reportsList.innerHTML = '<div class="mini-empty">Failed: ' + escapeHtml(err.message || 'error') + '</div>';
    }
  }

  async function scanReports() {
    var result = await fetchJson('/chat/reports/scan', { method: 'POST' });
    setWarning('Scanned: ' + String(result.scanned || 0) + ' reports indexed.');
    await loadReports();
  }

  if (reportsScanBtn) reportsScanBtn.addEventListener('click', function () { scanReports().catch(function (e) { setWarning(e.message || 'Scan failed.'); }); });
  if (reportsReloadBtn) reportsReloadBtn.addEventListener('click', function () { loadReports().catch(function () {}); });

  // ── Decision Ledger ───────────────────────────────────────────────────────────

  function renderDecisions(items) {
    if (!decisionsList) return;
    var active = (items || []).filter(function (d) { return d.status === 'active'; });
    if (decisionsCount) decisionsCount.textContent = String(active.length) + ' active';
    if (!items || !items.length) {
      decisionsList.innerHTML = '<div class="mini-empty">No decisions recorded.</div>';
      return;
    }
    decisionsList.innerHTML = items.map(function (d) {
      var statusBadge = d.status === 'active' ? 'badge-ok' : d.status === 'deprecated' ? 'badge-muted' : 'badge-error';
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge ' + statusBadge + '">' + escapeHtml(d.status || '') + '</span>',
        d.scope ? '<span class="badge badge-info">' + escapeHtml(d.scope) + '</span>' : '',
        '</div>',
        '<p class="mini-card-text">' + escapeHtml(d.decision || '') + '</p>',
        d.status === 'active' ? '<button type="button" class="btn-link decision-deprecate-btn" data-decision-id="' + escapeHtml(d.decision_id) + '">Deprecate</button>' : '',
        '</article>'
      ].join('');
    }).join('');

    decisionsList.querySelectorAll('.decision-deprecate-btn').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        await fetchJson('/chat/decisions/' + btn.getAttribute('data-decision-id') + '/deprecate', { method: 'POST' });
        await loadDecisions();
      });
    });
  }

  async function loadDecisions() {
    try {
      var activeOnly = decisionsActiveOnly && decisionsActiveOnly.checked;
      var items = await fetchJson('/chat/decisions' + (activeOnly ? '?active_only=true' : ''));
      renderDecisions(items);
    } catch (err) {
      if (decisionsList) decisionsList.innerHTML = '<div class="mini-empty">Failed: ' + escapeHtml(err.message || 'error') + '</div>';
    }
  }

  async function addDecision() {
    var text = decisionText && decisionText.value ? decisionText.value.trim() : '';
    if (!text) { setWarning('Decision statement is required.'); return; }
    await fetchJson('/chat/decisions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision: text, scope: decisionScope && decisionScope.value ? decisionScope.value.trim() : '' })
    });
    if (decisionText) decisionText.value = '';
    if (decisionScope) decisionScope.value = '';
    await loadDecisions();
  }

  if (decisionAddBtn) decisionAddBtn.addEventListener('click', function () { addDecision().catch(function (e) { setWarning(e.message || 'Add decision failed.'); }); });
  if (decisionsReloadBtn) decisionsReloadBtn.addEventListener('click', function () { loadDecisions().catch(function () {}); });
  if (decisionsActiveOnly) decisionsActiveOnly.addEventListener('change', function () { loadDecisions().catch(function () {}); });

  // ── Memory Patches ────────────────────────────────────────────────────────────

  function renderPatches(items) {
    if (!patchesList) return;
    if (patchesCount) patchesCount.textContent = String((items || []).length);
    if (!items || !items.length) {
      patchesList.innerHTML = '<div class="mini-empty">No memory patches.</div>';
      return;
    }
    patchesList.innerHTML = items.map(function (p) {
      var statusBadge = p.status === 'applied' ? 'badge-ok' : p.status === 'approved' ? 'badge-info' : p.status === 'rejected' ? 'badge-error' : 'badge-warn';
      var riskBadge = p.risk === 'high' ? 'badge-error' : p.risk === 'medium' ? 'badge-warn' : 'badge-muted';
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge ' + statusBadge + '">' + escapeHtml(p.status || '') + '</span>',
        '<span class="badge ' + riskBadge + '">' + escapeHtml(p.risk || '') + '</span>',
        '</div>',
        '<p class="mini-card-text">' + escapeHtml(p.proposed_change || '') + '</p>',
        p.reason ? '<p class="mini-card-text small">reason: ' + escapeHtml(p.reason) + '</p>' : '',
        p.status === 'pending' ? [
          '<div class="quick-buttons">',
          '<button type="button" class="btn-link patch-approve-btn" data-patch-id="' + escapeHtml(p.patch_id) + '">Approve</button>',
          '<button type="button" class="btn-link patch-reject-btn" data-patch-id="' + escapeHtml(p.patch_id) + '">Reject</button>',
          '</div>'
        ].join('') : '',
        '</article>'
      ].join('');
    }).join('');

    patchesList.querySelectorAll('.patch-approve-btn').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        await fetchJson('/chat/memory-patches/' + btn.getAttribute('data-patch-id') + '/approve', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved_by: 'user' })
        });
        await loadPatches();
      });
    });
    patchesList.querySelectorAll('.patch-reject-btn').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        await fetchJson('/chat/memory-patches/' + btn.getAttribute('data-patch-id') + '/reject', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: 'user rejected' })
        });
        await loadPatches();
      });
    });
  }

  async function loadPatches() {
    try {
      var items = await fetchJson('/chat/memory-patches');
      renderPatches(items);
    } catch (err) {
      if (patchesList) patchesList.innerHTML = '<div class="mini-empty">Failed: ' + escapeHtml(err.message || 'error') + '</div>';
    }
  }

  async function createPatch() {
    var change = patchChange && patchChange.value ? patchChange.value.trim() : '';
    if (!change) { setWarning('Proposed change is required.'); return; }
    await fetchJson('/chat/memory-patches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        proposed_change: change,
        affected_checkpoint_section: patchSection && patchSection.value ? patchSection.value.trim() : '',
        reason: patchReason && patchReason.value ? patchReason.value.trim() : '',
        risk: patchRisk && patchRisk.value ? patchRisk.value : 'low',
      })
    });
    if (patchChange) patchChange.value = '';
    if (patchSection) patchSection.value = '';
    if (patchReason) patchReason.value = '';
    await loadPatches();
  }

  if (patchCreateBtn) patchCreateBtn.addEventListener('click', function () { createPatch().catch(function (e) { setWarning(e.message || 'Patch create failed.'); }); });
  if (patchesReloadBtn) patchesReloadBtn.addEventListener('click', function () { loadPatches().catch(function () {}); });

  // ── Evidence Bundles ──────────────────────────────────────────────────────────

  function renderBundles(items) {
    if (!bundlesList) return;
    if (bundlesCount) bundlesCount.textContent = String((items || []).length);
    if (!items || !items.length) {
      bundlesList.innerHTML = '<div class="mini-empty">No evidence bundles. Click Scan Logs.</div>';
      return;
    }
    bundlesList.innerHTML = items.map(function (b) {
      var valBadge = b.validation === 'passed' ? 'badge-ok' : b.validation === 'failed' ? 'badge-error' : 'badge-warn';
      return [
        '<article class="mini-card">',
        '<div class="mini-card-head">',
        '<span class="badge badge-info">' + escapeHtml(b.source || '') + '</span>',
        '<span class="badge ' + valBadge + '">' + escapeHtml(b.validation || '') + '</span>',
        '</div>',
        '<p class="mini-card-text small">window: ' + escapeHtml(b.window || '') + ' · files: ' + String(b.row_count || 0) + ' rows</p>',
        b.insufficient_fields && b.insufficient_fields.length ? '<p class="mini-card-text small">insufficient: ' + escapeHtml(b.insufficient_fields.join(', ')) + '</p>' : '',
        '</article>'
      ].join('');
    }).join('');
  }

  async function loadBundles() {
    try {
      var items = await fetchJson('/chat/evidence-bundles');
      renderBundles(items);
    } catch (err) {
      if (bundlesList) bundlesList.innerHTML = '<div class="mini-empty">Failed: ' + escapeHtml(err.message || 'error') + '</div>';
    }
  }

  async function scanBundles() {
    var bundle = await fetchJson('/chat/evidence-bundles/scan', { method: 'POST' });
    setWarning('Bundle created: ' + escapeHtml(bundle.bundle_id || '') + ' validation=' + escapeHtml(bundle.validation || ''));
    await loadBundles();
  }

  if (bundlesScanBtn) bundlesScanBtn.addEventListener('click', function () { scanBundles().catch(function (e) { setWarning(e.message || 'Scan failed.'); }); });
  if (bundlesReloadBtn) bundlesReloadBtn.addEventListener('click', function () { loadBundles().catch(function () {}); });

  function bindRecentRunRows() {
    if (!recentRunsBody) {
      return;
    }
    Array.from(recentRunsBody.querySelectorAll('[data-run-id]')).forEach(function (row) {
      row.addEventListener('click', function () {
        loadRunDetail(row.getAttribute('data-run-id')).catch(function (error) {
          setWarning(error.message || 'Failed to load run detail.');
        });
      });
    });
  }

  function renderRunDetail(status, output, events) {
    const eventItems = Array.isArray(events) ? events : [];
    if (eventLogView) {
      eventLogView.textContent = eventItems.length ? eventItems.map(function (event) {
        return [
          '[' + formatTimestamp(event.created_at || event.timestamp) + ']',
          String(event.type || event.event_type || 'event'),
          String(event.message || event.detail || '')
        ].filter(Boolean).join(' ');
      }).join('\n') : 'Журнал подій порожній.';
    }
    if (traceView) {
      traceView.textContent = status ? stringifySurface(status) : 'Трейс відсутній.';
    }
    if (testResultView) {
      if (!output) {
        testResultView.textContent = 'Результатів тестів немає.';
      } else {
        testResultView.textContent = stringifySurface(output.output || output.stdout || output.stderr || output);
      }
    }
    if (drawerArtifactsView) {
      if (!output) {
        drawerArtifactsView.textContent = 'Артефактів немає.';
      } else {
        drawerArtifactsView.textContent = stringifySurface({
          run_id: status ? status.run_id : undefined,
          run_dir: output.run_dir,
          truncated: output.truncated,
          latest_event: status ? status.latest_event : undefined,
        });
      }
    }
  }

  async function loadRunDetail(runId) {
    if (!runId) {
      renderRunDetail(null, null, []);
      return;
    }
    state.selectedRunId = runId;
    const status = await fetchJson('/runs/' + runId + '/status');
    const output = await fetchJson('/runs/' + runId + '/output');
    const events = await fetchJson('/runs/' + runId + '/events');
    if (recentRunsBody) {
      Array.from(recentRunsBody.querySelectorAll('[data-run-id]')).forEach(function (row) {
        row.classList.toggle('is-active', row.getAttribute('data-run-id') === runId);
      });
    }
    renderRunDetail(status, output, events.events || []);
  }

  function renderRecentRuns(runs) {
    const items = Array.isArray(runs) ? runs : [];
    if (!recentRunsBody) {
      return;
    }
    if (!items.length) {
      recentRunsBody.innerHTML = '<tr><td colspan="5" class="table-empty">Останніх запусків немає.</td></tr>';
      renderRunDetail(null, null, []);
      return;
    }
    recentRunsBody.innerHTML = items.map(function (run) {
      const runId = escapeHtml(run.run_id || '—');
      const phase = escapeHtml(run.current_phase || run.latest_event || '—');
      const status = escapeHtml(run.status || 'idle');
      const active = state.selectedRunId && state.selectedRunId === run.run_id ? ' is-active' : '';
      return [
        '<tr class="run-row' + active + '" data-run-id="' + runId + '">',
        '<td><div class="run-row-title mono">' + runId + '</div><div class="run-row-subtitle prompt-cell">' + escapeHtml(run.prompt || '—') + '</div></td>',
        '<td><span class="badge ' + badgeToneClass(String(run.status || '').toLowerCase()) + '">' + status + '</span></td>',
        '<td>' + phase + '</td>',
        '<td class="mono small">' + escapeHtml(formatTimestamp(run.started_at || run.created_at)) + '</td>',
        '<td class="mono small">' + escapeHtml(formatDuration(run.duration_ms)) + '</td>',
        '</tr>'
      ].join('');
    }).join('');
    bindRecentRunRows();
  }

  async function loadRecentRuns() {
    try {
      const runs = await fetchJson('/runs');
      state.recentRuns = Array.isArray(runs) ? runs : (runs.runs || []);
      renderRecentRuns(state.recentRuns);
      if (state.recentRuns.length) {
        await loadRunDetail(state.selectedRunId || state.recentRuns[0].run_id);
      }
    } catch (error) {
      if (recentRunsBody) {
        recentRunsBody.innerHTML = '<tr><td colspan="5" class="table-empty">Не вдалося завантажити запуски.</td></tr>';
      }
      renderRunDetail(null, null, []);
      setWarning(error.message || 'Failed to load recent runs.');
    }
  }

  // ── Initial load of all Agent OS panels ──────────────────────────────────────

  loadPlaybooks().catch(function () {});
  loadTools().catch(function () {});
  loadApprovals().catch(function () {});
  loadReports().catch(function () {});
  loadDecisions().catch(function () {});
  loadPatches().catch(function () {});
  loadBundles().catch(function () {});
  loadRecentRuns().catch(function () {});

  populateProfileSelects();
  updateCharCount();
  renderProjectCapsule(state.projectCapsule);
  setOutputSurface('idle', 'Публічний результат з\'явиться після першої дії.', 'Немає результатів.');
  refreshSessions().catch(function (error) { setWarning(error.message || 'Failed to load sessions.'); });

  // ── Cockpit UI ─────────────────────────────────────────────────────────────

  var leftNav = document.getElementById('left-nav');
  var appShell = document.querySelector('.app-shell');
  var sessionsColumn = document.getElementById('sessions-column');
  var leftNavResizer = document.getElementById('left-nav-resizer');
  var navCollapseBtn = document.getElementById('nav-collapse-btn');
  var workspaceTabs = document.getElementById('workspace-tabs');
  var inspectorTabs = document.getElementById('inspector-tabs');
  var cockpitLayout = document.getElementById('cockpit-layout');
  var sessionPanelResizer = document.getElementById('session-panel-resizer');
  var inspectorColumn = document.getElementById('inspector-column');
  var inspectorPanelResizer = document.getElementById('inspector-panel-resizer');
  var bottomDrawer = document.getElementById('bottom-drawer');
  var bottomDrawerResizer = document.getElementById('bottom-drawer-resizer');
  var drawerToggleBtn = document.getElementById('drawer-toggle-btn');
  var drawerTabsEl = document.getElementById('drawer-tabs');
  var drawerRefreshBtn = document.getElementById('drawer-refresh-btn');
  var headerInspectorToggle = document.getElementById('header-inspector-toggle');
  var inspectorToggleBtn = document.getElementById('inspector-toggle-btn');
  var headerReasoningBtn = document.getElementById('header-reasoning-btn');
  var headerReasoningStatus = document.getElementById('header-reasoning-status');
  var headerModelBtn = document.getElementById('header-model-btn');
  var projectSelectorBtn = document.getElementById('project-selector-btn');
  var reasoningToggleBtn = document.getElementById('reasoning-toggle-btn');
  var reasoningBody = document.getElementById('reasoning-body');
  var cmdPaletteModal = document.getElementById('cmd-palette-modal');
  var cmdPaletteBtn = document.getElementById('cmd-palette-btn');
  var cmdPaletteBackdrop = document.getElementById('cmd-palette-backdrop');
  var cmdPaletteInput = document.getElementById('cmd-palette-input');
  var cmdPaletteList = document.getElementById('cmd-palette-list');
  var contextPreviewBtn = document.getElementById('context-preview-btn');
  var inspectContextBtn2 = document.getElementById('inspect-context-btn2');
  var compressBtn2 = document.getElementById('compress-btn2');
  var scenarioBar = document.getElementById('scenario-buttons-bar');
  var modelSelector = document.getElementById('model-selector');
  var composerDefaultBtn = document.getElementById('composer-default-btn');

  function syncDrawerState() {
    if (!drawerToggleBtn || !bottomDrawer) {
      return;
    }
    drawerToggleBtn.textContent = bottomDrawer.classList.contains('is-open') ? '▾' : '▴';
    drawerToggleBtn.setAttribute('aria-expanded', bottomDrawer.classList.contains('is-open') ? 'true' : 'false');
  }

  function setDrawerOpen(open, options) {
    options = options || {};
    if (!bottomDrawer) {
      return;
    }
    bottomDrawer.classList.toggle('is-open', !!open);
    syncDrawerState();
    if (!options.skipLegacyStorage) {
      writeStoredValue(STORAGE_KEYS.drawerOpen, !!open);
    }
    ensureLayoutState().bottomDrawerCollapsed = !open;
    if (state.boardLayoutState && state.boardLayoutState.panels && state.boardLayoutState.panels.artifacts) {
      state.boardLayoutState.panels.artifacts.collapsed = !open;
      if (state.layoutMode === 'board' && !options.skipSave) {
        saveBoardLayoutState();
      }
    }
    if (!options.skipSave) {
      saveLayoutState();
    }
  }

  function setWorkspacePreset(preset, options) {
    options = options || {};
    var normalized = normalizePreset(preset);
    var layout = ensureLayoutState();
    state.layoutPreset = normalized;
    layout.layoutPreset = normalized;
    if (normalized !== 'custom' && !options.preserveOrder) {
      applySectionOrder(LAYOUT_PRESET_ORDERS[normalized], { skipSave: true, preservePreset: true });
    } else {
      syncWorkspacePresetControl(layout.centralSectionOrder);
      syncMoveControls();
    }
    if (!options.skipLegacyStorage) {
      writeStoredValue(STORAGE_KEYS.layoutPreset, normalized);
    }
    if (!options.skipSave) {
      saveLayoutState();
    }
  }

  function getExpandedComposerHeight() {
    var targetHeight = centralWorkspace && centralWorkspace.clientHeight > 0
      ? Math.floor(centralWorkspace.clientHeight * 0.48)
      : 260;
    return clampSectionHeight('composer', targetHeight);
  }

  function setComposerExpanded(expanded, options) {
    options = options || {};
    state.composerExpanded = !!expanded;
    if (composer) {
      composer.classList.toggle('is-expanded', state.composerExpanded);
    }
    if (composerExpandBtn) {
      composerExpandBtn.textContent = state.composerExpanded ? 'Expanded' : 'Expand';
      composerExpandBtn.setAttribute('aria-pressed', state.composerExpanded ? 'true' : 'false');
    }
    if (chatInput) {
      chatInput.rows = state.composerExpanded ? 10 : 5;
    }
    if (!options.skipHeightChange) {
      setSectionHeight('composer', state.composerExpanded ? getExpandedComposerHeight() : LAYOUT_SECTION_CONFIG.composer.defaultHeight, { skipSave: true });
    }
    ensureLayoutState().composerExpanded = state.composerExpanded;
    if (!options.skipLegacyStorage) {
      writeStoredValue(STORAGE_KEYS.composerExpanded, state.composerExpanded);
    }
    if (!options.skipSave) {
      saveLayoutState();
    }
  }

  function setTraceMode(mode) {
    state.traceMode = ['compact', 'working', 'detailed'].indexOf(String(mode || '')) >= 0 ? mode : 'compact';
    writeStoredValue(STORAGE_KEYS.traceMode, state.traceMode);
    if (traceModeSwitcher) {
      traceModeSwitcher.querySelectorAll('[data-trace-mode]').forEach(function (button) {
        button.classList.toggle('is-active', button.getAttribute('data-trace-mode') === state.traceMode);
      });
    }
    syncReasoningSurface(!(reasoningBody && reasoningBody.classList.contains('hidden')));
    if (state.currentSessionDetail) {
      renderThread(state.currentSessionDetail);
      renderWorkTrace(state.currentSessionDetail);
    }
  }

  function syncCollapseButton(button, expanded) {
    button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    button.textContent = expanded ? '▾' : '▸';
    var card = button.closest('.collapsible-card');
    if (card) {
      card.classList.toggle('is-open', expanded);
      card.classList.toggle('workspace-section--collapsed', !expanded);
    }
  }

  function syncReasoningSurface(expanded) {
    var badge = document.getElementById('reasoning-mode-badge');
    var label = formatTraceModeLabel(state.traceMode);
    if (badge) {
      badge.textContent = label;
    }
    if (headerReasoningStatus) {
      headerReasoningStatus.textContent = expanded ? label : 'collapsed';
    }
    if (headerReasoningBtn) {
      headerReasoningBtn.setAttribute('aria-pressed', expanded ? 'true' : 'false');
    }
  }

  function setCollapsedState(targetId, expanded, options) {
    options = options || {};
    var target = document.getElementById(targetId);
    if (!target) {
      return false;
    }
    target.classList.toggle('hidden', !expanded);
    document.querySelectorAll('[data-collapse-target="' + targetId + '"]').forEach(function (button) {
      syncCollapseButton(button, expanded);
    });
    if (!options.skipLegacyStorage) {
      var sectionStates = readStoredValue(STORAGE_KEYS.sections, {});
      sectionStates[targetId] = !!expanded;
      writeStoredValue(STORAGE_KEYS.sections, sectionStates);
    }
    var sectionKey = getLayoutSectionKeyFromTarget(targetId);
    if (sectionKey) {
      ensureLayoutState().collapsedSections[sectionKey] = !expanded;
      if (state.boardLayoutState && state.boardLayoutState.panels && state.boardLayoutState.panels[sectionKey]) {
        state.boardLayoutState.panels[sectionKey].collapsed = !expanded;
        if (state.layoutMode === 'board' && !options.skipSave) {
          saveBoardLayoutState();
        }
      }
      if (!options.skipSave) {
        saveLayoutState();
      }
    }
    if (targetId === 'reasoning-body') {
      syncReasoningSurface(expanded);
    }
    return expanded;
  }

  document.querySelectorAll('[data-collapse-target]').forEach(function (button) {
    var targetId = button.getAttribute('data-collapse-target');
    var target = targetId ? document.getElementById(targetId) : null;
    syncCollapseButton(button, target ? !target.classList.contains('hidden') : true);
    button.addEventListener('click', function () {
      if (!target) {
        return;
      }
      setCollapsedState(targetId, target.classList.contains('hidden'));
    });
  });

  function restoreWorkspaceSectionStates() {
    var stored = readStoredValue(STORAGE_KEYS.sections, {});
    Object.keys(stored).forEach(function (targetId) {
      if (typeof stored[targetId] === 'boolean') {
        setCollapsedState(targetId, stored[targetId]);
      }
    });
  }

  function setInspectorCollapsed(collapsed, options) {
    options = options || {};
    if (!inspectorColumn || !cockpitLayout) {
      return;
    }
    inspectorColumn.classList.toggle('is-collapsed', collapsed);
    cockpitLayout.classList.toggle('is-inspector-collapsed', collapsed);
    [headerInspectorToggle, inspectorToggleBtn].forEach(function (button) {
      if (!button) {
        return;
      }
      button.textContent = collapsed ? 'Показати' : 'Сховати';
      button.setAttribute('aria-pressed', collapsed ? 'true' : 'false');
    });
    ensureLayoutState().inspectorCollapsed = !!collapsed;
    if (!options.skipSave) {
      saveLayoutState();
    }
  }

  function setNavCollapsed(collapsed, options) {
    options = options || {};
    if (!leftNav) {
      return;
    }
    leftNav.classList.toggle('is-collapsed', collapsed);
    if (appShell) {
      appShell.classList.toggle('is-nav-collapsed', collapsed);
    }
    if (navCollapseBtn) {
      var icon = navCollapseBtn.querySelector('.nav-icon');
      if (icon) {
        icon.textContent = collapsed ? '▸' : '◂';
      }
    }
    ensureLayoutState().navCollapsed = !!collapsed;
    if (!options.skipSave) {
      saveLayoutState();
    }
  }

  function beginResizeInteraction(cursor, target) {
    document.body.classList.add('layout-resizing');
    document.body.style.cursor = cursor;
    if (appShell) {
      appShell.classList.add('app-shell--resizing');
    }
    if (target) {
      target.classList.add('workspace-section--resizing');
      target.classList.add('is-active');
    }
  }

  function endResizeInteraction(target) {
    document.body.classList.remove('layout-resizing');
    document.body.style.cursor = '';
    if (appShell) {
      appShell.classList.remove('app-shell--resizing');
    }
    if (target) {
      target.classList.remove('workspace-section--resizing');
      target.classList.remove('is-active');
    }
  }

  function startPointerResize(event, options) {
    if (!event || event.button !== 0) {
      return;
    }
    event.preventDefault();
    var startX = event.clientX;
    var startY = event.clientY;
    beginResizeInteraction(options.cursor, options.target);
    function onPointerMove(moveEvent) {
      options.onMove({
        deltaX: moveEvent.clientX - startX,
        deltaY: moveEvent.clientY - startY
      });
    }
    function onPointerUp() {
      document.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('pointerup', onPointerUp);
      document.removeEventListener('pointercancel', onPointerUp);
      endResizeInteraction(options.target);
      if (typeof options.onEnd === 'function') {
        options.onEnd();
      }
    }
    document.addEventListener('pointermove', onPointerMove);
    document.addEventListener('pointerup', onPointerUp);
    document.addEventListener('pointercancel', onPointerUp);
  }

  function moveSection(sectionKey, direction) {
    var layout = ensureLayoutState();
    var order = normalizeSectionOrder(layout.centralSectionOrder);
    var currentIndex = order.indexOf(sectionKey);
    var delta = direction === 'up' ? -1 : 1;
    var nextIndex = currentIndex + delta;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= order.length) {
      return;
    }
    var swap = order[nextIndex];
    order[nextIndex] = order[currentIndex];
    order[currentIndex] = swap;
    layout.layoutPreset = 'custom';
    applySectionOrder(order, { skipSave: true, preservePreset: true });
    syncWorkspacePresetControl(order);
    saveLayoutState();
  }

  function initSectionMoveControls() {
    document.querySelectorAll('[data-section-move][data-section-key]').forEach(function (button) {
      if (button.dataset.bound === 'true') {
        return;
      }
      button.dataset.bound = 'true';
      button.addEventListener('click', function () {
        moveSection(button.getAttribute('data-section-key'), button.getAttribute('data-section-move'));
      });
    });
    syncMoveControls();
  }

  function initSectionResize() {
    document.querySelectorAll('[data-layout-resize]').forEach(function (handle) {
      if (handle.dataset.bound === 'true') {
        return;
      }
      handle.dataset.bound = 'true';
      handle.addEventListener('pointerdown', function (event) {
        var sectionKey = handle.getAttribute('data-layout-resize');
        var section = getSectionElementByKey(sectionKey);
        var body = getSectionBodyByKey(sectionKey);
        if (!section || !body) {
          return;
        }
        var startHeight = body.getBoundingClientRect().height;
        startPointerResize(event, {
          cursor: 'row-resize',
          target: section,
          onMove: function (movement) {
            setSectionHeight(sectionKey, startHeight + movement.deltaY, { skipSave: true });
            if (sectionKey === 'composer') {
              setComposerExpanded(false, { skipSave: true, skipLegacyStorage: true, skipHeightChange: true });
            }
          },
          onEnd: saveLayoutState
        });
      });
    });
  }

  function bindPanelResize(handle, panelKey, element, axisDirection) {
    if (!handle || !element || handle.dataset.bound === 'true') {
      return;
    }
    handle.dataset.bound = 'true';
    handle.addEventListener('pointerdown', function (event) {
      var startWidth = element.getBoundingClientRect().width;
      startPointerResize(event, {
        cursor: 'col-resize',
        target: handle,
        onMove: function (movement) {
          setPanelWidth(panelKey, startWidth + (movement.deltaX * axisDirection), { skipSave: true });
        },
        onEnd: saveLayoutState
      });
    });
  }

  function initPanelResize() {
    bindPanelResize(leftNavResizer, 'leftNav', leftNav, 1);
    bindPanelResize(sessionPanelResizer, 'sessionPanel', sessionsColumn, 1);
    bindPanelResize(inspectorPanelResizer, 'rightInspector', inspectorColumn, -1);
  }

  function initBottomDrawerResize() {
    if (!bottomDrawerResizer || !bottomDrawer || bottomDrawerResizer.dataset.bound === 'true') {
      return;
    }
    bottomDrawerResizer.dataset.bound = 'true';
    bottomDrawerResizer.addEventListener('pointerdown', function (event) {
      var startHeight = ensureLayoutState().bottomDrawerHeight;
      startPointerResize(event, {
        cursor: 'row-resize',
        target: bottomDrawerResizer,
        onMove: function (movement) {
          setBottomDrawerHeight(startHeight - movement.deltaY, { skipSave: true });
        },
        onEnd: saveLayoutState
      });
    });
  }

  function initGlobalScrollGuards() {
    [centralWorkspace, inspectorColumn, document.getElementById('drawer-content')].forEach(function (node) {
      if (!node) {
        return;
      }
      node.style.overscrollBehavior = 'auto';
    });
  }

  function runPaletteAction(actionId) {
    var actions = {
      'new-session': function () { createSession().catch(function (error) { setWarning(error.message || 'Failed to create session.'); }); },
      'toggle-inspector': function () { setInspectorCollapsed(!(inspectorColumn && inspectorColumn.classList.contains('is-collapsed'))); },
      'toggle-drawer': function () { setDrawerOpen(!(bottomDrawer && bottomDrawer.classList.contains('is-open'))); },
      'inspect-context': function () { inspectContext().catch(function (error) { setWarning(error.message || 'Context inspect failed.'); }); },
      'focus-composer': function () { if (chatInput) { chatInput.focus(); } },
      'open-monitoring': function () {
        var tabBtn = workspaceTabs ? workspaceTabs.querySelector('[data-ws-tab="monitoring-tab"]') : null;
        if (tabBtn) { tabBtn.click(); }
      },
      'open-runs': function () { window.location.href = '/'; }
    };
    if (actions[actionId]) {
      actions[actionId]();
    }
    closeCmdPalette();
  }

  function renderCmdPalette(query) {
    if (!cmdPaletteList) {
      return;
    }
    var commands = [
      { id: 'new-session', title: 'Нова сесія', subtitle: 'Створити нову chat session' },
      { id: 'toggle-inspector', title: 'Toggle Inspector', subtitle: 'Сховати або показати правий inspector rail' },
      { id: 'toggle-drawer', title: 'Toggle Drawer', subtitle: 'Відкрити або закрити нижній utility drawer' },
      { id: 'inspect-context', title: 'Inspect Context', subtitle: 'Зібрати поточний context pack' },
      { id: 'focus-composer', title: 'Focus Composer', subtitle: 'Перейти до textarea запиту' },
      { id: 'open-monitoring', title: 'Open Monitoring Tab', subtitle: 'Перемкнутися на вкладку Моніторинг' },
      { id: 'open-runs', title: 'Open Runs Page', subtitle: 'Відкрити сторінку /runs' }
    ];
    var filter = String(query || '').trim().toLowerCase();
    var filtered = commands.filter(function (item) {
      return !filter || item.title.toLowerCase().indexOf(filter) >= 0 || item.subtitle.toLowerCase().indexOf(filter) >= 0;
    });
    if (!filtered.length) {
      cmdPaletteList.innerHTML = '<div class="mini-empty">Команд не знайдено.</div>';
      return;
    }
    cmdPaletteList.innerHTML = filtered.map(function (item) {
      return [
        '<button type="button" class="cmd-palette-item" data-command-id="' + escapeHtml(item.id) + '">',
        '<strong>' + escapeHtml(item.title) + '</strong>',
        '<span>' + escapeHtml(item.subtitle) + '</span>',
        '</button>'
      ].join('');
    }).join('');
    Array.from(cmdPaletteList.querySelectorAll('[data-command-id]')).forEach(function (button) {
      button.addEventListener('click', function () {
        runPaletteAction(button.getAttribute('data-command-id'));
      });
    });
  }

  function openCmdPalette() {
    if (!cmdPaletteModal) { return; }
    cmdPaletteModal.classList.remove('hidden');
    renderCmdPalette(cmdPaletteInput ? cmdPaletteInput.value : '');
    if (cmdPaletteInput) { cmdPaletteInput.focus(); }
  }

  function closeCmdPalette() {
    if (!cmdPaletteModal) { return; }
    cmdPaletteModal.classList.add('hidden');
  }

  function updateHeaderFromCapsule(capsule) {
    var headerProjectName = document.getElementById('header-project-name');
    if (headerProjectName && capsule && capsule.project) {
      headerProjectName.textContent = capsule.project.name || 'Не завантажено';
    }
  }

  function updateHeaderFromSession(session) {
    var headerModel = document.getElementById('header-model-name');
    var headerStatus = document.getElementById('header-session-status');
    if (headerModel && session && session.active_profile) {
      headerModel.textContent = session.active_profile.model_id || '—';
    }
    if (headerStatus && session) {
      headerStatus.textContent = session.status || 'idle';
      applyBadgeTone(headerStatus, session.status || 'idle');
    }
  }

  if (leftNav) {
    leftNav.querySelectorAll('.nav-item[data-module]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var moduleId = 'module-' + btn.getAttribute('data-module');
        leftNav.querySelectorAll('.nav-item[data-module]').forEach(function (n) { n.classList.remove('is-active'); });
        btn.classList.add('is-active');
        document.querySelectorAll('.module').forEach(function (m) { m.classList.remove('is-active'); });
        var target = document.getElementById(moduleId);
        if (target) { target.classList.add('is-active'); }
      });
    });
  }

  if (navCollapseBtn) {
    navCollapseBtn.addEventListener('click', function () {
      setNavCollapsed(!(leftNav && leftNav.classList.contains('is-collapsed')));
    });
  }

  if (workspaceTabs) {
    workspaceTabs.querySelectorAll('.tab-button[data-ws-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var tabId = 'ws-tab-' + btn.getAttribute('data-ws-tab');
        workspaceTabs.querySelectorAll('.tab-button[data-ws-tab]').forEach(function (b) { b.classList.remove('is-active'); });
        btn.classList.add('is-active');
        document.querySelectorAll('.ws-tab').forEach(function (t) { t.classList.remove('is-active'); });
        var target = document.getElementById(tabId);
        if (target) { target.classList.add('is-active'); }
      });
    });
  }

  if (inspectorTabs) {
    inspectorTabs.querySelectorAll('.tab-button[data-inspector]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var panelId = btn.getAttribute('data-inspector');
        inspectorTabs.querySelectorAll('.tab-button[data-inspector]').forEach(function (b) { b.classList.remove('is-active'); });
        btn.classList.add('is-active');
        document.querySelectorAll('.inspector-panel').forEach(function (p) { p.classList.remove('is-active'); });
        var target = document.getElementById(panelId);
        if (target) { target.classList.add('is-active'); }
      });
    });
  }

  if (drawerToggleBtn && bottomDrawer) {
    drawerToggleBtn.addEventListener('click', function () {
      setDrawerOpen(!bottomDrawer.classList.contains('is-open'));
    });
  }

  if (drawerRefreshBtn) {
    drawerRefreshBtn.addEventListener('click', function () {
      loadRecentRuns().catch(function (error) {
        setWarning(error.message || 'Failed to refresh runs.');
      });
    });
  }

  if (drawerTabsEl) {
    drawerTabsEl.querySelectorAll('.tab-button[data-drawer-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var panelId = 'drawer-tab-' + btn.getAttribute('data-drawer-tab');
        drawerTabsEl.querySelectorAll('.tab-button[data-drawer-tab]').forEach(function (b) { b.classList.remove('is-active'); });
        btn.classList.add('is-active');
        document.querySelectorAll('.drawer-tab-panel').forEach(function (p) { p.classList.remove('is-active'); });
        var target = document.getElementById(panelId);
        if (target) { target.classList.add('is-active'); }
      });
    });
  }

  [headerInspectorToggle, inspectorToggleBtn].forEach(function (button) {
    if (!button) {
      return;
    }
    button.addEventListener('click', function () {
      setInspectorCollapsed(!(inspectorColumn && inspectorColumn.classList.contains('is-collapsed')));
    });
  });

  if (headerReasoningBtn) {
    headerReasoningBtn.addEventListener('click', function () {
      setCollapsedState('reasoning-body', reasoningBody && reasoningBody.classList.contains('hidden'));
    });
  }

  if (cmdPaletteBtn) { cmdPaletteBtn.addEventListener('click', openCmdPalette); }
  if (cmdPaletteBackdrop) { cmdPaletteBackdrop.addEventListener('click', closeCmdPalette); }
  if (cmdPaletteInput) {
    cmdPaletteInput.addEventListener('input', function () {
      renderCmdPalette(cmdPaletteInput.value);
    });
  }

  document.addEventListener('keydown', function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      openCmdPalette();
    }
    if (event.key === 'Escape') { closeCmdPalette(); }
  });

  if (chatInput) {
    chatInput.addEventListener('keydown', function (event) {
      if (event.ctrlKey && event.key === 'Enter') {
        event.preventDefault();
        sendMessage().catch(function (error) { setWarning(error.message || 'Send failed.'); });
      }
    });
  }

  if (contextPreviewBtn) {
    contextPreviewBtn.addEventListener('click', function () {
      inspectContext().catch(function (error) { setWarning(error.message || 'Context inspect failed.'); });
    });
  }

  if (composerUseScenarioBtn) {
    composerUseScenarioBtn.addEventListener('click', function () {
      if (!state.selectedScenarioId) {
        setOutputSurface('warn', 'Спочатку виберіть сценарій.', 'Scenario preview покаже metadata та source.');
        return;
      }
      applyScenarioToComposer(getScenarioMeta(state.selectedScenarioId), 'Вибраний сценарій повторно вставлено в composer.');
    });
  }

  if (composerClearBtn) {
    composerClearBtn.addEventListener('click', function () {
      if (chatInput) {
        chatInput.value = '';
        updateCharCount();
      }
      setOutputSurface('success', 'Composer очищено.', '');
    });
  }

  if (composerExpandBtn) {
    composerExpandBtn.addEventListener('click', function () {
      setComposerExpanded(!state.composerExpanded);
    });
  }

  if (composerDefaultBtn) {
    composerDefaultBtn.addEventListener('click', function () {
      setSectionHeight('composer', LAYOUT_SECTION_CONFIG.composer.defaultHeight, { skipSave: true });
      setComposerExpanded(false, { skipHeightChange: true, skipSave: true });
      saveLayoutState();
    });
  }

  if (inspectContextBtn2) {
    inspectContextBtn2.addEventListener('click', function () { inspectContext().catch(function () {}); });
  }
  if (compressBtn2) {
    compressBtn2.addEventListener('click', function () { compressSession().catch(function () {}); });
  }

  if (scenarioBar) {
    scenarioBar.querySelectorAll('.scenario-btn[data-playbook]').forEach(function (btn) {
      btn.addEventListener('click', function (event) {
        var meta = getScenarioMeta(btn.getAttribute('data-playbook'));
        renderScenarioPreview(meta.playbookId);
        if (event.altKey) {
          runScenario(meta).catch(function (error) {
            setWarning(error.message || 'Scenario run failed.');
          });
          return;
        }
        if (event.shiftKey) {
          applyScenarioToComposer(meta, 'Шаблон вставлено без запуску.');
          return;
        }
        applyScenarioToComposer(meta, isGuardedScenario(meta)
          ? 'Guarded сценарій підготовлено. Перегляньте preview перед запуском.'
          : 'Composer заповнено зі сценарію.');
      });
    });
  }

  if (scenarioApplyBtn) {
    scenarioApplyBtn.addEventListener('click', function () {
      if (!state.selectedScenarioId) {
        return;
      }
      applyScenarioToComposer(getScenarioMeta(state.selectedScenarioId), 'Сценарій вставлено з preview panel.');
    });
  }

  if (scenarioRunBtn) {
    scenarioRunBtn.addEventListener('click', function () {
      if (!state.selectedScenarioId) {
        return;
      }
      runScenario(getScenarioMeta(state.selectedScenarioId)).catch(function (error) {
        setWarning(error.message || 'Scenario run failed.');
      });
    });
  }

  if (scenarioOpenSourceBtn) {
    scenarioOpenSourceBtn.addEventListener('click', function () {
      if (!state.selectedScenarioId) {
        return;
      }
      var meta = getScenarioMeta(state.selectedScenarioId);
      setOutputSurface('success', 'Source template visible.', meta.sourceFile || '—');
    });
  }

  if (traceModeSwitcher) {
    traceModeSwitcher.querySelectorAll('[data-trace-mode]').forEach(function (button) {
      button.addEventListener('click', function () {
        setTraceMode(button.getAttribute('data-trace-mode'));
      });
    });
  }

  async function populateModelSelector() {
    try {
      var data = await fetchJson('/models');
      var models = Array.isArray(data) ? data : (data.models || data.catalog || []);
      if (!modelSelector || !models.length) { return; }
      modelSelector.innerHTML = '<option value="">Модель…</option>' +
        models.map(function (m) {
          var id = typeof m === 'string' ? m : (m.model_id || m.id || String(m));
          var label = typeof m === 'string' ? m : (m.display_name || m.name || id);
          return '<option value="' + escapeHtml(id) + '">' + escapeHtml(label) + '</option>';
        }).join('');
    } catch (e) { /* model selector stays as default placeholder */ }
  }

  if (headerModelBtn) {
    headerModelBtn.addEventListener('click', function () {
      if (profileSelect) {
        profileSelect.focus();
      }
    });
  }

  if (projectSelectorBtn) {
    projectSelectorBtn.addEventListener('click', openCmdPalette);
  }

  if (modelSelector) {
    modelSelector.addEventListener('change', function () {
      setOutputSurface('success', 'Composer model updated.', modelSelector.value || 'default');
    });
  }

  if (workspacePresetSelect) {
    workspacePresetSelect.addEventListener('change', function () {
      setWorkspacePreset(workspacePresetSelect.value);
    });
  }

  if (workspaceModeSwitch) {
    workspaceModeSwitch.querySelectorAll('[data-layout-mode]').forEach(function (button) {
      button.addEventListener('click', function () {
        setLayoutMode(button.getAttribute('data-layout-mode'));
        setOutputSurface('success', button.getAttribute('data-layout-mode') === 'board' ? 'Board Mode увімкнено.' : 'Cockpit Mode увімкнено.', button.getAttribute('data-layout-mode') === 'board'
          ? 'Canvas layout зберігається окремо від cockpit.'
          : 'Класичний cockpit layout відновлено.');
      });
    });
  }

  if (boardResetBtn) {
    boardResetBtn.addEventListener('click', function () {
      resetBoardLayoutState();
      setOutputSurface('success', 'Board layout restored.', 'Canvas windows повернуто до початкового bounded layout.');
    });
  }

  if (workspaceResetBtn) {
    workspaceResetBtn.addEventListener('click', function () {
      if (state.layoutMode === 'board') {
        resetBoardLayoutState();
      } else {
        resetLayoutState();
      }
      setTraceMode('compact');
      setOutputSurface('success', 'Layout restored.', state.layoutMode === 'board'
        ? 'Canvas windows повернуто до базового board layout.'
        : 'Central workspace повернуто до базового preset.');
    });
  }

  if (resultCopyBtn) {
    resultCopyBtn.addEventListener('click', function () {
      var text = outputResultBox ? outputResultBox.textContent || '' : '';
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).catch(function () {});
      }
      setOutputSurface('success', 'Result copied.', text || 'Немає результату для копіювання.');
    });
  }

  if (resultAddMemoryBtn) {
    resultAddMemoryBtn.addEventListener('click', function () {
      if (!state.currentSessionId) {
        setWarning('Select a session first.');
        return;
      }
      fetchJson('/chat/sessions/' + state.currentSessionId + '/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: (outputResultBox && outputResultBox.textContent) || '', kind: 'summary' })
      }).then(function () {
        setOutputSurface('success', 'Result додано в memory.', outputResultBox ? outputResultBox.textContent || '' : '');
        return loadSession(state.currentSessionId);
      }).catch(function (error) {
        setWarning(error.message || 'Memory add failed.');
      });
    });
  }

  if (resultFocusTraceBtn) {
    resultFocusTraceBtn.addEventListener('click', function () {
      setCollapsedState('reasoning-body', true);
      if (reasoningBody && reasoningBody.scrollIntoView) {
        reasoningBody.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  if (resultFocusArtifactsBtn) {
    resultFocusArtifactsBtn.addEventListener('click', function () {
      if (state.layoutMode === 'board') {
        focusBoardPanel('artifacts');
        scrollBoardPanelIntoView('artifacts');
      }
      var artifactsTab = inspectorTabs ? inspectorTabs.querySelector('[data-inspector="inspector-artifacts"]') : null;
      if (artifactsTab) {
        artifactsTab.click();
      }
    });
  }

  populateModelSelector().catch(function () {});
  updateHeaderFromCapsule(state.projectCapsule);
  restoreWorkspaceSectionStates();
  state.layoutState = loadLayoutState();
  applyLayoutState(state.layoutState, { skipSave: true });
  state.boardLayoutState = loadBoardLayoutState();
  setTraceMode(readStoredValue(STORAGE_KEYS.traceMode, 'compact'));
  syncReasoningSurface(reasoningBody ? !reasoningBody.classList.contains('hidden') : false);
  initSectionResize();
  initPanelResize();
  initSectionMoveControls();
  initBottomDrawerResize();
  initGlobalScrollGuards();
  initBoardInteractions();
  syncLayoutModeControls();
  setLayoutMode(loadLayoutMode(), { skipPersist: true, skipSave: true, skipScroll: false });
  window.addEventListener('resize', function () {
    if (state.layoutMode === 'board') {
      applyBoardLayoutState(state.boardLayoutState || loadBoardLayoutState(), { skipSave: true, skipScroll: true });
      return;
    }
    if (state.layoutState) {
      applyLayoutState(state.layoutState, { skipSave: true });
    }
  });
  updateScenarioButtons();
  if (!state.selectedScenarioId) {
    var defaultScenario = getScenarioButtons()[0];
    if (defaultScenario) {
      state.selectedScenarioId = defaultScenario.getAttribute('data-playbook');
      renderScenarioPreview(state.selectedScenarioId);
      updateScenarioButtons();
    }
  }

})();
