from types import SimpleNamespace
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


def mixer_result(control="PCM", capabilities="pvolume pswitch"):
    return SimpleNamespace(
        returncode=0,
        stdout=(
            f"Simple mixer control '{control}',0\n"
            f"  Capabilities: {capabilities}\n"
            "  Playback channels: Front Left - Front Right\n"
        ),
        stderr="",
    )


def ok_result():
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_apply_audio_sets_db_and_unmutes_for_pcm():
    player = make_player(volume=50, muted=False)
    with patch("subprocess.run", side_effect=[mixer_result("PCM"), ok_result()]) as run:
        player.apply_audio()
    command = run.call_args_list[1].args[0]
    assert command[:7] == ["amixer", "-q", "-c", "0", "sset", "PCM", "--"]
    assert command[-1] == "unmute"
    assert command[-2].endswith("dB")


def test_apply_audio_falls_back_to_speaker_and_uses_percent():
    player = make_player(volume=50, muted=False)
    with patch("subprocess.run", side_effect=[mixer_result("Speaker"), ok_result()]) as run:
        player.apply_audio()
    assert run.call_args_list[1].args[0] == [
        "amixer", "-q", "-c", "0", "sset", "Speaker", "50%", "unmute"
    ]


def test_apply_audio_mutes_at_zero_using_detected_control():
    player = make_player(volume=0, muted=False)
    with patch("subprocess.run", side_effect=[mixer_result("Speaker"), ok_result()]) as run:
        player.apply_audio()
    assert run.call_args_list[1].args[0] == [
        "amixer", "-q", "-c", "0", "sset", "Speaker", "mute"
    ]


def test_audio_control_detection_ignores_mic_playback_control_when_speaker_exists():
    player = make_player(volume=25, muted=False)
    contents = SimpleNamespace(
        returncode=0,
        stdout=(
            "Simple mixer control 'Speaker',0\n"
            "  Capabilities: pvolume pswitch pswitch-joined\n"
            "  Playback channels: Front Left - Front Right\n"
            "Simple mixer control 'Mic',0\n"
            "  Capabilities: pvolume cvolume pswitch cswitch\n"
            "  Playback channels: Mono\n"
            "  Capture channels: Mono\n"
        ),
        stderr="",
    )
    with patch("subprocess.run", side_effect=[contents, ok_result()]) as run:
        player.apply_audio()
    assert run.call_args_list[1].args[0][5] == "Speaker"


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


def test_vlc_custom_alignment_uses_independent_edge_padding():
    player = MediaPlayer(
        backend="vlc",
        player_path="cvlc",
        fullscreen=True,
        extra_args=[],
        display_mode="composite",
        display_resolution="480i",
        crt_overscan="custom",
        crt_custom_alignment={"left": 10, "right": 20, "top": 5, "bottom": 15},
    )
    args = player._vlc_display_args()
    assert "--vout=drm_vout" in args
    assert "--croppadd-paddleft=10" in args
    assert "--croppadd-paddright=20" in args
    assert "--croppadd-paddtop=5" in args
    assert "--croppadd-paddbottom=15" in args


def test_zero_w_composite_playback_ignores_runtime_overscan_filter():
    player = MediaPlayer(
        backend="vlc",
        player_path="cvlc",
        fullscreen=True,
        extra_args=[],
        display_mode="composite",
        display_resolution="480i",
        crt_overscan="standard",
        hardware_profile="rpi-zero-w",
    )
    channel = Channel(id="1", number="1", name="Test", url="http://example.test/live", logo="", group="")
    command = player._build_command(channel)
    assert "--video-filter=croppadd" not in command


def test_zero_w_composite_alignment_pattern_still_uses_runtime_filter():
    player = MediaPlayer(
        backend="vlc",
        player_path="cvlc",
        fullscreen=True,
        extra_args=[],
        display_mode="composite",
        display_resolution="480i",
        crt_overscan="none",
        hardware_profile="rpi-zero-w",
    )
    args = player._vlc_display_args({"left": 10, "right": 12, "top": 6, "bottom": 8})
    assert "--video-filter=croppadd" in args
    assert "--croppadd-paddleft=10" in args


