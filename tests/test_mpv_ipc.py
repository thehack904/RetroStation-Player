"""Tests for the mpv JSON IPC controller."""

import json
import socket
import threading
import time
from pathlib import Path

import pytest

from retrostation_player.mpv_ipc import MpvIpcController, MpvIpcError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_server(sock_path: Path, response: bytes) -> threading.Thread:
    """Start a minimal Unix socket server that sends *response* then closes."""

    def _serve() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
            srv.bind(str(sock_path))
            srv.listen(1)
            srv.settimeout(5)
            conn, _ = srv.accept()
            with conn:
                # Drain the request payload
                data = b""
                while not data.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                conn.sendall(response)

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return t


def _success_response(data: object = None) -> bytes:
    payload: dict = {"error": "success"}
    if data is not None:
        payload["data"] = data
    return (json.dumps(payload) + "\n").encode()


def _error_response(msg: str) -> bytes:
    return (json.dumps({"error": msg}) + "\n").encode()


# ---------------------------------------------------------------------------
# is_socket_ready
# ---------------------------------------------------------------------------

def test_is_socket_ready_false_when_no_file(tmp_path):
    ipc = MpvIpcController(tmp_path / "missing.sock")
    assert ipc.is_socket_ready() is False


def test_is_socket_ready_true_when_file_exists(tmp_path):
    sock_file = tmp_path / "present.sock"
    sock_file.touch()
    ipc = MpvIpcController(sock_file)
    assert ipc.is_socket_ready() is True


# ---------------------------------------------------------------------------
# send_command
# ---------------------------------------------------------------------------

def test_send_command_returns_success_response(tmp_path):
    sock_path = tmp_path / "mpv.sock"
    _make_server(sock_path, _success_response())
    ipc = MpvIpcController(sock_path)
    # Give the server thread a moment to start listening
    time.sleep(0.05)
    result = ipc.send_command(["get_property", "volume"])
    assert result["error"] == "success"


def test_send_command_raises_on_mpv_error(tmp_path):
    sock_path = tmp_path / "mpv.sock"
    _make_server(sock_path, _error_response("property unavailable"))
    ipc = MpvIpcController(sock_path)
    time.sleep(0.05)
    with pytest.raises(MpvIpcError, match="property unavailable"):
        ipc.send_command(["get_property", "nonexistent"])


def test_send_command_raises_when_socket_missing(tmp_path):
    ipc = MpvIpcController(tmp_path / "no.sock")
    with pytest.raises(MpvIpcError):
        ipc.send_command(["get_property", "volume"])


def test_send_command_raises_on_empty_response(tmp_path):
    """An empty response (connection closed without data) must raise MpvIpcError."""
    sock_path = tmp_path / "mpv.sock"
    _make_server(sock_path, b"")  # server sends nothing then closes
    ipc = MpvIpcController(sock_path)
    time.sleep(0.05)
    with pytest.raises(MpvIpcError, match="without sending a response"):
        ipc.send_command(["get_property", "volume"])


def test_send_command_sends_correct_json(tmp_path):
    """The request payload must be a newline-terminated JSON object with a 'command' key."""
    received: list[bytes] = []
    sock_path = tmp_path / "mpv.sock"

    def _capture_server() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
            srv.bind(str(sock_path))
            srv.listen(1)
            srv.settimeout(5)
            conn, _ = srv.accept()
            with conn:
                data = b""
                while not data.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                received.append(data)
                conn.sendall(_success_response())

    t = threading.Thread(target=_capture_server, daemon=True)
    t.start()
    time.sleep(0.05)

    ipc = MpvIpcController(sock_path)
    ipc.send_command(["set_property", "pause", True])
    t.join(timeout=2)

    assert received
    parsed = json.loads(received[0].decode().strip())
    assert parsed == {"command": ["set_property", "pause", True]}


# ---------------------------------------------------------------------------
# get_property
# ---------------------------------------------------------------------------

def test_get_property_returns_data_field(tmp_path):
    sock_path = tmp_path / "mpv.sock"
    _make_server(sock_path, _success_response(data=75))
    ipc = MpvIpcController(sock_path)
    time.sleep(0.05)
    value = ipc.get_property("volume")
    assert value == 75


