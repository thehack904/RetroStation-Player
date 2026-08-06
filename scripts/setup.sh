#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/retrostation-player"
CONFIG_DIR="/etc/retrostation-player"
STATE_DIR="/var/lib/retrostation-player"
SERVICE_USER="retrostation-player"
SERVICE_NAME="retrostation-player"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
OWNERSHIP_MARKER="# Managed-By: RetroStation-Player"
PORT=5050
DISPLAY_MODE="auto"
DISPLAY_CONNECTOR=""
ASSUME_YES=false
REBOOT_REQUIRED=false
PURGE=false
IS_PI_ZERO_W=false
IS_PI_3B=false
IS_PI_3B_PLUS=false
APPLY_ZERO_W_OPTIMIZATIONS=false
APPLY_PI_3B_OPTIMIZATIONS=false
APPLY_PI_3B_PLUS_OPTIMIZATIONS=false
ZERO_W_TUNING_UNIT="/etc/systemd/system/retrostation-player-zero-w-tuning.service"
PI_3B_TUNING_UNIT="/etc/systemd/system/retrostation-player-pi-3b-tuning.service"
PI_3B_PLUS_TUNING_UNIT="/etc/systemd/system/retrostation-player-pi-3b-plus-tuning.service"
STARTUP_SCREEN_HELPER="/usr/local/libexec/retrostation-player-startup-screen"
STARTUP_SCREEN_UNIT="/etc/systemd/system/retrostation-player-startup-screen.service"
STARTUP_SCREEN_CONTROL_HELPER="/usr/local/libexec/retrostation-player-startup-screen-control"
STARTUP_SCREEN_SUDOERS="/etc/sudoers.d/retrostation-player-startup-screen"
COMPOSITE_OVERSCAN_HELPER="/usr/local/libexec/retrostation-player-composite-overscan"
COMPOSITE_OVERSCAN_SUDOERS="/etc/sudoers.d/retrostation-player-composite-overscan"

usage() {
  cat >&2 <<'USAGE'
Usage:
  setup.sh install [--display auto|hdmi|composite|desktop|drm] [--yes]
  setup.sh uninstall [--purge]

Display modes:
  auto       Detect an active desktop or DRM connector. On a Raspberry Pi with
             no active digital connector, offer to enable composite output.
  hdmi       Use direct DRM/KMS output and require an active HDMI connector.
  composite  Enable Raspberry Pi KMS composite output and use VLC's DRM output.
  desktop    Use an existing graphical desktop through DISPLAY/WAYLAND_DISPLAY.
  drm        Use direct DRM/KMS output without requiring a specific connector.

Options:
  -y, --yes  Accept detected-hardware optimization and composite
             configuration prompts, including the Pi Zero W streaming notice.
  --purge     With uninstall, also remove configuration, state, service user,
              and installer-created Raspberry Pi boot configuration backups.
  -h, --help Show this help.
USAGE
}

fatal() {
  echo "Error: $*" >&2
  exit 1
}

parse_args() {
  [[ $# -ge 1 ]] || { usage; exit 1; }

  COMMAND="$1"
  shift

  case "$COMMAND" in
    install)
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --display)
            [[ $# -ge 2 ]] || fatal "--display requires a value."
            DISPLAY_MODE="$2"
            shift 2
            ;;
          --display=*)
            DISPLAY_MODE="${1#*=}"
            shift
            ;;
          -y|--yes)
            ASSUME_YES=true
            shift
            ;;
          -h|--help)
            usage
            exit 0
            ;;
          *)
            fatal "Unknown install option: $1"
            ;;
        esac
      done
      case "$DISPLAY_MODE" in
        auto|hdmi|composite|desktop|drm) ;;
        *) fatal "Invalid display mode '$DISPLAY_MODE'. Use auto, hdmi, composite, desktop, or drm." ;;
      esac
      ;;
    uninstall)
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --purge)
            PURGE=true
            shift
            ;;
          -h|--help)
            usage
            exit 0
            ;;
          *)
            fatal "Unknown uninstall option: $1"
            ;;
        esac
      done
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

# Validate that a directory path is safe to perform destructive operations on.
assert_safe_install_dir() {
  local dir="$1"
  local resolved="$dir"
  if command -v realpath >/dev/null 2>&1; then
    resolved="$(realpath -m -- "$dir")"
  fi
  [[ -n "$resolved" && "$resolved" == /opt/?* ]] || {
    echo "Unsafe INSTALL_DIR resolved to: $resolved" >&2
    exit 1
  }
}

is_raspberry_pi() {
  [[ -r /proc/device-tree/model ]] && grep -a -qi 'raspberry pi' /proc/device-tree/model
}

is_original_pi_zero_w() {
  local compatible_file="/proc/device-tree/compatible"
  [[ -r "$compatible_file" ]] || return 1
  tr '\0' '\n' < "$compatible_file" | grep -Fqx 'raspberrypi,model-zero-w'
}

is_pi_3b() {
  local compatible_file="/proc/device-tree/compatible"
  [[ -r "$compatible_file" ]] || return 1
  tr '\0' '\n' < "$compatible_file" | grep -Fqx 'raspberrypi,3-model-b'
}

is_pi_3b_plus() {
  local compatible_file="/proc/device-tree/compatible"
  [[ -r "$compatible_file" ]] || return 1
  tr '\0' '\n' < "$compatible_file" | grep -Fqx 'raspberrypi,3-model-b-plus'
}


prompt_streaming_notice() {
  cat <<'STREAMING_NOTICE'

Streaming performance notice

RetroStation Player does not transcode or reduce the incoming video stream.
Playback performance depends on the Raspberry Pi model, output mode, stream
resolution, bitrate, codec, and whether hardware decoding is available.

The original Raspberry Pi Zero W is intended for SD playback. Streams above
720x480, high-bitrate streams, or unsupported formats may stutter, buffer, lose
synchronization, or fail to play smoothly, especially over composite output.
RetroStation Player starts channels immediately and does not inspect each stream
with ffprobe before playback.
STREAMING_NOTICE

  if [[ "$ASSUME_YES" == true ]]; then
    echo "--yes specified; streaming performance notice acknowledged."
    return 0
  fi
  if [[ ! -t 0 ]]; then
    fatal "Non-interactive installation requires --yes to acknowledge the streaming performance notice."
  fi
  local answer
  read -r -p "Type YES to acknowledge this streaming performance notice: " answer
  [[ "$answer" == "YES" ]] || fatal "Streaming performance notice was not acknowledged. Installation cancelled."
}

