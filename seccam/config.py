"""Load config.json, then overlay config.local.json (git-ignored, holds the Telegram token)."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load(path=None):
    path = Path(path) if path else ROOT / "config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    local = path.with_name("config.local.json")
    if local.exists():
        _merge(cfg, json.loads(local.read_text(encoding="utf-8")))
    tg = cfg["telegram"]
    tg["token"] = os.environ.get("TELEGRAM_TOKEN", tg.get("token", ""))
    tg["chat_id"] = os.environ.get("TELEGRAM_CHAT_ID", tg.get("chat_id", ""))
    return cfg


def resolve(p):
    """Paths in the config are relative to the project root."""
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def save_local(updates):
    """Merge `updates` into config.local.json (used by tools/telegram_setup.py)."""
    local = ROOT / "config.local.json"
    data = json.loads(local.read_text(encoding="utf-8")) if local.exists() else {}
    _merge(data, updates)
    local.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(local, 0o600)
    except OSError:
        pass
    return local
