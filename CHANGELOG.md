# Changelog
### Boot splash refinements

- Added separate `boot-logo-starting.png` and `boot-logo-ready.png` assets.
- The startup helper now switches from the starting graphic to the ready/idle graphic after the Web service health check succeeds.
- The ready/idle graphic remains visible until playback has initialized and is shown again after Stop.
- Added managed quiet-boot options to suppress routine kernel/systemd service output and the console cursor on supported Raspberry Pi installations.
- Purge removes the quiet-boot options managed by RetroStation Player.


All notable changes to RetroStation Player are documented here.

## Unreleased
- Prevent tty2 login prompts from flashing during the HDMI startup-logo-to-video handoff by stopping and masking its getty services.

- Keep the boot logo visible on composite until VLC playback has initialized.
- Prevent tty2 login text from flashing during the splash-to-video handoff.
- Replace the boot logo with the clean variant that omits the startup status line.

## [0.2.0] - 2026-08-01

- The optional boot logo remains visible until playback actually begins and returns when playback is stopped from the Web UI.

### Added

- **Playback failure detection and automatic stream restart**: `MediaPlayer` now monitors the player process in a background watchdog thread. When the process exits unexpectedly (network drop, stream error, or player crash), the watchdog waits with exponential back-off (1 s, 2 s, 4 s … capped at 30 s) and automatically restarts the stream. Intentional stops and channel changes suppress the watchdog so user actions are never overridden. `status()` exposes `failure_count`, `restart_count`, `last_failure_reason`, and `last_failure_time` to surface health details to the Web UI.
- **mpv JSON IPC controller** (`retrostation_player/mpv_ipc.py`): `MpvIpcController` class and `MpvIpcError` exception for sending JSON IPC commands to a running mpv process over a Unix domain socket. Exposes `send_command`, `get_property`, `set_property`, and `is_socket_ready`. Reused by the player for both HDMI alignment and main playback IPC.
- mpv playback processes are now started with `--input-ipc-server` pointing at a stable Unix socket (`/tmp/retrostation-player.sock`), making them controllable at runtime. The `playback_ipc` attribute on `MediaPlayer` exposes the controller for future features such as software volume control and failure detection. User-supplied `--input-ipc-server` values in `extra_args` are filtered out so the managed socket path is always used.
- Required installer acknowledgment explaining original Pi Zero W streaming limitations.
- Persistent one-time Pi Zero W streaming-performance notice in the Web UI.
- Automatic ALSA playback-mixer detection for `PCM`, `Speaker`, `Headphone`, and `Master`.
- Browser cache prevention and versioned Web UI assets for reliable in-place upgrades.

- Added **Reset All CRT Settings** for the original Pi Zero W to remove both KMS composite margins and legacy managed firmware overscan settings before reboot.

- Added a Reboot Now/Later prompt after saving original Pi Zero W composite alignment.
- Added a narrowly scoped Web UI reboot endpoint backed by the existing validated privileged helper.
- HDMI alignment channel-preview workflow that keeps the tool open, applies the temporary underscan to the current channel, and allows returning to the test pattern before saving.
- Interactive HDMI alignment test pattern with live mpv JSON IPC underscan adjustment.
- HDMI Picture Size control with persistent 0–15% mpv underscan correction for televisions that crop HDMI edges.
- Interactive CRT alignment tool for VLC composite output using generated 480-line and 576-line test patterns through `drm_vout`.
- Revised CRT alignment patterns with large hard-edged block lettering, center-safe label placement, heavier borders, and simplified guides for composite CRT legibility.
- Position, dimension, centering, reset, adjustable step-size, save, and cancel controls in the Web UI.
- Persistent Custom Alignment overscan preference with independent left, right, top, and bottom padding values.

## [0.1.0] - 2026-07-19

### Added

