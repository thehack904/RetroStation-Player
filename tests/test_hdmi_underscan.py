from retrostation_player.channels import Channel
from retrostation_player.player import MediaPlayer


def make_player(percent):
    return MediaPlayer(
        backend="mpv", player_path="mpv", fullscreen=True, extra_args=[],
        display_mode="hdmi", display_connector="HDMI-A-1", display_resolution="1280x720",
        audio_control_mode="external", hdmi_underscan_percent=percent,
    )


def test_hdmi_underscan_adds_centered_video_zoom():
    command = make_player(5)._build_command(Channel(id="1", number="1", name="Test", url="http://example/test.m3u8", logo="", group=""))
    assert any(arg.startswith("--video-zoom=-") for arg in command)
    assert "--video-align-x=0" in command
    assert "--video-align-y=0" in command


def test_zero_hdmi_underscan_adds_no_zoom():
    command = make_player(0)._build_command(Channel(id="1", number="1", name="Test", url="http://example/test.m3u8", logo="", group=""))
    assert not any(arg.startswith("--video-zoom=") for arg in command)


def test_hdmi_configure_display_does_not_validate_composite_alignment():
    player = make_player(0)
    player.configure_display(
        "1280x720@59.94",
        "none",
        custom_alignment={"left": 0, "right": 0, "top": 0, "bottom": 0},
        hdmi_underscan_percent=5,
    )
    assert player.display_resolution == "1280x720@59.94"
    assert player.hdmi_underscan_percent == 5


def test_hdmi_alignment_start_timeout_is_longer_on_zero_w():
    player = make_player(0)
    player.hardware_profile = "rpi-zero-w"
    assert player._hdmi_alignment_start_timeout() == 20.0


def test_hdmi_alignment_start_timeout_is_short_on_other_hardware():
    player = make_player(0)
    player.hardware_profile = "default"
    assert player._hdmi_alignment_start_timeout() == 4.0
