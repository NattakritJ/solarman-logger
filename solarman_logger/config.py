"""Config loader for solarman_logger.

Loads and validates a YAML configuration file at startup.
Raises ConfigError immediately on any missing or invalid required field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised on missing or invalid config at startup."""


@dataclass
class InfluxConfig:
    url: str      # e.g. "http://localhost:8086"
    org: str
    bucket: str
    token: str


@dataclass
class DeviceConfig:
    name: str
    host: str
    port: int                  # default 8899
    serial: int                # Solarman V5 serial number (logger stick SN)
    slave: int                 # Modbus slave ID, default 1
    poll_interval: int         # seconds, resolved from device override or global default
    profile_dir: str           # absolute directory path ending with "/"
    profile_filename: str      # e.g. "deye_micro.yaml"


@dataclass
class Config:
    influxdb: InfluxConfig
    poll_interval: int         # global default poll interval (seconds)
    devices: list[DeviceConfig]


def _require(data: dict[str, Any], key: str, context: str = "") -> Any:
    """Return data[key] or raise ConfigError naming the missing field."""
    value = data.get(key)
    field_path = f"{context}.{key}" if context else key
    if value is None:
        raise ConfigError(f"Missing required config: {field_path}")
    if isinstance(value, str) and not value.strip():
        raise ConfigError(f"Missing required config: {field_path}")
    return value


def load_config(path: str) -> Config:
    """Load and validate config from YAML file at `path`.

    Raises ConfigError immediately on any missing required field.
    Profile paths in device entries are resolved relative to the directory of `path`.
    """
    abs_path = Path(path).resolve()

    # Open and parse YAML
    try:
        with open(abs_path) as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}")
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}")

    if not isinstance(raw, dict):
        raise ConfigError("Config file must be a YAML mapping")

    # --- Validate influxdb section ---
    influxdb_raw = raw.get("influxdb")
    if not isinstance(influxdb_raw, dict):
        raise ConfigError("Missing required config: influxdb")

    influx_url = _require(influxdb_raw, "url", "influxdb")
    influx_org = _require(influxdb_raw, "org", "influxdb")
    influx_bucket = _require(influxdb_raw, "bucket", "influxdb")
    influx_token = _require(influxdb_raw, "token", "influxdb")

    influx_cfg = InfluxConfig(
        url=str(influx_url),
        org=str(influx_org),
        bucket=str(influx_bucket),
        token=str(influx_token),
    )

    # --- Validate defaults section ---
    defaults_raw = raw.get("defaults")
    if not isinstance(defaults_raw, dict):
        raise ConfigError("Missing required config: defaults.poll_interval")

    global_poll = defaults_raw.get("poll_interval")
    if global_poll is None:
        raise ConfigError("Missing required config: defaults.poll_interval")
    if not isinstance(global_poll, int) or global_poll <= 0:
        raise ConfigError("Config error: defaults.poll_interval must be a positive integer")

    # --- Validate devices section ---
    devices_raw = raw.get("devices")
    if not devices_raw:
        raise ConfigError("Missing required config: devices (must be a non-empty list)")
    if not isinstance(devices_raw, list):
        raise ConfigError("Config error: devices must be a list")

    # The config file's directory for profile path resolution
    config_dir = str(abs_path.parent) + "/"

    devices: list[DeviceConfig] = []
    for i, dev in enumerate(devices_raw):
        if not isinstance(dev, dict):
            raise ConfigError(f"Config error: devices[{i}] must be a mapping")

        # Required per-device fields
        dev_name = _require(dev, "name", f"devices[{i}]")
        dev_host = _require(dev, "host", f"devices[{i}]")
        dev_serial = dev.get("serial")
        if dev_serial is None:
            raise ConfigError(f"Missing required config: devices[{i}].serial")
        dev_profile = _require(dev, "profile", f"devices[{i}]")

        # Optional with defaults
        dev_port = dev.get("port", 8899)
        dev_slave = dev.get("slave", 1)
        dev_poll = dev.get("poll_interval", global_poll)

        devices.append(DeviceConfig(
            name=str(dev_name),
            host=str(dev_host),
            port=int(dev_port),
            serial=int(dev_serial),
            slave=int(dev_slave),
            poll_interval=int(dev_poll),
            profile_dir=config_dir,
            profile_filename=str(dev_profile),
        ))

    return Config(
        influxdb=influx_cfg,
        poll_interval=global_poll,
        devices=devices,
    )
