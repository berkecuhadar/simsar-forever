import copy
import os
from pathlib import Path

import yaml

DEFAULTS = {
    "tsm": {
        "game_type": "forever",
        "region": "eu",
        "realm": "normal-alliance",
        "check_minutes": 30,
        "timeout_seconds": 60,
    },
    "wow": {
        "game_dir": None,
        "account": None,
        "auctionator_realm": None,
        "watch_seconds": 10,
    },
    "player": {
        "professions": [],
    },
    "economy": {
        "ah_cut": 0.05,
        "deposit_rate": 0.15,
        "auction_hours": 24,
        "realm_share": 0.25,
        "market_share": 0.20,
        "sell_price": "avg_sale",
        "max_relists": 5,
    },
    "analysis": {
        "history_days": 14,
        "min_points_volatility": 6,
        "min_days_trend": 4,
        "good_margin": 0.15,
        "fast_sales_per_day": 5,
        "bubble_ratio": 1.6,
        "stale_hours": 12,
        "live_price_hours": 72,
        "reference_price": "market",
    },
    "alerts": {
        "enabled": True,
        "cheap_below": 0.25,
        "min_craft_profit_gold": 5,
        "min_sales_per_day": 1,
    },
    "storage": {
        "db_path": "data/simsar.db",
        "retain_days": 180,
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8765,
    },
}


class ConfigError(ValueError):
    pass


def _merge(base, override):
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def default_path():
    return Path(os.environ.get("SIMSAR_CONFIG", "config.yaml"))


def load(path=None, overrides=None):
    path = Path(path) if path else default_path()
    user = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        if not isinstance(user, dict):
            raise ConfigError(f"{path} must contain a mapping at the top level")
    cfg = _merge(DEFAULTS, user)
    cfg = _merge(cfg, overrides or {})
    cfg["_path"] = str(path.resolve())
    cfg["_base_dir"] = str(path.resolve().parent)
    validate(cfg)
    return cfg


def validate(cfg):
    eco = cfg["economy"]
    for key in ("ah_cut", "deposit_rate", "realm_share", "market_share"):
        v = eco[key]
        if not isinstance(v, (int, float)) or not 0 <= v <= 1:
            raise ConfigError(f"economy.{key} must be a number between 0 and 1, got {v!r}")
    if eco["auction_hours"] not in (2, 8, 24):
        raise ConfigError("economy.auction_hours must be 2, 8 or 24")
    if eco["sell_price"] not in ("avg_sale", "market"):
        raise ConfigError("economy.sell_price must be 'avg_sale' or 'market'")
    if cfg["analysis"]["reference_price"] not in ("market", "historical"):
        raise ConfigError("analysis.reference_price must be 'market' or 'historical'")
    if cfg["server"]["host"] not in ("127.0.0.1", "localhost", "::1"):
        raise ConfigError("server.host must be a loopback address; Simsar Forever is not meant to be exposed")


def db_path(cfg):
    p = Path(cfg["storage"]["db_path"])
    if not p.is_absolute():
        p = Path(cfg["_base_dir"]) / p
    return p
