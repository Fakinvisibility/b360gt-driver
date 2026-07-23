const $ = (selector) => document.querySelector(selector);

const fileInput = $("#fileInput");
const dropZone = $("#dropZone");
const imagePreview = $("#imagePreview");
const emptyPreview = $("#emptyPreview");
const playbackEnabled = $("#playbackEnabled");
const probeButton = $("#probeButton");
const libraryList = $("#libraryList");
const libraryCount = $("#libraryCount");

let uploadPromise = null;
let previewUrl = "";
let restoredMedia = "";
let selectedLibraryId = "";
let libraryItems = [];
let lastStatus = { state: "idle" };
let previewRevision = 0;
let monitorConfigLoaded = false;
let currentMonitorConfig = null;
let playbackUpdatePending = false;
let mediaSelectionRevision = 0;
let mediaSelectionPending = false;
let mediaSelectionTimer = null;
let mediaSelectionInFlight = false;
let pendingMediaSelection = null;
let latestSelectionRevision = 0;
const MEDIA_SELECTION_DEBOUNCE_MS = 140;

function setMessage(text, type = "") {
  const node = $("#message");
  node.textContent = text;
  node.className = type;
}

function stateLabel(state) {
  return {
    idle: "未显示内容",
    starting: "正在初始化",
    playing: "媒体显示中",
    stopping: "正在停止",
    error: "发生错误",
  }[state] || state;
}

function kindLabel(kind) {
  return {
    image: "静态图片",
    animated_image: "动态图片",
    video: "视频",
  }[kind] || "自动识别";
}

function shortKind(kind) {
  return {
    image: "IMAGE",
    animated_image: "GIF",
    video: "VIDEO",
  }[kind] || "MEDIA";
}

