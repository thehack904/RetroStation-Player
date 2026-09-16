import importlib

import retrostation_player


def test_index_renders_retrostation_branding(monkeypatch, tmp_path):
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path / "state"))

    # Import after patching the environment so the Flask app reads the test paths.
    app_module = importlib.import_module("retrostation_player.app")
    monkeypatch.setattr("retrostation_player.player.state_file", lambda: tmp_path / "state" / "state.json")

    response = app_module.app.test_client().get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "RetroStation Player" in page
    assert "/static/logo.png" in page
    assert "brand-mark" in page
    assert "Browser-controlled IPTV display" in page
    assert "Service Logs" in page
    assert "logs-button" in page
    assert "Show Boot Logo during startup" in page


def test_index_renders_package_version(monkeypatch, tmp_path):
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path / "state"))

    app_module = importlib.import_module("retrostation_player.app")
    monkeypatch.setattr("retrostation_player.player.state_file", lambda: tmp_path / "state" / "state.json")

    response = app_module.app.test_client().get("/")
    page = response.get_data(as_text=True)

    assert f"v{retrostation_player.__version__}" in page


def test_health_returns_package_version(monkeypatch, tmp_path):
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path / "state"))

    app_module = importlib.import_module("retrostation_player.app")
    monkeypatch.setattr("retrostation_player.player.state_file", lambda: tmp_path / "state" / "state.json")

    response = app_module.app.test_client().get("/api/health")
    data = response.get_json()

    assert data["version"] == retrostation_player.__version__


def test_remote_renders_tv_remote_ui(monkeypatch, tmp_path):
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path / "state"))

    app_module = importlib.import_module("retrostation_player.app")
    monkeypatch.setattr("retrostation_player.player.state_file", lambda: tmp_path / "state" / "state.json")

    response = app_module.app.test_client().get("/remote")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "RetroStation Remote" in page
    assert "remote.css" in page
    assert "remote.js" in page
    assert "ch-up" in page
    assert "ch-down" in page
    assert "mute-btn" in page
    assert "fullscreen-btn" in page
    assert 'name="apple-mobile-web-app-title" content="RetroStation Remote"' in page


def test_remote_script_includes_fullscreen_fallbacks(monkeypatch, tmp_path):
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path / "state"))

    app_module = importlib.import_module("retrostation_player.app")
    monkeypatch.setattr("retrostation_player.player.state_file", lambda: tmp_path / "state" / "state.json")

    response = app_module.app.test_client().get("/static/remote.js")
    assert response.status_code == 200
    script = response.get_data(as_text=True)

    assert "webkitRequestFullscreen" in script
    assert "mozRequestFullScreen" in script
    assert "msRequestFullscreen" in script
    assert "On iPhone or iPad, add this page to the home screen for fullscreen mode" in script
    assert "Remote is already running in fullscreen app mode" in script
    assert "[document.body, document.documentElement]" in script
    assert 'if (fullscreenBtn)' in script


def test_system_info_api_exposes_platform_and_playback_info(monkeypatch, tmp_path):
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path / "state"))

    app_module = importlib.import_module("retrostation_player.app")
    monkeypatch.setattr("retrostation_player.player.state_file", lambda: tmp_path / "state" / "state.json")

    response = app_module.app.test_client().get("/api/system/info")
    assert response.status_code == 200
    data = response.get_json()

    assert "machine" in data
    assert "operating_system" in data
    assert "display_mode" in data
    assert "display_connector" in data
    assert "detected_drm_connectors" in data
    assert "display_resolution" in data
    assert "active_resolution" in data
    assert "player_backend" in data
    assert "audio_output" in data
    assert "audio_device" in data
    assert "audio_control_mode" in data
    assert "crt_overscan" in data
    assert "hdmi_underscan_percent" in data
    assert "zero_w_video_sizing" in data


def test_index_renders_platform_and_playback_info_section(monkeypatch, tmp_path):
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path / "state"))

    app_module = importlib.import_module("retrostation_player.app")
    monkeypatch.setattr("retrostation_player.player.state_file", lambda: tmp_path / "state" / "state.json")

    response = app_module.app.test_client().get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Platform &amp; Playback Information" in page
    assert "system-raspberry-pi-row" in page
    assert "system-drm-connectors-row" in page
    assert "system-audio-output-row" in page
    assert "system-audio-device-row" in page
    assert "system-drm-kms-row" in page
