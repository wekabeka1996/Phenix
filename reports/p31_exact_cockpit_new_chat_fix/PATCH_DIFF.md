# Patch Diff

Here is the exact git diff for the changes applied to resolve the New Chat active session visibility bug:

```diff
diff --git a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/static/chat.js b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/static/chat.js
index de90351a..1f4f9ae2 100644
--- a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/static/chat.js
+++ b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/static/chat.js
@@ -11,6 +11,8 @@
   const workspaceSessionPill = document.getElementById("workspace-session-pill");
   const profileSelect = document.getElementById("profile-select");
   const simpleChatModelSelect = document.getElementById("simple-chat-model");
+  const simpleSessionList = document.getElementById("simple-session-list");
+  const simpleChatSessionTitle = document.getElementById("simple-chat-session-title");
   const centralWorkspace = document.getElementById("central-workspace");
   const centralWorkspaceStack = document.getElementById("central-workspace-stack");
   const workspacePresetSelect = document.getElementById("workspace-preset-select");
@@ -2164,27 +2166,47 @@ function applyBoardPanelState(panelKey, panelState) {
   }
 
   function renderSessions() {
-    if (!sessionList) {
-      return;
+    if (sessionList) {
+      if (!state.sessions.length) {
+        sessionList.innerHTML = '<div class="mini-empty">No sessions yet.</div>';
+      } else {
+        sessionList.innerHTML = state.sessions.map(function (session) {
+          const active = session.session_id === state.currentSessionId ? " is-active" : "";
+          return [
+            '<button type="button" class="session-row' + active + '" data-session-id="' + escapeHtml(session.session_id) + '">',
+            '<span class="session-row-title">' + escapeHtml(session.title || "New Session") + '</span>',
+            '<span class="session-row-meta mono">' + escapeHtml(session.active_profile ? session.active_profile.model_id : "") + '</span>',
+            '</button>'
+          ].join("");
+        }).join("");
+        Array.from(sessionList.querySelectorAll("[data-session-id]")).forEach(function (button) {
+          button.addEventListener("click", function () {
+            loadSession(button.getAttribute("data-session-id"));
+          });
+        });
+      }
     }
-    if (!state.sessions.length) {
-      sessionList.innerHTML = '<div class="mini-empty">No sessions yet.</div>';
-      return;
+
+    if (simpleSessionList) {
+      if (!state.sessions.length) {
+        simpleSessionList.innerHTML = '<div class="simple-chat-drawer__empty">Тут з’являться елементи керування чатами та сесіями.</div>';
+      } else {
+        simpleSessionList.innerHTML = state.sessions.map(function (session) {
+          const active = session.session_id === state.currentSessionId ? " is-active" : "";
+          return [
+            '<button type="button" class="session-row' + active + '" data-session-id="' + escapeHtml(session.session_id) + '">',
+            '<span class="session-row-title">' + escapeHtml(session.title || "New Session") + '</span>',
+            '<span class="session-row-meta mono">' + escapeHtml(session.active_profile ? session.active_profile.model_id : "") + '</span>',
+            '</button>'
+          ].join("");
+        }).join("");
+        Array.from(simpleSessionList.querySelectorAll("[data-session-id]")).forEach(function (button) {
+          button.addEventListener("click", function () {
+            loadSession(button.getAttribute("data-session-id"));
+          });
+        });
+      }
     }
-    sessionList.innerHTML = state.sessions.map(function (session) {
-      const active = session.session_id === state.currentSessionId ? " is-active" : "";
-      return [
-        '<button type="button" class="session-row' + active + '" data-session-id="' + escapeHtml(session.session_id) + '">',
-        '<span class="session-row-title">' + escapeHtml(session.title || "New Session") + '</span>',
-        '<span class="session-row-meta mono">' + escapeHtml(session.active_profile ? session.active_profile.model_id : "") + '</span>',
-        '</button>'
-      ].join("");
-    }).join("");
-    Array.from(sessionList.querySelectorAll("[data-session-id]")).forEach(function (button) {
-      button.addEventListener("click", function () {
-        loadSession(button.getAttribute("data-session-id"));
-      });
-    });
   }
 
   function normalizeSimpleTraceEvent(item) {
@@ -2615,6 +2637,9 @@ function renderThread(detail) {
     if (sessionTitle) {
       sessionTitle.textContent = session.title || 'Conversation';
     }
+    if (simpleChatSessionTitle) {
+      simpleChatSessionTitle.textContent = session.title || 'Нова сесія';
+    }
     if (sessionMeta) {
       sessionMeta.textContent = (session.active_profile ? session.active_profile.name + ' · ' + session.active_profile.model_id : 'No active profile');
     }
diff --git a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/templates/chat.html b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/templates/chat.html
index 08608784..07b384f8 100644
--- a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/templates/chat.html
+++ b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/templates/chat.html
@@ -1134,7 +1134,7 @@
       <h3 class="simple-chat-drawer__title">Панель управління чатами</h3>
       <button type="button" class="btn-ghost" id="simple-chat-left-drawer-close">✕</button>
     </div>
-    <div class="simple-chat-drawer__body">
+    <div class="simple-chat-drawer__body" id="simple-session-list">
       <div class="simple-chat-drawer__empty">Тут з’являться елементи керування чатами та сесіями.</div>
     </div>
   </div>
```
