"""Tests for playback failure detection and automatic stream restart."""

import threading
import time

import pytest

from retrostation_player.channels import Channel
from retrostation_player.player import MediaPlayer, PlayerError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(tmp_path, monkeypatch, *, backend: str = "mpv") -> MediaPlayer:
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path))
    return MediaPlayer(
        backend=backend,
        player_path="cvlc" if backend == "vlc" else "mpv",
        fullscreen=False,
        extra_args=[],
        display_mode="composite" if backend == "vlc" else "desktop",
        display_resolution="480i" if backend == "vlc" else "",
        audio_control_mode="external",
    )


def _make_channel(channel_id: str = "ch1") -> Channel:
    return Channel(id=channel_id, number="1", name="Test", url="http://example/test.m3u8", logo="", group="")


class _FakeProcess:
    """Simulates a subprocess.Popen with controllable exit."""

    def __init__(self, returncode: int = 1):
        self.pid = 12345
        self._exit_event = threading.Event()
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode if self._exit_event.is_set() else None

    def wait(self, timeout=None) -> int:
        self._exit_event.wait(timeout=timeout)
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self._exit_event.set()

    def kill(self) -> None:
        self.killed = True
        self._exit_event.set()

    def exit(self) -> None:
        """Simulate the process exiting unexpectedly."""
        self._exit_event.set()


# ---------------------------------------------------------------------------
# Failure tracking initialised correctly
# ---------------------------------------------------------------------------

def test_player_initial_failure_state(tmp_path, monkeypatch):
    player = _make_player(tmp_path, monkeypatch)
    status = player.status()
    assert status["failure_count"] == 0
    assert status["restart_count"] == 0
    assert status["last_failure_reason"] is None
    assert status["last_failure_time"] is None


# ---------------------------------------------------------------------------
# Watchdog restarts on unexpected exit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("backend", ["mpv", "vlc"])
def test_watchdog_restarts_after_unexpected_exit(tmp_path, monkeypatch, backend):
    player = _make_player(tmp_path, monkeypatch, backend=backend)
    channel = _make_channel()

    processes = []
    restart_event = threading.Event()

    def fake_start_process(command):
        proc = _FakeProcess()
        processes.append(proc)
        player._process = proc
        if len(processes) >= 2:
            restart_event.set()

    monkeypatch.setattr(player, "_start_process", fake_start_process)
    monkeypatch.setattr(player, "_build_command", lambda ch: ["mpv", ch.url])

    player.play(channel)
    assert len(processes) == 1

    # Simulate the first process exiting unexpectedly
    processes[0].exit()

    # Watchdog should restart within a few seconds (first delay is 1 s)
    restarted = restart_event.wait(timeout=5)
    player.stop(clear_channel=True)

    assert restarted, "Watchdog did not restart the stream after failure"
    assert len(processes) >= 2


@pytest.mark.parametrize("backend", ["mpv", "vlc"])
def test_watchdog_increments_failure_count(tmp_path, monkeypatch, backend):
    player = _make_player(tmp_path, monkeypatch, backend=backend)
    channel = _make_channel()

    restart_event = threading.Event()
    processes = []

    def fake_start_process(command):
        proc = _FakeProcess()
        processes.append(proc)
        player._process = proc
        if len(processes) >= 2:
            restart_event.set()

    monkeypatch.setattr(player, "_start_process", fake_start_process)
    monkeypatch.setattr(player, "_build_command", lambda ch: ["mpv", ch.url])

    player.play(channel)
    processes[0].exit()

    restart_event.wait(timeout=5)
    player.stop(clear_channel=True)

    assert player.status()["failure_count"] >= 1


@pytest.mark.parametrize("backend", ["mpv", "vlc"])
def test_watchdog_sets_last_failure_reason(tmp_path, monkeypatch, backend):
    player = _make_player(tmp_path, monkeypatch, backend=backend)
    channel = _make_channel()

    restart_event = threading.Event()
    processes = []

    def fake_start_process(command):
        proc = _FakeProcess(returncode=1)
        processes.append(proc)
        player._process = proc
        if len(processes) >= 2:
            restart_event.set()

    monkeypatch.setattr(player, "_start_process", fake_start_process)
    monkeypatch.setattr(player, "_build_command", lambda ch: ["mpv", ch.url])

    player.play(channel)
    processes[0].exit()

    restart_event.wait(timeout=5)
    player.stop(clear_channel=True)

    reason = player.status()["last_failure_reason"]
    assert reason is not None
    assert "1" in reason  # exit code is included


@pytest.mark.parametrize("backend", ["mpv", "vlc"])
def test_watchdog_sets_last_failure_time(tmp_path, monkeypatch, backend):
    player = _make_player(tmp_path, monkeypatch, backend=backend)
    channel = _make_channel()

    restart_event = threading.Event()
    processes = []

    def fake_start_process(command):
        proc = _FakeProcess()
        processes.append(proc)
        player._process = proc
        if len(processes) >= 2:
            restart_event.set()

    monkeypatch.setattr(player, "_start_process", fake_start_process)
    monkeypatch.setattr(player, "_build_command", lambda ch: ["mpv", ch.url])

    player.play(channel)
    processes[0].exit()

    restart_event.wait(timeout=5)
    player.stop(clear_channel=True)

    assert player.status()["last_failure_time"] is not None


