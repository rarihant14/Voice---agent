const API = "";
const SESSION_KEY = "voxa-session-id";

let mediaRecorder = null;
let recordedChunks = [];
let recordingTimer = null;
let recordingSeconds = 0;
let currentAudioBlob = null;
let isRecording = false;

const recordBtn = document.getElementById("recordBtn");
const recordLabel = document.getElementById("recordLabel");
const recordTimerEl = document.getElementById("recordTimer");
const waveformBars = document.getElementById("waveformBars");
const processBtn = document.getElementById("processBtn");
const audioFile = document.getElementById("audioFile");
const uploadZone = document.getElementById("uploadZone");
const uploadName = document.getElementById("uploadName");
const textInput = document.getElementById("textInput");
const textSubmitBtn = document.getElementById("textSubmitBtn");
const loadingOverlay = document.getElementById("loadingOverlay");
const loadingText = document.getElementById("loadingText");
const loadingSteps = document.getElementById("loadingSteps");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const emptyState = document.getElementById("emptyState");
const memoryPanel = document.getElementById("memoryPanel");
const memoryList = document.getElementById("memoryList");
const memoryCountTag = document.getElementById("memoryCountTag");

let sessionId = getOrCreateSessionId();

function getOrCreateSessionId() {
  const existing = sessionStorage.getItem(SESSION_KEY);
  if (existing) return existing;

  const created = `voxa-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  sessionStorage.setItem(SESSION_KEY, created);
  return created;
}

function updateClock() {
  const now = new Date();
  document.getElementById("clock").textContent = now.toLocaleTimeString("en-GB", { hour12: false });
}

setInterval(updateClock, 1000);
updateClock();

async function checkHealth() {
  try {
    const response = await fetch(`${API}/health`, {
      headers: { "X-Session-ID": sessionId },
    });
    const data = await response.json();
    statusDot.className = "status-dot online";
    statusText.textContent = data.groq_configured ? "ONLINE - GROQ READY" : "ONLINE - NO API KEY";
  } catch {
    statusDot.className = "status-dot error";
    statusText.textContent = "SERVER OFFLINE";
  }
}

function buildWaveform() {
  waveformBars.innerHTML = "";
  for (let i = 0; i < 32; i += 1) {
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.cssText = `--h:${6 + Math.random() * 28}px; animation-delay:${(i * 0.05).toFixed(2)}s;`;
    waveformBars.appendChild(bar);
  }
}

function showWaveform(active) {
  waveformBars.style.display = active ? "flex" : "none";
  if (active) buildWaveform();
}

showWaveform(false);

recordBtn.addEventListener("click", async () => {
  if (isRecording) {
    stopRecording();
  } else {
    await startRecording();
  }
});

audioFile.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  currentAudioBlob = file;
  uploadName.textContent = `SELECTED ${file.name}`;
  processBtn.disabled = false;
});

uploadZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  uploadZone.classList.add("drag-over");
});

uploadZone.addEventListener("dragleave", () => {
  uploadZone.classList.remove("drag-over");
});

uploadZone.addEventListener("drop", (event) => {
  event.preventDefault();
  uploadZone.classList.remove("drag-over");
  const file = event.dataTransfer.files[0];
  if (!file) return;
  currentAudioBlob = file;
  uploadName.textContent = `SELECTED ${file.name}`;
  processBtn.disabled = false;
});

textSubmitBtn.addEventListener("click", async () => {
  const text = textInput.value.trim();
  if (!text) return;
  await runTextPipeline(text);
});

textInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    textSubmitBtn.click();
  }
});

processBtn.addEventListener("click", async () => {
  if (!currentAudioBlob) return;
  await runAudioPipeline(currentAudioBlob);
});

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordedChunks = [];
    mediaRecorder = new MediaRecorder(stream, { mimeType: getSupportedMimeType() });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data);
    };

    mediaRecorder.onstop = () => {
      const blob = new Blob(recordedChunks, { type: mediaRecorder.mimeType });
      currentAudioBlob = blob;
      audioFile.value = "";
      uploadName.textContent = `RECORDED ${formatTime(recordingSeconds)}`;
      processBtn.disabled = false;
      stream.getTracks().forEach((track) => track.stop());
    };

    mediaRecorder.start(100);
    isRecording = true;
    recordBtn.classList.add("recording");
    recordLabel.textContent = "CLICK TO STOP";
    showWaveform(true);

    recordingSeconds = 0;
    recordTimerEl.textContent = "00:00";
    recordingTimer = setInterval(() => {
      recordingSeconds += 1;
      recordTimerEl.textContent = formatTime(recordingSeconds);
    }, 1000);
  } catch {
    alert("Microphone access denied. Please allow microphone access and try again.");
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  isRecording = false;
  recordBtn.classList.remove("recording");
  recordLabel.textContent = "RECORDING SAVED - CLICK PROCESS";
  showWaveform(false);
  clearInterval(recordingTimer);
}

function getSupportedMimeType() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  return types.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainder = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

async function runAudioPipeline(blob) {
  showLoading("TRANSCRIBING AUDIO...");
  const formData = new FormData();
  formData.append("file", blob, blob.name || "recording.webm");

  try {
    const response = await fetch(`${API}/process/audio`, {
      method: "POST",
      headers: { "X-Session-ID": sessionId },
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Server error");
    }
    const data = await response.json();
    applySessionId(data.session_id);
    hideLoading();
    renderResults(data);
    loadOutputFiles();
  } catch (error) {
    hideLoading();
    showError(error.message);
  }
}

async function runTextPipeline(text) {
  showLoading("PROCESSING TEXT...");
  try {
    const response = await fetch(`${API}/process/text`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Session-ID": sessionId,
      },
      body: JSON.stringify({ text, session_id: sessionId }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Server error");
    }
    const data = await response.json();
    applySessionId(data.session_id);
    hideLoading();
    renderResults(data);
    loadOutputFiles();
  } catch (error) {
    hideLoading();
    showError(error.message);
  }
}

function applySessionId(nextSessionId) {
  if (!nextSessionId) return;
  sessionId = nextSessionId;
  sessionStorage.setItem(SESSION_KEY, nextSessionId);
}

function renderResults(data) {
  emptyState.style.display = "none";

  const pipelinePanel = document.getElementById("pipelinePanel");
  const stepsList = document.getElementById("stepsList");
  pipelinePanel.style.display = "block";
  stepsList.innerHTML = "";
  (data.steps || []).forEach((step, index) => {
    setTimeout(() => {
      const element = document.createElement("div");
      element.className = "step-item done";
      element.textContent = step;
      stepsList.appendChild(element);
    }, index * 80);
  });

  const transPanel = document.getElementById("transcriptionPanel");
  const transText = document.getElementById("transcriptionText");
  const sttTag = document.getElementById("sttMethodTag");
  transPanel.style.display = "block";
  transText.textContent = data.transcription || "(empty)";
  sttTag.textContent = data.stt_method || "direct";

  const intentPanel = document.getElementById("intentPanel");
  const intentBadge = document.getElementById("intentBadge");
  const confidenceFill = document.getElementById("confidenceFill");
  const confidenceVal = document.getElementById("confidenceVal");
  const reasoningText = document.getElementById("reasoningText");
  const entitiesGrid = document.getElementById("entitiesGrid");

  intentPanel.style.display = "block";
  intentBadge.textContent = formatIntent(data.intent);
  intentBadge.className = `intent-badge badge-${data.intent}`;

  const confidence = Math.round((data.confidence || 0) * 100);
  setTimeout(() => {
    confidenceFill.style.width = `${confidence}%`;
  }, 100);
  confidenceVal.textContent = `${confidence}%`;
  reasoningText.textContent = data.reasoning || "-";

  entitiesGrid.innerHTML = "";
  Object.entries(data.entities || {}).forEach(([key, value]) => {
    if (!value) return;
    const chip = document.createElement("div");
    chip.className = "entity-chip";
    chip.innerHTML = `<span class="entity-key">${escapeHtml(key)}</span><span class="entity-val">${escapeHtml(String(value))}</span>`;
    entitiesGrid.appendChild(chip);
  });

  const outputPanel = document.getElementById("outputPanel");
  const outputContent = document.getElementById("outputContent");
  const actionTag = document.getElementById("actionTag");
  const outputFile = document.getElementById("outputFile");
  const outputFileLink = document.getElementById("outputFileLink");
  const outputFileName = document.getElementById("outputFileName");

  outputPanel.style.display = "block";
  outputContent.textContent = data.output_content || "(no output)";
  actionTag.textContent = data.action_taken || "DONE";

  const existingError = outputPanel.querySelector(".output-error");
  if (existingError) existingError.remove();

  if (data.output_path) {
    const fileName = data.output_path.split("/").pop().split("\\").pop();
    outputFile.style.display = "block";
    outputFileLink.href = `/output/${fileName}`;
    outputFileName.textContent = fileName;
  } else {
    outputFile.style.display = "none";
  }

  if (data.error) {
    const errorElement = document.createElement("div");
    errorElement.className = "output-error";
    errorElement.style.cssText = "color:#ff4444;font-family:var(--font-mono);font-size:0.7rem;padding:8px 16px;";
    errorElement.textContent = `WARNING ${data.error}`;
    outputPanel.appendChild(errorElement);
  }

  renderMemory(data.history || []);
}

function renderMemory(history) {
  memoryPanel.style.display = "block";
  memoryCountTag.textContent = `${history.length} ITEMS`;
  memoryList.innerHTML = "";

  if (!history.length) {
    memoryList.innerHTML = '<div class="no-files">NO SESSION MEMORY YET</div>';
    return;
  }

  [...history].reverse().forEach((item) => {
    const element = document.createElement("div");
    element.className = "memory-item";
    element.innerHTML = `
      <div class="memory-item-header">
        <span class="memory-intent">${escapeHtml(formatIntent(item.intent || "general_chat"))}</span>
        <span class="memory-method">${escapeHtml(item.stt_method || "direct")}</span>
      </div>
      <div class="memory-text">${escapeHtml(item.input || "(empty input)")}</div>
      <div class="memory-output">${escapeHtml(item.action_taken || item.output_preview || "(no action)")}</div>
    `;
    memoryList.appendChild(element);
  });
}

function formatIntent(intent) {
  const labels = {
    write_code: "WRITE CODE",
    create_file: "CREATE FILE",
    summarize_text: "SUMMARIZE",
    general_chat: "GENERAL CHAT",
  };
  return labels[intent] || String(intent || "UNKNOWN").toUpperCase();
}

async function loadOutputFiles() {
  try {
    const response = await fetch(`${API}/output/files`);
    const data = await response.json();
    const list = document.getElementById("filesList");

    if (!data.files || !data.files.length) {
      list.innerHTML = '<div class="no-files">NO FILES GENERATED YET</div>';
      return;
    }

    list.innerHTML = "";
    data.files.forEach((file) => {
      const link = document.createElement("a");
      link.href = file.path;
      link.target = "_blank";
      link.className = "file-item";
      link.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <span>${escapeHtml(file.name)}</span>
        <span class="file-size">${formatSize(file.size)}</span>
      `;
      list.appendChild(link);
    });
  } catch {
    return;
  }
}

