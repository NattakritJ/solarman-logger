"""Tests for solarman_logger.config — config loader with startup validation."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from solarman_logger.config import load_config, Config, DeviceConfig, ConfigError

# Path to the fixtures directory (relative to this test file)
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_valid_config_returns_config_object():
    """Test 1: load_config() with a valid config returns Config with 2 devices and InfluxConfig populated."""
    cfg = load_config(str(FIXTURES_DIR / "valid_config.yaml"))

    assert isinstance(cfg, Config)
    assert len(cfg.devices) == 2

    # InfluxDB section populated
    assert cfg.influxdb.url == "http://localhost:8086"
    assert cfg.influxdb.org == "myorg"
    assert cfg.influxdb.bucket == "solar"
    assert cfg.influxdb.token == "my-secret-token"

    # Global poll_interval
    assert cfg.poll_interval == 60


def test_missing_token_raises_config_error():
    """Test 2: load_config() with missing influxdb.token raises ConfigError mentioning 'influxdb.token'."""
    with pytest.raises(ConfigError) as exc_info:
        load_config(str(FIXTURES_DIR / "missing_token_config.yaml"))

    assert "influxdb.token" in str(exc_info.value)


def test_per_device_poll_interval_override():
    """Test 3: Device with poll_interval override gets that value; device without override gets global default."""
    cfg = load_config(str(FIXTURES_DIR / "valid_config.yaml"))

    # First device has poll_interval: 30 (override)
    deye = cfg.devices[0]
    assert deye.name == "Deye Micro"
    assert deye.poll_interval == 30

    # Second device has no poll_interval — uses global default of 60
    meter = cfg.devices[1]
    assert meter.name == "DDZY Meter"
    assert meter.poll_interval == 60


def test_slave_defaults_to_1():
    """Test 4: Device slave field defaults to 1 when not specified in config."""
    cfg = load_config(str(FIXTURES_DIR / "valid_config.yaml"))

    # First device has slave: 2 explicitly
    deye = cfg.devices[0]
    assert deye.slave == 2

    # Second device has no slave — defaults to 1
    meter = cfg.devices[1]
    assert meter.slave == 1


def test_profile_path_resolution():
    """Test 5: profile_dir ends with '/' and is the absolute directory of the config file; profile_filename is bare filename."""
    cfg = load_config(str(FIXTURES_DIR / "valid_config.yaml"))

    deye = cfg.devices[0]
    meter = cfg.devices[1]

    # profile_dir must be the absolute directory of the config file, ending with "/"
    expected_dir = str(FIXTURES_DIR.resolve()) + "/"
    assert deye.profile_dir == expected_dir, f"Expected '{expected_dir}', got '{deye.profile_dir}'"
    assert meter.profile_dir == expected_dir, f"Expected '{expected_dir}', got '{meter.profile_dir}'"

    # profile_filename is the bare filename from config
    assert deye.profile_filename == "deye_micro.yaml"
    assert meter.profile_filename == "ddzy422-d2.yaml"


def test_nonexistent_file_raises_config_error():
    """Test 6: load_config() with a nonexistent file raises ConfigError."""
    with pytest.raises(ConfigError):
        load_config("nonexistent_file_that_does_not_exist.yaml")


def test_empty_devices_list_raises_config_error():
    """Test 7: Config with empty devices list raises ConfigError."""
    import tempfile
    import yaml

    cfg_data = {
        "influxdb": {"url": "http://localhost:8086", "org": "o", "bucket": "b", "token": "t"},
        "defaults": {"poll_interval": 60},
        "devices": [],
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(cfg_data, f)
        tmp_path = f.name

    try:
        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)
        assert "devices" in str(exc_info.value).lower()
    finally:
        os.unlink(tmp_path)


def test_device_type_field_loaded():
    """Test 8: load_config with valid_config.yaml returns DeviceConfig where .type == 'inverter' for first device and .type == 'meter' for second."""
    cfg = load_config(str(FIXTURES_DIR / "valid_config.yaml"))

    assert cfg.devices[0].type == "inverter"
    assert cfg.devices[1].type == "meter"


def test_missing_type_raises_config_error():
    """Test 9: load_config with config missing devices[0].type raises ConfigError containing 'devices[0].type'."""
    import tempfile
    import yaml

    cfg_data = {
        "influxdb": {"url": "http://localhost:8086", "org": "o", "bucket": "b", "token": "t"},
        "defaults": {"poll_interval": 60},
        "devices": [
            {
                "name": "TestDevice",
                # type intentionally missing
                "host": "192.168.1.1",
                "serial": 12345,
                "profile": "test.yaml",
            }
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(cfg_data, f)
        tmp_path = f.name

    try:
        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)
        assert "devices[0].type" in str(exc_info.value)
    finally:
        os.unlink(tmp_path)