prompt_zero_w_optimizations() {
  IS_PI_ZERO_W=true

  cat <<'ZERO_W_NOTICE'

Original Raspberry Pi Zero W detected.

RetroStation Player can reduce background resource use by applying these
Pi Zero W-only optimizations:

  - Disable the Bluetooth hardware overlay
    Turns off the onboard Bluetooth radio so it does not reserve hardware or
    consume power when Bluetooth devices are not being used.

  - Disable bluetooth.service and hciuart.service
    Stops the Linux Bluetooth stack and the UART helper that initializes the
    onboard Bluetooth controller during startup.

  - Disable ModemManager.service when installed
    Stops background scanning for cellular modems and mobile-broadband devices
    that are not used by RetroStation Player.

  - Disable triggerhappy.service when installed
    Stops the hotkey daemon that monitors hardware input events for button and
    keyboard shortcuts that are not needed by a Web UI-controlled player.

  - Disable unused console gettys on tty1 and tty3 through tty6
    Removes unused local login prompts with tty2 reserved exclusively for video playback.

  - Disable Wi-Fi power saving while RetroStation Player is running
    Keeps the wireless adapter fully awake to reduce stream buffering, latency,
    and brief network interruptions.

  - Use the performance CPU governor while RetroStation Player is running
    Keeps the CPU at its highest available clock during playback to reduce
    frequency-scaling delays and improve playback consistency.

The player keeps tty2, networking, SSH, systemd-journald, Avahi/mDNS, and
automatic package-update timers unchanged. Bluetooth keyboards, remotes,
controllers, and Bluetooth audio will no longer work after the required reboot.
ZERO_W_NOTICE

  if [[ "$ASSUME_YES" == true ]]; then
    echo "--yes specified; applying Pi Zero W optimizations."
    APPLY_ZERO_W_OPTIMIZATIONS=true
    return 0
  fi

  if [[ ! -t 0 ]]; then
    echo "Non-interactive installation detected; Pi Zero W optimizations were not applied."
    echo "Re-run interactively or use --yes to approve them."
    return 0
  fi

  local answer
  read -r -p "Apply these Pi Zero W optimizations? [Y/n] " answer
  case "$answer" in
    ''|[Yy]|[Yy][Ee][Ss]) APPLY_ZERO_W_OPTIMIZATIONS=true ;;
    *) echo "Pi Zero W optimizations were skipped." ;;
  esac
}


prompt_pi_3b_optimizations() {
  IS_PI_3B=true

  cat <<'PI_3B_NOTICE'

Raspberry Pi 3 Model B detected.

RetroStation Player can reduce unused background activity by applying these
Pi 3B-only optimizations:

  - Disable the Bluetooth hardware overlay
    Turns off the onboard Bluetooth radio so it does not reserve hardware or
    consume power when Bluetooth devices are not being used.

  - Disable bluetooth.service and hciuart.service
    Stops the Linux Bluetooth stack and the UART helper that initializes the
    onboard Bluetooth controller during startup.

  - Disable ModemManager.service when installed
    Stops background scanning for cellular modems and mobile-broadband devices
    that are not used by RetroStation Player.

  - Disable triggerhappy.service when installed
    Stops the hotkey daemon that monitors hardware input events for button and
    keyboard shortcuts that are not needed by a Web UI-controlled player.

  - Disable unused console gettys on tty1 and tty3 through tty6
    Removes unused local login prompts with tty2 reserved exclusively for video playback.

  - Disable Wi-Fi power saving while RetroStation Player is running
    Keeps the wireless adapter fully awake to reduce stream buffering, latency,
    and brief network interruptions.

  - Use the performance CPU governor while RetroStation Player is running
    Keeps the CPU cores at their highest available clock during playback to
    reduce frequency-scaling delays and improve playback consistency.

The player keeps tty2, networking, SSH, systemd-journald, Avahi/mDNS, and
automatic package-update timers unchanged. Bluetooth keyboards, remotes,
controllers, and Bluetooth audio will no longer work after the required reboot.
PI_3B_NOTICE

  if [[ "$ASSUME_YES" == true ]]; then
    echo "--yes specified; applying Pi 3B optimizations."
    APPLY_PI_3B_OPTIMIZATIONS=true
    return 0
  fi

  if [[ ! -t 0 ]]; then
    echo "Non-interactive installation detected; Pi 3B optimizations were not applied."
    echo "Re-run interactively or use --yes to approve them."
    return 0
  fi

  local answer
  read -r -p "Apply these Pi 3B optimizations? [Y/n] " answer
  case "$answer" in
    ''|[Yy]|[Yy][Ee][Ss]) APPLY_PI_3B_OPTIMIZATIONS=true ;;
    *) echo "Pi 3B optimizations were skipped." ;;
  esac
}

prompt_pi_3b_plus_optimizations() {
  IS_PI_3B_PLUS=true

  cat <<'PI_3B_PLUS_NOTICE'

Raspberry Pi 3 Model B+ detected.

RetroStation Player can reduce unused background activity by applying these
Pi 3B+-only optimizations:

  - Disable the Bluetooth hardware overlay
    Turns off the onboard Bluetooth radio so it does not reserve hardware or
    consume power when Bluetooth devices are not being used.

  - Disable bluetooth.service and hciuart.service
    Stops the Linux Bluetooth stack and the UART helper that initializes the
    onboard Bluetooth controller during startup.

  - Disable ModemManager.service when installed
    Stops background scanning for cellular modems and mobile-broadband devices
    that are not used by RetroStation Player.

  - Disable triggerhappy.service when installed
    Stops the hotkey daemon that monitors hardware input events for button and
    keyboard shortcuts that are not needed by a Web UI-controlled player.

  - Disable unused console gettys on tty1 and tty3 through tty6
    Removes unused local login prompts with tty2 reserved exclusively for video playback.

  - Disable Wi-Fi power saving while RetroStation Player is running
    Keeps the wireless adapter fully awake to reduce stream buffering, latency,
    and brief network interruptions.

  - Use the performance CPU governor while RetroStation Player is running
    Keeps the CPU cores at their highest available clock during playback to
    reduce frequency-scaling delays and improve playback consistency.

The player keeps tty2, networking, SSH, systemd-journald, Avahi/mDNS, and
automatic package-update timers unchanged. Bluetooth keyboards, remotes,
controllers, and Bluetooth audio will no longer work after the required reboot.
PI_3B_PLUS_NOTICE

  if [[ "$ASSUME_YES" == true ]]; then
    echo "--yes specified; applying Pi 3B+ optimizations."
    APPLY_PI_3B_PLUS_OPTIMIZATIONS=true
    return 0
  fi

  if [[ ! -t 0 ]]; then
    echo "Non-interactive installation detected; Pi 3B+ optimizations were not applied."
    echo "Re-run interactively or use --yes to approve them."
    return 0
  fi

  local answer
  read -r -p "Apply these Pi 3B+ optimizations? [Y/n] " answer
  case "$answer" in
    ''|[Yy]|[Yy][Ee][Ss]) APPLY_PI_3B_PLUS_OPTIMIZATIONS=true ;;
    *) echo "Pi 3B+ optimizations were skipped." ;;
  esac
}


configure_pi_3b_boot_overlay() {
  local config_file backup timestamp
  config_file="$(find_pi_config_file)" || fatal "Unable to locate Raspberry Pi config.txt."

  if grep -Eq '^[[:space:]]*dtoverlay=disable-bt([[:space:]]*(#.*)?)?$' "$config_file"; then
    echo "Bluetooth hardware overlay is already disabled."
    return 0
  fi

  timestamp="$(date +%Y%m%d-%H%M%S)"
  backup="${config_file}.retrostation-player-pi-3b.${timestamp}.bak"
  cp -a -- "$config_file" "$backup"
  printf '
# RetroStation Player Pi 3B optimization
dtoverlay=disable-bt
' >> "$config_file"
  echo "Disabled Pi 3B Bluetooth hardware in: $config_file"
  echo "Backup created at: $backup"
  REBOOT_REQUIRED=true
}

