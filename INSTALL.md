# Installation & Technical Reference

This document covers the full installation process, display and audio configuration, service management, and uninstall options for RetroStation Player.

For a general overview, see the [README](README.md).

---

## Requirements

- Linux
- Python 3.10 or later
- A network-accessible M3U/M3U8 playlist
- Root access for installation
- One of the supported output paths:
  - mpv for HDMI or DRM/KMS output
  - VLC for Raspberry Pi composite output

The installer installs the required Debian packages, including:

- `python3`, `python3-venv`, `mpv`, `alsa-utils`, `socat`
- `vlc` for composite installations

---

## Installation

Extract the release archive and enter its directory:

```bash
cd RetroStation-Player-Private-main
```

### Automatic display selection

```bash
sudo ./scripts/setup.sh install --display auto
```

`auto` uses the following order:

1. Connected HDMI connector
2. Another connected DRM connector
3. On a Raspberry Pi with no digital connector, prompt to enable composite output

To accept the composite prompt non-interactively:

```bash
sudo ./scripts/setup.sh install --display auto --yes
```

### Explicit display modes

```bash
sudo ./scripts/setup.sh install --display hdmi
sudo ./scripts/setup.sh install --display composite
sudo ./scripts/setup.sh install --display drm
```

After installation, open the Web UI at:

```
http://PLAYER-IP:5050
```

The Settings panel opens automatically when the playlist cannot be loaded. Enter the M3U URL and save.

Example:

```
http://192.0.2.123:8409/iptv/channels.m3u
```

---

## Display modes

### HDMI

HDMI uses mpv with direct DRM/KMS output. The installer:

- Detects the connected `HDMI-A-*` connector
- Stores the connector without the DRM card prefix, such as `HDMI-A-1`
- Detects the matching ALSA HDMI audio device

On Raspberry Pi 4 and 5 systems with two HDMI ports, the player rechecks the active connector at service startup, when display options are requested, and before channel playback. Moving the cable to the other port therefore updates the connector, available resolutions, and corresponding HDMI audio device without reinstalling.

When both HDMI connectors are attached, the lowest-numbered connector is selected.

### Composite

Composite output uses VLC because mpv did not provide reliable Raspberry Pi composite playback in the validated configuration. This path has been validated on Raspberry Pi 3 / 3B+ and Raspberry Pi 4 hardware with Raspberry Pi OS 13 Lite.

Available composite resolutions:

- `480i` — NTSC interlaced
- `576i` — PAL interlaced
- `240` — 240-line progressive-style mode
- `288` — 288-line progressive-style mode

Available CRT overscan presets:

- None
- Light
- Standard CRT
- Heavy Overscan
- Custom Alignment

The CRT Overscan control appears only for composite installations. On the original Pi Zero W, saved CRT overscan is applied after a reboot through a managed full-KMS `video=Composite-1:...margin_*` entry in `/boot/firmware/cmdline.txt`. This keeps normal playback off VLC's expensive `croppadd` path. The installer adds a root-owned, narrowly scoped helper and sudoers rule so the Web service can update only that composite KMS entry or request a reboot.

### Interactive CRT alignment

Composite installations using VLC include an **Open CRT Alignment Tool** button. The tool stops the current channel, displays a generated 480-line or 576-line test pattern through VLC `drm_vout`, and provides Web UI controls to:

- Move the picture left, right, up, or down
- Make the picture wider, narrower, taller, or shorter
- Center or reset the alignment
- Select 1, 2, 5, or 10-pixel adjustment steps

The pattern uses three references:

- The **outer yellow box** is the **Safe Area** and should be fully visible when alignment is complete.
- The **circle** is a geometry reference and should remain round after resizing.

Each adjustment restarts the test pattern so VLC applies the new `croppadd` values. **Save as Custom** stores independent left, right, top, and bottom values and selects **Custom Alignment** in the CRT Overscan list. **Stop & Close**, the heading **Close** button, or the Escape key closes the panel immediately and makes a time-limited background request to stop the test pattern and resume the previously selected channel. This prevents a stalled API request from trapping the alignment panel open.

On the original Pi Zero W, saving CRT alignment displays **Reboot Now** and **Later** options. Choosing Later leaves a reminder in Settings. A reboot is also required after composite output is first enabled or after purge restores the original Raspberry Pi boot configuration.

When **Show Boot Logo during startup** is enabled in the Web UI, RetroStation Player keeps the installer-managed `retrostation-player-startup-screen.service` enabled. The helper first displays `/opt/retrostation-player/static/boot-logo-starting.png` while the application initializes, then switches to `/opt/retrostation-player/static/boot-logo-ready.png` once the Web service is healthy. The ready logo remains visible until video playback has taken control and returns after the user presses Stop. On supported Raspberry Pi installations, the installer also adds quiet-boot kernel and systemd options so routine service messages and the console cursor are suppressed. Purging RetroStation Player removes those managed quiet-boot options.

---

## Audio behavior

### Analog and composite audio

Raspberry Pi analog/composite audio uses an ALSA playback mixer. RetroStation Player automatically detects common controls such as `PCM`, `Speaker`, `Headphone`, and `Master`. This supports USB audio adapters that do not expose a `PCM` control. The Web UI volume and mute controls apply immediately without restarting playback.

