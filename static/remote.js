/* ==========================================================
   RetroStation Remote Control – JavaScript
   ========================================================== */

(function () {
  "use strict";

  // ---- DOM refs ----
  const screenChannel = document.getElementById("screen-channel");
  const screenState   = document.getElementById("screen-state");
  const numpadDisplay = document.getElementById("numpad-display");
  const statusMsg     = document.getElementById("status-msg");
  const volBar        = document.getElementById("vol-bar");
  const volLabel      = document.getElementById("vol-label");
  const muteBtn       = document.getElementById("mute-btn");
  const fullscreenBtn = document.getElementById("fullscreen-btn");

  // ---- State ----
  let channels     = [];  // [{id, number, name, ...}]
  let currentVol   = 100;
  let currentMuted = false;
  let numBuffer    = "";
  let numTimer     = null;

  // ---- Helpers ----
  function setStatus(msg, type) {
    statusMsg.textContent = msg;
    statusMsg.className = "status-msg" + (type ? " " + type : "");
  }

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || "Request failed (" + res.status + ")");
    }
    return data;
  }

  function updateScreen(status) {
    if (status.channel) {
      screenChannel.textContent = status.channel.number + " \u00B7 " + status.channel.name;
    } else {
      screenChannel.textContent = "\u2014";
    }
    screenState.textContent = status.playing ? "Playing" : "Stopped";

    const vol = Number.isFinite(Number(status.volume)) ? Number(status.volume) : 100;
    const muted = status.muted === true;
    currentVol   = vol;
    currentMuted = muted;

    volBar.style.width = muted ? "0%" : vol + "%";
    volLabel.textContent = muted ? "MUTED" : vol + "%";

    muteBtn.setAttribute("aria-pressed", String(muted));
    muteBtn.classList.toggle("active", muted);

    const volumeControlAvailable = status.audio && status.audio.volume_control_available !== false;
    const volumeRow = document.querySelector(".volume-row");
    if (volumeRow) {
      volumeRow.hidden = !volumeControlAvailable;
    }

    highlightActiveChannel();
  }

  async function refreshStatus() {
    try {
      const status = await api("/api/player/status");
      updateScreen(status);
    } catch (e) {
      // silently ignore status poll failures
    }
  }

  async function loadChannels() {
    try {
      const data = await api("/api/channels");
      // API returns { channels: [...], error: ... }
      channels = Array.isArray(data.channels) ? data.channels : (Array.isArray(data) ? data : []);
      renderChannelList();
    } catch (e) {
      setStatus("Could not load channels", "error");
    }
  }

  // ---- Channel list dropdown ----
  function renderChannelList() {
    const container = document.getElementById("channel-list-items");
    if (!container) return;
    container.innerHTML = "";
    if (channels.length === 0) {
      const empty = document.createElement("div");
      empty.className = "channel-list-item";
      empty.style.justifyContent = "center";
      empty.style.color = "var(--remote-text-dim)";
      empty.textContent = "No channels";
      container.appendChild(empty);
      return;
    }
    channels.forEach(function (ch) {
      const btn = document.createElement("button");
      btn.className = "channel-list-item";
      btn.dataset.channelId = ch.id;

      const numSpan = document.createElement("span");
      numSpan.className = "channel-list-num";
      numSpan.textContent = ch.number;

      const nameSpan = document.createElement("span");
      nameSpan.className = "channel-list-name";
      nameSpan.textContent = ch.name;

      btn.appendChild(numSpan);
      btn.appendChild(nameSpan);

      btn.addEventListener("click", async function () {
        closeChannelList();
        await playChannel(ch);
      });

      container.appendChild(btn);
    });
  }

  function highlightActiveChannel() {
    const text = screenChannel.textContent;
    const match = text.match(/^([^\s\u00B7]+)/);
    const activeNum = match ? match[1].trim() : null;
    document.querySelectorAll(".channel-list-item").forEach(function (btn) {
      const numSpan = btn.querySelector(".channel-list-num");
      btn.classList.toggle("active", !!(numSpan && numSpan.textContent === activeNum));
    });
  }

  function openChannelList() {
    const toggle = document.getElementById("channel-list-toggle");
    const dropdown = document.getElementById("channel-list-dropdown");
    if (!toggle || !dropdown) return;
    toggle.setAttribute("aria-expanded", "true");
    dropdown.hidden = false;
    highlightActiveChannel();
  }

  function closeChannelList() {
    const toggle = document.getElementById("channel-list-toggle");
    const dropdown = document.getElementById("channel-list-dropdown");
    if (!toggle || !dropdown) return;
    toggle.setAttribute("aria-expanded", "false");
    dropdown.hidden = true;
  }

  (function wireChannelList() {
    const toggle = document.getElementById("channel-list-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", function () {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      if (expanded) {
        closeChannelList();
      } else {
        openChannelList();
      }
    });
  }());

  // ---- Channel navigation ----
  function findChannelByNumber(numStr) {
    return channels.find(function (c) { return c.number === numStr; });
  }

  function currentChannelIndex() {
    const text = screenChannel.textContent;
    const match = text.match(/^([^\s\u00B7]+)/);
    if (!match) return -1;
    const num = match[1].trim();
    return channels.findIndex(function (c) { return c.number === num; });
  }

  async function playChannel(channel) {
    if (!channel) {
      setStatus("Channel not found", "error");
      return;
    }
    setStatus("Tuning…");
    try {
      const status = await api("/api/player/channel", {
        method: "POST",
        body: JSON.stringify({ channel_id: channel.id }),
      });
      updateScreen(status);
      setStatus(channel.number + " \u00B7 " + channel.name, "ok");
    } catch (e) {
      setStatus(e.message, "error");
    }
  }

  async function channelStep(direction) {
    if (channels.length === 0) {
      await loadChannels();
    }
    if (channels.length === 0) {
      setStatus("No channels loaded", "error");
      return;
    }
    let idx = currentChannelIndex();
    idx = idx < 0 ? 0 : (idx + direction + channels.length) % channels.length;
    await playChannel(channels[idx]);
  }

  // ---- Volume ----
  async function setVolume(vol, muted) {
    try {
      const status = await api("/api/player/volume", {
        method: "POST",
        body: JSON.stringify({ volume: vol, muted: muted }),
      });
      updateScreen(status);
    } catch (e) {
      setStatus(e.message, "error");
    }
  }

  // ---- Numpad ----
  function appendDigit(digit) {
    if (numBuffer.length >= 4) return;
    numBuffer += digit;
    numpadDisplay.textContent = numBuffer;

    clearTimeout(numTimer);
    numTimer = setTimeout(function () {
      commitNumber();
    }, 2500);
  }

  function clearNum() {
    numBuffer = "";
    numpadDisplay.innerHTML = "&nbsp;";
    clearTimeout(numTimer);
  }

  async function commitNumber() {
    const num = numBuffer;
    clearNum();
    if (!num) return;
    if (channels.length === 0) await loadChannels();
    const channel = findChannelByNumber(num);
    if (channel) {
      await playChannel(channel);
    } else {
      setStatus("Channel " + num + " not found", "error");
    }
  }

  // ---- Fullscreen ----
  function getFullscreenElement() {
    return document.fullscreenElement ||
      document.webkitFullscreenElement ||
      document.mozFullScreenElement ||
      document.msFullscreenElement ||
      document.webkitCurrentFullScreenElement ||
      null;
  }

  function isStandaloneDisplayMode() {
    return (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
      window.navigator.standalone === true;
  }

  function isIosBrowser() {
    return /iPad|iPhone|iPod/.test(window.navigator.userAgent) ||
      (window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1);
  }

  function unsupportedFullscreenMessage() {
    if (isStandaloneDisplayMode()) {
      return "Remote is already running in fullscreen app mode";
    }
    if (isIosBrowser()) {
      return "On iPhone or iPad, add this page to the home screen for fullscreen mode";
    }
    return "Fullscreen is not supported in this browser";
  }

  function invokeFullscreen(target, methodNames) {
    const methodName = methodNames.find(function (name) {
      return typeof target[name] === "function";
    });
    if (!methodName) {
      return { supported: false, result: null };
    }
    return { supported: true, result: target[methodName].call(target) };
  }

  function requestFullscreen() {
    const targets = [document.body, document.documentElement].filter(Boolean);

    for (const target of targets) {
      const action = invokeFullscreen(target, [
        "requestFullscreen",
        "webkitRequestFullscreen",
        "webkitRequestFullScreen",
        "mozRequestFullScreen",
        "msRequestFullscreen",
      ]);
      if (action.supported) {
        return action;
      }
    }

    return { supported: false, result: null };
  }

  function toggleFullscreen() {
    const fullscreen = getFullscreenElement();
    let action;

    try {
      action = fullscreen
        ? invokeFullscreen(document, [
          "exitFullscreen",
          "webkitExitFullscreen",
          "webkitCancelFullScreen",
          "mozCancelFullScreen",
          "msExitFullscreen",
        ])
        : requestFullscreen();
    } catch (e) {
      setStatus("Could not change fullscreen mode", "error");
      return;
    }

    if (!action.supported) {
      if (isIosBrowser() && !isStandaloneDisplayMode()) {
        showIosModal();
      } else {
        setStatus(unsupportedFullscreenMessage(), "error");
      }
      return;
    }

    Promise.resolve(action.result).catch(function () {
      setStatus("Could not change fullscreen mode", "error");
    });
  }

  // ---- iOS "Add to Home Screen" modal ----
  function showIosModal() {
    const modal = document.getElementById("ios-modal");
    if (modal) {
      modal.hidden = false;
    }
  }

  function hideIosModal() {
    const modal      = document.getElementById("ios-modal");
    const stepsView  = document.getElementById("ios-modal-steps-view");
    const guideView  = document.getElementById("ios-modal-guide-view");
    if (modal) {
      modal.hidden = true;
    }
    // Reset to steps view so the modal is fresh if reopened.
    if (stepsView) { stepsView.hidden = false; }
    if (guideView) { guideView.hidden = true; }
  }

  (function wireIosModal() {
    const modal      = document.getElementById("ios-modal");
    const doitBtn    = document.getElementById("ios-modal-doit");
    const okBtn      = document.getElementById("ios-modal-ok");
    const guideOkBtn = document.getElementById("ios-modal-guide-ok");
    const stepsView  = document.getElementById("ios-modal-steps-view");
    const guideView  = document.getElementById("ios-modal-guide-view");
    const backdrop   = modal && modal.querySelector(".ios-modal-backdrop");

    if (okBtn) {
      okBtn.addEventListener("click", hideIosModal);
    }

    if (backdrop) {
      backdrop.addEventListener("click", hideIosModal);
    }

    if (guideOkBtn) {
      guideOkBtn.addEventListener("click", hideIosModal);
    }

    if (doitBtn) {
      doitBtn.addEventListener("click", function () {
        // Switch to the visual guide that points at the Safari share bar.
        if (stepsView) { stepsView.hidden = true; }
        if (guideView) { guideView.hidden = false; }
      });
    }
  }());

  // ---- Event wiring ----
  document.getElementById("ch-up").addEventListener("click", function () {
    channelStep(1);
  });

  document.getElementById("ch-down").addEventListener("click", function () {
    channelStep(-1);
  });

  document.getElementById("stop-btn").addEventListener("click", async function () {
    setStatus("Stopping…");
    try {
      const status = await api("/api/player/stop", { method: "POST" });
      updateScreen(status);
      setStatus("Stopped", "ok");
    } catch (e) {
      setStatus(e.message, "error");
    }
  });

  document.getElementById("restart-btn").addEventListener("click", async function () {
    setStatus("Restarting…");
    try {
      const status = await api("/api/player/restart", { method: "POST" });
      updateScreen(status);
      setStatus("Restarted", "ok");
    } catch (e) {
      setStatus(e.message, "error");
    }
  });

  document.getElementById("vol-up").addEventListener("click", function () {
    const vol = Math.min(100, currentVol + 5);
    setVolume(vol, currentMuted);
  });

  document.getElementById("vol-down").addEventListener("click", function () {
    const vol = Math.max(0, currentVol - 5);
    setVolume(vol, currentMuted);
  });

  muteBtn.addEventListener("click", function () {
    setVolume(currentVol, !currentMuted);
  });

  document.querySelectorAll(".num-btn[data-digit]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      appendDigit(btn.dataset.digit);
    });
  });

  document.getElementById("num-clear").addEventListener("click", clearNum);

  document.getElementById("num-go").addEventListener("click", commitNumber);

  if (fullscreenBtn) {
    fullscreenBtn.addEventListener("click", toggleFullscreen);
  }

  // ---- Auto-poll status every 5 s ----
  refreshStatus();
  loadChannels();
  setInterval(refreshStatus, 5000);
}());
