# Changelog

All notable changes to RetroStation Player are documented here.

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