configure_pi_3b_plus_boot_overlay() {
  local config_file backup timestamp
  config_file="$(find_pi_config_file)" || fatal "Unable to locate Raspberry Pi config.txt."

  if grep -Eq '^[[:space:]]*dtoverlay=disable-bt([[:space:]]*(#.*)?)?$' "$config_file"; then
    echo "Bluetooth hardware overlay is already disabled."
    return 0
  fi

  timestamp="$(date +%Y%m%d-%H%M%S)"
  backup="${config_file}.retrostation-player-pi-3b-plus.${timestamp}.bak"
  cp -a -- "$config_file" "$backup"
  printf '\n# RetroStation Player Pi 3B+ optimization\ndtoverlay=disable-bt\n' >> "$config_file"
  echo "Disabled Pi 3B+ Bluetooth hardware in: $config_file"
  echo "Backup created at: $backup"
  REBOOT_REQUIRED=true
}

configure_zero_w_boot_overlay() {
  local config_file backup timestamp
  config_file="$(find_pi_config_file)" || fatal "Unable to locate Raspberry Pi config.txt."

  if grep -Eq '^[[:space:]]*dtoverlay=disable-bt([[:space:]]*(#.*)?)?$' "$config_file"; then
    echo "Bluetooth hardware overlay is already disabled."
    return 0
  fi

  timestamp="$(date +%Y%m%d-%H%M%S)"
  backup="${config_file}.retrostation-player-zero-w.${timestamp}.bak"
  cp -a -- "$config_file" "$backup"
  printf '\n# RetroStation Player Pi Zero W optimization\ndtoverlay=disable-bt\n' >> "$config_file"
  echo "Disabled Pi Zero W Bluetooth hardware in: $config_file"
  echo "Backup created at: $backup"
  REBOOT_REQUIRED=true
}


configure_quiet_boot() {
  local cmdline_file=""
  local token
  local -a quiet_tokens=(quiet loglevel=3 systemd.show_status=false rd.systemd.show_status=false vt.global_cursor_default=0 logo.nologo consoleblank=0)

  if [[ -f /boot/firmware/cmdline.txt ]]; then
    cmdline_file=/boot/firmware/cmdline.txt
  elif [[ -f /boot/cmdline.txt ]]; then
    cmdline_file=/boot/cmdline.txt
  else
    echo "Boot command line was not found; skipped quiet-boot configuration."
    return 0
  fi

  local timestamp backup current
  timestamp="$(date +%Y%m%d-%H%M%S)"
  backup="${cmdline_file}.retrostation-player.${timestamp}.bak"
  current="$(tr '\n' ' ' < "$cmdline_file" | xargs)"

  for token in "${quiet_tokens[@]}"; do
    if [[ " $current " != *" $token "* ]]; then
      current+=" $token"
    fi
  done

  current="$(printf '%s' "$current" | xargs)"
  if [[ "$(tr '\n' ' ' < "$cmdline_file" | xargs)" != "$current" ]]; then
    cp -a -- "$cmdline_file" "$backup"
    printf '%s\n' "$current" > "$cmdline_file"
    echo "Enabled quiet boot in: $cmdline_file"
    echo "Backup created at: $backup"
    REBOOT_REQUIRED=true
  else
    echo "Quiet boot is already configured."
  fi
}