- M3U/M3U8 channel loading.
- Browser-based channel list with search and channel logos.
- Remote channel selection and fullscreen mpv playback.
- Stop, restart, and playback-status API endpoints.
- Persistent last-channel state.
- Automatic last-channel playback during service startup.
- Retry behavior when the M3U source is unavailable during boot.
- Debian-style installation and systemd service scripts.
- Responsive Web UI.
- Separate exact installer detection for the original Raspberry Pi Zero W (`raspberrypi,model-zero-w`), Raspberry Pi 3 Model B (`raspberrypi,3-model-b`), and Raspberry Pi 3 Model B+ (`raspberrypi,3-model-b-plus`).
- Independent, hardware-specific optimization prompts whose wording never references another Raspberry Pi model.
- Optional model-specific disablement of the Bluetooth hardware overlay, Bluetooth services, ModemManager, Triggerhappy, and unused console gettys while preserving tty2.
- Separate Zero W, Pi 3B, and Pi 3B+ systemd runtime-tuning units that disable Wi-Fi power saving and request the performance CPU governor while the player is active.
- Installer-created Raspberry Pi boot backups for model-specific Bluetooth changes, with purge restoration and cleanup.
- Lightweight original Pi Zero W log handling: runtime logs by default, manual-only journal reads, a 100-line journal cap, and disabled journal auto-refresh.
- Web UI service-log viewer with runtime and system-journal sources, severity filtering, text filtering, selectable line counts, manual refresh, five-second runtime auto-refresh, and plain-text export.
- `GET /api/logs` and `GET /api/logs/download` endpoints with bounded output and automatic runtime fallback when journal access fails.
- Installer display selection through the documented `--display auto|hdmi|composite|drm` modes.
- Automatic active-display detection for HDMI, generic DRM, and Raspberry Pi composite fallback.
- VLC playback backend for Raspberry Pi composite output.
- Raspberry Pi KMS composite configuration using `dtoverlay=vc4-kms-v3d,composite`.
- Composite resolution selection for `480i`, `576i`, `240`, and `288`.
- CRT overscan presets for composite output: None, Light, Standard CRT, and Heavy Overscan.
- Direct ALSA volume and mute controls for Raspberry Pi analog/composite audio.
- Installer dependencies for `alsa-utils` and `socat`.
- HDMI ALSA-device detection and explicit mpv HDMI audio routing.
- HDMI external-volume capability reporting and disabled Web UI volume controls.
- Connected HDMI/DRM resolution detection with duplicate-mode removal.
- Connector-specific resolution lists and explicit mpv `--drm-connector` and `--drm-mode` arguments.
- Dual-HDMI Raspberry Pi 4/5 connector and matching audio-device selection.
- Runtime HDMI connector rebinding at service startup, display-option requests, and channel playback.
- Read-only System Information section and `/api/system/info` endpoint.
- Complete uninstall mode through `setup.sh uninstall --purge`.
- Original Pi Zero W HDMI profile using V4L2 M2M hardware decoding, DRM PRIME output, plane reversal, and ordered fallback modes.

### Changed

- Removed per-channel `ffprobe` inspection so channel playback starts immediately without the previous 10–15 second probe delay.
- Pi Zero W stream compatibility is now documented and acknowledged instead of being checked before every playback request.

- Original Pi Zero W composite playback now avoids VLC runtime `croppadd` filtering during normal channel playback; saved CRT overscan and custom alignment are written as full-KMS `video=Composite-1:...margin_*` kernel command-line properties instead.

