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
