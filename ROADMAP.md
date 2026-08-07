# Roadmap

Completed items are retained here to show current project status. Version placement may change before release tagging.

## Completed v0.1.0

- [x] Web configuration page
- [x] Persistent volume and mute controls for ALSA analog/composite audio
- [x] Player backend abstraction between mpv and VLC
- [x] Raspberry Pi composite VLC backend
- [x] Automatic display-mode detection
- [x] Explicit installer display selection
- [x] HDMI and DRM connector detection
- [x] Display-resolution selection
- [x] CRT overscan presets
- [x] Interactive CRT alignment tool with saved custom per-edge alignment
- [x] HDMI audio-device detection
- [x] Dual-HDMI Raspberry Pi 4/5 support
- [x] Runtime HDMI-port rebinding
- [x] Machine and operating-system information in Settings
- [x] Complete purge uninstall
- [x] Improved direct DRM/KMS display-session handling
- [x] Isolated installer detection and optimization prompts for original Pi Zero W, Pi 3B, and Pi 3B+
- [x] Separate model-specific runtime tuning services and boot-backup handling
- [x] Web UI runtime and system-journal log viewer
- [x] Bounded log API, filtering, download, and journal fallback
- [x] Lightweight Pi Zero W journal policy
- [x] Original Pi Zero W optimized HDMI playback profile and fallback resolutions

## v0.2.0

- [x] mpv JSON IPC controller
- [ ] Software volume and mute control for HDMI playback through mpv IPC
- [x] Playback failure detection and automatic stream restart
- [x] Configurable default channel independent of last-channel state
- [ ] Player-process health details and recent failure reason in the Web UI
- [ ] Installer and runtime diagnostics bundle export beyond the current plain-text log export
- [ ] Confirm and document Raspberry Pi Zero W operating limits across a wider channel sample
- [ ] Validate and document Raspberry Pi Zero 2 W separately

## v0.3.0

- [ ] Multiple M3U sources and XMLTV sources
- [ ] Channel capability analysis and warnings for resource-constrained hardware
- [ ] Optional local authentication
- [ ] Hardware acceleration and output capability detection by platform
- [ ] Additional Linux packaging formats
- [ ] Web UI selection when multiple displays are connected simultaneously
- [ ] Optional software scaling and aspect-ratio controls for HDMI/DRM output

## Longer-term considerations

- [ ] Possible HDMI-CEC remote-control integration after hardware and television compatibility testing