- Removed the CRT alignment corner markers so the yellow Safe Area is the only rectangular alignment target.
- Added an always-available CRT Alignment Close control, Escape-key support, and immediate panel dismissal with a time-limited background playback-cancel request.
- The original Pi Zero W HDMI default is `1280x720@59.94`, followed by `1280x720@60`, `720x480`, and `640x480` fallbacks.
- Zero W resolution labels and warnings distinguish widescreen, lower-load SD, and compatibility modes.
- Stretch documentation now warns that the image may be distorted and may still fail to fill correctly when a television interprets 480p HDMI as 4:3.
- mpv remains the backend for HDMI and DRM modes; VLC is selected automatically for Raspberry Pi composite.
- Composite playback forces VLC software decoding so `croppadd` receives supported software frames.
- Analog volume uses a useful mapping of approximately `-30 dB` through `+4 dB`.
- HDMI and DRM mode lists expose progressive modes only; unreliable interlaced modes are hidden.
- CRT Overscan is hidden outside composite mode.
- Raspberry Pi machine information is cached at service startup; non-Raspberry Pi hardware information is refreshed when requested.
- Existing connector values containing a DRM card prefix are normalized automatically.
- Settings can save unrelated values when resolution detection is temporarily unavailable.
- Standard uninstall retains configuration, state, service identity, tuning state, and boot backups; purge removes RetroStation Player-owned configuration, state, identities, tuning units, and backups.

### Fixed

- Added cache-busted Web UI assets and no-cache response headers so the Pi Zero W above-SD confirmation modal loads immediately after an upgrade.

- Reboot prompts now appear only when Zero W composite boot-time display settings actually change; unrelated Settings saves no longer request a reboot.

- Legacy firmware-only `overscan_*` settings being lost when full KMS took control of composite output.

- Pi Zero W composite overscan saves now use an installer-managed root helper instead of attempting to write the Raspberry Pi boot configuration directly from the unprivileged service.
- Severe Raspberry Pi Zero W composite stutter whenever any CRT overscan value enabled VLC's `croppadd` filter.

- False HDMI alignment startup timeouts on the original Raspberry Pi Zero W by using a hardware-specific 20-second readiness window while mpv initializes.
- HDMI alignment IPC failures caused by a missing mpv socket; the tool now uses a dedicated stable socket path, verifies the alignment process, and automatically recovers the test pattern when needed.
- HDMI settings saves incorrectly validating the active HDMI resolution as a composite resolution.
- HDMI Picture Size changes now apply automatically after the slider stops moving; no reboot is required.
- CRT alignment pattern updated so the outer yellow box is the Safe Area target, while the corner markers remain the outer display-limit references.
- CRT alignment guidance that incorrectly treated an inner yellow rectangle as the Safe Area; the outer box is now the Safe Area target and the corner markers represent the outer display limits.
- Raspberry Pi composite playback failures under mpv by moving the validated composite path to VLC.
- VLC composite overscan failures caused by DRM PRIME hardware-decoded frames.
- ALSA commands with negative dB values by using the `--` option terminator.
- HDMI audio incorrectly defaulting to the Raspberry Pi headphone output.
- HDMI Web UI volume controls modifying the unrelated analog mixer.
- Resolution dropdown showing only the global `480i` fallback on HDMI.
- Duplicate HDMI resolution entries caused by multiple refresh-rate variants in DRM sysfs.
- Interlaced HDMI modes starting and immediately stopping on Raspberry Pi 3 DRM output.
- Dual-HDMI installations saving a DRM-card-prefixed connector name.
- Empty resolution lists caused by connector-name mismatches.
- Cable moves between Raspberry Pi 4/5 HDMI ports requiring reinstall or manual configuration changes.
- Composite installation exiting after display selection because a valid no-connector state returned shell status 1 under `set -e`.
- HDMI interlace filtering incorrectly removing composite presets.
- CSS rules overriding the hidden state of the CRT Overscan section.

### Documentation

- Updated README, configuration reference, changelog, and roadmap for separate Zero W, Pi 3B, and Pi 3B+ detection and tuning.
- Added the Pi 4 and Pi 5 support distinction: both remain supported playback targets but receive no Zero W/Pi 3 optimization prompt.
- Documented Web UI runtime/journal log behavior, log API endpoints, Zero W safeguards, standard uninstall, and purge semantics.
- Consolidated temporary patch notes into maintained project documentation.

### Fixed
- Corrected the two-stage startup-screen state selection so `boot-logo-ready.png` is shown immediately when RetroStation Player is already healthy, including after playback is stopped.
- Forced an explicit framebuffer repaint with the ready/idle asset when the Web service becomes healthy, preventing the starting asset from remaining visible.
