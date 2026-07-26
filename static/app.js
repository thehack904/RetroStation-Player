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
let displayOptions = { resolutions: [], overscan_presets: [], backend: "mpv", display_mode: "desktop" };

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
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value ?? "";
  return element.innerHTML;
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

async function playChannel(channelId) {
  message.textContent = "Changing channel…";
  try {
    const status = await api("/api/player/channel", {
      method: "POST",
      body: JSON.stringify({ channel_id: channelId }),
    });
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

    const displaySettings = document.getElementById("display-settings");
    const resolutionSetting = document.getElementById("display-resolution-setting");
    const overscanSetting = document.getElementById("crt-overscan-setting");
    const zeroWVideoSizingSetting = document.getElementById("zero-w-video-sizing-setting");
    displaySettings.hidden = !options.resolution_control_available && !options.overscan_control_available && !options.zero_w_video_sizing_available;
    resolutionSetting.hidden = !options.resolution_control_available;
    overscanSetting.hidden = !options.overscan_control_available;
    zeroWVideoSizingSetting.hidden = !options.zero_w_video_sizing_available;

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
    document.getElementById("zero-w-video-sizing-input").value = config.zero_w_video_sizing || "auto";
  } catch (_) {
    // Non-fatal; form stays usable for basic settings.
  }
}

async function saveConfig() {
  const m3uUrl = document.getElementById("m3u-url-input").value.trim();
  const autoplay = document.getElementById("autoplay-input").checked;
  const displayResolution = document.getElementById("display-resolution-input").value;
  const crtOverscan = document.getElementById("crt-overscan-input").value;
  const zeroWVideoSizing = document.getElementById("zero-w-video-sizing-input").value;

  if (!m3uUrl) {
    setupMessage.textContent = "M3U URL is required.";
    return;
  }

  setupMessage.textContent = "Saving…";
  try {
    const payload = { m3u_url: m3uUrl, autoplay };
    if (displayOptions.resolution_control_available) {
      payload.display_resolution = displayResolution;
    }
    if (displayOptions.overscan_control_available) {
      payload.crt_overscan = crtOverscan;
    }
    if (displayOptions.zero_w_video_sizing_available) {
      payload.zero_w_video_sizing = zeroWVideoSizing;
    }
    await api("/api/config", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setupMessage.textContent = "Settings saved.";
    hideSetup();
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

