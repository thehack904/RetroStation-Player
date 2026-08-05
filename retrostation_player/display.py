from __future__ import annotations

from pathlib import Path
import re
import subprocess

_COMPOSITE_MODE_LABELS = {
    "720x576i": "576i",
    "720x480i": "480i",
    "720x288": "288",
    "720x240": "240",
}

_COMPOSITE_MODE_VALUES = {
    "576i": ("720x576", 720, 576),
    "480i": ("720x480", 720, 480),
    "288": ("720x288", 720, 288),
    "240": ("720x240", 720, 240),
}

_OVERSCAN_PRESETS = {
    "none": (0.00, 0.00),
    "light": (0.03, 0.02),
    "standard": (0.06, 0.04),
    "heavy": (0.09, 0.06),
}


def normalize_connector_name(connector: str) -> str:
    """Return mpv/sysfs connector name without the DRM card prefix."""
    value = str(connector).strip()
    return re.sub(r"^card\d+-", "", value)




def connected_connector_names(connector_pattern: str = "*") -> list[str]:
    """Return connected DRM connector names without card prefixes."""
    connectors: list[str] = []
    seen: set[str] = set()
    for status_path in Path("/sys/class/drm").glob(f"card*-{connector_pattern}-*/status"):
        try:
            if status_path.read_text(encoding="utf-8").strip() != "connected":
                continue
        except OSError:
            continue
        name = normalize_connector_name(status_path.parent.name)
        if name and name not in seen:
            seen.add(name)
            connectors.append(name)
    return sorted(connectors, key=_natural_connector_key)


def _natural_connector_key(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value))


def select_active_connector(display_mode: str, preferred: str = "") -> str:
    """Select the connected connector for the current runtime display mode."""
    mode = display_mode.casefold()
    pattern = "HDMI-A" if mode == "hdmi" else "*"
    connected = connected_connector_names(pattern)
    preferred = normalize_connector_name(preferred)
    if preferred in connected:
        return preferred
    return connected[0] if connected else ""


def detect_hdmi_audio_device(connector: str = "") -> str:
    """Map HDMI-A-N to the corresponding ALSA hdmi: device."""
    try:
        completed = subprocess.run(
            ["aplay", "-L"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""
    devices = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.startswith("hdmi:CARD=")
    ]
    if not devices:
        return ""
    match = re.search(r"HDMI-A-(\d+)$", normalize_connector_name(connector))
    index = max(0, int(match.group(1)) - 1) if match else 0
    return devices[index] if index < len(devices) else devices[0]


def _connected_mode_files(connector_pattern: str, connector: str = "") -> list[Path]:
    connector = normalize_connector_name(connector)
    result: list[Path] = []
    for modes_path in Path("/sys/class/drm").glob(f"card*-{connector_pattern}-*/modes"):
        if connector and not modes_path.parent.name.endswith(f"-{connector}"):
            continue
        status_path = modes_path.parent / "status"
        try:
            if status_path.read_text(encoding="utf-8").strip() != "connected":
                continue
        except OSError:
            continue
        result.append(modes_path)
    return result


def _read_unique_modes(paths: list[Path]) -> list[str]:
    modes: list[str] = []
    seen: set[str] = set()
    for modes_path in paths:
        try:
            lines = modes_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            mode = line.strip()
            # mpv's DRM output on the Raspberry Pi 3B+ cannot reliably
            # activate the EDID-advertised interlaced HDMI modes. Do not
            # expose modes such as 1920x1080i or 720x480i in the Web UI.
            if mode.endswith("i"):
                continue
            if mode and mode not in seen:
                seen.add(mode)
                modes.append(mode)
    return modes


def detected_resolution_labels(display_mode: str = "composite", connector: str = "", hardware_profile: str = "default") -> list[str]:
    """Return display resolutions supported by the selected output path."""
    mode = display_mode.casefold()
    if mode == "composite":
        # Composite playback uses VLC's explicit drm_vout mode selection rather
        # than the HDMI/DRM EDID list. Expose every composite mode supported by
        # the player even when sysfs advertises only the currently active NTSC
        # mode (normally 720x480i). Interlaced filtering applies only to mpv's
        # HDMI/DRM path.
        return ["576i", "480i", "288", "240"]

    if mode == "hdmi":
        detected = _read_unique_modes(_connected_mode_files("HDMI-A", connector))
        if hardware_profile == "rpi-zero-w":
            allowed: list[str] = []
            if "1280x720" in detected:
                allowed.extend(["1280x720@59.94", "1280x720@60"])
            if "720x480" in detected:
                allowed.extend(["720x480@59.94", "720x480@60"])
            if "640x480" in detected:
                allowed.extend(["640x480@59.94", "640x480@60"])
            return allowed
        return detected

    if mode == "drm":
        return _read_unique_modes(_connected_mode_files("*", connector))

    return []


def default_resolution(display_mode: str, detected: list[str] | None = None, hardware_profile: str = "default") -> str:
    mode = display_mode.casefold()
    available = detected if detected is not None else detected_resolution_labels(mode, hardware_profile=hardware_profile)
    if available:
        if mode == "composite" and "480i" in available:
            return "480i"
        if hardware_profile == "rpi-zero-w":
            for preferred in ("1280x720@59.94", "1280x720@60", "720x480@59.94", "720x480@60", "640x480@59.94", "640x480@60"):
                if preferred in available:
                    return preferred
        return available[0]
    return "480i" if mode == "composite" else ""


def resolution_details(label: str) -> tuple[str, int, int]:
    try:
        return _COMPOSITE_MODE_VALUES[label]
    except KeyError as exc:
        raise ValueError(f"Unsupported composite display resolution: {label}") from exc


def overscan_padding(label: str, preset: str) -> tuple[int, int]:
    _, width, height = resolution_details(label)
    try:
        horizontal, vertical = _OVERSCAN_PRESETS[preset]
    except KeyError as exc:
        raise ValueError(f"Unsupported CRT overscan preset: {preset}") from exc
    return round(width * horizontal), round(height * vertical)


def normalize_custom_alignment(value: object, label: str) -> dict[str, int]:
    """Validate and normalize custom CRT padding for a composite mode."""
    _, width, height = resolution_details(label)
    source = value if isinstance(value, dict) else {}
    result: dict[str, int] = {}
    limits = {"left": width // 4, "right": width // 4, "top": height // 4, "bottom": height // 4}
    for edge, limit in limits.items():
        try:
            amount = int(source.get(edge, 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Custom CRT {edge} value must be an integer") from exc
        if not 0 <= amount <= limit:
            raise ValueError(f"Custom CRT {edge} value must be from 0 to {limit}")
        result[edge] = amount
    if width - result["left"] - result["right"] < 320:
        raise ValueError("Custom CRT alignment leaves less than 320 visible horizontal pixels")
    if height - result["top"] - result["bottom"] < 200:
        raise ValueError("Custom CRT alignment leaves less than 200 visible vertical pixels")
    return result


def valid_overscan_presets() -> tuple[str, ...]:
    return (*_OVERSCAN_PRESETS, "custom")