remove_quiet_boot_settings() {
  local cmdline_file="" token current
  local -a quiet_tokens=(quiet loglevel=3 systemd.show_status=false rd.systemd.show_status=false vt.global_cursor_default=0 logo.nologo consoleblank=0)
  if [[ -f /boot/firmware/cmdline.txt ]]; then
    cmdline_file=/boot/firmware/cmdline.txt
  elif [[ -f /boot/cmdline.txt ]]; then
    cmdline_file=/boot/cmdline.txt
  else
    return 0
  fi
  current="$(tr '\n' ' ' < "$cmdline_file" | xargs)"
  for token in "${quiet_tokens[@]}"; do
    current="$(printf ' %s ' "$current" | sed "s/[[:space:]]${token//./\.}[[:space:]]/ /g" | xargs)"
  done
  printf '%s\n' "$current" > "$cmdline_file"
}

unit_exists() {
  local unit="$1"
  systemctl list-unit-files "$unit" --no-legend 2>/dev/null | grep -q "^${unit}[[:space:]]"
}

disable_unit_if_present() {
  local unit="$1"
  if unit_exists "$unit"; then
    systemctl disable --now "$unit" 2>/dev/null || true
    echo "Disabled: $unit"
  else
    echo "Not installed; skipped: $unit"
  fi
}

install_startup_screen() {
  configure_quiet_boot

  local source_script="$INSTALL_DIR/scripts/retrostation-player-startup-screen"
  install -m 755 "$source_script" "$STARTUP_SCREEN_HELPER"

  cat > "$STARTUP_SCREEN_UNIT" <<EOF_STARTUP_UNIT
# Managed-By: RetroStation-Player
[Unit]
Description=RetroStation Player boot-time startup screen
After=local-fs.target systemd-user-sessions.service
Before=retrostation-player.service
Conflicts=getty@tty1.service getty@tty2.service serial-getty@tty2.service

[Service]
Type=simple
User=root
StandardInput=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
ExecStartPre=-/usr/bin/systemctl stop getty@tty2.service
ExecStartPre=-/usr/bin/systemctl stop serial-getty@tty2.service
ExecStartPre=/usr/bin/chvt 1
Environment=RETROSTATION_PLAYER_PORT=$PORT
Environment=RETROSTATION_PLAYER_PLAYBACK_TTY=2
Environment=RETROSTATION_PLAYER_PLAYBACK_READY_DELAY=3
Environment=RETROSTATION_PLAYER_STARTING_LOGO_PATH=/opt/retrostation-player/static/boot-logo-starting.png
Environment=RETROSTATION_PLAYER_READY_LOGO_PATH=/opt/retrostation-player/static/boot-logo-ready.png
ExecStart=$STARTUP_SCREEN_HELPER
TimeoutStartSec=0
TimeoutStopSec=5
KillMode=process

[Install]
WantedBy=multi-user.target
EOF_STARTUP_UNIT

  # tty2 is dedicated to DRM/VLC playback. Mask it even on upgrades so an
  # existing agetty cannot flash a login prompt during the logo-to-video handoff.
  systemctl disable --now getty@tty2.service 2>/dev/null || true
  systemctl mask getty@tty2.service 2>/dev/null || true
  systemctl disable --now serial-getty@tty2.service 2>/dev/null || true
  systemctl mask serial-getty@tty2.service 2>/dev/null || true

  systemctl daemon-reload
  systemctl enable retrostation-player-startup-screen.service
  echo "Installed boot-time startup screen service."
}

install_startup_screen_control_helper() {
  local source_helper="$INSTALL_DIR/scripts/retrostation-player-startup-screen-control-helper"
  [[ -f "$source_helper" ]] || fatal "Startup screen control helper is missing: $source_helper"
  install -d -m 755 -o root -g root "$(dirname "$STARTUP_SCREEN_CONTROL_HELPER")"
  install -m 755 -o root -g root "$source_helper" "$STARTUP_SCREEN_CONTROL_HELPER"
  cat > "$STARTUP_SCREEN_SUDOERS" <<EOF_SUDOERS
$SERVICE_USER ALL=(root) NOPASSWD: $STARTUP_SCREEN_CONTROL_HELPER *
EOF_SUDOERS
  chmod 440 "$STARTUP_SCREEN_SUDOERS"
  chown root:root "$STARTUP_SCREEN_SUDOERS"
  visudo -cf "$STARTUP_SCREEN_SUDOERS" >/dev/null || fatal "Generated sudoers rule is invalid: $STARTUP_SCREEN_SUDOERS"
}

apply_zero_w_optimizations() {
  [[ "$IS_PI_ZERO_W" == true && "$APPLY_ZERO_W_OPTIMIZATIONS" == true ]] || return 0

  configure_zero_w_boot_overlay

  disable_unit_if_present bluetooth.service
  disable_unit_if_present hciuart.service
  disable_unit_if_present ModemManager.service
  disable_unit_if_present triggerhappy.service

  local tty
  for tty in 1 2 3 4 5 6; do
    systemctl disable --now "getty@tty${tty}.service" 2>/dev/null || true
    systemctl mask "getty@tty${tty}.service" 2>/dev/null || true
    echo "Disabled unused console: getty@tty${tty}.service"
  done

  install_startup_screen

  cat > "$ZERO_W_TUNING_UNIT" <<'EOF_ZERO_W_UNIT'
# Managed-By: RetroStation-Player
[Unit]
Description=RetroStation Player Pi Zero W runtime tuning
After=network.target
Before=retrostation-player.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'test ! -w /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor || echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'
ExecStart=/bin/sh -c 'command -v iw >/dev/null 2>&1 && iw dev wlan0 set power_save off || true'
ExecStop=/bin/sh -c 'test ! -w /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor || echo ondemand > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor || true'

[Install]
WantedBy=multi-user.target
EOF_ZERO_W_UNIT

  systemctl daemon-reload
  systemctl enable retrostation-player-zero-w-tuning.service
  systemctl start retrostation-player-zero-w-tuning.service || true
  echo "Enabled Pi Zero W runtime CPU and Wi-Fi tuning."
}


apply_pi_3b_optimizations() {
  [[ "$IS_PI_3B" == true && "$APPLY_PI_3B_OPTIMIZATIONS" == true ]] || return 0

  configure_pi_3b_boot_overlay

  disable_unit_if_present bluetooth.service
  disable_unit_if_present hciuart.service
  disable_unit_if_present ModemManager.service
  disable_unit_if_present triggerhappy.service

  local tty
  for tty in 1 2 3 4 5 6; do
    systemctl disable --now "getty@tty${tty}.service" 2>/dev/null || true
    systemctl mask "getty@tty${tty}.service" 2>/dev/null || true
    echo "Disabled unused console: getty@tty${tty}.service"
  done

  install_startup_screen

  cat > "$PI_3B_TUNING_UNIT" <<'EOF_PI_3B_UNIT'
# Managed-By: RetroStation-Player
[Unit]
Description=RetroStation Player Pi 3B runtime tuning
After=network.target
Before=retrostation-player.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'for governor in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do test ! -w "$governor" || echo performance > "$governor"; done'
ExecStart=/bin/sh -c 'command -v iw >/dev/null 2>&1 && iw dev wlan0 set power_save off || true'
ExecStop=/bin/sh -c 'for governor in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do test ! -w "$governor" || echo ondemand > "$governor" || true; done'

[Install]
WantedBy=multi-user.target
EOF_PI_3B_UNIT

  systemctl daemon-reload
  systemctl enable retrostation-player-pi-3b-tuning.service
  systemctl start retrostation-player-pi-3b-tuning.service || true
  echo "Enabled Pi 3B runtime CPU and Wi-Fi tuning."
}

apply_pi_3b_plus_optimizations() {
  [[ "$IS_PI_3B_PLUS" == true && "$APPLY_PI_3B_PLUS_OPTIMIZATIONS" == true ]] || return 0

  configure_pi_3b_plus_boot_overlay

  disable_unit_if_present bluetooth.service
  disable_unit_if_present hciuart.service
  disable_unit_if_present ModemManager.service
  disable_unit_if_present triggerhappy.service

  local tty
  for tty in 1 2 3 4 5 6; do
    systemctl disable --now "getty@tty${tty}.service" 2>/dev/null || true
    systemctl mask "getty@tty${tty}.service" 2>/dev/null || true
    echo "Disabled unused console: getty@tty${tty}.service"
  done

  install_startup_screen

  cat > "$PI_3B_PLUS_TUNING_UNIT" <<'EOF_PI_3B_PLUS_UNIT'
# Managed-By: RetroStation-Player
[Unit]
Description=RetroStation Player Pi 3B+ runtime tuning
After=network.target
Before=retrostation-player.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'for governor in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do test ! -w "$governor" || echo performance > "$governor"; done'
ExecStart=/bin/sh -c 'command -v iw >/dev/null 2>&1 && iw dev wlan0 set power_save off || true'
ExecStop=/bin/sh -c 'for governor in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do test ! -w "$governor" || echo ondemand > "$governor" || true; done'

[Install]
WantedBy=multi-user.target
EOF_PI_3B_PLUS_UNIT

  systemctl daemon-reload
  systemctl enable retrostation-player-pi-3b-plus-tuning.service
  systemctl start retrostation-player-pi-3b-plus-tuning.service || true
  echo "Enabled Pi 3B+ runtime CPU and Wi-Fi tuning."
}

has_desktop_session() {
  pgrep -x Xorg >/dev/null 2>&1 ||
    pgrep -x Xwayland >/dev/null 2>&1 ||
    pgrep -x labwc >/dev/null 2>&1 ||
    pgrep -x wayfire >/dev/null 2>&1 ||
    pgrep -x weston >/dev/null 2>&1
}

connected_drm_connectors() {
  local status connector state
  for status in /sys/class/drm/card*-*/status; do
    [[ -r "$status" ]] || continue
    connector="${status%/status}"
    connector="${connector##*/}"
    connector="${connector#card*-}"
    case "$connector" in
      *Writeback*|*Virtual*) continue ;;
    esac
    state="$(<"$status")"
    [[ "$state" == "connected" ]] && printf '%s\n' "$connector"
  done
}

has_connected_connector_type() {
  local pattern="$1"
  local connector
  while IFS= read -r connector; do
    [[ "$connector" == *"$pattern"* ]] && return 0
  done < <(connected_drm_connectors)
  return 1
}

