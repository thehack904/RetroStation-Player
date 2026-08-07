from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .display import normalize_connector_name

DEFAULT_CONFIG: dict[str, Any] = {
    "m3u_url": "http://ersatztv.local:8409/iptv/channels.m3u",
    "listen_host": "0.0.0.0",
    "listen_port": 5050,
    "autoplay": True,
    "fullscreen": True,
    "player_backend": "mpv",
    "player_path": "mpv",
    "player_extra_args": ["--hwdec=auto-safe", "--no-osc", "--no-input-default-bindings"],
    "mpv_path": "mpv",
    "mpv_extra_args": ["--hwdec=auto-safe", "--no-osc", "--no-input-default-bindings"],
    "request_timeout_seconds": 15,
    "display_mode": "desktop",
    "display_connector": "",
    "display_resolution": "",
    "crt_overscan": "none",
    "crt_custom_alignment": {"left": 0, "right": 0, "top": 0, "bottom": 0},
    "hdmi_underscan_percent": 0,
    "zero_w_video_sizing": "auto",
    "volume": 100,
    "muted": False,
    "audio_output": "analog",
    "audio_device": "",
    "audio_control_mode": "alsa",
    "audio_card": 0,
    "audio_control": "auto",
    "streaming_notice_acknowledged": False,
    "boot_logo_enabled": True,
    "default_channel_id": "",
}


def config_dir() -> Path:
    return Path(os.environ.get("RETROSTATION_PLAYER_CONFIG_DIR", "/etc/retrostation-player"))


def state_dir() -> Path:
    return Path(os.environ.get("RETROSTATION_PLAYER_STATE_DIR", "/var/lib/retrostation-player"))


def load_config() -> dict[str, Any]:
    path = config_dir() / "config.json"
    if not path.exists():
        return DEFAULT_CONFIG.copy()
    with path.open("r", encoding="utf-8") as handle:
        user_config = json.load(handle)
    merged = DEFAULT_CONFIG.copy()
    merged.update(user_config)
    merged["display_connector"] = normalize_connector_name(merged.get("display_connector", ""))

    # Preserve compatibility with v0.1.0 configuration files.
    if "player_path" not in user_config and "mpv_path" in user_config:
        merged["player_path"] = user_config["mpv_path"]
    if "player_extra_args" not in user_config and "mpv_extra_args" in user_config:
        merged["player_extra_args"] = user_config["mpv_extra_args"]

    return merged


def ensure_directories() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)


def save_config(updates: dict[str, Any]) -> None:
    """Merge *updates* into the stored config and persist it to disk."""
    ensure_directories()
    path = config_dir() / "config.json"
    current = load_config()
    current.update(updates)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(current, handle, indent=2)
        handle.write("\n")


def state_file() -> Path:
    return state_dir() / "state.json"



COMPOSITE_OVERSCAN_HELPER = Path("/usr/local/libexec/retrostation-player-composite-overscan")
STARTUP_SCREEN_HELPER = Path("/usr/local/libexec/retrostation-player-startup-screen-control")


def kernel_cmdline_path() -> Path:
    for candidate in (Path("/boot/firmware/cmdline.txt"), Path("/boot/cmdline.txt")):
        if candidate.exists():
            return candidate
    return Path("/boot/firmware/cmdline.txt")


def _run_privileged_display_helper(arguments: list[str], timeout: int = 10) -> str:
    import subprocess
    command = ["sudo", "-n", str(COMPOSITE_OVERSCAN_HELPER), *arguments]
    try:
        completed = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        raise OSError("sudo is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise OSError("Timed out running the privileged display helper") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise OSError(detail or "Privileged display helper failed")
    return completed.stdout.strip()


def save_zero_w_composite_overscan(resolution: str, values: dict[str, int] | None) -> Path:
    """Write KMS composite margins to the kernel command line."""
    arguments = ["disable", resolution]
    if values and any(int(values.get(edge, 0)) for edge in ("left", "right", "top", "bottom")):
        arguments = [resolution, *(str(int(values.get(edge, 0))) for edge in ("left", "right", "top", "bottom"))]
    output = _run_privileged_display_helper(arguments)
    return Path(output) if output else kernel_cmdline_path()


def request_system_reboot() -> None:
    _run_privileged_display_helper(["reboot"], timeout=5)


def reset_zero_w_composite_overscan() -> str:
    """Remove current KMS margins and the older managed firmware overscan block."""
    return _run_privileged_display_helper(["reset-original"])




def show_startup_screen() -> None:
    """Return the local display to the enabled RetroStation Player logo."""
    import subprocess

    command = ["sudo", "-n", str(STARTUP_SCREEN_HELPER), "show"]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise OSError("Unable to display the startup screen") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise OSError(detail or "Startup screen helper failed")

def set_startup_screen_enabled(enabled: bool) -> None:
    import subprocess

    command = ["sudo", "-n", str(STARTUP_SCREEN_HELPER), "enable" if enabled else "disable"]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError as exc:
        raise OSError("sudo is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise OSError("Timed out running the startup screen helper") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise OSError(detail or "Startup screen helper failed")
