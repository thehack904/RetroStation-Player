"use strict";

const list = document.getElementById("channel-list");
const search = document.getElementById("search");
const message = document.getElementById("message");
const currentChannel = document.getElementById("current-channel");
const playerState = document.getElementById("player-state");
const setupPanel = document.getElementById("setup-panel");
const settingsButton = document.getElementById("settings-button");
const setupMessage = document.getElementById("setup-message");
const aboutPanel = document.getElementById("about-panel");
const aboutButton = document.getElementById("about-button");
const volumeInput = document.getElementById("volume-input");
const volumeValue = document.getElementById("volume-value");
const muteButton = document.getElementById("mute-button");
const audioControlNote = document.getElementById("audio-control-note");
let channels = [];
let setupAutoShown = false;
let savedDefaultChannelId = "";
let displayOptions = { resolutions: [], overscan_presets: [], backend: "mpv", display_mode: "desktop", hdmi_underscan_control_available: false };
let hdmiUnderscanSaveTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed (${response.status})`);
  }
  return payload;
}

function renderChannels() {
  const query = search.value.trim().toLowerCase();
  const visible = channels.filter((channel) =>
    `${channel.number} ${channel.name} ${channel.group}`.toLowerCase().includes(query)
  );

  list.replaceChildren();
  if (!visible.length) {
    list.innerHTML = '<p class="empty">No channels found.</p>';
    return;
  }

  for (const channel of visible) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "channel";
    button.dataset.channelId = channel.id;

    if (channel.logo) {
      const img = document.createElement("img");
      img.src = channel.logo;
      img.alt = "";
      img.loading = "lazy";
      button.appendChild(img);
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "logo-placeholder";
      placeholder.textContent = channel.number;
      button.appendChild(placeholder);
    }

    const text = document.createElement("span");
    text.className = "channel-text";
    text.innerHTML = `<strong>${escapeHtml(channel.number)} · ${escapeHtml(channel.name)}</strong><small>${escapeHtml(channel.group || "Uncategorized")}</small>`;
    button.appendChild(text);
    button.addEventListener("click", () => playChannel(channel.id));
    list.appendChild(button);
  }
  populateDefaultChannelSelect(savedDefaultChannelId);
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value ?? "";
  return element.innerHTML;
}

function populateDefaultChannelSelect(selectedId) {
  const select = document.getElementById("default-channel-input");
  if (!select) return;
  const current = selectedId !== undefined ? selectedId : select.value;
  select.replaceChildren();
  const noneOption = document.createElement("option");
  noneOption.value = "";
  noneOption.textContent = "Last played channel";
  select.appendChild(noneOption);
  for (const channel of channels) {
    const option = document.createElement("option");
    option.value = channel.id;
    option.textContent = `${channel.number} · ${channel.name}`;
    select.appendChild(option);
  }
  if (current && [...select.options].some((o) => o.value === current)) {
    select.value = current;
  }
}

async function loadChannels(force = false) {
  message.textContent = force ? "Refreshing channels…" : "Loading channels…";
  try {
    const payload = force
      ? await api("/api/channels/refresh", { method: "POST" })
      : await api("/api/channels");
    channels = payload.channels || [];
    message.textContent = `${channels.length} channel${channels.length === 1 ? "" : "s"}`;
    renderChannels();
    if (!channels.length && !setupAutoShown) {
      showSetup("Enter your M3U URL to load channels.");
    }
  } catch (error) {
    message.textContent = error.message;
    list.replaceChildren();
    if (!setupAutoShown) {
      showSetup("Enter your M3U URL to load channels.");
    }
  }
}

async function requestChannelPlayback(channelId) {
  return api("/api/player/channel", {
    method: "POST",
    body: JSON.stringify({ channel_id: channelId }),
  });
}

async function playChannel(channelId) {
  message.textContent = "Starting channel…";
  try {
    const status = await requestChannelPlayback(channelId);
    updateStatus(status);
    message.textContent = "Channel selected.";
  } catch (error) {
    message.textContent = error.message;
  }
}

function updateVolumeUi(status) {
  const volume = Number.isFinite(Number(status.volume)) ? Number(status.volume) : 100;
  const muted = status.muted === true;
  const audio = status.audio || {};
  const available = audio.volume_control_available !== false;

  volumeInput.value = String(volume);
  volumeValue.textContent = available ? `${volume}%` : "HDMI";
  muteButton.textContent = muted && available ? "Unmute" : "Mute";
  muteButton.setAttribute("aria-pressed", String(muted && available));
  muteButton.disabled = !available;
  volumeInput.disabled = !available;
  muteButton.title = available ? "" : (audio.message || "Volume is controlled externally.");
  volumeInput.title = muteButton.title;
  audioControlNote.textContent = available ? "" : (audio.message || "Volume is controlled externally.");
  audioControlNote.hidden = available;
  document.body.classList.toggle("is-muted", muted && available);
  document.body.classList.toggle("external-audio", !available);
}

async function setVolume(volume, muted) {
  message.textContent = "Updating volume…";
  try {
    const status = await api("/api/player/volume", {
      method: "POST",
      body: JSON.stringify({ volume, muted }),
    });
    updateStatus(status);
    message.textContent = muted ? "Audio muted." : `Volume set to ${status.volume}%.`;
  } catch (error) {
    message.textContent = error.message;
    await pollStatus();
  }
}

function updateStatus(status) {
  currentChannel.textContent = status.channel
    ? `${status.channel.number} · ${status.channel.name}`
    : "Nothing selected";
  playerState.textContent = status.playing ? "Playing" : "Stopped";
  document.body.classList.toggle("is-playing", Boolean(status.playing));
  updateVolumeUi(status);
}

async function pollStatus() {
  try {
    updateStatus(await api("/api/player/status"));
  } catch (_) {
    playerState.textContent = "Backend unavailable";
  }
}


function formatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return "Unknown";
  return `${(value / (1024 ** 3)).toFixed(1)} GiB`;
}

function setSystemText(id, value) {
  document.getElementById(id).textContent = value || "Unknown";
}

async function loadSystemInfo() {
  try {
    const info = await api("/api/system/info");
    setSystemText("system-machine", info.machine);
    setSystemText("system-os", info.operating_system);
    setSystemText("system-kernel", info.kernel);
    setSystemText("system-kernel-architecture", info.kernel_architecture);
    setSystemText("system-userspace-architecture", info.userspace_architecture);
    setSystemText("system-processor", info.processor);
    setSystemText("system-cpu-cores", String(info.cpu_cores || "Unknown"));
    setSystemText("system-memory", formatBytes(info.memory_bytes));
    setSystemText("system-display-mode", String(info.display_mode || "desktop").toUpperCase());
    setSystemText("system-display-connector", info.display_connector || "Not applicable");
    setSystemText("system-display-resolution", info.display_resolution || "Managed externally");
    setSystemText("system-player-backend", String(info.player_backend || "Unknown").toUpperCase());
    document.getElementById("system-connector-row").hidden = !info.display_connector;
    document.getElementById("system-resolution-row").hidden = !info.display_resolution;
  } catch (_) {
    setSystemText("system-machine", "Unavailable");
  }
}

// Settings panel

async function loadConfig() {
  try {
    const [config, options] = await Promise.all([
      api("/api/config"),
      api("/api/display/options"),
    ]);
    displayOptions = options;
    document.getElementById("m3u-url-input").value = config.m3u_url || "";
    document.getElementById("autoplay-input").checked = config.autoplay === true;
    document.getElementById("boot-logo-enabled-input").checked = config.boot_logo_enabled !== false;
    savedDefaultChannelId = config.default_channel_id || "";
    populateDefaultChannelSelect(savedDefaultChannelId);

    const displaySettings = document.getElementById("display-settings");
    const resolutionSetting = document.getElementById("display-resolution-setting");
    const overscanSetting = document.getElementById("crt-overscan-setting");
    const zeroWVideoSizingSetting = document.getElementById("zero-w-video-sizing-setting");
    const hdmiUnderscanSetting = document.getElementById("hdmi-underscan-setting");
    displaySettings.hidden = !options.resolution_control_available && !options.overscan_control_available && !options.zero_w_video_sizing_available && !options.hdmi_underscan_control_available;
    resolutionSetting.hidden = !options.resolution_control_available;
    overscanSetting.hidden = !options.overscan_control_available;
    zeroWVideoSizingSetting.hidden = !options.zero_w_video_sizing_available;
    hdmiUnderscanSetting.hidden = !options.hdmi_underscan_control_available;

    const resolutionSelect = document.getElementById("display-resolution-input");
    resolutionSelect.replaceChildren();
    for (const resolution of options.resolutions || []) {
      const option = document.createElement("option");
      option.value = resolution;
      const label = options.resolution_labels?.[resolution];
      const warning = options.resolution_warnings?.[resolution];
      option.textContent = label ? `${resolution} — ${label}` : resolution;
      if (warning) option.title = warning;
      resolutionSelect.appendChild(option);
    }
    if (config.display_resolution && [...resolutionSelect.options].some((item) => item.value === config.display_resolution)) {
      resolutionSelect.value = config.display_resolution;
    }
    document.getElementById("crt-overscan-input").value = config.crt_overscan || "none";
    alignmentValues = { left: 0, right: 0, top: 0, bottom: 0, ...(config.crt_custom_alignment || {}) };
    renderAlignmentValues();
    document.getElementById("zero-w-video-sizing-input").value = config.zero_w_video_sizing || "auto";
    const hdmiUnderscan = Number(config.hdmi_underscan_percent || 0);
    document.getElementById("hdmi-underscan-input").value = String(hdmiUnderscan);
    document.getElementById("hdmi-underscan-value").textContent = `${hdmiUnderscan}%`;
  } catch (_) {
    // Non-fatal; form stays usable for basic settings.
  }
}

async function saveConfig() {
  const m3uUrl = document.getElementById("m3u-url-input").value.trim();
  const autoplay = document.getElementById("autoplay-input").checked;
  const bootLogoEnabled = document.getElementById("boot-logo-enabled-input").checked;
  const displayResolution = document.getElementById("display-resolution-input").value;
  const crtOverscan = document.getElementById("crt-overscan-input").value;
  const zeroWVideoSizing = document.getElementById("zero-w-video-sizing-input").value;
  const hdmiUnderscan = Number(document.getElementById("hdmi-underscan-input").value);

  if (!m3uUrl) {
    setupMessage.textContent = "M3U URL is required.";
    return;
  }

  setupMessage.textContent = "Saving…";
  try {
    const payload = { m3u_url: m3uUrl, autoplay, boot_logo_enabled: bootLogoEnabled, default_channel_id: document.getElementById("default-channel-input").value };
    if (displayOptions.resolution_control_available) {
      payload.display_resolution = displayResolution;
    }
    if (displayOptions.overscan_control_available) {
      payload.crt_overscan = crtOverscan;
    }
    if (displayOptions.zero_w_video_sizing_available) {
      payload.zero_w_video_sizing = zeroWVideoSizing;
    }
    if (displayOptions.hdmi_underscan_control_available) {
      payload.hdmi_underscan_percent = hdmiUnderscan;
    }
    const result = await api("/api/config", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setupMessage.textContent = result.message || "Settings saved.";
    savedDefaultChannelId = payload.default_channel_id;
    if (result.reboot_required) showRebootPrompt(result.message);
    else hideSetup();
    loadChannels(true);
  } catch (error) {
    setupMessage.textContent = error.message;
  }
}

function showSetup(hint) {
  setupAutoShown = true;
  setupPanel.hidden = false;
  settingsButton.setAttribute("aria-expanded", "true");
  if (hint) {
    setupMessage.textContent = hint;
  }
  loadConfig();
}

function hideSetup() {
  setupPanel.hidden = true;
  settingsButton.setAttribute("aria-expanded", "false");
  setupMessage.textContent = "";
}

const rebootPanel = document.getElementById("reboot-panel");
const rebootNowButton = document.getElementById("reboot-now-button");
const rebootStatus = document.getElementById("reboot-status");

function showRebootPrompt(message) {
  document.getElementById("reboot-message").textContent = message || "CRT alignment changes are saved but are not active. Reboot to apply them.";
  rebootStatus.textContent = "";
  rebootNowButton.disabled = false;
  rebootPanel.hidden = false;
}

function hideRebootPrompt() {
  rebootPanel.hidden = true;
}

document.getElementById("reboot-later-button").addEventListener("click", () => {
  hideRebootPrompt();
  setupMessage.textContent = "CRT alignment changes are saved but not active. Reboot to apply.";
});

rebootNowButton.addEventListener("click", async () => {
  rebootNowButton.disabled = true;
  rebootStatus.textContent = "Requesting reboot…";
  try {
    const result = await api("/api/system/reboot", { method: "POST" });
    rebootStatus.textContent = result.message || "Reboot requested. RetroStation Player will disconnect shortly.";
  } catch (error) {
    rebootNowButton.disabled = false;
    rebootStatus.textContent = error.message;
  }
});

function toggleSetup() {
  if (setupPanel.hidden) {
    showSetup();
  } else {
    hideSetup();
  }
}

// About panel

function showAbout() {
  aboutPanel.hidden = false;
  aboutButton.setAttribute("aria-expanded", "true");
  loadSystemInfo();
}

function hideAbout() {
  aboutPanel.hidden = true;
  aboutButton.setAttribute("aria-expanded", "false");
}

function toggleAbout() {
  if (aboutPanel.hidden) {
    showAbout();
  } else {
    hideAbout();
  }
}

search.addEventListener("input", renderChannels);
settingsButton.addEventListener("click", toggleSetup);
aboutButton.addEventListener("click", toggleAbout);
document.getElementById("save-config-button").addEventListener("click", saveConfig);
volumeInput.addEventListener("input", () => {
  volumeValue.textContent = `${volumeInput.value}%`;
});
volumeInput.addEventListener("change", () => {
  setVolume(Number(volumeInput.value), false);
});
muteButton.addEventListener("click", () => {
  const muted = muteButton.getAttribute("aria-pressed") !== "true";
  setVolume(Number(volumeInput.value), muted);
});
document.getElementById("refresh-button").addEventListener("click", () => loadChannels(true));
document.getElementById("stop-button").addEventListener("click", async () => {
  try { updateStatus(await api("/api/player/stop", { method: "POST" })); }
  catch (error) { message.textContent = error.message; }
});
document.getElementById("restart-button").addEventListener("click", async () => {
  try { updateStatus(await api("/api/player/restart", { method: "POST" })); }
  catch (error) { message.textContent = error.message; }
});

loadChannels();
pollStatus();
setInterval(pollStatus, 3000);

// Service log viewer
const logsButton = document.getElementById("logs-button");
const logsPanel = document.getElementById("logs-panel");
const logsOutput = document.getElementById("logs-output");
const logsMessage = document.getElementById("logs-message");
const logsAutoRefresh = document.getElementById("logs-auto-refresh");
const logsSource = document.getElementById("logs-source");
const logsLines = document.getElementById("logs-lines");
const isZeroW = logsPanel.dataset.zeroW === "true";
let logsRefreshTimer = null;

function logQueryString() {
  const params = new URLSearchParams({
    source: logsSource.value,
    level: document.getElementById("logs-level").value,
    lines: logsLines.value,
    search: document.getElementById("logs-search").value.trim(),
  });
  return params.toString();
}

function applyLogSourcePolicy() {
  const journalSelected = logsSource.value === "journal";
  if (isZeroW && journalSelected) {
    logsAutoRefresh.checked = false;
    logsAutoRefresh.disabled = true;
    if (Number(logsLines.value) > 100) logsLines.value = "100";
  } else {
    logsAutoRefresh.disabled = false;
  }
  updateLogsAutoRefresh();
}

async function loadLogs() {
  logsMessage.textContent = "Loading logs…";
  try {
    const payload = await api(`/api/logs?${logQueryString()}`);
    logsOutput.textContent = payload.text || "No matching log entries.";
    const sourceLabel = payload.source === "journal" ? "system journal" : "current runtime";
    logsMessage.textContent = payload.warning
      ? `Showing ${sourceLabel}. Journal unavailable; runtime logs shown instead.`
      : `Showing ${sourceLabel}.`;
    logsOutput.scrollTop = logsOutput.scrollHeight;
  } catch (error) {
    logsMessage.textContent = error.message;
    logsOutput.textContent = "Unable to load logs.";
  }
}

function updateLogsAutoRefresh() {
  if (logsRefreshTimer) {
    clearInterval(logsRefreshTimer);
    logsRefreshTimer = null;
  }
  const journalBlocked = isZeroW && logsSource.value === "journal";
  if (logsAutoRefresh.checked && !logsPanel.hidden && !document.hidden && !journalBlocked) {
    logsRefreshTimer = setInterval(loadLogs, 5000);
  }
}

function showLogs() {
  logsPanel.hidden = false;
  logsButton.setAttribute("aria-expanded", "true");
  logsSource.value = "runtime";
  applyLogSourcePolicy();
  loadLogs();
}

function hideLogs() {
  logsPanel.hidden = true;
  logsButton.setAttribute("aria-expanded", "false");
  updateLogsAutoRefresh();
}

logsButton.addEventListener("click", () => logsPanel.hidden ? showLogs() : hideLogs());
document.getElementById("logs-close-button").addEventListener("click", hideLogs);
document.getElementById("logs-refresh-button").addEventListener("click", loadLogs);
document.getElementById("logs-download-button").addEventListener("click", () => {
  window.location.href = `/api/logs/download?${logQueryString()}`;
});
logsAutoRefresh.addEventListener("change", updateLogsAutoRefresh);
logsSource.addEventListener("change", () => {
  applyLogSourcePolicy();
  if (logsSource.value === "runtime") loadLogs();
  else logsMessage.textContent = isZeroW
    ? "System journal is manual-only on the Pi Zero W. Select Refresh Logs to load it."
    : "Select Refresh Logs to load the system journal.";
});
document.getElementById("logs-level").addEventListener("change", () => {
  if (logsSource.value === "runtime") loadLogs();
});
logsLines.addEventListener("change", () => {
  applyLogSourcePolicy();
  if (logsSource.value === "runtime") loadLogs();
});
document.getElementById("logs-search").addEventListener("search", () => {
  if (logsSource.value === "runtime") loadLogs();
});
document.addEventListener("visibilitychange", updateLogsAutoRefresh);



// Interactive CRT alignment tool
const alignmentPanel = document.getElementById("alignment-panel");
const alignmentMessage = document.getElementById("alignment-message");
const alignmentStatus = document.getElementById("alignment-status");
let alignmentValues = { left: 0, right: 0, top: 0, bottom: 0 };
let alignmentBusy = false;

function renderAlignmentValues() {
  for (const edge of ["left", "right", "top", "bottom"]) {
    const target = document.getElementById(`align-${edge}-value`);
    if (target) target.textContent = String(alignmentValues[edge] || 0);
  }
}

function adjustAlignment(action) {
  const step = Number(document.getElementById("alignment-step").value || 5);
  const next = { ...alignmentValues };
  if (action === "left") { next.left = Math.max(0, next.left - step); next.right += step; }
  if (action === "right") { next.left += step; next.right = Math.max(0, next.right - step); }
  if (action === "up") { next.top = Math.max(0, next.top - step); next.bottom += step; }
  if (action === "down") { next.top += step; next.bottom = Math.max(0, next.bottom - step); }
  if (action === "wider") { next.left = Math.max(0, next.left - step); next.right = Math.max(0, next.right - step); }
  if (action === "narrower") { next.left += step; next.right += step; }
  if (action === "taller") { next.top = Math.max(0, next.top - step); next.bottom = Math.max(0, next.bottom - step); }
  if (action === "shorter") { next.top += step; next.bottom += step; }
  if (action === "center") {
    const horizontal = Math.round((next.left + next.right) / 2);
    const vertical = Math.round((next.top + next.bottom) / 2);
    next.left = next.right = horizontal; next.top = next.bottom = vertical;
  }
  return next;
}

async function sendAlignment(values) {
  if (alignmentBusy) return;
  alignmentBusy = true;
  alignmentMessage.textContent = "Applying…";
  try {
    const result = await api("/api/display/alignment/update", { method: "POST", body: JSON.stringify({ values }) });
    alignmentValues = result.values;
    renderAlignmentValues();
    alignmentStatus.textContent = "Test pattern active";
    alignmentMessage.textContent = "Adjustment applied.";
  } catch (error) { alignmentMessage.textContent = error.message; }
  finally { alignmentBusy = false; }
}

async function openAlignment() {
  alignmentPanel.hidden = false;
  alignmentMessage.textContent = "Starting test pattern…";
  try {
    const status = await api("/api/display/alignment");
    if (!status.available) throw new Error("CRT alignment requires VLC composite output.");
    alignmentValues = status.values;
    renderAlignmentValues();
    const result = await api("/api/display/alignment/start", { method: "POST" });
    alignmentValues = result.values;
    renderAlignmentValues();
    alignmentStatus.textContent = "Test pattern active";
    alignmentMessage.textContent = "Adjust the picture until the yellow Safe Area box is fully visible and confirm the circle remains round.";
  } catch (error) { alignmentMessage.textContent = error.message; }
}

document.getElementById("crt-alignment-button").addEventListener("click", openAlignment);
document.querySelectorAll("[data-align-action]").forEach((button) => button.addEventListener("click", () => sendAlignment(adjustAlignment(button.dataset.alignAction))));
document.getElementById("alignment-reset-button").addEventListener("click", () => sendAlignment({ left: 0, right: 0, top: 0, bottom: 0 }));
function hideAlignmentPanel() {
  alignmentPanel.hidden = true;
  alignmentStatus.textContent = "Test pattern inactive";
}

async function stopAlignmentInBackground() {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch("/api/display/alignment/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
  } finally {
    window.clearTimeout(timeout);
  }
}

function closeAlignment() {
  hideAlignmentPanel();
  void stopAlignmentInBackground().catch(() => {
    setupMessage.textContent = "CRT Alignment was closed, but the test pattern may still be active. Use Restart Playback to resume the selected channel.";
  });
}

document.getElementById("alignment-close-button").addEventListener("click", closeAlignment);
document.getElementById("alignment-cancel-button").addEventListener("click", closeAlignment);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !alignmentPanel.hidden) closeAlignment();
});

async function resetOriginalCrtSettings() {
  const confirmed = window.confirm("Remove all RetroStation Player CRT overscan settings and restore the original boot and KMS picture size after reboot?");
  if (!confirmed) return;
  alignmentMessage.textContent = "Removing saved CRT settings…";
  setupMessage.textContent = "Removing saved CRT settings…";
  try {
    const result = await api("/api/display/alignment/reset-original", { method: "POST" });
    alignmentValues = { left: 0, right: 0, top: 0, bottom: 0 };
    renderAlignmentValues();
    document.getElementById("crt-overscan-input").value = "none";
    hideAlignmentPanel();
    setupMessage.textContent = result.message;
    showRebootPrompt(result.message);
  } catch (error) {
    alignmentMessage.textContent = error.message;
    setupMessage.textContent = error.message;
  }
}

const crtResetOriginalButton = document.getElementById("crt-reset-original-button");
if (crtResetOriginalButton) crtResetOriginalButton.addEventListener("click", resetOriginalCrtSettings);
const alignmentResetOriginalButton = document.getElementById("alignment-reset-original-button");
if (alignmentResetOriginalButton) alignmentResetOriginalButton.addEventListener("click", resetOriginalCrtSettings);

document.getElementById("alignment-save-button").addEventListener("click", async () => {
  try {
    const result = await api("/api/display/alignment/save", { method: "POST", body: JSON.stringify({ values: alignmentValues }) });
    document.getElementById("crt-overscan-input").value = "custom";
    alignmentPanel.hidden = true;
    alignmentStatus.textContent = "Test pattern inactive";
    setupMessage.textContent = result.message || "Custom CRT alignment saved.";
    if (result.reboot_required) showRebootPrompt(result.message);
  } catch (error) { alignmentMessage.textContent = error.message; }
});


document.getElementById("hdmi-underscan-input").addEventListener("input", (event) => {
  document.getElementById("hdmi-underscan-value").textContent = `${Number(event.target.value)}%`;
});

const hdmiAlignmentPanel = document.getElementById("hdmi-alignment-panel");
const hdmiAlignmentInput = document.getElementById("hdmi-alignment-input");
const hdmiAlignmentMessage = document.getElementById("hdmi-alignment-message");
const hdmiAlignmentStatus = document.getElementById("hdmi-alignment-status");
const hdmiPreviewButton = document.getElementById("hdmi-alignment-preview-button");
const hdmiPatternButton = document.getElementById("hdmi-alignment-pattern-button");
let hdmiAlignmentTimer = null;
let hdmiAlignmentPreviewing = false;
function renderHdmiAlignment(value) {
  hdmiAlignmentInput.value = String(value);
  document.getElementById("hdmi-alignment-value").textContent = `${value}%`;
}
function setHdmiPreviewState(previewing) {
  hdmiAlignmentPreviewing = previewing;
  hdmiAlignmentInput.disabled = previewing;
  hdmiPreviewButton.hidden = previewing;
  hdmiPatternButton.hidden = !previewing;
  hdmiAlignmentStatus.textContent = previewing ? "Channel preview active" : "Test pattern active";
}
async function openHdmiAlignment() {
  hdmiAlignmentPanel.hidden = false;
  hdmiAlignmentMessage.textContent = "Starting HDMI test pattern…";
  try {
    const status = await api("/api/display/hdmi-alignment");
    if (!status.available) throw new Error("HDMI alignment requires HDMI output using mpv.");
    renderHdmiAlignment(status.value);
    const result = await api("/api/display/hdmi-alignment/start", { method: "POST" });
    renderHdmiAlignment(result.value);
    setHdmiPreviewState(false);
    hdmiAlignmentMessage.textContent = "Adjust until the yellow Safe Area box is fully visible, then preview the actual channel.";
  } catch (error) {
    hdmiAlignmentMessage.textContent = error.message;
  }
}
hdmiAlignmentInput.addEventListener("input", (event) => {
  if (hdmiAlignmentPreviewing) return;
  const value = Number(event.target.value);
  renderHdmiAlignment(value);
  clearTimeout(hdmiAlignmentTimer);
  hdmiAlignmentTimer = setTimeout(async () => {
    try {
      const result = await api("/api/display/hdmi-alignment/update", { method: "POST", body: JSON.stringify({ value }) });
      renderHdmiAlignment(result.value);
      hdmiAlignmentMessage.textContent = "Test pattern updated.";
    } catch (error) {
      hdmiAlignmentMessage.textContent = error.message;
    }
  }, 250);
});
async function closeHdmiAlignment() {
  hdmiAlignmentPanel.hidden = true;
  hdmiAlignmentStatus.textContent = "Test pattern inactive";
  try {
    await api("/api/display/hdmi-alignment/cancel", { method: "POST" });
  } catch (_) {
    setupMessage.textContent = "HDMI Alignment closed, but playback may need to be restarted.";
  }
  setHdmiPreviewState(false);
}
document.getElementById("hdmi-alignment-button").addEventListener("click", openHdmiAlignment);
document.getElementById("hdmi-alignment-close-button").addEventListener("click", closeHdmiAlignment);
document.getElementById("hdmi-alignment-cancel-button").addEventListener("click", closeHdmiAlignment);
document.getElementById("hdmi-alignment-reset-button").addEventListener("click", () => {
  if (hdmiAlignmentPreviewing) return;
  renderHdmiAlignment(0);
  hdmiAlignmentInput.dispatchEvent(new Event("input"));
});
hdmiPreviewButton.addEventListener("click", async () => {
  const value = Number(hdmiAlignmentInput.value);
  try {
    clearTimeout(hdmiAlignmentTimer);
    const result = await api("/api/display/hdmi-alignment/preview", { method: "POST", body: JSON.stringify({ value }) });
    renderHdmiAlignment(result.value);
    setHdmiPreviewState(true);
    hdmiAlignmentMessage.textContent = "Previewing the current channel with this underscan. Return to the test pattern to refine it.";
  } catch (error) {
    hdmiAlignmentMessage.textContent = error.message;
  }
});
hdmiPatternButton.addEventListener("click", async () => {
  try {
    const result = await api("/api/display/hdmi-alignment/pattern", { method: "POST" });
    renderHdmiAlignment(result.value);
    setHdmiPreviewState(false);
    hdmiAlignmentMessage.textContent = "Test pattern restored. Continue adjusting or preview the channel again.";
  } catch (error) {
    hdmiAlignmentMessage.textContent = error.message;
  }
});
document.getElementById("hdmi-alignment-save-button").addEventListener("click", async () => {
  const value = Number(hdmiAlignmentInput.value);
  try {
    clearTimeout(hdmiAlignmentTimer);
    await api("/api/display/hdmi-alignment/save", { method: "POST", body: JSON.stringify({ value }) });
    document.getElementById("hdmi-underscan-input").value = String(value);
    document.getElementById("hdmi-underscan-value").textContent = `${value}%`;
    hdmiAlignmentPanel.hidden = true;
    setHdmiPreviewState(false);
    hdmiAlignmentStatus.textContent = "Test pattern inactive";
    setupMessage.textContent = `HDMI alignment saved at ${value}% underscan.`;
  } catch (error) {
    hdmiAlignmentMessage.textContent = error.message;
  }
});


const streamingNoticePanel = document.getElementById("streaming-notice-panel");
if (streamingNoticePanel) {
  const acknowledgeButton = document.getElementById("streaming-notice-acknowledge-button");
  const noticeStatus = document.getElementById("streaming-notice-status");
  api("/api/streaming-notice").then((notice) => {
    if (notice.required) {
      streamingNoticePanel.hidden = false;
      acknowledgeButton.focus();
    }
  }).catch(() => {});
  acknowledgeButton.addEventListener("click", async () => {
    acknowledgeButton.disabled = true;
    noticeStatus.textContent = "Saving acknowledgment…";
    try {
      await api("/api/streaming-notice/acknowledge", { method: "POST" });
      streamingNoticePanel.hidden = true;
      noticeStatus.textContent = "";
    } catch (error) {
      noticeStatus.textContent = error.message;
      acknowledgeButton.disabled = false;
    }
  });
}
