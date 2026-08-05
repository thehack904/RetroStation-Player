# RetroStation Player

<p align="center">
  <a href="https://github.com/thehack904/RetroStation-Player">
    <img src="https://img.shields.io/badge/version-v0.2.0-blue?style=for-the-badge" alt="Version">
  </a>
  <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">
    <img src="https://img.shields.io/badge/license-CC--BY--NC--SA%204.0-lightgrey?style=for-the-badge" alt="License">
  </a>
</p>
<p align="center">
  <img src="static/logo.png" width="900">
</p>

RetroStation Player turns a Raspberry Pi or Linux computer into a dedicated TV player. Plug it into your television, point it at an IPTV playlist, and use any phone or browser on your network to pick channels — the video plays fullscreen on the connected display.

It pairs naturally with [RetroStation MC](https://github.com/thehack904/RetroStation_MC), [ErsatzTV](https://ersatztv.org/), [Tunarr](https://github.com/chrisbenincasa/tunarr), and any other service that provides an M3U channel list.

---

## What it does

- **Pick a channel from your phone or browser** — the Web UI shows your full channel list with logos, names, and numbers
- **Plays fullscreen on the connected TV** — no remote, no keyboard required on the player itself
- **Works over HDMI or composite (CRT) output** — connect to a modern TV or a classic television
- **Interactive CRT alignment tool** — display a generated test pattern over VLC `drm_vout`, adjust position and dimensions from the Web UI, and save the result as the Custom CRT Overscan preference
- **Remembers where you left off** — resumes the last channel automatically after a reboot
- **Adjusts volume from the Web UI** — no need to reach for the TV remote (analog/composite output)
- **Shows a built-in log viewer** — useful when something goes wrong

---

## Supported hardware

| Device | HDMI | Composite (CRT) |
|---|:---:|:---:|
| Raspberry Pi Zero W | ✅ | ✅ (480i input max on composite; higher via HDMI) |
| Raspberry Pi 3 Model B / B+ | ✅ | ✅ |
| Raspberry Pi 4 | ✅ | ✅ |
| Raspberry Pi 5 | ✅ | — |
| Debian / Ubuntu x86 Linux | ✅ | — |

---

## Quick start

**1. Download and extract** the latest release, then open a terminal in its folder.

**2. Run the installer** (connect your TV before running):

```bash
sudo ./scripts/setup.sh install --display auto
```

The installer detects your display automatically and installs everything needed.

**3. Open the Web UI** from any device on the same network:

```
http://PLAYER-IP:5050
```

**4. Enter your M3U playlist URL** in Settings and save. Your channels will load and you can start watching.

> **Tip:** If Settings opens automatically on first launch, that just means the player is waiting for a playlist URL — enter yours and you're good to go.

---

## Limitations

- One player and one M3U source per installation
- No built-in login — intended for use on a trusted home network
- No TV guide, recording, or DVR features
- HDMI volume is controlled by your TV or receiver, not the Web UI

---

## Going further

For full installation options, display mode details, audio configuration, uninstall instructions, and advanced topics, see [INSTALL.md](INSTALL.md).

For what's coming next, see [ROADMAP.md](ROADMAP.md).

---

## License

See [LICENSE](LICENSE).

### HDMI overscan correction

When a television crops the edges of HDMI video, open **Settings** and increase **HDMI Picture Size** from `0%` until the full picture is visible. The setting applies mpv underscan while preserving the source aspect ratio and is stored separately from CRT composite alignment. Use the smallest value that reveals the entire picture; typical corrections are approximately `2%` to `6%`. Slider changes are saved and applied to the current channel automatically after a short delay; a reboot is not required.

On composite installations, **CRT Overscan** presets and the **CRT Alignment Tool** control how much border is reserved around the picture. On the original Pi Zero W, saved CRT overscan is applied after a reboot so normal composite playback can remain smooth without using VLC's runtime `croppadd` filter for every frame.

### Interactive HDMI alignment

The HDMI Alignment Tool displays a test pattern once and updates mpv live through JSON IPC while the underscan slider moves. Use **Preview Channel** to view the current channel with the temporary underscan while the tool remains open. **Return to Test Pattern** allows further adjustment before saving. Saving closes the tool and keeps the selected value.

On the original Pi Zero W, use **Reset All CRT Settings** to remove both current KMS margins and any older RetroStation-managed firmware overscan block. Reboot to restore the original boot text and composite picture size.

On the original Pi Zero W, use a 720×480 or lower source stream for the most reliable playback. Higher-resolution, high-bitrate, or unsupported streams may stutter or lose synchronization, especially over composite output. The installer and first Web UI visit require acknowledgment of this limitation; channels then start immediately without an `ffprobe` delay.
