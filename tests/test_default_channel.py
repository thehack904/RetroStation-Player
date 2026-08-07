"""Tests for the configurable default channel feature."""
import importlib
import json


def _make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path / "state"))
    app_module = importlib.import_module("retrostation_player.app")
    monkeypatch.setattr("retrostation_player.player.state_file", lambda: tmp_path / "state" / "state.json")
    return app_module.app.test_client()


def test_default_channel_id_in_config_api(monkeypatch, tmp_path):
    client = _make_client(monkeypatch, tmp_path)
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.get_json()
    assert "default_channel_id" in data
    assert data["default_channel_id"] == ""


def test_save_default_channel_id(monkeypatch, tmp_path):
    client = _make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/config",
        data=json.dumps({"default_channel_id": "ch-42"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data.get("default_channel_id") == "ch-42"

    # Persisted value is returned on subsequent GET.
    get_response = client.get("/api/config")
    assert get_response.get_json()["default_channel_id"] == "ch-42"


def test_clear_default_channel_id(monkeypatch, tmp_path):
    client = _make_client(monkeypatch, tmp_path)
    client.post(
        "/api/config",
        data=json.dumps({"default_channel_id": "ch-42"}),
        content_type="application/json",
    )
    response = client.post(
        "/api/config",
        data=json.dumps({"default_channel_id": ""}),
        content_type="application/json",
    )
    assert response.status_code == 200
    get_response = client.get("/api/config")
    assert get_response.get_json()["default_channel_id"] == ""


def test_index_renders_default_channel_select(monkeypatch, tmp_path):
    client = _make_client(monkeypatch, tmp_path)
    response = client.get("/")
    page = response.get_data(as_text=True)
    assert "default-channel-input" in page
    assert "Default Channel on Startup" in page
    assert "Last played channel" in page
