/**
 * app.js — PrivateGPT Frontend Application
 *
 * Vanilla JS SPA that communicates with the FastAPI backend.
 * Zero framework overhead — instant page transitions, SSE streaming,
 * and reactive UI updates.
 */

// ═══════════════════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════════════════

const state = {
  backendUrl: "http://localhost:8765",
  currentPage: "chat",
  sessionId: null,
  messages: [],
  selectedDocs: [],
  model: "phi3",
  showDebug: false,
  isGenerating: false,
};


// ═══════════════════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", async () => {
  // Initialize Lucide icons
  lucide.createIcons();

  // Get backend URL from Electron
  if (window.electronAPI) {
    state.backendUrl = await window.electronAPI.getBackendUrl();
    setupWindowControls();
    window.electronAPI.onBackendReady(() => onBackendReady());
    window.electronAPI.onBackendError(() => onBackendError());
  } else {
    // Running in regular browser (dev mode)
    setTimeout(() => onBackendReady(), 500);
  }

  setupEventListeners();
  setupChatInput();
});


// ═══════════════════════════════════════════════════════════════════════════
// Backend lifecycle
// ═══════════════════════════════════════════════════════════════════════════

async function onBackendReady() {
  document.getElementById("loading-status").textContent = "Loading models and index…";

  // Small delay for UX
  await sleep(400);

  const overlay = document.getElementById("loading-overlay");
  overlay.classList.add("hidden");

  // Initial data load
  await Promise.all([
    refreshOllamaStatus(),
    refreshDocuments(),
    refreshModels(),
    loadSessions(),
  ]);

  // Create initial session if needed
  if (!state.sessionId) {
    await createNewSession();
  }
}

function onBackendError() {
  document.getElementById("loading-status").textContent =
    "Failed to start backend. Check Python environment.";
}


// ═══════════════════════════════════════════════════════════════════════════
// Event Listeners
// ═══════════════════════════════════════════════════════════════════════════

function setupWindowControls() {
  document.getElementById("btn-minimize")?.addEventListener("click", () => window.electronAPI.minimize());
  document.getElementById("btn-maximize")?.addEventListener("click", () => window.electronAPI.maximize());
  document.getElementById("btn-close")?.addEventListener("click", () => window.electronAPI.close());
}

function setupEventListeners() {
  // Navigation
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => navigateTo(btn.dataset.page));
  });

  // New chat buttons
  document.getElementById("btn-new-chat")?.addEventListener("click", newChat);
  document.getElementById("btn-new-chat-header")?.addEventListener("click", newChat);

  // Ollama start
  document.getElementById("btn-start-ollama")?.addEventListener("click", startOllama);

  // Documents
  document.getElementById("btn-upload-docs")?.addEventListener("click", uploadDocuments);
  document.getElementById("btn-rebuild-index")?.addEventListener("click", rebuildIndex);

  // Models
  document.getElementById("btn-pull-custom")?.addEventListener("click", pullCustomModel);

  // Model selector
  document.getElementById("model-selector")?.addEventListener("change", (e) => {
    state.model = e.target.value;
  });

  // Debug toggle
  document.getElementById("debug-toggle")?.addEventListener("change", (e) => {
    state.showDebug = e.target.checked;
  });
}

function setupChatInput() {
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("btn-send");

  input?.addEventListener("input", () => {
    // Auto-resize
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
    // Enable/disable send
    sendBtn.disabled = !input.value.trim() || state.isGenerating;
  });

  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (input.value.trim() && !state.isGenerating) {
        sendMessage();
      }
    }
  });

  sendBtn?.addEventListener("click", () => {
    if (!state.isGenerating) sendMessage();
  });
}


// ═══════════════════════════════════════════════════════════════════════════
// Navigation
// ═══════════════════════════════════════════════════════════════════════════

function navigateTo(page) {
  state.currentPage = page;

  // Update nav buttons
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === page);
  });

  // Show/hide pages
  document.querySelectorAll(".page").forEach((p) => {
    p.classList.toggle("active", p.id === `page-${page}`);
  });

  // Refresh data for the page
  if (page === "documents") refreshDocuments();
  if (page === "models") refreshModels();
  if (page === "history") loadSessions();

  // Re-init icons for newly visible page
  lucide.createIcons();
}