function formatSize(value) {
  if (value < 1024 * 1024) return `${Math.max(1, value / 1024).toFixed(0)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function applyMediaInfo(info) {
  if (!info) return;
  $("#mediaType").textContent = kindLabel(info.kind);
  const resolution = $("#resolution");
  resolution.textContent = `${info.width} × ${info.height} → 480 × 480`;
  resolution.classList.remove("hidden");
}

function showEmptyPreview(text = "请上传媒体文件") {
  imagePreview.removeAttribute("src");
  imagePreview.style.display = "none";
  emptyPreview.querySelector("span").textContent = text;
  emptyPreview.style.display = "grid";
}

function showSelectedPreview(info) {
  if (!info) {
    showEmptyPreview();
    return;
  }

  const revision = ++previewRevision;
  emptyPreview.style.display = "none";
  imagePreview.style.display = "block";
  imagePreview.onerror = () => {
    if (revision !== previewRevision) return;
    showEmptyPreview("预览加载失败");
  };
  imagePreview.src = info.kind === "video"
    ? `/api/preview-stream?v=${revision}-${Date.now()}`
    : info.kind === "image"
      ? `/api/preview?v=${revision}-${Date.now()}`
      : `/api/media?v=${revision}-${Date.now()}`;
}

function applySelectedStatus(status) {
  if (Number.isFinite(status.selection_revision)) {
    latestSelectionRevision = Math.max(
      latestSelectionRevision,
      status.selection_revision,
    );
  }
  lastStatus = status;
  restoredMedia = status.media || "";
  selectedLibraryId = status.library_id || "";

  if (!status.media) {
    $("#mediaName").textContent = "尚未选择媒体";
    $("#mediaType").textContent = "—";
    $("#resolution").classList.add("hidden");
    showEmptyPreview();
    renderLibrary();
    return;
  }

  $("#mediaName").textContent = status.media_name || "已选择媒体";
  applyMediaInfo(status.media_info);
  showSelectedPreview(status.media_info);
  renderLibrary();
}

function renderLibrary() {
  libraryList.replaceChildren();
  libraryCount.textContent = `${libraryItems.length} 项`;

  if (!libraryItems.length) {
    const empty = document.createElement("div");
    empty.className = "library-empty";
    empty.textContent = "媒体库为空，上传后会永久保存在这里";
    libraryList.append(empty);
    return;
  }

  for (const item of libraryItems) {
    const card = document.createElement("div");
    card.className = "library-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    if (item.id === selectedLibraryId) card.classList.add("selected");
    card.dataset.id = item.id;
    card.title = `切换到 ${item.name}`;

    const thumb = document.createElement("img");
    thumb.src = `/api/library/thumbnail?id=${encodeURIComponent(item.id)}`;
    thumb.alt = "";

    const details = document.createElement("span");
    details.className = "library-details";
    const name = document.createElement("strong");
    name.textContent = item.name;
    const meta = document.createElement("small");
    meta.textContent = `${shortKind(item.media_info.kind)} · ${formatSize(item.size)}`;
    details.append(name, meta);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "delete-media";
    remove.textContent = "×";
    remove.title = `删除 ${item.name}`;
    remove.setAttribute("aria-label", `删除 ${item.name}`);
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteLibraryItem(item);
    });

    card.append(thumb, details, remove);
    card.addEventListener("click", () => selectLibraryItem(item));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectLibraryItem(item);
      }
    });
    libraryList.append(card);
  }
}

async function refreshLibrary() {
  const result = await api("/api/library");
  libraryItems = result.items;
  if (!selectedLibraryId) selectedLibraryId = result.selected_id || "";
  renderLibrary();
}

function selectLibraryItem(item) {
  if (item.id === selectedLibraryId) return;
  const revision = ++mediaSelectionRevision;
  mediaSelectionPending = true;
  selectedLibraryId = item.id;
  $("#mediaName").textContent = item.name;
  applyMediaInfo(item.media_info);
  const previewRevisionForSelection = ++previewRevision;
  emptyPreview.style.display = "none";
  imagePreview.style.display = "block";
  imagePreview.onerror = () => {
    if (previewRevisionForSelection !== previewRevision) return;
    showEmptyPreview("预览加载失败");
  };
  imagePreview.src =
    `/api/library/thumbnail?id=${encodeURIComponent(item.id)}` +
    `&v=${previewRevisionForSelection}`;
  renderLibrary();
  setMessage(`正在切换到 ${item.name}…`);

  pendingMediaSelection = { item, revision };
  if (mediaSelectionTimer !== null) {
    window.clearTimeout(mediaSelectionTimer);
  }
  mediaSelectionTimer = window.setTimeout(
    commitLatestMediaSelection,
    MEDIA_SELECTION_DEBOUNCE_MS,
  );
}

async function commitLatestMediaSelection() {
  mediaSelectionTimer = null;
  if (mediaSelectionInFlight || pendingMediaSelection === null) return;

  const { item, revision } = pendingMediaSelection;
  pendingMediaSelection = null;
  mediaSelectionInFlight = true;
  try {
    const result = await api("/api/library/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: item.id }),
    });
    if (revision !== mediaSelectionRevision) return;
    applySelectedStatus(result.media);
    renderLibrary();
    setMessage(
      result.resumed ? "已切换媒体，正在更新水冷屏…" : "媒体切换中",
      "success",
    );
  } catch (error) {
    if (revision !== mediaSelectionRevision) return;
    const status = await api("/api/status").catch(() => null);
    if (status) applySelectedStatus(status);
    setMessage(error.message, "error");
  } finally {
    mediaSelectionInFlight = false;
    if (pendingMediaSelection !== null) {
      if (mediaSelectionTimer !== null) {
        window.clearTimeout(mediaSelectionTimer);
      }
      mediaSelectionTimer = window.setTimeout(commitLatestMediaSelection, 0);
    } else if (revision === mediaSelectionRevision) {
      mediaSelectionPending = false;
    }
  }
}

async function deleteLibraryItem(item) {
  if (!window.confirm(`确定永久删除“${item.name}”吗？此操作无法撤销。`)) return;
  try {
    await api("/api/library/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: item.id }),
    });
    if (selectedLibraryId === item.id) {
      selectedLibraryId = "";
      restoredMedia = "";
      applySelectedStatus({
        state: "idle",
        media: null,
        media_name: null,
        media_info: null,
        library_id: null,
      });
    }
    await refreshLibrary();
    setMessage(`已删除 ${item.name}`);
  } catch (error) {
    setMessage(error.message, "error");
  }
}

async function selectFile(file) {
  restoredMedia = "";
  selectedLibraryId = "";
  $("#mediaName").textContent = file.name;
  $("#mediaType").textContent = "正在识别…";

  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  if (file.type.startsWith("video/")) {
    showEmptyPreview("正在上传并准备动态预览…");
  } else {
    emptyPreview.style.display = "none";
    imagePreview.src = previewUrl;
    imagePreview.style.display = "block";
  }
  setMessage(`正在保存到媒体库：${file.name}…`);

  const currentUpload = api("/api/upload", {
    method: "POST",
    headers: { "X-Filename": encodeURIComponent(file.name) },
    body: file,
  }).then(async (result) => {
    selectedLibraryId = result.item.id;
    applySelectedStatus(result.media);
    await refreshLibrary();
    setMessage(`已保存到媒体库：${file.name}`, "success");
    return result;
  }).catch((error) => {
    setMessage(error.message, "error");
    throw error;
  });
  uploadPromise = currentUpload;

  try {
    await currentUpload;
  } catch {
    // The visible error message is set above.
  } finally {
    if (uploadPromise === currentUpload) uploadPromise = null;
  }
}

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) selectFile(fileInput.files[0]);
  fileInput.value = "";
});

["dragenter", "dragover"].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});
dropZone.addEventListener("drop", (event) => {
  if (event.dataTransfer.files[0]) selectFile(event.dataTransfer.files[0]);
});

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function formatMetric(value, suffix) {
  return value == null ? "N/A" : `${Math.round(value)}${suffix}`;
}

function formatRate(value) {
  if (value == null) return "N/A";
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)}M/s`;
  return `${Math.round(value / 1024)}K/s`;
}

