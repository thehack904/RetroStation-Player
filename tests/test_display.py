from pathlib import Path

from retrostation_player import display


def test_read_unique_modes_filters_interlaced_and_duplicates(tmp_path):
    modes = tmp_path / "modes"
    modes.write_text(
        "1920x1080\n1920x1080i\n1920x1080\n720x480i\n1280x720\n",
        encoding="utf-8",
    )

    assert display._read_unique_modes([modes]) == ["1920x1080", "1280x720"]


def test_connected_mode_files_can_be_limited_to_connector(monkeypatch, tmp_path):
    drm = tmp_path / "drm"
    for connector, modes in (("HDMI-A-1", "1920x1080\n"), ("HDMI-A-2", "1280x720\n")):
        directory = drm / f"card0-{connector}"
        directory.mkdir(parents=True)
        (directory / "status").write_text("connected\n", encoding="utf-8")
        (directory / "modes").write_text(modes, encoding="utf-8")

    original_path = display.Path

    class FakePath:
        def __new__(cls, value):
            if value == "/sys/class/drm":
                return original_path(drm)
            return original_path(value)

    monkeypatch.setattr(display, "Path", FakePath)
    assert display.detected_resolution_labels("hdmi", "HDMI-A-2") == ["1280x720"]


def test_normalize_connector_name():
    from retrostation_player.display import normalize_connector_name
    assert normalize_connector_name("card0-HDMI-A-1") == "HDMI-A-1"
    assert normalize_connector_name("card1-HDMI-A-2") == "HDMI-A-2"
    assert normalize_connector_name("HDMI-A-1") == "HDMI-A-1"


def test_select_active_connector_moves_to_connected_port(monkeypatch):
    monkeypatch.setattr(display, "connected_connector_names", lambda pattern="*": ["HDMI-A-2"])
    assert display.select_active_connector("hdmi", "HDMI-A-1") == "HDMI-A-2"


def test_detect_hdmi_audio_device_matches_port(monkeypatch):
    class Result:
        stdout = """null\nhdmi:CARD=vc4hdmi0,DEV=0\n    HDMI 0\nhdmi:CARD=vc4hdmi1,DEV=0\n    HDMI 1\n"""
    monkeypatch.setattr(display.subprocess, "run", lambda *args, **kwargs: Result())
    assert display.detect_hdmi_audio_device("HDMI-A-2") == "hdmi:CARD=vc4hdmi1,DEV=0"


def test_composite_exposes_all_vlc_resolution_presets():
    assert display.detected_resolution_labels("composite") == [
        "576i",
        "480i",
        "288",
        "240",
    ]


def test_zero_w_hdmi_modes_are_limited(monkeypatch):
    monkeypatch.setattr(display, '_connected_mode_files', lambda pattern, connector='': [])
    monkeypatch.setattr(display, '_read_unique_modes', lambda paths: ['1920x1080', '1280x720', '720x480', '640x480'])
    assert display.detected_resolution_labels('hdmi', 'HDMI-A-1', 'rpi-zero-w') == [
        '1280x720@59.94', '1280x720@60', '720x480@59.94', '720x480@60',
        '640x480@59.94', '640x480@60'
    ]
    assert display.default_resolution('hdmi', ['1280x720@59.94', '720x480@60'], 'rpi-zero-w') == '1280x720@59.94'
    assert display.default_resolution('hdmi', ['720x480@60', '640x480@60'], 'rpi-zero-w') == '720x480@60'
