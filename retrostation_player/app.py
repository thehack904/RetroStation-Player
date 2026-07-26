from __future__ import annotations

import atexit
import logging
import threading
import time
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

from .channels import Channel, fetch_channels, find_channel
from .config import config_dir, ensure_directories, load_config, save_config
from .display import (
    default_resolution,
    detect_hdmi_audio_device,
    detected_resolution_labels,
    select_active_connector,
    valid_overscan_presets,
)
from .logs import (
    DEFAULT_LINES,
    MAX_LINES,
    configure_logging,
    format_runtime_entries,
    normalize_line_count,
    read_journal,
    runtime_log_buffer,
)
from .player import MediaPlayer, PlayerError
from .system_info import collect_system_info

_EDITABLE_KEYS: frozenset[str] = frozenset(
    {
        "m3u_url",
        "autoplay",
        "fullscreen",
        "request_timeout_seconds",
        "display_mode",
        "display_resolution",
        "crt_overscan",
        "volume",
        "muted",
        "zero_w_video_sizing",
    }
)


def create_app() -> Flask:
    configure_logging()
    logger = logging.getLogger("retrostation_player.app")
    ensure_directories()
    config = load_config()
    initial_system_info = collect_system_info()
    hardware_profile = str(initial_system_info.get("hardware_profile", "default"))

    def resolve_runtime_display_binding(persist: bool = True) -> bool:
        display_mode = str(config.get("display_mode", "desktop")).casefold()
        if display_mode not in {"hdmi", "drm"}:
            return False
        connector = select_active_connector(display_mode, str(config.get("display_connector", "")))
        if not connector:
            return False
        detected = detected_resolution_labels(display_mode, connector, hardware_profile)
        resolution = str(config.get("display_resolution", ""))
        if resolution not in detected:
            resolution = default_resolution(display_mode, detected, hardware_profile)
        updates: dict[str, Any] = {
            "display_connector": connector,
            "display_resolution": resolution,
        }
        if display_mode == "hdmi":
            audio_device = detect_hdmi_audio_device(connector)
            if audio_device:
                updates.update(
                    {
                        "audio_output": "hdmi",
                        "audio_device": audio_device,
                        "audio_control_mode": "external",
                    }
                )
        changed = any(config.get(key) != value for key, value in updates.items())
        config.update(updates)
        if changed and persist:
            save_config(updates)
        return changed

    resolve_runtime_display_binding()
    logger.info("RetroStation Player starting with hardware profile %s", hardware_profile)
    cached_raspberry_pi_info = initial_system_info if initial_system_info.get("is_raspberry_pi") else None
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    player = MediaPlayer(
        backend=str(config.get("player_backend", "mpv")),
        player_path=str(config.get("player_path", config.get("mpv_path", "mpv"))),
        fullscreen=bool(config["fullscreen"]),
        extra_args=list(
            config.get("player_extra_args", config.get("mpv_extra_args", []))
        ),
        display_mode=str(config.get("display_mode", "desktop")),
        display_connector=str(config.get("display_connector", "")),
        display_resolution=str(config.get("display_resolution", "")),
        crt_overscan=str(config.get("crt_overscan", "none")),
        volume=int(config.get("volume", 100)),
        muted=bool(config.get("muted", False)),
        audio_card=int(config.get("audio_card", 0)),
        audio_control=str(config.get("audio_control", "PCM")),
        audio_output=str(config.get("audio_output", "analog")),
        audio_device=str(config.get("audio_device", "")),
        audio_control_mode=str(config.get("audio_control_mode", "alsa")),
        hardware_profile=hardware_profile,
        zero_w_video_sizing=str(config.get("zero_w_video_sizing", "auto")),
    )
    def refresh_runtime_display_binding() -> bool:
        changed = resolve_runtime_display_binding()
        if changed:
            player.configure_output(
                str(config.get("display_connector", "")),
                str(config.get("display_resolution", "")),
                str(config.get("audio_device", "")),
            )
        return changed

    try:
        player.apply_audio()
    except PlayerError:
        # Keep the Web UI available if the configured mixer is temporarily absent.
        pass
    channel_cache: dict[str, Any] = {"channels": [], "error": None}
    cache_lock = threading.RLock()

    def refresh_channels() -> list[Channel]:
        try:
            channels = fetch_channels(
                str(config["m3u_url"]),
                timeout=int(config["request_timeout_seconds"]),
            )
            channels.sort(key=lambda c: _channel_sort_key(c.number))
            with cache_lock:
                channel_cache["channels"] = channels
                channel_cache["error"] = None
            logger.info("Loaded %d channels from the configured playlist", len(channels))
            return channels
        except Exception as exc:
            with cache_lock:
                channel_cache["error"] = str(exc)
            logger.error("Channel refresh failed: %s", exc)
            raise

    def get_channels() -> list[Channel]:
        with cache_lock:
            channels = list(channel_cache["channels"])
        return channels or refresh_channels()

    def autoplay_worker() -> None:
        if not config.get("autoplay", True):
            return
        channel_id = player.load_saved_channel_id()
        if not channel_id:
            return
        while True:
            try:
                channel = find_channel(refresh_channels(), channel_id)
                if channel:
                    refresh_runtime_display_binding()
                    player.play(channel)
                    logger.info("Autoplay started channel %s (%s)", channel.name, channel.number)
                return
            except Exception:
                time.sleep(5)

    @app.get("/")
    def index():
        return render_template("index.html", version="0.1.0", is_zero_w=(hardware_profile == "rpi-zero-w"))

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "version": "0.1.0"})

    @app.get("/api/channels")
    def channels_api():
        try:
            channels = get_channels()
            with cache_lock:
                error = channel_cache["error"]
            return jsonify({"channels": [c.to_dict() for c in channels], "error": error})
        except Exception as exc:
            return jsonify({"channels": [], "error": str(exc)}), 502

    @app.post("/api/channels/refresh")
    def refresh_api():
        try:
            channels = refresh_channels()
            return jsonify({"channels": [c.to_dict() for c in channels]})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 502

    @app.get("/api/player/status")
    def player_status():
        return jsonify(player.status())

    @app.post("/api/player/channel")
    def select_channel():
        data = request.get_json(silent=True) or {}
        channel_id = str(data.get("channel_id", "")).strip()
        if not channel_id:
            return jsonify({"error": "channel_id is required"}), 400
        try:
            channel = find_channel(get_channels(), channel_id)
            if channel is None:
                return jsonify({"error": "Channel not found"}), 404
            refresh_runtime_display_binding()
            player.play(channel)
            logger.info("Channel selected: %s (%s)", channel.name, channel.number)
            return jsonify(player.status())
        except PlayerError as exc:
            return jsonify({"error": str(exc)}), 500
        except Exception as exc:
            return jsonify({"error": str(exc)}), 502


    @app.post("/api/player/volume")
    def set_player_volume():
        if str(config.get("audio_control_mode", "alsa")).casefold() != "alsa":
            return jsonify({"error": "Volume control is unavailable while HDMI audio is active."}), 409
        data = request.get_json(silent=True) or {}
        try:
            volume = int(data.get("volume", config.get("volume", 100)))
        except (TypeError, ValueError):
            return jsonify({"error": "Volume must be an integer from 0 to 100"}), 400
        if not 0 <= volume <= 100:
            return jsonify({"error": "Volume must be from 0 to 100"}), 400
        muted = bool(data.get("muted", config.get("muted", False)))
        updates = {"volume": volume, "muted": muted}
        try:
            save_config(updates)
        except OSError:
            path = config_dir() / "config.json"
            return jsonify({"error": f"Failed to save configuration to {path}. Check file permissions."}), 500
        config.update(updates)
        try:
            player.configure_audio(volume, muted)
        except PlayerError as exc:
            return jsonify({"error": str(exc)}), 500
        return jsonify(player.status())

    @app.post("/api/player/stop")
    def stop_player():
        player.stop(clear_channel=False)
        logger.info("Playback stopped from the Web UI")
        return jsonify(player.status())

    @app.post("/api/player/restart")
    def restart_player():
        try:
            player.restart()
            logger.info("Playback restarted from the Web UI")
            return jsonify(player.status())
        except PlayerError as exc:
            return jsonify({"error": str(exc)}), 409

    @app.get("/api/display/options")
    def display_options_api():
        refresh_runtime_display_binding()
        refresh_runtime_display_binding()
        display_mode = str(config.get("display_mode", "desktop")).casefold()
        display_connector = str(config.get("display_connector", ""))
        detected = detected_resolution_labels(display_mode, display_connector, hardware_profile)
        configured = str(config.get("display_resolution", ""))
        if configured and configured not in detected and hardware_profile != "rpi-zero-w":
            detected.append(configured)
        return jsonify(
            {
                "resolutions": detected,
                "overscan_presets": list(valid_overscan_presets()),
                "backend": str(config.get("player_backend", "mpv")),
                "display_mode": display_mode,
                "display_connector": display_connector,
                "resolution_control_available": bool(detected) and display_mode in {"composite", "hdmi", "drm"},
                "overscan_control_available": display_mode == "composite",
                "zero_w_video_sizing_available": hardware_profile == "rpi-zero-w" and display_mode == "hdmi",
                "resolution_labels": {
                    "1280x720@59.94": "Recommended for widescreen TVs",
                    "1280x720@60": "Widescreen fallback",
                    "720x480@59.94": "Lower-load SD output",
                    "720x480@60": "Lower-load SD fallback",
                    "640x480@59.94": "Compatibility mode",
                    "640x480@60": "Compatibility fallback",
                } if hardware_profile == "rpi-zero-w" and display_mode == "hdmi" else {},
                "resolution_warnings": {
                    "1280x720@59.94": "Recommended for widescreen TVs. Demanding channels may still drop occasional frames.",
                    "1280x720@60": "Use when 59.94 Hz is unavailable. Demanding channels may still drop occasional frames.",
                    "720x480@59.94": "Some televisions interpret 480p HDMI as 4:3 and may add side borders.",
                    "720x480@60": "Some televisions interpret 480p HDMI as 4:3 and may add side borders.",
                } if hardware_profile == "rpi-zero-w" and display_mode == "hdmi" else {},
                "hardware_profile": hardware_profile,
            }
        )

    @app.get("/api/system/info")
    def system_info_api():
        info = dict(cached_raspberry_pi_info or collect_system_info())
        info.update(
            {
                "display_mode": str(config.get("display_mode", "desktop")),
                "display_connector": str(config.get("display_connector", "")),
                "display_resolution": str(config.get("display_resolution", "")),
                "player_backend": str(config.get("player_backend", "mpv")),
                "zero_w_video_sizing": str(config.get("zero_w_video_sizing", "auto")),
            }
        )
        return jsonify(info)


    @app.get("/api/logs")
    def logs_api():
        lines = normalize_line_count(request.args.get("lines", DEFAULT_LINES))
        level = str(request.args.get("level", "all"))
        search = str(request.args.get("search", ""))[:200]
        source = str(request.args.get("source", "runtime")).casefold()

        if source == "runtime":
            entries = runtime_log_buffer.read(lines=lines, level=level, search=search)
            return jsonify({
                "source": "runtime",
                "available": True,
                "lines": lines,
                "entries": entries,
                "text": format_runtime_entries(entries),
                "error": None,
            })

        journal = read_journal(
            lines=lines,
            priority=level,
            search=search,
            max_lines=100 if hardware_profile == "rpi-zero-w" else MAX_LINES,
        )
        if journal["available"]:
            return jsonify({"source": "journal", "lines": lines, **journal})

        entries = runtime_log_buffer.read(lines=lines, level=level, search=search)
        return jsonify({
            "source": "runtime",
            "available": True,
            "lines": lines,
            "entries": entries,
            "text": format_runtime_entries(entries),
            "warning": journal["error"],
            "error": None,
        })

    @app.get("/api/logs/download")
    def download_logs_api():
        lines = normalize_line_count(request.args.get("lines", MAX_LINES))
        level = str(request.args.get("level", "all"))
        search = str(request.args.get("search", ""))[:200]
        source = str(request.args.get("source", "runtime")).casefold()
        if source == "journal":
            journal = read_journal(
                lines=lines,
                priority=level,
                search=search,
                max_lines=100 if hardware_profile == "rpi-zero-w" else MAX_LINES,
            )
            if journal["available"]:
                text = str(journal["text"])
            else:
                entries = runtime_log_buffer.read(lines=lines, level=level, search=search)
                text = format_runtime_entries(entries)
        else:
            entries = runtime_log_buffer.read(lines=lines, level=level, search=search)
            text = format_runtime_entries(entries)
        return Response(
            text + ("\n" if text else ""),
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment; filename=retrostation-player.log"},
        )

    @app.get("/api/config")
    def get_config_api():
        return jsonify({k: config[k] for k in _EDITABLE_KEYS if k in config})

    @app.post("/api/config")
    def update_config_api():
        data = request.get_json(silent=True) or {}
        updates = {k: v for k, v in data.items() if k in _EDITABLE_KEYS}
        if not updates:
            return jsonify({"error": "No valid configuration fields provided"}), 400

        display_mode = str(config.get("display_mode", "desktop")).casefold()
        display_connector = str(config.get("display_connector", ""))
        detected = detected_resolution_labels(display_mode, display_connector, hardware_profile)
        if "display_resolution" in updates:
            resolution = str(updates["display_resolution"])
            if display_mode not in {"composite", "hdmi", "drm"}:
                return jsonify({"error": "Display resolution is managed by the desktop"}), 400
            if resolution not in detected:
                return jsonify({"error": "Selected resolution is not currently available"}), 400
            updates["display_resolution"] = resolution

        if "volume" in updates:
            try:
                volume = int(updates["volume"])
            except (TypeError, ValueError):
                return jsonify({"error": "Volume must be an integer from 0 to 100"}), 400
            if not 0 <= volume <= 100:
                return jsonify({"error": "Volume must be from 0 to 100"}), 400
            updates["volume"] = volume

        if "muted" in updates:
            updates["muted"] = bool(updates["muted"])

        if "zero_w_video_sizing" in updates:
            if hardware_profile != "rpi-zero-w" or display_mode != "hdmi":
                return jsonify({"error": "Zero W video sizing is available only on a Raspberry Pi Zero W using HDMI"}), 400
            sizing = str(updates["zero_w_video_sizing"]).strip().casefold()
            if sizing not in {"auto", "stretch"}:
                return jsonify({"error": "Invalid Zero W video sizing mode"}), 400
            updates["zero_w_video_sizing"] = sizing

        if "crt_overscan" in updates:
            if display_mode != "composite":
                return jsonify({"error": "CRT overscan is available only in composite mode"}), 400
            overscan = str(updates["crt_overscan"])
            if overscan not in valid_overscan_presets():
                return jsonify({"error": "Invalid CRT overscan preset"}), 400
            updates["crt_overscan"] = overscan

        try:
            save_config(updates)
        except OSError:
            path = config_dir() / "config.json"
            return jsonify({"error": f"Failed to save configuration to {path}. Check file permissions."}), 500

        m3u_url_changed = "m3u_url" in updates
        display_changed = bool({"display_resolution", "crt_overscan", "zero_w_video_sizing"} & updates.keys())
        audio_changed = bool({"volume", "muted"} & updates.keys())
        config.update(updates)
        logger.info("Configuration updated: %s", ", ".join(sorted(updates)))

        if m3u_url_changed:
            with cache_lock:
                channel_cache["channels"] = []
                channel_cache["error"] = None

        if audio_changed:
            try:
                player.configure_audio(
                    int(config.get("volume", 100)),
                    bool(config.get("muted", False)),
                )
            except PlayerError as exc:
                return jsonify({"error": str(exc)}), 500

        if display_changed:
            try:
                player.configure_display(
                    str(config.get("display_resolution", default_resolution(display_mode, detected, hardware_profile))),
                    str(config.get("crt_overscan", "none")),
                    str(config.get("zero_w_video_sizing", "auto")),
                )
                if player.status()["channel"] is not None:
                    player.restart()
            except (PlayerError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 500

        return jsonify({k: config[k] for k in _EDITABLE_KEYS if k in config})

    @atexit.register
    def shutdown_player() -> None:
        try:
            player.stop(clear_channel=False)
        except OSError:
            pass

    threading.Thread(target=autoplay_worker, name="autoplay", daemon=True).start()
    return app


def _channel_sort_key(number: str):
    try:
        return (0, float(number))
    except ValueError:
        return (1, number.casefold())


app = create_app()


def main() -> None:
    config = load_config()
    app.run(
        host=str(config["listen_host"]),
        port=int(config["listen_port"]),
        threaded=True,
    )


if __name__ == "__main__":
    main()