@pytest.mark.parametrize("backend", ["mpv", "vlc"])
def test_watchdog_increments_restart_count(tmp_path, monkeypatch, backend):
    player = _make_player(tmp_path, monkeypatch, backend=backend)
    channel = _make_channel()

    # restart_count is incremented after play() returns in the watchdog.
    # We need to wait until the restart is complete and restart_count updated.
    restart_done = threading.Event()
    processes = []

    original_play = player.play

    def patched_play(ch):
        original_play(ch)
        if len(processes) >= 2:
            restart_done.set()

    def fake_start_process(command):
        proc = _FakeProcess()
        processes.append(proc)
        player._process = proc

    monkeypatch.setattr(player, "_start_process", fake_start_process)
    monkeypatch.setattr(player, "_build_command", lambda ch: ["mpv", ch.url])
    monkeypatch.setattr(player, "play", patched_play)

    original_play(channel)
    processes[0].exit()

    restart_done.wait(timeout=5)
    # Give the watchdog thread a moment to increment restart_count after play()
    time.sleep(0.1)
    player.stop(clear_channel=True)

    assert player.status()["restart_count"] >= 1


# ---------------------------------------------------------------------------
# Intentional stop suppresses restart
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("backend", ["mpv", "vlc"])
def test_watchdog_does_not_restart_after_intentional_stop(tmp_path, monkeypatch, backend):
    """stop() must suppress the automatic restart."""
    player = _make_player(tmp_path, monkeypatch, backend=backend)
    channel = _make_channel()

    start_calls = []

    def fake_start_process(command):
        proc = _FakeProcess()
        start_calls.append(proc)
        player._process = proc

    monkeypatch.setattr(player, "_start_process", fake_start_process)
    monkeypatch.setattr(player, "_build_command", lambda ch: ["mpv", ch.url])

    player.play(channel)
    assert len(start_calls) == 1

    # Stop intentionally; this sets _intentional_stop = True.
    player.stop(clear_channel=True)

    # Wait longer than the first restart delay to confirm no restart occurs.
    time.sleep(1.5)

    assert len(start_calls) == 1, "Watchdog restarted after intentional stop"


# ---------------------------------------------------------------------------
# Channel change suppresses previous watchdog
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("backend", ["mpv", "vlc"])
def test_watchdog_does_not_restart_after_channel_change(tmp_path, monkeypatch, backend):
    """Switching to a different channel must suppress the old watchdog."""
    player = _make_player(tmp_path, monkeypatch, backend=backend)
    channel_a = _make_channel("ch1")
    channel_b = _make_channel("ch2")

    processes = []
    new_channel_restart_ids = []

    def fake_start_process(command):
        proc = _FakeProcess()
        processes.append(proc)
        player._process = proc

    def fake_build_command(ch):
        return ["mpv", ch.url]

    monkeypatch.setattr(player, "_start_process", fake_start_process)
    monkeypatch.setattr(player, "_build_command", fake_build_command)

    player.play(channel_a)
    proc_a = processes[0]

    # Switch to channel_b before proc_a exits
    player.play(channel_b)

    # Now let proc_a "exit unexpectedly" – the watchdog for channel_a should
    # detect the stale session and not restart.
    proc_a.exit()

    time.sleep(1.5)

    # Only the two explicit play() calls should have occurred (channel_a and channel_b).
    assert len(processes) == 2, f"Expected 2 processes, got {len(processes)}"

    player.stop(clear_channel=True)


# ---------------------------------------------------------------------------
# Failure tracking resets when a new channel is selected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("backend", ["mpv", "vlc"])
def test_failure_count_resets_on_new_channel(tmp_path, monkeypatch, backend):
    player = _make_player(tmp_path, monkeypatch, backend=backend)
    channel_a = _make_channel("ch1")
    channel_b = _make_channel("ch2")

    restart_event = threading.Event()
    processes = []

    def fake_start_process(command):
        proc = _FakeProcess()
        processes.append(proc)
        player._process = proc
        if len(processes) >= 2:
            restart_event.set()

    monkeypatch.setattr(player, "_start_process", fake_start_process)
    monkeypatch.setattr(player, "_build_command", lambda ch: ["mpv", ch.url])

    player.play(channel_a)
    processes[0].exit()
    restart_event.wait(timeout=5)
    # Give the watchdog thread time to finish incrementing restart_count
    time.sleep(0.2)
    player.stop()

    # Failure count should be >= 1 for channel_a
    assert player.status()["failure_count"] >= 1

    # Select a different channel – counters must reset
    player.play(channel_b)
    player.stop(clear_channel=True)

    status = player.status()
    assert status["failure_count"] == 0
    assert status["restart_count"] == 0
    assert status["last_failure_reason"] is None
    assert status["last_failure_time"] is None


# ---------------------------------------------------------------------------
# status() always includes failure fields
# ---------------------------------------------------------------------------

def test_status_includes_failure_fields_when_not_playing(tmp_path, monkeypatch):
    player = _make_player(tmp_path, monkeypatch)
    status = player.status()
    for key in ("failure_count", "restart_count", "last_failure_reason", "last_failure_time"):
        assert key in status, f"Missing key in status(): {key}"


def test_vlc_stop_clears_process_reference(tmp_path, monkeypatch):
    player = _make_player(tmp_path, monkeypatch, backend="vlc")
    channel = _make_channel()
    process = _FakeProcess()

    def fake_start_process(command):
        player._process = process

    monkeypatch.setattr(player, "_start_process", fake_start_process)
    monkeypatch.setattr(player, "_build_command", lambda ch: ["cvlc", ch.url])

    player.play(channel)
    player.stop(clear_channel=True)

    assert player._process is None
    assert player.status()["playing"] is False
    assert process.terminated or process.killed
