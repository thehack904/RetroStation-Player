import json
from pathlib import Path

from retrostation_player.config import DEFAULT_CONFIG, load_config


def test_default_config_does_not_enable_generic_hwdec(monkeypatch, tmp_path):
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    config = load_config()

    assert config["player_extra_args"] == ["--no-osc", "--no-input-default-bindings"]
    assert config["mpv_extra_args"] == ["--no-osc", "--no-input-default-bindings"]


def test_default_config_constants_do_not_enable_generic_hwdec():
    assert DEFAULT_CONFIG["player_extra_args"] == ["--no-osc", "--no-input-default-bindings"]
    assert DEFAULT_CONFIG["mpv_extra_args"] == ["--no-osc", "--no-input-default-bindings"]


def test_example_config_does_not_enable_generic_hwdec():
    example_path = Path(__file__).resolve().parent.parent / "config.example.json"
    example = json.loads(example_path.read_text(encoding="utf-8"))

    assert example["player_extra_args"] == ["--no-osc", "--no-input-default-bindings"]