def test_get_property_returns_none_when_data_absent(tmp_path):
    sock_path = tmp_path / "mpv.sock"
    _make_server(sock_path, _success_response())
    ipc = MpvIpcController(sock_path)
    time.sleep(0.05)
    assert ipc.get_property("volume") is None


# ---------------------------------------------------------------------------
# set_property
# ---------------------------------------------------------------------------

def test_set_property_does_not_raise_on_success(tmp_path):
    sock_path = tmp_path / "mpv.sock"
    _make_server(sock_path, _success_response())
    ipc = MpvIpcController(sock_path)
    time.sleep(0.05)
    ipc.set_property("volume", 80)  # should not raise


def test_set_property_raises_on_mpv_error(tmp_path):
    sock_path = tmp_path / "mpv.sock"
    _make_server(sock_path, _error_response("not implemented"))
    ipc = MpvIpcController(sock_path)
    time.sleep(0.05)
    with pytest.raises(MpvIpcError, match="not implemented"):
        ipc.set_property("unknown-prop", 1)


# ---------------------------------------------------------------------------
# MpvIpcError is an OSError subclass
# ---------------------------------------------------------------------------

def test_mpv_ipc_error_is_oserror():
    err = MpvIpcError("test")
    assert isinstance(err, OSError)


# ---------------------------------------------------------------------------
# Integration: MediaPlayer includes --input-ipc-server in mpv command
# ---------------------------------------------------------------------------

def test_mpv_build_command_includes_ipc_server(tmp_path, monkeypatch):
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path))
    from retrostation_player.channels import Channel
    from retrostation_player.player import MediaPlayer

    player = MediaPlayer(
        backend="mpv",
        player_path="mpv",
        fullscreen=True,
        extra_args=[],
        display_mode="hdmi",
        display_connector="HDMI-A-1",
        display_resolution="1280x720",
        audio_control_mode="external",
    )
    channel = Channel(id="1", number="1", name="Test", url="http://example/test.m3u8", logo="", group="")
    command = player._build_command(channel)
    ipc_args = [a for a in command if a.startswith("--input-ipc-server=")]
    assert len(ipc_args) == 1
    assert ipc_args[0] == f"--input-ipc-server={player._playback_socket}"


def test_mpv_build_command_filters_extra_arg_ipc_server(tmp_path, monkeypatch):
    """User-supplied --input-ipc-server in extra_args should be overridden."""
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path))
    from retrostation_player.channels import Channel
    from retrostation_player.player import MediaPlayer

    player = MediaPlayer(
        backend="mpv",
        player_path="mpv",
        fullscreen=True,
        extra_args=["--input-ipc-server=/tmp/user-override.sock"],
        display_mode="hdmi",
        display_connector="HDMI-A-1",
        display_resolution="1280x720",
        audio_control_mode="external",
    )
    channel = Channel(id="1", number="1", name="Test", url="http://example/test.m3u8", logo="", group="")
    command = player._build_command(channel)
    ipc_args = [a for a in command if a.startswith("--input-ipc-server=")]
    assert len(ipc_args) == 1
    assert "/user-override" not in ipc_args[0]


def test_vlc_build_command_does_not_include_ipc_server():
    from retrostation_player.channels import Channel
    from retrostation_player.player import MediaPlayer

    player = MediaPlayer(
        backend="vlc",
        player_path="cvlc",
        fullscreen=True,
        extra_args=[],
        display_mode="composite",
        display_resolution="480i",
    )
    channel = Channel(id="1", number="1", name="Test", url="http://example/test.m3u8", logo="", group="")
    command = player._build_command(channel)
    assert not any(a.startswith("--input-ipc-server=") for a in command)


def test_media_player_exposes_playback_ipc_controller(tmp_path, monkeypatch):
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path))
    from retrostation_player.player import MediaPlayer

    player = MediaPlayer(
        backend="mpv",
        player_path="mpv",
        fullscreen=True,
        extra_args=[],
    )
    assert isinstance(player.playback_ipc, MpvIpcController)
    assert player.playback_ipc.socket_path == player._playback_socket