function renderScreenOverlay(config, telemetry) {
  const overlay = $("#screenOverlay");
  currentMonitorConfig = config;
  overlay.className = `screen-overlay ${config.position}`;
  if (!config.enabled) {
    overlay.replaceChildren();
    overlay.style.display = "none";
    return;
  }

  const lines = [
    `CPU ${formatMetric(telemetry.cpu_percent, "%")}`,
    `GPU ${formatMetric(telemetry.gpu_percent, "%")}  ${formatMetric(telemetry.gpu_temperature_c, "°C")}`,
    `RAM ${formatMetric(telemetry.memory_percent, "%")}  DISK ${formatMetric(telemetry.disk_percent, "%")}`,
    `NET ↓${formatRate(telemetry.network_down_bps)} ↑${formatRate(telemetry.network_up_bps)}`,
  ];
  overlay.replaceChildren(...lines.map((line) => {
    const row = document.createElement("div");
    row.textContent = line;
    return row;
  }));
  overlay.style.display = "block";
}

function updateMonitorHint(telemetry) {
  const hint = $("#monitorHint");
  hint.textContent = "仅采集操作系统及显卡厂商只读接口数据";
  hint.className = "online";
}

async function refreshMonitor() {
  try {
    const result = await api("/api/monitor");
    const config = result.config;
    const telemetry = result.telemetry;
    if (!monitorConfigLoaded) {
      $("#overlayEnabled").checked = config.enabled;
      $("#gpuMonitoringEnabled").checked = config.gpu_enabled;
      $("#overlayPosition").value = config.position;
      $("#overlayRefresh").value = String(config.refresh_seconds);
      monitorConfigLoaded = true;
    }
    updateMonitorHint(telemetry);
    renderScreenOverlay(config, telemetry);
  } catch {
    // The next successful poll restores the overlay and source status.
  }
}

