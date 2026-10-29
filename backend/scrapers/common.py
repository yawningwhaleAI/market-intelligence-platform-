"""Shared helpers for scrapers: env/config loading, run logging, raw storage.

Keeps the token handling in one place so it is never printed or committed
(spec §2). Importing this module does NOT require the token — that is only
fetched when you actually connect to Apify.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
RAW_DIR = ROOT / "raw_data"
LOG_CSV = ROOT / "logs" / "run_log.csv"
IST = ZoneInfo("Asia/Kolkata")

LOG_FIELDS = [
    "run_id", "platform", "actor", "locations", "queries",
    "rows", "cost_usd", "status", "errors", "started_at", "finished_at",
]


def now_ist() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def _load_dotenv() -> None:
    """Minimal .env loader (avoids importing python-dotenv at module import).

    Only sets keys not already in the environment.
    """
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def get_apify_token() -> str:
    """Return the Apify token or raise a clear error. Never logs the value."""
    _load_dotenv()
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token or token == "your_apify_token_here":
        raise RuntimeError(
            "APIFY_TOKEN is not set. Copy .env.example to .env and paste your "
            "token (or set it in the environment). See README Step 0."
        )
    return token


def get_spend_cap_usd() -> float | None:
    """Per-run spend cap in USD, or None if unset.

    Precedence: SOS_SPEND_CAP_USD in the environment/.env overrides the
    committed default in config/actors.yaml (guardrails.spend_cap_usd).
    """
    _load_dotenv()
    raw = os.environ.get("SOS_SPEND_CAP_USD", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    # Fall back to the version-controlled default.
    try:
        cap = (load_yaml("actors.yaml") or {}).get("guardrails", {}).get("spend_cap_usd")
        return float(cap) if cap is not None else None
    except Exception:  # noqa: BLE001 — config is optional/absent pre-Step-0
        return None


def load_yaml(name: str):
    """Load a config YAML. Imports yaml lazily so Step 0 works pre-install."""
    import yaml  # noqa: PLC0415 — lazy so `init_db.py` needs no deps
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def raw_path(platform: str, run_id: str, name: str) -> Path:
    """Path for an untouched Apify JSON payload. Cleaning never overwrites it."""
    d = RAW_DIR / platform / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def save_raw(platform: str, run_id: str, name: str, payload) -> Path:
    p = raw_path(platform, run_id, name)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def append_run_log(row: dict) -> None:
    """Append one row to logs/run_log.csv, writing the header if new."""
    LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG_CSV.exists()
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in LOG_FIELDS})

