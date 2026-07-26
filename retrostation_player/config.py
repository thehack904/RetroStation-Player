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
    "zero_w_video_sizing": "auto",
    "volume": 100,
    "muted": False,
    "audio_output": "analog",
    "audio_device": "",
    "audio_control_mode": "alsa",
    "audio_card": 0,
    "audio_control": "PCM",
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
