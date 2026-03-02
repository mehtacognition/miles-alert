"""Configuration and state management for miles-alert."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "miles-alert"
CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = CONFIG_DIR / "sent_alerts.json"
LOG_DIR = CONFIG_DIR / "logs"

REQUIRED_FIELDS = ["origin", "phone"]
STATE_PRUNE_DAYS = 14


def ensure_config_dir():
    """Create config and log directories if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    """Load configuration from JSON file."""
    ensure_config_dir()
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Config not found at {CONFIG_FILE}\n"
            f"Create it with at least: origin, phone"
        )
    with open(CONFIG_FILE) as f:
        config = json.load(f)

    for field in REQUIRED_FIELDS:
        if field not in config:
            raise ValueError(f"Missing required config field: {field}")

    config.setdefault("min_cents_per_mile", 2.0)
    config.setdefault("min_seats", 2)
    config.setdefault("cabins", ["first", "business"])
    config.setdefault("sources", ["seats_aero"])
    config.setdefault("seats_aero_api_key", None)
    config.setdefault("excluded_destinations", [])
    return config


def load_state():
    """Load sent alert state. Prunes entries older than STATE_PRUNE_DAYS."""
    if not STATE_FILE.exists():
        return {}
    with open(STATE_FILE) as f:
        data = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=STATE_PRUNE_DAYS)
    pruned = {}
    for key, ts in data.items():
        if ts is None:
            pruned[key] = ts
        else:
            alert_time = datetime.fromisoformat(ts)
            if alert_time > cutoff:
                pruned[key] = ts
    return pruned


def save_state(state):
    """Save alert state to disk."""
    ensure_config_dir()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