select_connected_connector() {
  local type_filter="$1"
  local connectors connector count
  connectors="$(connected_drm_connectors | grep "$type_filter" | sort -V || true)"
  [[ -n "$connectors" ]] || return 1
  count="$(printf '%s\n' "$connectors" | grep -c .)"
  connector="$(printf '%s\n' "$connectors" | head -n1)"
  if [[ "$count" -gt 1 ]]; then
    echo "Multiple connected $type_filter connectors detected; selecting $connector." >&2
    printf '%s\n' "$connectors" | sed 's/^/  /' >&2
  fi
  printf '%s\n' "$connector"
}

prompt_enable_composite() {
  if [[ "$ASSUME_YES" == true ]]; then
    return 0
  fi
  [[ -t 0 ]] || return 1

  local answer
  echo
  echo "No active HDMI, DisplayPort, DVI, or VGA connector was detected."
  read -r -p "Enable Raspberry Pi composite video output? [y/N] " answer
  [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

resolve_display_mode() {
  local connectors
  connectors="$(connected_drm_connectors || true)"

  case "$DISPLAY_MODE" in
    auto)
      if has_connected_connector_type "HDMI-A"; then
        DISPLAY_MODE="hdmi"
        DISPLAY_CONNECTOR="$(select_connected_connector "HDMI-A")"
        echo "Detected active HDMI DRM connector: $DISPLAY_CONNECTOR"
      elif [[ -n "$connectors" ]]; then
        DISPLAY_MODE="drm"
        DISPLAY_CONNECTOR="$(printf '%s\n' "$connectors" | sort -V | head -n1)"
        echo "Detected active DRM connector: $DISPLAY_CONNECTOR"
      elif has_desktop_session; then
        DISPLAY_MODE="desktop"
        echo "Detected an active graphical desktop session."
      elif is_raspberry_pi; then
        if prompt_enable_composite; then
          DISPLAY_MODE="composite"
        else
          fatal "No active display was detected. Re-run with --display composite, desktop, drm, or connect a display."
        fi
      else
        fatal "No active display was detected. Re-run with --display desktop or --display drm as appropriate."
      fi
      ;;
    hdmi)
      has_connected_connector_type "HDMI-A" || fatal "No active HDMI DRM connector was detected."
      DISPLAY_CONNECTOR="$(select_connected_connector "HDMI-A")"
      ;;
    desktop)
      if ! has_desktop_session; then
        echo "Warning: no active desktop process was detected; desktop mode may not display video." >&2
      fi
      ;;
    composite)
      is_raspberry_pi || fatal "Composite mode is supported only on Raspberry Pi systems."
      ;;
    drm)
      if [[ -z "$connectors" ]]; then
        echo "Warning: no active DRM connector is currently reported." >&2
      else
        DISPLAY_CONNECTOR="$(printf '%s\n' "$connectors" | sort -V | head -n1)"
      fi
      ;;
  esac

  echo "Selected display mode: $DISPLAY_MODE"
  if [[ -n "$DISPLAY_CONNECTOR" ]]; then
    echo "Selected DRM connector: $DISPLAY_CONNECTOR"
  fi
  return 0
}

find_pi_config_file() {
  local candidate
  for candidate in /boot/firmware/config.txt /boot/config.txt; do
    [[ -f "$candidate" ]] && { printf '%s\n' "$candidate"; return 0; }
  done
  return 1
}

configure_pi_composite() {
  local config_file backup timestamp
  config_file="$(find_pi_config_file)" || fatal "Unable to locate Raspberry Pi config.txt."
  timestamp="$(date +%Y%m%d-%H%M%S)"
  backup="${config_file}.retrostation-player.${timestamp}.bak"
  cp -a -- "$config_file" "$backup"

  python3 - "$config_file" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
lines = text.splitlines()
result = []
found_overlay = False
found_enable_tvout = False
found_sdtv_mode = False
found_sdtv_aspect = False

for line in lines:
    stripped = line.strip()
    if re.match(r"^dtoverlay=vc4-kms-v3d(?:,.*)?$", stripped):
        found_overlay = True
        prefix, _, options = stripped.partition(",")
        option_list = [item.strip() for item in options.split(",") if item.strip()]
        if "composite" not in option_list:
            option_list.append("composite")
        line = prefix + ("," + ",".join(option_list) if option_list else "")
    elif re.match(r"^enable_tvout=", stripped):
        found_enable_tvout = True
        line = "enable_tvout=1"
    elif re.match(r"^sdtv_mode=", stripped):
        found_sdtv_mode = True
        line = "sdtv_mode=0"
    elif re.match(r"^sdtv_aspect=", stripped):
        found_sdtv_aspect = True
        line = "sdtv_aspect=1"
    result.append(line)

if not found_overlay:
    result.append("dtoverlay=vc4-kms-v3d,composite")
if not found_enable_tvout:
    result.append("enable_tvout=1")
if not found_sdtv_mode:
    result.append("sdtv_mode=0")
if not found_sdtv_aspect:
    result.append("sdtv_aspect=1")

path.write_text("\n".join(result) + "\n", encoding="utf-8")
PY

  echo "Configured Raspberry Pi composite output in: $config_file"
  echo "Backup created at: $backup"
  REBOOT_REQUIRED=true
}

ensure_system_packages() {
  is_apt_cache_stale() {
    local apt_update_success_stamp="$1"
    local max_age_minutes="$2"
    local recent_update_stamp

    recent_update_stamp="$(find "$apt_update_success_stamp" -mmin "-$max_age_minutes" -print -quit 2>/dev/null || true)"
    [[ -z "$recent_update_stamp" ]]
  }

  local required_command package installed_version candidate_version candidate_policy
  local required_commands=(apt-get apt-cache dpkg-query dpkg)
  local packages=(python3 python3-venv mpv alsa-utils socat sudo)
  if [[ ( "$IS_PI_ZERO_W" == true && "$APPLY_ZERO_W_OPTIMIZATIONS" == true ) ||
        ( "$IS_PI_3B" == true && "$APPLY_PI_3B_OPTIMIZATIONS" == true ) ||
        ( "$IS_PI_3B_PLUS" == true && "$APPLY_PI_3B_PLUS_OPTIMIZATIONS" == true ) ]]; then
    packages+=(iw fbi)
  fi
  if [[ "$DISPLAY_MODE" == "composite" ]]; then
    packages+=(vlc)
    if [[ "$IS_PI_ZERO_W" == true ]]; then
      packages+=(ffmpeg)
    fi
  fi
  local package_installed_status="install ok installed"
  local apt_update_success_stamp="/var/lib/apt/periodic/update-success-stamp"
  local apt_cache_max_age_24h_minutes=1440

  for required_command in "${required_commands[@]}"; do
    command -v "$required_command" >/dev/null 2>&1 || fatal "$required_command is required."
  done

  if is_apt_cache_stale "$apt_update_success_stamp" "$apt_cache_max_age_24h_minutes"; then
    apt-get update || fatal "Failed to refresh apt package metadata. Check repository configuration and network access."
  fi

  for package in "${packages[@]}"; do
    if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "$package_installed_status"; then
      DEBIAN_FRONTEND=noninteractive apt-get install -y "$package" || fatal "Failed to install required package: $package"
      continue
    fi

    candidate_policy="$(apt-cache policy "$package" 2>/dev/null)" || fatal "Failed to query apt metadata for package: $package."
    installed_version="$(dpkg-query -W -f='${Version}' "$package" 2>/dev/null)"
    candidate_version="$(LC_ALL=C printf '%s\n' "$candidate_policy" | awk '$1 == "Candidate:" {print $2; exit}')"

    [[ -n "$candidate_version" && "$candidate_version" != "(none)" ]] || fatal "Unable to determine candidate version for package: $package."

    if dpkg --compare-versions "$installed_version" lt "$candidate_version"; then
      DEBIAN_FRONTEND=noninteractive apt-get install --only-upgrade -y "$package" || fatal "Failed to upgrade required package: $package"
    fi
  done
}