// ═══════════════════════════════════════════════════════════════════════════
// Ollama
// ═══════════════════════════════════════════════════════════════════════════

async function refreshOllamaStatus() {
  try {
    const data = await api("/api/ollama/status");
    const dot = document.getElementById("ollama-dot");
    const label = document.getElementById("ollama-label");
    const startBtn = document.getElementById("btn-start-ollama");

    if (data.running) {
      dot.className = "status-dot online";
      label.textContent = `Ollama running · ${data.model_count} model(s)`;
      startBtn.classList.add("hidden");

      // Update model selector
      const selector = document.getElementById("model-selector");
      selector.innerHTML = "";
      data.models.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m;
        if (m === state.model) opt.selected = true;
        selector.appendChild(opt);
      });
      if (data.models.length > 0 && !data.models.includes(state.model)) {
        state.model = data.models[0];
      }
    } else {
      dot.className = "status-dot offline";
      label.textContent = "Ollama offline";
      startBtn.classList.remove("hidden");
    }
  } catch {
    // Backend not ready yet
  }
}

async function startOllama() {
  const btn = document.getElementById("btn-start-ollama");
  btn.textContent = "Starting…";
  btn.disabled = true;

  try {
    const data = await api("/api/ollama/start", { method: "POST" });
    if (data.ok) {
      toast("Ollama started successfully", "success");
    } else {
      toast(data.message, "error");
    }
    await refreshOllamaStatus();
    await refreshModels();
  } catch (e) {
    toast("Failed to start Ollama", "error");
  }

  btn.disabled = false;
  btn.innerHTML = '<i data-lucide="play"></i> Start Ollama';
  lucide.createIcons();
}


// ═══════════════════════════════════════════════════════════════════════════
// Chat
// ═══════════════════════════════════════════════════════════════════════════