### HDMI audio

HDMI audio is routed to the detected HDMI ALSA device. Hardware volume controls are disabled in the Web UI.

The Web UI displays:

> HDMI audio is active. Use the TV or receiver volume control.

---

## Settings

Editable settings include:

- M3U URL
- Autoplay
- Display resolution when controlled by RetroStation Player
- CRT overscan preset in composite mode
- Analog volume and mute

The read-only System Information section displays:

- Machine model, Operating system, Kernel version, Kernel architecture
- Userspace architecture, Processor, CPU core count, Installed memory
- Display mode, Active connector, Display resolution, Player backend

Raspberry Pi system information is cached at application startup. On non-Raspberry Pi systems it is read when Settings requests it, allowing CPU or memory changes recognized by the operating system to appear without reinstalling the application.

---

## Configuration

The installed configuration is stored at:

```
/etc/retrostation-player/config.json
```

---

## Service and files

```
/etc/retrostation-player/config.json       User configuration
/var/lib/retrostation-player/state.json    Last selected channel and state
/opt/retrostation-player                   Installed application
/etc/systemd/system/retrostation-player.service
```

Useful service commands:

```bash
sudo systemctl status retrostation-player
sudo systemctl restart retrostation-player
```

---

## Uninstalling

Remove the application while retaining configuration, state, service account, and Raspberry Pi boot backups:

```bash
sudo ./scripts/setup.sh uninstall
```

Completely remove all RetroStation Player-owned files and identities:

```bash
sudo ./scripts/setup.sh uninstall --purge
```

Purge removes:

- `/opt/retrostation-player`
- `/etc/retrostation-player`
- `/var/lib/retrostation-player`
- The systemd service unit
- The `retrostation-player` service user and matching group
- Installer-created Raspberry Pi boot-configuration backups

When a composite backup exists, purge restores the oldest pre-install Raspberry Pi `config.txt` backup before removing the backups. Reboot afterward for the restored display configuration to take effect.

Shared packages such as mpv, VLC, ALSA utilities, socat, and Python are retained because other software may depend on them.

---

## Pi Zero W / 3 / 3B+ installation optimizations

When accepted, the installer can disable the Bluetooth overlay and services, ModemManager, Triggerhappy, and unused console gettys on tty1 and tty3 through tty6. It preserves tty2 for direct display playback and leaves networking, SSH, systemd-journald, Avahi/mDNS, and automatic package-update timers enabled. A model-specific systemd tuning unit disables Wi-Fi power saving and requests the performance CPU governor while RetroStation Player is active.

These changes are intended for a dedicated player. Bluetooth keyboards, remotes, controllers, and audio stop working after the required reboot. Standard uninstall retains the optimization state; `uninstall --purge` removes the model-specific tuning unit, unmasks the installer-managed gettys, restores the oldest installer-created Raspberry Pi boot backup when available, and removes those backups. Services disabled during installation are not automatically re-enabled because their prior administrative state cannot be reconstructed safely.

Pi 4 / 5 remain fully supported playback targets but currently receive no model-specific resource-optimization prompt.

---

## Log viewer behavior

The Logs screen opens on the lightweight **Current runtime** source. **System journal** is an on-demand diagnostic source: select it and press **Refresh Logs**. On the original Pi Zero W, journal auto-refresh is disabled and each request is limited to 100 lines to avoid disrupting playback. Log polling also stops whenever the panel is closed or the browser tab is hidden.

---

## Coexistence with other RetroStation applications

RetroStation Player is isolated from RetroStation MC and RetroIPTVGuide:

| Application | Service | Default port | Application path |
|---|---|---:|---|
| RetroIPTVGuide | `retroiptvguide.service` | 5000 | `/home/iptv/iptv-server` |
| RetroStation MC | `retrostation-mc.service` | 8787 | `/home/iptv/retrostation-mc` |
| RetroStation Player | `retrostation-player.service` | 5050 | `/opt/retrostation-player` |

### HDMI overscan correction

When a television crops the edges of HDMI video, open **Settings** and increase **HDMI Picture Size** from `0%` until the full picture is visible. The setting applies mpv underscan while preserving the source aspect ratio and is stored separately from CRT composite alignment. Use the smallest value that reveals the entire picture; typical corrections are approximately `2%` to `6%`. Slider changes are saved and applied to the current channel automatically after a short delay; a reboot is not required.

### Interactive HDMI alignment

The HDMI Alignment Tool displays a test pattern once and updates mpv live through JSON IPC while the underscan slider moves. Use **Preview Channel** to view the current channel with the temporary underscan while the tool remains open. **Return to Test Pattern** allows further adjustment before saving. Saving closes the tool and keeps the selected value.

On the original Pi Zero W, use a 720×480 or lower source stream for the most reliable playback. Higher-resolution, high-bitrate, or unsupported streams may stutter or lose synchronization, especially over composite output. The installer and first Web UI visit require acknowledgment of this limitation; channels then start immediately without an `ffprobe` delay.
