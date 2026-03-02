"""Tests for config loading and state management."""
import json
import pytest
from pathlib import Path
from config import (
    load_config,
    load_state,
    save_state,
    ensure_config_dir,
    CONFIG_DIR,
)


@pytest.fixture
def tmp_config_dir(tmp_path, monkeypatch):
    """Redirect config dir to temp path."""
    monkeypatch.setattr("config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr("config.STATE_FILE", tmp_path / "sent_alerts.json")
    monkeypatch.setattr("config.LOG_DIR", tmp_path / "logs")
    return tmp_path


def test_load_config_missing_file(tmp_config_dir):
    with pytest.raises(FileNotFoundError):
        load_config()


def test_load_config_valid(tmp_config_dir):
    config_file = tmp_config_dir / "config.json"
    config_file.write_text(json.dumps({
        "origin": "ATL",
        "phone": "+15551234567",
        "min_cents_per_mile": 2.0,
        "min_seats": 2,
        "cabins": ["first", "business"],
        "sources": ["delta_search"],
    }))
    config = load_config()
    assert config["origin"] == "ATL"
    assert config["min_cents_per_mile"] == 2.0


def test_load_config_missing_required_field(tmp_config_dir):
    config_file = tmp_config_dir / "config.json"
    config_file.write_text(json.dumps({"origin": "ATL"}))
    with pytest.raises(ValueError, match="phone"):
        load_config()


def test_load_state_empty(tmp_config_dir):
    state = load_state()
    assert state == {}


def test_load_state_valid(tmp_config_dir):
    state_file = tmp_config_dir / "sent_alerts.json"
    state_file.write_text(json.dumps({
        "ATL-NRT-first-2026-05-15": "2026-03-01T10:00:00+00:00"
    }))
    state = load_state()
    assert "ATL-NRT-first-2026-05-15" in state


def test_load_state_prunes_old_entries(tmp_config_dir):
    state_file = tmp_config_dir / "sent_alerts.json"
    state_file.write_text(json.dumps({
        "old-deal": "2025-01-01T00:00:00+00:00",
        "recent-deal": "2026-02-28T00:00:00+00:00",
    }))
    state = load_state()
    assert "old-deal" not in state
    assert "recent-deal" in state


def test_save_state(tmp_config_dir):
    save_state({"deal-1": "2026-03-01T10:00:00+00:00"})
    state_file = tmp_config_dir / "sent_alerts.json"
    data = json.loads(state_file.read_text())
    assert "deal-1" in data


def test_ensure_config_dir(tmp_config_dir):
    log_dir = tmp_config_dir / "logs"
    ensure_config_dir()
    assert log_dir.exists()