detect_hdmi_alsa_device() {
  local connector="$1"
  local port_index=0
  local -a devices=()
  command -v aplay >/dev/null 2>&1 || return 1
  mapfile -t devices < <(aplay -L 2>/dev/null | awk '/^hdmi:CARD=/{print}')
  [[ ${#devices[@]} -gt 0 ]] || return 1

  if [[ "$connector" =~ HDMI-A-([0-9]+)$ ]]; then
    port_index=$((BASH_REMATCH[1] - 1))
  fi
  if (( port_index >= 0 && port_index < ${#devices[@]} )); then
    printf '%s\n' "${devices[$port_index]}"
  else
    printf '%s\n' "${devices[0]}"
  fi
}

configure_player_json() {
  local config_file="$CONFIG_DIR/config.json"
  local hdmi_audio_device=""
  if [[ "$DISPLAY_MODE" == "hdmi" ]]; then
    hdmi_audio_device="$(detect_hdmi_alsa_device "$DISPLAY_CONNECTOR" || true)"
    [[ -n "$hdmi_audio_device" ]] || fatal "HDMI display was selected, but no ALSA HDMI audio device was detected."
    echo "Detected HDMI audio device: $hdmi_audio_device"
  fi
  python3 - "$config_file" "$DISPLAY_MODE" "$DISPLAY_CONNECTOR" "$hdmi_audio_device" <<'PYJSON'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
mode = sys.argv[2]
display_connector = sys.argv[3]
hdmi_audio_device = sys.argv[4]
data = json.loads(path.read_text(encoding="utf-8"))
legacy_path = data.get("mpv_path", "mpv")
legacy_args = list(data.get("mpv_extra_args", []))
data.pop("mpv_path", None)
data.pop("mpv_extra_args", None)
data["display_mode"] = mode
data["display_connector"] = display_connector if mode in {"hdmi", "drm"} else ""

if mode == "composite":
    data["player_backend"] = "vlc"
    data["player_path"] = "cvlc"
    data["player_extra_args"] = [
        "--aout=alsa",
        "--avcodec-hw=none",
        "--file-caching=1000",
        "--network-caching=1500",
    ]
    if data.get("display_resolution") not in {"576i", "480i", "288", "240"}:
        data["display_resolution"] = "480i"
    data.setdefault("crt_overscan", "none")
    data.setdefault("volume", 100)
    data.setdefault("muted", False)
    data["audio_output"] = "analog"
    data["audio_device"] = ""
    data["audio_control_mode"] = "alsa"
    data.setdefault("audio_card", 0)
    data.setdefault("audio_control", "auto")
else:
    args = list(data.get("player_extra_args", legacy_args))
    managed_prefixes = (
        "--vo=", "--gpu-context=", "--drm-connector=",
        "--drm-device=", "--drm-mode=", "--hwdec=", "--profile=",
        "--audio-device=",
    )
    args = [arg for arg in args if not arg.startswith(managed_prefixes)]
    if mode in {"drm", "hdmi"}:
        args[0:0] = ["--vo=gpu", "--gpu-context=drm", "--hwdec=no"]
        if mode == "hdmi":
            args.insert(3, f"--audio-device=alsa/{hdmi_audio_device}")
    else:
        args.insert(0, "--hwdec=auto-safe")
    data["player_backend"] = "mpv"
    data["player_path"] = legacy_path if legacy_path != "cvlc" else "mpv"
    data["player_extra_args"] = args
    if mode in {"hdmi", "drm"}:
        # The application validates this against the connected connector's modes.
        # Leave an existing digital mode intact; otherwise the first advertised
        # connector mode becomes the default when settings are loaded.
        if data.get("display_resolution") in {"576i", "480i", "288", "240"}:
            data["display_resolution"] = ""
    else:
        data["display_resolution"] = ""
    if mode == "hdmi":
        data["audio_output"] = "hdmi"
        data["audio_device"] = hdmi_audio_device
        data["audio_control_mode"] = "external"
    else:
        data["audio_output"] = data.get("audio_output", "analog")
        data["audio_device"] = data.get("audio_device", "")
        data["audio_control_mode"] = data.get("audio_control_mode", "alsa")

path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PYJSON

  if [[ "$DISPLAY_MODE" == "hdmi" || "$DISPLAY_MODE" == "drm" ]]; then
    local detected_mode="" modes_file=""
    if [[ -n "$DISPLAY_CONNECTOR" ]]; then
      for modes_file in /sys/class/drm/card*-${DISPLAY_CONNECTOR}/modes; do
        [[ -f "$modes_file" ]] && break
        modes_file=""
      done
    fi
    if [[ -n "$modes_file" && -f "$modes_file" ]]; then
      detected_mode="$(awk 'NF && $0 !~ /i$/ {print; exit}' "$modes_file")"
    fi
    if [[ -n "$detected_mode" ]]; then
      python3 - "$config_file" "$detected_mode" <<'PYMODE'
from pathlib import Path
import json
import sys
path = Path(sys.argv[1])
mode = sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
if not data.get("display_resolution"):
    data["display_resolution"] = mode
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PYMODE
      echo "Detected display resolution: $detected_mode"
    fi
  fi
}

install_composite_overscan_helper() {
  local source_helper="$INSTALL_DIR/scripts/retrostation-player-composite-overscan-helper"
  [[ -f "$source_helper" ]] || fatal "Composite overscan helper is missing: $source_helper"
  install -d -m 755 -o root -g root "$(dirname "$COMPOSITE_OVERSCAN_HELPER")"
  install -m 755 -o root -g root "$source_helper" "$COMPOSITE_OVERSCAN_HELPER"
  cat > "$COMPOSITE_OVERSCAN_SUDOERS" <<EOF_SUDOERS
$SERVICE_USER ALL=(root) NOPASSWD: $COMPOSITE_OVERSCAN_HELPER *
EOF_SUDOERS
  chmod 440 "$COMPOSITE_OVERSCAN_SUDOERS"
  chown root:root "$COMPOSITE_OVERSCAN_SUDOERS"
  visudo -cf "$COMPOSITE_OVERSCAN_SUDOERS" >/dev/null || fatal "Generated sudoers rule is invalid: $COMPOSITE_OVERSCAN_SUDOERS"
}

write_service_file() {
  {
    echo "$OWNERSHIP_MARKER"
    cat <<EOF_SERVICE
[Unit]
Description=RetroStation Player
Wants=network-online.target
After=network-online.target systemd-user-sessions.service
EOF_SERVICE

    if [[ "$IS_PI_ZERO_W" == true && "$APPLY_ZERO_W_OPTIMIZATIONS" == true ]]; then
      echo 'Wants=retrostation-player-zero-w-tuning.service'
      echo 'After=retrostation-player-zero-w-tuning.service'
    fi
    if [[ "$IS_PI_3B" == true && "$APPLY_PI_3B_OPTIMIZATIONS" == true ]]; then
      echo 'Wants=retrostation-player-pi-3b-tuning.service'
      echo 'After=retrostation-player-pi-3b-tuning.service'
    fi
    if [[ "$IS_PI_3B_PLUS" == true && "$APPLY_PI_3B_PLUS_OPTIMIZATIONS" == true ]]; then
      echo 'Wants=retrostation-player-pi-3b-plus-tuning.service'
      echo 'After=retrostation-player-pi-3b-plus-tuning.service'
    fi

    if [[ "$DISPLAY_MODE" == "composite" ]]; then
      echo 'Conflicts=getty@tty2.service'
    fi

    cat <<EOF_SERVICE

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
SupplementaryGroups=video render audio
WorkingDirectory=$INSTALL_DIR
Environment=RETROSTATION_PLAYER_CONFIG_DIR=$CONFIG_DIR
Environment=RETROSTATION_PLAYER_STATE_DIR=$STATE_DIR
EOF_SERVICE

    if [[ "$DISPLAY_MODE" == "desktop" ]]; then
      echo 'Environment=DISPLAY=:0'
    elif [[ "$DISPLAY_MODE" == "composite" ]]; then
      cat <<'EOF_SERVICE'
# The startup-screen service owns tty1 until playback is initialized. Do not
# switch to tty2 here; doing so blanks composite output before VLC is ready.
StandardOutput=journal
StandardError=journal
EOF_SERVICE
    fi

    cat <<EOF_SERVICE
ExecStart=$INSTALL_DIR/.venv/bin/waitress-serve --host=0.0.0.0 --port=$PORT retrostation_player.app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF_SERVICE
  } > "$SERVICE_FILE"
}

cmd_install() {
  [[ "$(uname -s)" == "Linux" ]] || fatal "This installer supports Linux only."
  [[ $EUID -eq 0 ]] || fatal "Run this installer as root (sudo)."
  command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]] || fatal "systemd is required."

  if is_original_pi_zero_w; then
    prompt_streaming_notice
    prompt_zero_w_optimizations
  elif is_pi_3b; then
    prompt_pi_3b_optimizations
  elif is_pi_3b_plus; then
    prompt_pi_3b_plus_optimizations
  fi

  resolve_display_mode
  ensure_system_packages

  if [[ "$DISPLAY_MODE" == "composite" ]]; then
    configure_pi_composite
  fi

  local SOURCE_DIR
  SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

  if [[ -f "$SERVICE_FILE" ]] && ! grep -Fqx "$OWNERSHIP_MARKER" "$SERVICE_FILE"; then
    fatal "Refusing to overwrite unrecognized service unit: $SERVICE_FILE"
  fi

  if command -v ss >/dev/null 2>&1 && ss -H -ltn "sport = :$PORT" 2>/dev/null | grep -q .; then
    if ! systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
      fatal "TCP port $PORT is already in use. Nothing was stopped or modified."
    fi
  fi

  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
  fi

  for group in video render audio; do
    getent group "$group" >/dev/null 2>&1 && usermod -aG "$group" "$SERVICE_USER" || true
  done

  if [[ -f "$SERVICE_FILE" ]]; then
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  fi

  assert_safe_install_dir "$INSTALL_DIR"

  mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$STATE_DIR"
  find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  (
    cd "$SOURCE_DIR"
    tar --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
        --exclude='.pytest_cache' --exclude='*.pyc' -cf - .
  ) | tar -xf - -C "$INSTALL_DIR"

  python3 -m venv "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
  "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

  if [[ ! -f "$CONFIG_DIR/config.json" ]]; then
    cp "$INSTALL_DIR/config.example.json" "$CONFIG_DIR/config.json"
  fi
  configure_player_json

  chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR" "$STATE_DIR"
  chown root:"$SERVICE_USER" "$CONFIG_DIR" "$CONFIG_DIR/config.json"
  chmod 750 "$CONFIG_DIR"
  chmod 660 "$CONFIG_DIR/config.json"

  install_composite_overscan_helper
  install_startup_screen_control_helper
  write_service_file
  apply_zero_w_optimizations
  apply_pi_3b_optimizations
  apply_pi_3b_plus_optimizations

  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}.service"
  if [[ "$REBOOT_REQUIRED" == false ]]; then
    systemctl start "${SERVICE_NAME}.service" || true
  fi

  local PLAYER_IP PLAYER_HOSTNAME PLAYER_FQDN
  PLAYER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')" || true
  PLAYER_HOSTNAME="$(hostname 2>/dev/null)" || true
  PLAYER_FQDN="$(hostname -f 2>/dev/null)" || true

  echo
  echo "RetroStation Player installed."
  echo "Application: $INSTALL_DIR"
  echo "Configuration: $CONFIG_DIR/config.json"
  echo "State: $STATE_DIR"
  echo "Service: $SERVICE_NAME"
  echo "Display mode: $DISPLAY_MODE"
  echo "Port: $PORT"
  if [[ -n "${PLAYER_HOSTNAME:-}" ]]; then
    echo "Hostname: $PLAYER_HOSTNAME"
  fi
  if [[ -n "${PLAYER_FQDN:-}" && "${PLAYER_FQDN:-}" != "${PLAYER_HOSTNAME:-}" ]]; then
    echo "FQDN: $PLAYER_FQDN"
  fi
  echo
  if [[ "$REBOOT_REQUIRED" == true ]]; then
    if [[ "$APPLY_ZERO_W_OPTIMIZATIONS" == true ]]; then
      echo "A reboot is required to apply the Pi Zero W hardware optimizations"
      echo "and any Raspberry Pi display configuration changes:"
    elif [[ "$APPLY_PI_3B_OPTIMIZATIONS" == true ]]; then
      echo "A reboot is required to apply the Pi 3B hardware optimizations"
      echo "and any Raspberry Pi display configuration changes:"
    elif [[ "$APPLY_PI_3B_PLUS_OPTIMIZATIONS" == true ]]; then
      echo "A reboot is required to apply the Pi 3B+ hardware optimizations"
      echo "and any Raspberry Pi display configuration changes:"
    else
      echo "A reboot is required before composite video can be used:"
    fi
    echo "  sudo reboot"
  else
    echo "RetroStation Player was started."
  fi
  echo
  if [[ -n "${PLAYER_IP:-}" ]]; then
    echo "Open the web interface to complete setup:"
    echo "  http://$PLAYER_IP:$PORT"
    if [[ -n "${PLAYER_HOSTNAME:-}" ]]; then
      echo "  http://$PLAYER_HOSTNAME.local:$PORT"
    fi
  else
    echo "Open the web interface to complete setup:"
    if [[ -n "${PLAYER_HOSTNAME:-}" ]]; then
      echo "  http://$PLAYER_HOSTNAME.local:$PORT"
    else
      echo "  http://PLAYER-IP:$PORT"
    fi
  fi
}

restore_pi_boot_config_for_purge() {
  local config_file backup_dir backup_pattern oldest_backup
  config_file="$(find_pi_config_file 2>/dev/null || true)"
  [[ -n "$config_file" ]] || return 0

  backup_dir="$(dirname "$config_file")"
  backup_pattern="$(basename "$config_file").retrostation-player."
  oldest_backup="$(find "$backup_dir" -maxdepth 1 -type f \
    \( -name "${backup_pattern}*.bak" -o -name "$(basename "$config_file").retrostation-player-zero-w.*.bak" -o -name "$(basename "$config_file").retrostation-player-pi-3b.*.bak" -o -name "$(basename "$config_file").retrostation-player-pi-3b-plus.*.bak" \) \
    -printf '%p\n' 2>/dev/null | sort | head -n1)"

  if [[ -n "$oldest_backup" ]]; then
    cp -a -- "$oldest_backup" "$config_file"
    echo "Restored Raspberry Pi boot configuration from: $oldest_backup"
  fi

  find "$backup_dir" -maxdepth 1 -type f \
    \( -name "${backup_pattern}*.bak" -o -name "$(basename "$config_file").retrostation-player-zero-w.*.bak" -o -name "$(basename "$config_file").retrostation-player-pi-3b.*.bak" -o -name "$(basename "$config_file").retrostation-player-pi-3b-plus.*.bak" \) \
    -delete 2>/dev/null || true
}

assert_safe_purge_dir() {
  local actual="$1" expected="$2"
  local resolved_actual="$actual" resolved_expected="$expected"
  if command -v realpath >/dev/null 2>&1; then
    resolved_actual="$(realpath -m -- "$actual")"
    resolved_expected="$(realpath -m -- "$expected")"
  fi
  [[ "$resolved_actual" == "$resolved_expected" ]] || fatal "Refusing unsafe purge path: $resolved_actual"
}

cmd_uninstall() {
  [[ "$(uname -s)" == "Linux" ]] || fatal "This uninstaller supports Linux only."
  [[ $EUID -eq 0 ]] || fatal "Run this uninstaller as root (sudo)."

  if [[ -f "$SERVICE_FILE" ]]; then
    if ! grep -Fqx "$OWNERSHIP_MARKER" "$SERVICE_FILE"; then
      fatal "Refusing to remove unrecognized service unit: $SERVICE_FILE"
    fi
    systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
  else
    systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
  fi

  rm -f "$COMPOSITE_OVERSCAN_HELPER" "$COMPOSITE_OVERSCAN_SUDOERS" "$STARTUP_SCREEN_HELPER" "$STARTUP_SCREEN_CONTROL_HELPER" "$STARTUP_SCREEN_SUDOERS"

  if [[ -f "$STARTUP_SCREEN_UNIT" ]] && grep -Fqx "$OWNERSHIP_MARKER" "$STARTUP_SCREEN_UNIT"; then
    systemctl disable --now retrostation-player-startup-screen.service 2>/dev/null || true
    rm -f "$STARTUP_SCREEN_UNIT"
    systemctl daemon-reload
  fi

  assert_safe_install_dir "$INSTALL_DIR"
  if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf -- "$INSTALL_DIR"
  fi

  if [[ "$PURGE" == true ]]; then
    assert_safe_purge_dir "$CONFIG_DIR" "/etc/retrostation-player"
    assert_safe_purge_dir "$STATE_DIR" "/var/lib/retrostation-player"

    remove_quiet_boot_settings
    restore_pi_boot_config_for_purge
    if [[ -f "$ZERO_W_TUNING_UNIT" ]] && grep -Fqx "$OWNERSHIP_MARKER" "$ZERO_W_TUNING_UNIT"; then
      systemctl disable --now retrostation-player-zero-w-tuning.service 2>/dev/null || true
      rm -f "$ZERO_W_TUNING_UNIT"
      systemctl daemon-reload
    fi
    if [[ -f "$PI_3B_TUNING_UNIT" ]] && grep -Fqx "$OWNERSHIP_MARKER" "$PI_3B_TUNING_UNIT"; then
      systemctl disable --now retrostation-player-pi-3b-tuning.service 2>/dev/null || true
      rm -f "$PI_3B_TUNING_UNIT"
      systemctl daemon-reload
    fi
    if [[ -f "$PI_3B_PLUS_TUNING_UNIT" ]] && grep -Fqx "$OWNERSHIP_MARKER" "$PI_3B_PLUS_TUNING_UNIT"; then
      systemctl disable --now retrostation-player-pi-3b-plus-tuning.service 2>/dev/null || true
      rm -f "$PI_3B_PLUS_TUNING_UNIT"
      systemctl daemon-reload
    fi
    if [[ -f "$STARTUP_SCREEN_UNIT" ]] && grep -Fqx "$OWNERSHIP_MARKER" "$STARTUP_SCREEN_UNIT"; then
      systemctl disable --now retrostation-player-startup-screen.service 2>/dev/null || true
      rm -f "$STARTUP_SCREEN_UNIT"
      systemctl daemon-reload
    fi
    for tty in 1 2 3 4 5 6; do
      systemctl unmask "getty@tty${tty}.service" 2>/dev/null || true
    done
    rm -rf -- "$CONFIG_DIR" "$STATE_DIR"

    if getent passwd "$SERVICE_USER" >/dev/null 2>&1; then
      userdel "$SERVICE_USER" 2>/dev/null || userdel -f "$SERVICE_USER" 2>/dev/null || true
    fi
    if getent group "$SERVICE_USER" >/dev/null 2>&1; then
      groupdel "$SERVICE_USER" 2>/dev/null || true
    fi
    systemctl reset-failed "$SERVICE_NAME" 2>/dev/null || true

    cat <<MSG
RetroStation Player was purged.
Removed application:   $INSTALL_DIR
Removed configuration: $CONFIG_DIR
Removed state:         $STATE_DIR
Removed service user:  $SERVICE_USER

Installer-created Raspberry Pi boot configuration backups were removed. If a
composite installation backup was available, the oldest pre-install backup was
restored. Reboot the Raspberry Pi for restored display settings to take effect.

Shared operating-system packages were retained because other applications may use them.
No RetroStation MC or RetroIPTVGuide service, process, user, or directory was modified.
MSG
  else
    cat <<MSG
RetroStation Player application files were removed.
Retained configuration: $CONFIG_DIR
Retained state:         $STATE_DIR
Retained service user:  $SERVICE_USER

Raspberry Pi boot configuration changes are retained. Restore the timestamped
config.txt backup manually if composite output was enabled by this installer.

Run 'setup.sh uninstall --purge' to remove all RetroStation Player configuration,
state, service-account, and installer-created boot-backup files.

No RetroStation MC or RetroIPTVGuide service, process, user, or directory was modified.
MSG
  fi
}

parse_args "$@"

case "$COMMAND" in
  install) cmd_install ;;
  uninstall) cmd_uninstall ;;
esac