async function sendMessage() {
  const input = document.getElementById("chat-input");
  const question = input.value.trim();
  if (!question) return;

  // Clear input
  input.value = "";
  input.style.height = "auto";
  document.getElementById("btn-send").disabled = true;
  state.isGenerating = true;

  // Hide welcome
  const welcome = document.getElementById("chat-welcome");
  if (welcome) welcome.style.display = "none";

  // Add user message
  addMessage("user", question);

  // Create assistant placeholder
  const assistantEl = addMessage("assistant", "", true);
  const contentEl = assistantEl.querySelector(".message-content");

  try {
    const response = await fetch(`${state.backendUrl}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        model: state.model,
        session_id: state.sessionId,
        filter_files: state.selectedDocs,
      }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullAnswer = "";
    let sources = [];
    let metrics = {};
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // Keep incomplete line in buffer

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6);
        try {
          const event = JSON.parse(jsonStr);

          if (event.type === "sources") {
            sources = event.sources || [];
            renderSourceChips(assistantEl, sources);
          } else if (event.type === "token") {
            fullAnswer += event.token;
            contentEl.textContent = fullAnswer;
            contentEl.classList.add("typing-cursor");
            scrollToBottom();
          } else if (event.type === "done") {
            metrics = event.metrics || {};
            contentEl.classList.remove("typing-cursor");
            renderMetrics(assistantEl, metrics);
            if (state.showDebug) {
              // Could add debug context here
            }
          }
        } catch {
          // Skip malformed JSON
        }
      }
    }

    // Store in local state
    state.messages.push({
      role: "user",
      content: question,
    });
    state.messages.push({
      role: "assistant",
      content: fullAnswer,
      metadata: { sources, metrics },
    });

  } catch (e) {
    contentEl.textContent = `⚠️ Connection error: ${e.message}`;
    contentEl.classList.remove("typing-cursor");
  }

  state.isGenerating = false;
  document.getElementById("btn-send").disabled = !document.getElementById("chat-input").value.trim();
}

function addMessage(role, content, isStreaming = false) {
  const container = document.getElementById("chat-messages");

  const msg = document.createElement("div");
  msg.className = `message ${role}`;

  const avatarIcon = role === "user" ? "user" : "sparkles";
  msg.innerHTML = `
    <div class="message-avatar">
      <i data-lucide="${avatarIcon}"></i>
    </div>
    <div class="message-body">
      <div class="message-content${isStreaming ? " typing-cursor" : ""}">${escapeHtml(content)}</div>
    </div>
  `;

  container.appendChild(msg);
  lucide.createIcons();
  scrollToBottom();
  return msg;
}

function renderSourceChips(msgEl, sources) {
  if (!sources.length) return;
  const body = msgEl.querySelector(".message-body");

  const existing = body.querySelector(".source-chips");
  if (existing) existing.remove();

  const chipsContainer = document.createElement("div");
  chipsContainer.className = "source-chips";

  sources.forEach((s) => {
    const chip = document.createElement("span");
    chip.className = "source-chip";
    chip.innerHTML = `<i data-lucide="file-text"></i> ${escapeHtml(s.file)} p.${s.page}`;
    chipsContainer.appendChild(chip);
  });

  body.appendChild(chipsContainer);
  lucide.createIcons();
}

function renderMetrics(msgEl, metrics) {
  if (!metrics || !metrics.latency_sec) return;
  const body = msgEl.querySelector(".message-body");

  const metricsEl = document.createElement("div");
  metricsEl.className = "message-metrics";
  metricsEl.innerHTML = `
    <span class="metric-item"><i data-lucide="timer"></i> ${metrics.latency_sec}s</span>
    ${metrics.retrieval_sec ? `<span class="metric-item"><i data-lucide="search"></i> ${metrics.retrieval_sec}s retrieval</span>` : ""}
    <span class="metric-item"><i data-lucide="layers"></i> ${metrics.chunks_used} chunks</span>
    <span class="metric-item"><i data-lucide="cpu"></i> ${metrics.model}</span>
  `;
  body.appendChild(metricsEl);
  lucide.createIcons();
}

function scrollToBottom() {
  const container = document.getElementById("chat-messages");
  container.scrollTop = container.scrollHeight;
}


// ═══════════════════════════════════════════════════════════════════════════
// Sessions
// ═══════════════════════════════════════════════════════════════════════════

async function createNewSession() {
  try {
    const data = await api("/api/sessions", { method: "POST" });
    state.sessionId = data.id;
    state.messages = [];
  } catch {
    // Will retry later
  }
}

async function newChat() {
  await createNewSession();

  // Clear chat UI
  const container = document.getElementById("chat-messages");
  container.innerHTML = "";

  // Re-add welcome
  const welcome = document.createElement("div");
  welcome.id = "chat-welcome";
  welcome.className = "chat-welcome";
  welcome.innerHTML = `
    <div class="welcome-icon"><i data-lucide="sparkles"></i></div>
    <h2>Welcome to PrivateGPT</h2>
    <p>Ask anything about your uploaded documents. Everything runs locally on your machine.</p>
    <div class="welcome-chips">
      <button class="chip" onclick="fillQuestion('Summarize the key points of the document')">
        <i data-lucide="list"></i> Summarize key points
      </button>
      <button class="chip" onclick="fillQuestion('What are the main conclusions?')">
        <i data-lucide="target"></i> Main conclusions
      </button>
      <button class="chip" onclick="fillQuestion('Explain the methodology used')">
        <i data-lucide="flask-conical"></i> Explain methodology
      </button>
    </div>
  `;
  container.appendChild(welcome);
  lucide.createIcons();

  navigateTo("chat");
  toast("New conversation started", "info");
}

async function loadSessions() {
  try {
    const data = await api("/api/sessions");
    renderHistory(data.sessions || []);
  } catch {
    // Not ready
  }
}

async function loadSession(id) {
  try {
    const data = await api(`/api/sessions/${id}`);
    state.sessionId = data.id;
    state.messages = data.messages || [];

    // Render messages
    const container = document.getElementById("chat-messages");
    container.innerHTML = "";

    if (state.messages.length === 0) {
      // Show welcome
      container.innerHTML = `
        <div id="chat-welcome" class="chat-welcome">
          <div class="welcome-icon"><i data-lucide="sparkles"></i></div>
          <h2>Welcome to PrivateGPT</h2>
          <p>Ask anything about your uploaded documents.</p>
        </div>`;
    } else {
      state.messages.forEach((msg) => {
        const el = addMessage(msg.role, msg.content);
        if (msg.role === "assistant" && msg.metadata) {
          renderSourceChips(el, msg.metadata.sources || []);
          renderMetrics(el, msg.metadata.metrics || {});
        }
      });
    }

    navigateTo("chat");
    lucide.createIcons();
  } catch (e) {
    toast("Failed to load session", "error");
  }
}

async function deleteSession(id) {
  try {
    await api(`/api/sessions/${id}`, { method: "DELETE" });
    toast("Chat deleted", "info");
    loadSessions();
  } catch {
    toast("Failed to delete", "error");
  }
}

async function exportSession(id) {
  try {
    const data = await api(`/api/sessions/${id}/export`);
    const blob = new Blob([data.text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat_${id}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    toast("Export failed", "error");
  }
}

function renderHistory(sessions) {
  const container = document.getElementById("history-list");

  if (!sessions.length) {
    container.innerHTML = `
      <div class="empty-state">
        <i data-lucide="message-square-dashed"></i>
        <p>No saved chats yet</p>
        <span>Your conversations will appear here</span>
      </div>`;
    lucide.createIcons();
    return;
  }

  container.innerHTML = sessions
    .map(
      (s) => `
    <div class="history-card" onclick="loadSession('${s.id}')">
      <div class="history-icon"><i data-lucide="message-square"></i></div>
      <div class="history-info">
        <div class="history-label">${escapeHtml(s.label)}</div>
        <div class="history-meta">${formatDate(s.created_at)} · ${s.msg_count} messages</div>
      </div>
      <div class="history-actions" onclick="event.stopPropagation()">
        <button class="btn-icon-text" onclick="exportSession('${s.id}')" title="Export">
          <i data-lucide="download"></i>
        </button>
        <button class="btn-danger" onclick="deleteSession('${s.id}')" title="Delete">
          <i data-lucide="trash-2"></i>
        </button>
      </div>
    </div>`
    )
    .join("");

  lucide.createIcons();
}


// ═══════════════════════════════════════════════════════════════════════════
// Documents
// ═══════════════════════════════════════════════════════════════════════════

async function refreshDocuments() {
  try {
    const data = await api("/api/documents");
    renderDocuments(data.documents || []);
    updateDocFilter(data.documents || []);
    document.getElementById("footer-doc-count").textContent = `${(data.documents || []).length} docs indexed`;
  } catch {
    // Not ready
  }
}

function renderDocuments(docs) {
  const container = document.getElementById("documents-list");

  if (!docs.length) {
    container.innerHTML = `
      <div class="empty-state">
        <i data-lucide="file-plus"></i>
        <p>No documents indexed yet</p>
        <span>Upload PDF files to get started</span>
      </div>`;
    lucide.createIcons();
    return;
  }

  container.innerHTML = docs
    .map(
      (d) => `
    <div class="doc-card">
      <div class="doc-icon"><i data-lucide="file-text"></i></div>
      <div class="doc-info">
        <div class="doc-name">${escapeHtml(d.name)}</div>
        <div class="doc-meta">
          <span>${d.pages} pages</span>
          <span>${d.chunks} chunks</span>
          <span>${formatDate(d.indexed_at)}</span>
        </div>
      </div>
      <button class="btn-danger" onclick="deleteDocument('${escapeHtml(d.name)}')" title="Remove">
        <i data-lucide="trash-2"></i>
      </button>
    </div>`
    )
    .join("");

  lucide.createIcons();
}

function updateDocFilter(docs) {
  const container = document.getElementById("doc-filter-list");

  if (!docs.length) {
    container.innerHTML = '<p class="muted-text">No documents indexed</p>';
    state.selectedDocs = [];
    return;
  }

  // Default: select all
  if (!state.selectedDocs.length) {
    state.selectedDocs = docs.map((d) => d.name);
  }

  container.innerHTML = docs
    .map(
      (d) => `
    <label class="filter-item">
      <input type="checkbox" value="${escapeHtml(d.name)}"
             ${state.selectedDocs.includes(d.name) ? "checked" : ""}
             onchange="toggleDocFilter('${escapeHtml(d.name)}', this.checked)" />
      <span class="filter-item-name" title="${escapeHtml(d.name)}">${escapeHtml(d.name)}</span>
    </label>`
    )
    .join("");
}

function toggleDocFilter(name, checked) {
  if (checked && !state.selectedDocs.includes(name)) {
    state.selectedDocs.push(name);
  } else if (!checked) {
    state.selectedDocs = state.selectedDocs.filter((n) => n !== name);
  }
}

async function uploadDocuments() {
  let files;

  if (window.electronAPI) {
    // Electron native file dialog
    const paths = await window.electronAPI.selectFiles();
    if (!paths || !paths.length) return;

    // Read files and create form data
    const formData = new FormData();
    for (const filePath of paths) {
      const response = await fetch(`file://${filePath}`);
      const blob = await response.blob();
      const name = filePath.split(/[\\/]/).pop();
      formData.append("files", blob, name);
    }
    
    await doUpload(formData);
  } else {
    // Browser fallback
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".pdf";
    input.multiple = true;
    input.onchange = async () => {
      if (!input.files.length) return;
      const formData = new FormData();
      for (const file of input.files) {
        formData.append("files", file);
      }
      await doUpload(formData);
    };
    input.click();
  }
}