async function loadSessionMemory() {
  try {
    const response = await fetch(`${API}/session/history`, {
      headers: { "X-Session-ID": sessionId },
    });
    const data = await response.json();
    applySessionId(data.session_id);
    renderMemory(data.history || []);
  } catch {
    return;
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function showLoading(text) {
  statusDot.className = "status-dot processing";
  statusText.textContent = "PROCESSING";
  loadingText.textContent = text;
  loadingSteps.innerHTML = "";
  loadingOverlay.style.display = "flex";

  ["STT - TRANSCRIBING", "LLM - CLASSIFYING INTENT", "AGENT - EXECUTING TOOLS"].forEach((step, index) => {
    setTimeout(() => {
      const element = document.createElement("div");
      element.textContent = `[ ${step} ]`;
      loadingSteps.appendChild(element);
    }, index * 800);
  });
}

function hideLoading() {
  loadingOverlay.style.display = "none";
  statusDot.className = "status-dot online";
  statusText.textContent = "PIPELINE COMPLETE";
}

function showError(message) {
  statusDot.className = "status-dot error";
  statusText.textContent = "ERROR";
  alert(`Error: ${message}`);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

document.getElementById("refreshFiles").addEventListener("click", loadOutputFiles);

checkHealth();
loadOutputFiles();
loadSessionMemory();
