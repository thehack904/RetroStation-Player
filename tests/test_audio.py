from unittest.mock import patch

from retrostation_player.channels import Channel
from retrostation_player.player import MediaPlayer


def make_player(volume=100, muted=False):
    return MediaPlayer(
        backend="vlc",
        player_path="cvlc",
        fullscreen=True,
        extra_args=[],
        volume=volume,
        muted=muted,
        audio_card=0,
        audio_control="PCM",
    )


def test_volume_mapping_endpoints():
    assert round(MediaPlayer._volume_to_db(1), 2) == -30.00
    assert round(MediaPlayer._volume_to_db(100), 2) == 4.00


def test_apply_audio_sets_db_and_unmutes():
    player = make_player(volume=50, muted=False)
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        run.return_value.stdout = ""
        player.apply_audio()
    command = run.call_args.args[0]
    assert command[:7] == ["amixer", "-q", "-c", "0", "sset", "PCM", "--"]
    assert command[-1] == "unmute"
    assert command[-2].endswith("dB")


def test_apply_audio_mutes_at_zero():
    player = make_player(volume=0, muted=False)
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        run.return_value.stdout = ""
        player.apply_audio()
    assert run.call_args.args[0] == ["amixer", "-q", "-c", "0", "sset", "PCM", "mute"]


def test_external_audio_does_not_call_amixer():
    player = MediaPlayer(
        backend="mpv",
        player_path="mpv",
        fullscreen=True,
        extra_args=[],
        audio_output="hdmi",
        audio_device="hdmi:CARD=vc4hdmi,DEV=0",
        audio_control_mode="external",
    )
    with patch("subprocess.run") as run:
        player.apply_audio()
    run.assert_not_called()
    status = player.status()
    assert status["audio"]["volume_control_available"] is False
    assert status["audio"]["output"] == "hdmi"


def test_external_audio_rejects_volume_changes():
    player = MediaPlayer(
        backend="mpv",
        player_path="mpv",
        fullscreen=True,
        extra_args=[],
        audio_control_mode="external",
    )
    try:
        player.configure_audio(50, False)
    except Exception as exc:
        assert "HDMI audio" in str(exc)
    else:
        raise AssertionError("Expected external audio volume control to be rejected")


def test_mpv_command_pins_display_connector():
    player = MediaPlayer(
        backend="mpv",
        player_path="mpv",
        fullscreen=True,
        extra_args=["--vo=gpu", "--gpu-context=drm"],
        display_mode="hdmi",
        display_connector="HDMI-A-2",
        display_resolution="1280x720",
        audio_control_mode="external",
    )
    channel = Channel(id="1", number="1", name="Test", url="http://example.test/live", logo="", group="")
    command = player._build_command(channel)
    assert "--drm-connector=HDMI-A-2" in command
    assert "--drm-mode=1280x720" in command


def test_mpv_command_uses_runtime_audio_device_not_stale_extra_arg():
    player = MediaPlayer(
        backend="mpv",
        player_path="mpv",
        fullscreen=True,
        extra_args=["--vo=gpu", "--gpu-context=drm", "--audio-device=alsa/hdmi:CARD=vc4hdmi0,DEV=0"],
        display_mode="hdmi",
        display_connector="HDMI-A-2",
        display_resolution="1280x720",
        audio_device="hdmi:CARD=vc4hdmi1,DEV=0",
        audio_control_mode="external",
    )
    channel = Channel(id="1", number="1", name="Test", url="http://example.test/live", logo="", group="")
    command = player._build_command(channel)
    assert "--audio-device=alsa/hdmi:CARD=vc4hdmi1,DEV=0" in command
    assert "--audio-device=alsa/hdmi:CARD=vc4hdmi0,DEV=0" not in command


def test_zero_w_mpv_profile_and_stretch(tmp_path, monkeypatch):
    from retrostation_player.channels import Channel
    from retrostation_player.player import MediaPlayer
    monkeypatch.setenv('RETROSTATION_PLAYER_STATE_DIR', str(tmp_path))
    player = MediaPlayer(
        backend='mpv', player_path='mpv', fullscreen=True,
        extra_args=['--hwdec=no', '--no-osc'], display_mode='hdmi',
        display_connector='HDMI-A-1', display_resolution='720x480@59.94',
        audio_device='hdmi:CARD=vc4hdmi,DEV=0', hardware_profile='rpi-zero-w',
        zero_w_video_sizing='stretch',
    )
    channel = Channel(id='1', number='1', name='Test', url='http://example/test.m3u8', logo='', group='')
    command = player._build_command(channel)
    assert '--hwdec=v4l2m2m' in command
    assert '--hwdec=no' not in command
    assert '--drm-draw-plane=overlay' in command
    assert '--drm-drmprime-video-plane=primary' in command
    assert '--drm-mode=720x480@59.94' in command
    assert '--keepaspect=no' in command