async function doUpload(formData) {
  const progressContainer = document.getElementById("upload-progress");
  const progressFill = document.getElementById("upload-progress-fill");
  const progressText = document.getElementById("upload-progress-text");

  progressContainer.classList.remove("hidden");
  progressFill.style.width = "20%";
  progressText.textContent = "Uploading & indexing documents…";

  try {
    const response = await fetch(`${state.backendUrl}/api/documents/upload`, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();

    progressFill.style.width = "100%";

    if (result.ingested && result.ingested.length) {
      toast(`Indexed: ${result.ingested.join(", ")}`, "success");
    }
    if (result.skipped && result.skipped.length) {
      toast(`Skipped (unchanged): ${result.skipped.join(", ")}`, "info");
    }
    if (result.errors) {
      result.errors.forEach((e) => toast(`${e.file}: ${e.error}`, "error"));
    }

    await refreshDocuments();
    await refreshOllamaStatus();
  } catch (e) {
    toast(`Upload failed: ${e.message}`, "error");
  }

  setTimeout(() => {
    progressContainer.classList.add("hidden");
    progressFill.style.width = "0%";
  }, 1000);
}

async function deleteDocument(name) {
  try {
    await api(`/api/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
    toast(`Removed "${name}". Rebuild index to apply changes.`, "info");
    refreshDocuments();
  } catch {
    toast("Failed to delete document", "error");
  }
}

async function rebuildIndex() {
  const btn = document.getElementById("btn-rebuild-index");
  btn.disabled = true;
  btn.innerHTML = '<i data-lucide="loader"></i><span>Rebuilding…</span>';
  lucide.createIcons();

  try {
    const result = await api("/api/documents/rebuild", { method: "POST" });
    toast(`Rebuilt: ${result.total_chunks} chunks across ${result.total_docs} docs`, "success");
    await refreshDocuments();
  } catch (e) {
    toast("Rebuild failed", "error");
  }

  btn.disabled = false;
  btn.innerHTML = '<i data-lucide="refresh-cw"></i><span>Rebuild Index</span>';
  lucide.createIcons();
}


// ═══════════════════════════════════════════════════════════════════════════
// Models
// ═══════════════════════════════════════════════════════════════════════════

async function refreshModels() {
  try {
    // Downloaded models
    const modelsData = await api("/api/ollama/models");
    renderDownloadedModels(modelsData.models || []);

    // Recommended models
    const recData = await api("/api/ollama/recommended");
    renderRecommendedModels(recData.models || []);
  } catch {
    // Not ready
  }
}

function renderDownloadedModels(models) {
  const container = document.getElementById("downloaded-models");

  if (!models.length) {
    container.innerHTML = `
      <div class="empty-state small">
        <i data-lucide="package-open"></i>
        <p>No models downloaded</p>
      </div>`;
    lucide.createIcons();
    return;
  }

  container.innerHTML = models
    .map(
      (m) => `
    <div class="model-card">
      <div class="model-icon downloaded"><i data-lucide="check-circle"></i></div>
      <div class="model-info">
        <div class="model-name">${escapeHtml(m.name)}</div>
        <div class="model-badges">
          <span class="badge badge-green">${m.parameters}</span>
          <span class="badge badge-blue">${m.quantization}</span>
        </div>
      </div>
      <div class="model-actions">
        <button class="btn-danger" onclick="deleteModel('${escapeHtml(m.name)}')" title="Delete">
          <i data-lucide="trash-2"></i> Delete
        </button>
      </div>
    </div>`
    )
    .join("");

  lucide.createIcons();
}

function renderRecommendedModels(models) {
  const container = document.getElementById("recommended-models");

  container.innerHTML = models
    .map(
      (m) => `
    <div class="model-card">
      <div class="model-icon ${m.available ? "downloaded" : "available"}">
        <i data-lucide="${m.available ? "check-circle" : "cloud-download"}"></i>
      </div>
      <div class="model-info">
        <div class="model-name">
          ${escapeHtml(m.label)}
          ${m.recommended ? '<span class="badge badge-recommended">Recommended</span>' : ""}
        </div>
        <div class="model-desc">${escapeHtml(m.description)}</div>
        <div class="model-badges">
          <span class="badge badge-yellow">${m.ram}</span>
          ${m.available ? '<span class="badge badge-green">Downloaded</span>' : ""}
        </div>
      </div>
      <div class="model-actions">
        ${
          m.available
            ? '<span class="badge badge-green">Ready ✓</span>'
            : `<button class="btn-accent" onclick="pullModel('${escapeHtml(m.name)}')">
                <i data-lucide="download"></i> Pull
              </button>`
        }
      </div>
    </div>`
    )
    .join("");

  lucide.createIcons();
}

async function pullModel(name) {
  toast(`Pulling ${name}… This may take a few minutes.`, "info");

  try {
    const data = await api("/api/ollama/pull/sync", {
      method: "POST",
      body: JSON.stringify({ name }),
    });

    if (data.ok) {
      toast(data.message, "success");
    } else {
      toast(data.message, "error");
    }

    await refreshModels();
    await refreshOllamaStatus();
  } catch (e) {
    toast(`Pull failed: ${e.message}`, "error");
  }
}

async function pullCustomModel() {
  const input = document.getElementById("custom-model-input");
  const name = input.value.trim();
  if (!name) return;

  input.value = "";
  await pullModel(name);
}

async function deleteModel(name) {
  try {
    const data = await api(`/api/ollama/models/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (data.ok) {
      toast(data.message, "success");
    } else {
      toast(data.message, "error");
    }
    await refreshModels();
    await refreshOllamaStatus();
  } catch {
    toast("Failed to delete model", "error");
  }
}


// ═══════════════════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════════════════

async function api(path, opts = {}) {
  const url = `${state.backendUrl}${path}`;
  const defaults = {
    headers: { "Content-Type": "application/json" },
  };

  // Don't set Content-Type for FormData
  if (opts.body instanceof FormData) {
    delete defaults.headers["Content-Type"];
  }

  const response = await fetch(url, { ...defaults, ...opts });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso.slice(0, 16);
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// Fill chat input from welcome chips
function fillQuestion(text) {
  const input = document.getElementById("chat-input");
  input.value = text;
  input.dispatchEvent(new Event("input"));
  input.focus();
}


// ═══════════════════════════════════════════════════════════════════════════
// Toast Notification System
// ═══════════════════════════════════════════════════════════════════════════

function toast(message, type = "info") {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const icons = {
    success: "check-circle",
    error: "alert-circle",
    info: "info",
  };

  const t = document.createElement("div");
  t.className = `toast toast-${type}`;
  t.innerHTML = `<i data-lucide="${icons[type] || "info"}"></i> ${escapeHtml(message)}`;
  container.appendChild(t);
  lucide.createIcons();

  setTimeout(() => {
    t.classList.add("toast-out");
    setTimeout(() => t.remove(), 200);
  }, 4000);
}