async function saveMonitorConfig() {
  try {
    const result = await api("/api/monitor/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: $("#overlayEnabled").checked,
        gpu_enabled: $("#gpuMonitoringEnabled").checked,
        position: $("#overlayPosition").value,
        refresh_seconds: Number($("#overlayRefresh").value),
      }),
    });
    currentMonitorConfig = result.config;
    await refreshMonitor();
    setMessage("监控叠加设置已应用", "success");
  } catch (error) {
    setMessage(error.message, "error");
  }
}

["#overlayEnabled", "#gpuMonitoringEnabled", "#overlayPosition", "#overlayRefresh"]
  .forEach((selector) => $(selector).addEventListener("change", saveMonitorConfig));

playbackEnabled.addEventListener("change", async () => {
  const enabled = playbackEnabled.checked;
  playbackUpdatePending = true;
  try {
    playbackEnabled.disabled = true;
    if (uploadPromise) await uploadPromise;
    if (enabled && !selectedLibraryId) throw new Error("请先从媒体库选择或上传文件");
    await api("/api/playback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    setMessage(enabled ? "屏幕正在初始化，请稍候…" : "正在安全停止显示…", enabled ? "success" : "");
  } catch (error) {
    playbackEnabled.checked = !enabled;
    setMessage(error.message, "error");
  } finally {
    playbackUpdatePending = false;
    playbackEnabled.disabled = false;
  }
});

probeButton.addEventListener("click", async () => {
  const dot = $("#deviceDot");
  const text = $("#deviceText");
  const startedAt = performance.now();
  const minimumFeedbackMs = 450;
  let probeError = null;

  probeButton.disabled = true;
  probeButton.title = "正在检测水冷屏";
  probeButton.setAttribute("aria-busy", "true");
  dot.className = "status-dot detecting";
  text.textContent = "正在检测…";
  try {
    await api("/api/probe", { method: "POST" });
  } catch (error) {
    probeError = error;
  }

  const remaining = minimumFeedbackMs - (performance.now() - startedAt);
  if (remaining > 0) {
    await new Promise((resolve) => window.setTimeout(resolve, remaining));
  }

  probeButton.disabled = false;
  probeButton.title = "点击重新检测";
  probeButton.removeAttribute("aria-busy");
  if (!probeError) {
    dot.className = "status-dot online";
    text.textContent = "水冷屏已连接";
    setMessage("已找到 B360GT USB 屏幕", "success");
  } else {
    dot.className = "status-dot error";
    text.textContent = "未找到设备";
    setMessage(probeError.message, "error");
  }
});

function restorePreview(status) {
  if (mediaSelectionPending) return;
  if (
    Number.isFinite(status.selection_revision) &&
    status.selection_revision < latestSelectionRevision
  ) return;
  if (!status.media) {
    if (restoredMedia) applySelectedStatus(status);
    return;
  }
  if (status.media === restoredMedia) return;
  applySelectedStatus(status);
}

async function pollStatus() {
  try {
    const status = await api("/api/status");
    lastStatus = status;
    const channelWarning = $("#channelWarning");
    const conflicts = status.channel_conflicts || [];
    channelWarning.textContent = conflicts.length
      ? `可能占用显示通道：${conflicts.join("、")}，请先关闭后再播放`
      : "显示通道为独占资源，请勿同时运行 Myth.Cool 或多个 B360GT 后端";
    channelWarning.classList.toggle("active", conflicts.length > 0);
    restorePreview(status);
    $("#playbackState").textContent = stateLabel(status.state);
    if (!playbackUpdatePending) {
      playbackEnabled.checked = Boolean(status.enabled);
    }
    if (status.error) setMessage(status.error, "error");
    if (status.state === "playing") {
      setMessage("正在向水冷屏持续发送画面", "success");
    }
    if (status.state === "idle" && status.media && !status.error) {
      setMessage("媒体已就绪");
    }
  } catch (error) {
    setMessage(`控制台连接异常：${error.message}`, "error");
  } finally {
    window.setTimeout(pollStatus, 500);
  }
}

async function initialize() {
  await refreshLibrary().catch((error) => setMessage(error.message, "error"));
  probeButton.click();
  refreshMonitor();
  window.setInterval(refreshMonitor, 2000);
  pollStatus();
}

initialize();
