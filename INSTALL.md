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

The CRT Overscan control appears only for composite installations.

A reboot is required after composite output is first enabled or after purge restores the original Raspberry Pi boot configuration.

---

## Audio behavior

### Analog and composite audio

Raspberry Pi analog/composite audio uses the ALSA `PCM` mixer. The Web UI volume and mute controls apply immediately without restarting playback.

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
