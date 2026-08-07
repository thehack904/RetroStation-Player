from __future__ import annotations

import json
import math
import logging
import os
import subprocess
import threading
import time
import re
from pathlib import Path
from typing import Any

from .channels import Channel
from .config import state_file
from .display import normalize_connector_name, normalize_custom_alignment, overscan_padding, resolution_details
from .mpv_ipc import MpvIpcController, MpvIpcError

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
        crt_custom_alignment: dict[str, int] | None = None,
        volume: int = 100,
        muted: bool = False,
        audio_card: int = 0,
        audio_control: str = "auto",
        audio_output: str = "analog",
        audio_device: str = "",
        audio_control_mode: str = "alsa",
        hardware_profile: str = "default",
        zero_w_video_sizing: str = "auto",
        hdmi_underscan_percent: int = 0,
    ) -> None:
        self.backend = backend.casefold()
        self.player_path = player_path
        self.fullscreen = fullscreen
        self.extra_args = extra_args
        self.display_mode = display_mode.casefold()
        self.display_connector = normalize_connector_name(display_connector)
        self.display_resolution = display_resolution
        self.crt_overscan = crt_overscan
        self.crt_custom_alignment = dict(crt_custom_alignment or {"left": 0, "right": 0, "top": 0, "bottom": 0})
        self.volume = max(0, min(100, int(volume)))
        self.muted = bool(muted)
        self.audio_card = int(audio_card)
        self.audio_control = str(audio_control).strip() or "auto"
        self._resolved_audio_control: str | None = None
        self.audio_output = str(audio_output).strip().casefold() or "analog"
        self.audio_device = str(audio_device).strip()
        self.audio_control_mode = str(audio_control_mode).strip().casefold() or "alsa"
        self.hardware_profile = str(hardware_profile).strip().casefold() or "default"
        self.zero_w_video_sizing = str(zero_w_video_sizing).strip().casefold() or "auto"
        self.hdmi_underscan_percent = max(0, min(15, int(hdmi_underscan_percent)))
        self._process: subprocess.Popen[bytes] | None = None
        self._channel: Channel | None = None
        self._lock = threading.RLock()
        self._alignment_active = False
        self._alignment_values = dict(self.crt_custom_alignment)
        self._hdmi_alignment_active = False
        self._hdmi_alignment_value = self.hdmi_underscan_percent
        self._hdmi_alignment_original_value = self.hdmi_underscan_percent
        self._hdmi_alignment_previewing = False
        self._hdmi_alignment_socket = Path("/tmp/retrostation-player-hdmi-alignment.sock")
        self._hdmi_alignment_ipc = MpvIpcController(self._hdmi_alignment_socket)
        self._playback_socket = Path("/tmp/retrostation-player.sock")
        self.playback_ipc = MpvIpcController(self._playback_socket)
        self._intentional_stop: bool = False
        self._play_session: int = 0
        self._failure_count: int = 0
        self._restart_count: int = 0
        self._last_failure_reason: str | None = None
        self._last_failure_time: float | None = None

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

    def configure_display(self, resolution: str, overscan: str, zero_w_video_sizing: str | None = None, custom_alignment: dict[str, int] | None = None, hdmi_underscan_percent: int | None = None) -> None:
        with self._lock:
            if self.display_mode == "composite":
                resolution_details(resolution)
                if overscan == "custom":
                    normalize_custom_alignment(custom_alignment or self.crt_custom_alignment, resolution)
                else:
                    overscan_padding(resolution, overscan)
            elif not resolution:
                raise ValueError("A display resolution is required")
            self.display_resolution = resolution
            self.crt_overscan = overscan
            if custom_alignment is not None and self.display_mode == "composite":
                self.crt_custom_alignment = normalize_custom_alignment(custom_alignment, resolution)
                self._alignment_values = dict(self.crt_custom_alignment)
            if zero_w_video_sizing is not None:
                sizing = str(zero_w_video_sizing).strip().casefold()
                if sizing not in {"auto", "stretch"}:
                    raise ValueError("Unsupported Zero W video sizing mode")
                self.zero_w_video_sizing = sizing
            if hdmi_underscan_percent is not None:
                value = int(hdmi_underscan_percent)
                if not 0 <= value <= 15:
                    raise ValueError("HDMI underscan must be from 0 to 15 percent")
                self.hdmi_underscan_percent = value

    @staticmethod
    def _volume_to_db(volume: int) -> float:
        """Map the Web UI's useful 1-100 range to -30 dB through +4 dB."""
        normalized = max(1, min(100, int(volume)))
        return -30.0 + ((normalized - 1) * 34.0 / 99.0)

    def _detect_audio_control(self) -> str:
        """Return a playback-capable ALSA mixer control for the selected card.

        Older configurations commonly specify ``PCM``. USB audio adapters often
        expose ``Speaker`` or ``Headphone`` instead, so an unavailable configured
        control falls back to the best playback-capable control on the card.
        """
        if self._resolved_audio_control:
            return self._resolved_audio_control

        command = ["amixer", "-c", str(self.audio_card), "scontents"]
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
            raise PlayerError(f"Unable to inspect ALSA mixer controls: {exc}") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise PlayerError(
                f"Unable to inspect ALSA card {self.audio_card}: {detail or 'amixer failed'}"
            )

        controls: dict[str, str] = {}
        current_name: str | None = None
        current_lines: list[str] = []
        for line in completed.stdout.splitlines():
            match = re.match(r"Simple mixer control '(.+)',\d+", line)
            if match:
                if current_name is not None:
                    controls[current_name] = "\n".join(current_lines)
                current_name = match.group(1)
                current_lines = []
            elif current_name is not None:
                current_lines.append(line)
        if current_name is not None:
            controls[current_name] = "\n".join(current_lines)

        playback_controls = {
            name for name, details in controls.items()
            if "Capabilities:" in details and ("pvolume" in details or "pswitch" in details)
        }
        configured = self.audio_control
        if configured.casefold() != "auto" and configured in playback_controls:
            selected = configured
        else:
            preferred = ("PCM", "Speaker", "Headphone", "Master", "Playback", "Digital")
            selected = next((name for name in preferred if name in playback_controls), "")
            if not selected and playback_controls:
                selected = sorted(playback_controls)[0]

        if not selected:
            requested = "automatic detection" if configured.casefold() == "auto" else f"control '{configured}'"
            raise PlayerError(
                f"Unable to find a playback-capable ALSA mixer on card {self.audio_card} "
                f"for {requested}"
            )

        if selected != configured:
            logger.info(
                "Using ALSA card %s control '%s' instead of configured control '%s'",
                self.audio_card, selected, configured,
            )
        self._resolved_audio_control = selected
        return selected

    def _run_amixer(self, *arguments: str) -> None:
        control = self._detect_audio_control()
        command = [
            "amixer",
            "-q",
            "-c",
            str(self.audio_card),
            "sset",
            control,
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
                f"control '{control}': {detail or 'amixer failed'}"
            )

    def apply_audio(self) -> None:
        with self._lock:
            if self.audio_control_mode != "alsa":
                return
            if self.muted or self.volume == 0:
                self._run_amixer("mute")
                return

            control = self._detect_audio_control()
            if control == "PCM":
                decibels = self._volume_to_db(self.volume)
                self._run_amixer("--", f"{decibels:.2f}dB", "unmute")
            else:
                self._run_amixer(f"{self.volume}%", "unmute")

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

    def _vlc_display_args(self, custom_alignment: dict[str, int] | None = None) -> list[str]:
        mode, _, _ = resolution_details(self.display_resolution)
        apply_runtime_overscan = not (
            self.hardware_profile == "rpi-zero-w"
            and self.display_mode == "composite"
            and custom_alignment is None
        )
        left = right = top = bottom = 0
        if apply_runtime_overscan:
            if custom_alignment is not None or self.crt_overscan == "custom":
                values = normalize_custom_alignment(custom_alignment or self.crt_custom_alignment, self.display_resolution)
                left, right, top, bottom = values["left"], values["right"], values["top"], values["bottom"]
            else:
                horizontal, vertical = overscan_padding(self.display_resolution, self.crt_overscan)
                left = right = horizontal
                top = bottom = vertical
        args = ["--vout=drm_vout", f"--drm-vout-mode={mode}"]
        if left or right or top or bottom:
            args.extend([
                "--video-filter=croppadd",
                f"--croppadd-paddleft={left}", f"--croppadd-paddright={right}",
                f"--croppadd-paddtop={top}", f"--croppadd-paddbottom={bottom}",
            ])
        return args

    def _start_process(self, command: list[str]) -> None:
        try:
            self._process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError as exc:
            raise PlayerError(f"{self.backend} was not found at '{self.player_path}'") from exc
        except OSError as exc:
            raise PlayerError(f"Unable to start {self.backend}: {exc}") from exc

    def start_alignment(self, values: dict[str, int] | None = None) -> dict[str, int]:
        with self._lock:
            if self.backend != "vlc" or self.display_mode != "composite":
                raise PlayerError("CRT alignment requires VLC composite output")
            normalized = normalize_custom_alignment(values or self.crt_custom_alignment, self.display_resolution)
            self.stop(clear_channel=False)
            _, _, height = resolution_details(self.display_resolution)
            asset = "crt-alignment-576.png" if height >= 576 else "crt-alignment-480.png"
            pattern = Path(__file__).resolve().parent.parent / "static" / asset
            if not pattern.exists():
                raise PlayerError(f"CRT alignment test pattern is missing: {pattern}")
            command = [self.player_path, "--intf=dummy", "--no-video-title-show", "--no-osd", "--fullscreen", "--repeat", "--image-duration=-1", "--avcodec-hw=none"]
            command.extend(self._vlc_display_args(normalized))
            command.append(str(pattern))
            self._start_process(command)
            self._alignment_active = True
            self._alignment_values = normalized
            logger.info("CRT alignment pattern started with values %s", normalized)
            return dict(normalized)

    def update_alignment(self, values: dict[str, int]) -> dict[str, int]:
        return self.start_alignment(values)

    def finish_alignment(self, resume: bool = True) -> None:
        with self._lock:
            channel = self._channel
            self.stop(clear_channel=False)
            self._alignment_active = False
        if resume and channel is not None:
            self.play(channel)


    @staticmethod
    def _underscan_zoom(percent: int) -> float:
        scale = 1.0 - (max(0, min(15, int(percent))) / 100.0)
        return math.log2(scale)

    def _send_mpv_ipc(self, command: list[Any]) -> None:
        try:
            self._hdmi_alignment_ipc.send_command(command)
        except MpvIpcError as exc:
            raise PlayerError(f"Unable to communicate with HDMI alignment mpv: {exc}") from exc

    def _hdmi_alignment_start_timeout(self) -> float:
        """Allow slower HDMI/DRM initialization on the original Pi Zero W."""
        return 20.0 if self.hardware_profile == "rpi-zero-w" else 4.0

    def _start_hdmi_alignment_pattern_locked(self, value: int) -> None:
        self.stop(clear_channel=False)
        self._hdmi_alignment_socket.unlink(missing_ok=True)
        pattern = Path(__file__).resolve().parent.parent / "static" / "hdmi-alignment-720.png"
        command = [self.player_path, "--no-config", "--really-quiet", "--fullscreen", "--force-window=yes", "--keep-open=yes", "--loop-file=inf", "--image-display-duration=inf", "--vo=gpu", "--gpu-context=drm", f"--input-ipc-server={self._hdmi_alignment_socket}", "--video-align-x=0", "--video-align-y=0"]
        if self.display_connector:
            command.append(f"--drm-connector={self.display_connector}")
        if self.display_resolution:
            command.append(f"--drm-mode={self.display_resolution}")
        command.extend([f"--video-zoom={self._underscan_zoom(value):.6f}", str(pattern)])
        self._start_process(command)
        deadline = time.monotonic() + self._hdmi_alignment_start_timeout()
        while time.monotonic() < deadline and not self._hdmi_alignment_socket.exists():
            if self._process is None or self._process.poll() is not None:
                raise PlayerError("HDMI alignment pattern failed to start")
            time.sleep(.05)
        if not self._hdmi_alignment_socket.exists():
            raise PlayerError("Timed out waiting for HDMI alignment mpv to become ready")
        self._hdmi_alignment_previewing = False

    def start_hdmi_alignment(self, percent: int | None = None) -> int:
        with self._lock:
            if self.backend != "mpv" or self.display_mode != "hdmi":
                raise PlayerError("HDMI alignment requires HDMI output using mpv")
            value = self.hdmi_underscan_percent if percent is None else max(0, min(15, int(percent)))
            if not self._hdmi_alignment_active:
                self._hdmi_alignment_original_value = self.hdmi_underscan_percent
            self._hdmi_alignment_active = True
            self._hdmi_alignment_value = value
            self._start_hdmi_alignment_pattern_locked(value)
            return value

    def update_hdmi_alignment(self, percent: int) -> int:
        with self._lock:
            if not self._hdmi_alignment_active:
                raise PlayerError("HDMI alignment is not active")
            if self._hdmi_alignment_previewing:
                raise PlayerError("Return to the test pattern before adjusting HDMI underscan")
            value = max(0, min(15, int(percent)))

            # The mpv IPC socket can disappear if mpv exits or the runtime
            # directory is recreated. Recover by restarting only the alignment
            # pattern with the requested value, then continue using live IPC.
            process_alive = self._process is not None and self._process.poll() is None
            if not process_alive or not self._hdmi_alignment_socket.exists():
                self._start_hdmi_alignment_pattern_locked(value)
            else:
                try:
                    self._send_mpv_ipc(["set_property", "video-zoom", self._underscan_zoom(value)])
                except PlayerError:
                    self._start_hdmi_alignment_pattern_locked(value)
            self._hdmi_alignment_value = value
            return value

    def preview_hdmi_alignment(self, percent: int) -> int:
        with self._lock:
            if not self._hdmi_alignment_active:
                raise PlayerError("HDMI alignment is not active")
            channel = self._channel
            if channel is None:
                raise PlayerError("No channel is available to preview")
            value = max(0, min(15, int(percent)))
            self._hdmi_alignment_value = value
            self.hdmi_underscan_percent = value
            self.play(channel)
            self._hdmi_alignment_previewing = True
            return value

    def return_to_hdmi_alignment_pattern(self) -> int:
        with self._lock:
            if not self._hdmi_alignment_active:
                raise PlayerError("HDMI alignment is not active")
            self._start_hdmi_alignment_pattern_locked(self._hdmi_alignment_value)
            return self._hdmi_alignment_value

    def finish_hdmi_alignment(self, resume: bool = True, commit: bool = False) -> None:
        with self._lock:
            channel = self._channel
            self.stop(clear_channel=False)
            if not commit:
                self.hdmi_underscan_percent = self._hdmi_alignment_original_value
            self._hdmi_alignment_active = False
            self._hdmi_alignment_previewing = False
            self._hdmi_alignment_socket.unlink(missing_ok=True)
        if resume and channel is not None:
            self.play(channel)

    def _build_command(self, channel: Channel) -> list[str]:
        if self.backend == "mpv":
            command = [
                self.player_path,
                "--no-config",
                "--really-quiet",
                "--force-window=yes",
                "--keep-open=no",
                f"--input-ipc-server={self._playback_socket}",
            ]
            if self.fullscreen:
                command.append("--fullscreen")
            managed_prefixes = ("--drm-mode=", "--drm-connector=", "--audio-device=", "--video-zoom=", "--video-align-x=", "--video-align-y=", "--input-ipc-server=")
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
                if self.display_mode == "hdmi":
                    if self.hdmi_underscan_percent > 0:
                        zoom = self._underscan_zoom(self.hdmi_underscan_percent)
                        command.extend([
                            f"--video-zoom={zoom:.6f}",
                            "--video-align-x=0",
                            "--video-align-y=0",
                        ])
                    if self.audio_device:
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

    def _watchdog(self, channel: Channel, process: subprocess.Popen, session: int) -> None:
        """Monitor a playback process and restart the stream on unexpected exit."""
        exit_code = process.wait()

        with self._lock:
            if self._intentional_stop or self._play_session != session:
                return
            self._failure_count += 1
            failure_count = self._failure_count
            self._last_failure_time = time.time()
            self._last_failure_reason = f"Process exited with code {exit_code}"
            logger.warning(
                "Playback failure detected for channel %s (%s): process exited with code %d",
                channel.name, channel.number, exit_code,
            )

        delay = min(2 ** min(failure_count - 1, 5), 30)
        logger.info(
            "Restarting channel %s (%s) in %.0f s (failure #%d)",
            channel.name, channel.number, delay, failure_count,
        )
        time.sleep(delay)

        with self._lock:
            if self._intentional_stop or self._play_session != session:
                return

        try:
            self.play(channel)
            with self._lock:
                self._restart_count += 1
            logger.info(
                "Stream restarted successfully for channel %s (%s)",
                channel.name, channel.number,
            )
        except PlayerError as exc:
            logger.error(
                "Automatic stream restart failed for channel %s (%s): %s",
                channel.name, channel.number, exc,
            )
            with self._lock:
                self._last_failure_reason = f"Restart failed: {exc}"

    def play(self, channel: Channel) -> None:
        with self._lock:
            if self._channel is None or self._channel.id != channel.id:
                self._failure_count = 0
                self._restart_count = 0
                self._last_failure_reason = None
                self._last_failure_time = None
            self._play_session += 1
            session = self._play_session
            self.stop(clear_channel=False)
            self._intentional_stop = False
            command = self._build_command(channel)
            self._start_process(command)
            self._alignment_active = False
            self._channel = channel
            self._write_state(playing=True)
            logger.info("Started %s for channel %s (%s), pid=%s", self.backend, channel.name, channel.number, self._process.pid)
        threading.Thread(
            target=self._watchdog,
            args=(channel, self._process, session),
            name="playback-watchdog",
            daemon=True,
        ).start()

    def stop(self, clear_channel: bool = False) -> None:
        with self._lock:
            self._intentional_stop = True
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
            if self.backend == "mpv":
                self._playback_socket.unlink(missing_ok=True)
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
                "alignment_active": self._alignment_active,
                "hdmi_alignment_active": self._hdmi_alignment_active,
                "hdmi_alignment_value": self._hdmi_alignment_value,
                "hdmi_alignment_previewing": self._hdmi_alignment_previewing,
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
                "failure_count": self._failure_count,
                "restart_count": self._restart_count,
                "last_failure_reason": self._last_failure_reason,
                "last_failure_time": self._last_failure_time,
            }


MPVPlayer = MediaPlayer
