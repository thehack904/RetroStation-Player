from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from typing import Any

from .channels import Channel
from .config import state_file
from .display import normalize_connector_name, overscan_padding, resolution_details

logger = logging.getLogger("retrostation_player.player")


class PlayerError(RuntimeError):
    pass


class MediaPlayer:
    def __init__(
        self,
        backend: str,
        player_path: str,
        fullscreen: bool,
        extra_args: list[str],
        display_mode: str = "desktop",
        display_connector: str = "",
        display_resolution: str = "",
        crt_overscan: str = "none",
        volume: int = 100,
        muted: bool = False,
        audio_card: int = 0,
        audio_control: str = "PCM",
        audio_output: str = "analog",
        audio_device: str = "",
        audio_control_mode: str = "alsa",
        hardware_profile: str = "default",
        zero_w_video_sizing: str = "auto",
    ) -> None:
        self.backend = backend.casefold()
        self.player_path = player_path
        self.fullscreen = fullscreen
        self.extra_args = extra_args
        self.display_mode = display_mode.casefold()
        self.display_connector = normalize_connector_name(display_connector)
        self.display_resolution = display_resolution
        self.crt_overscan = crt_overscan
        self.volume = max(0, min(100, int(volume)))
        self.muted = bool(muted)
        self.audio_card = int(audio_card)
        self.audio_control = str(audio_control).strip() or "PCM"
        self.audio_output = str(audio_output).strip().casefold() or "analog"
        self.audio_device = str(audio_device).strip()
        self.audio_control_mode = str(audio_control_mode).strip().casefold() or "alsa"
        self.hardware_profile = str(hardware_profile).strip().casefold() or "default"
        self.zero_w_video_sizing = str(zero_w_video_sizing).strip().casefold() or "auto"
        self._process: subprocess.Popen[bytes] | None = None
        self._channel: Channel | None = None
        self._lock = threading.RLock()

    def configure_output(
        self,
        connector: str,
        resolution: str,
        audio_device: str = "",
    ) -> None:
        with self._lock:
            self.display_connector = normalize_connector_name(connector)
            self.display_resolution = resolution
            if audio_device:
                self.audio_device = str(audio_device).strip()

    def configure_display(self, resolution: str, overscan: str, zero_w_video_sizing: str | None = None) -> None:
        with self._lock:
            if self.display_mode == "composite":
                resolution_details(resolution)
                overscan_padding(resolution, overscan)
            elif not resolution:
                raise ValueError("A display resolution is required")
            self.display_resolution = resolution
            self.crt_overscan = overscan
            if zero_w_video_sizing is not None:
                sizing = str(zero_w_video_sizing).strip().casefold()
                if sizing not in {"auto", "stretch"}:
                    raise ValueError("Unsupported Zero W video sizing mode")
                self.zero_w_video_sizing = sizing

    @staticmethod
    def _volume_to_db(volume: int) -> float:
        """Map the Web UI's useful 1-100 range to -30 dB through +4 dB."""
        normalized = max(1, min(100, int(volume)))
        return -30.0 + ((normalized - 1) * 34.0 / 99.0)

    def _run_amixer(self, *arguments: str) -> None:
        command = [
            "amixer",
            "-q",
            "-c",
            str(self.audio_card),
            "sset",
            self.audio_control,
            *arguments,
        ]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
        except FileNotFoundError as exc:
            raise PlayerError("amixer was not found; install the alsa-utils package") from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PlayerError(f"Unable to control ALSA volume: {exc}") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise PlayerError(
                f"Unable to control ALSA card {self.audio_card} "
                f"control '{self.audio_control}': {detail or 'amixer failed'}"
            )

    def apply_audio(self) -> None:
        with self._lock:
            if self.audio_control_mode != "alsa":
                return
            if self.muted or self.volume == 0:
                self._run_amixer("mute")
                return

            decibels = self._volume_to_db(self.volume)
            self._run_amixer("--", f"{decibels:.2f}dB", "unmute")

    def configure_audio(self, volume: int, muted: bool) -> None:
        with self._lock:
            if self.audio_control_mode != "alsa":
                raise PlayerError("Volume control is unavailable while HDMI audio is active")
            self.volume = max(0, min(100, int(volume)))
            self.muted = bool(muted)
            self.apply_audio()

    def _write_state(self, playing: bool) -> None:
        path = state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "playing": playing,
            "channel": self._channel.to_dict() if self._channel else None,
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def load_saved_channel_id(self) -> str | None:
        path = state_file()
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            channel = payload.get("channel") or {}
            return channel.get("id")
        except (OSError, json.JSONDecodeError, AttributeError):
            return None

    def _vlc_display_args(self) -> list[str]:
        mode, _, _ = resolution_details(self.display_resolution)
        horizontal, vertical = overscan_padding(
            self.display_resolution, self.crt_overscan
        )
        args = [
            "--vout=drm_vout",
            f"--drm-vout-mode={mode}",
        ]
        if horizontal or vertical:
            args.extend(
                [
                    "--video-filter=croppadd",
                    f"--croppadd-paddleft={horizontal}",
                    f"--croppadd-paddright={horizontal}",
                    f"--croppadd-paddtop={vertical}",
                    f"--croppadd-paddbottom={vertical}",
                ]
            )
        return args

    def _build_command(self, channel: Channel) -> list[str]:
        if self.backend == "mpv":
            command = [
                self.player_path,
                "--no-config",
                "--really-quiet",
                "--force-window=yes",
                "--keep-open=no",
            ]
            if self.fullscreen:
                command.append("--fullscreen")
            managed_prefixes = ("--drm-mode=", "--drm-connector=", "--audio-device=")
            if self.hardware_profile == "rpi-zero-w" and self.display_mode == "hdmi":
                managed_prefixes += (
                    "--profile=", "--vo=", "--gpu-context=", "--hwdec=",
                    "--drm-draw-plane=", "--drm-drmprime-video-plane=",
                    "--audio-format=", "--audio-buffer=", "--cache=",
                    "--cache-secs=", "--demuxer-max-bytes=",
                    "--demuxer-max-back-bytes=", "--keepaspect=",
                )
            command.extend(
                arg for arg in self.extra_args if not arg.startswith(managed_prefixes)
            )
            if self.hardware_profile == "rpi-zero-w" and self.display_mode == "hdmi":
                command.extend([
                    "--profile=fast",
                    "--vo=gpu",
                    "--gpu-context=drm",
                    "--hwdec=v4l2m2m",
                    "--drm-draw-plane=overlay",
                    "--drm-drmprime-video-plane=primary",
                    "--audio-format=s16",
                    "--audio-buffer=0.5",
                    "--cache=yes",
                    "--cache-secs=5",
                    "--demuxer-max-bytes=8MiB",
                    "--demuxer-max-back-bytes=1MiB",
                ])
                if self.zero_w_video_sizing == "stretch":
                    command.append("--keepaspect=no")
            if self.display_mode in {"hdmi", "drm"}:
                if self.display_connector:
                    command.append(f"--drm-connector={self.display_connector}")
                if self.display_resolution:
                    command.append(f"--drm-mode={self.display_resolution}")
                if self.display_mode == "hdmi" and self.audio_device:
                    command.append(f"--audio-device=alsa/{self.audio_device}")
        elif self.backend == "vlc":
            command = [
                self.player_path,
                "--intf=dummy",
                "--no-video-title-show",
                "--no-osd",
                "--play-and-exit",
            ]
            if self.fullscreen:
                command.append("--fullscreen")
            managed_prefixes = (
                "--vout=",
                "--drm-vout-mode=",
                "--video-filter=",
                "--croppadd-",
                "--avcodec-hw=",
            )
            command.extend(
                arg for arg in self.extra_args if not arg.startswith(managed_prefixes)
            )
            # VLC's croppadd filter cannot process DRM PRIME (DPV0) frames.
            # Composite output therefore uses software-decoded frames so the
            # fixed CRT overscan presets can be applied reliably.
            command.append("--avcodec-hw=none")
            command.extend(self._vlc_display_args())
        else:
            raise PlayerError(f"Unsupported player backend: {self.backend}")

        command.append(channel.url)
        return command

    def play(self, channel: Channel) -> None:
        with self._lock:
            self.stop(clear_channel=False)
            command = self._build_command(channel)
            try:
                self._process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError as exc:
                raise PlayerError(
                    f"{self.backend} was not found at '{self.player_path}'"
                ) from exc
            except OSError as exc:
                raise PlayerError(f"Unable to start {self.backend}: {exc}") from exc

            self._channel = channel
            self._write_state(playing=True)
            logger.info("Started %s for channel %s (%s), pid=%s", self.backend, channel.name, channel.number, self._process.pid)

    def stop(self, clear_channel: bool = False) -> None:
        with self._lock:
            process = self._process
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                except ProcessLookupError:
                    pass
            if process is not None:
                logger.info("Stopped %s playback", self.backend)
            self._process = None
            if clear_channel:
                self._channel = None
            self._write_state(playing=False)

    def restart(self) -> None:
        with self._lock:
            if self._channel is None:
                raise PlayerError("No channel has been selected")
            channel = self._channel
        self.play(channel)

    def status(self) -> dict[str, Any]:
        with self._lock:
            playing = self._process is not None and self._process.poll() is None
            return {
                "playing": playing,
                "channel": self._channel.to_dict() if self._channel else None,
                "backend": self.backend,
                "display_connector": self.display_connector,
                "volume": self.volume,
                "muted": self.muted,
                "audio": {
                    "output": self.audio_output,
                    "device": self.audio_device,
                    "control_mode": self.audio_control_mode,
                    "volume_control_available": self.audio_control_mode == "alsa",
                    "message": (
                        "HDMI audio is active. Use the TV or receiver volume control."
                        if self.audio_control_mode == "external"
                        else ""
                    ),
                },
            }


MPVPlayer = MediaPlayer
