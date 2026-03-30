"""Tests for solarman_logger.config — config loader with startup validation."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from solarman_logger.config import load_config, Config, DeviceConfig, ConfigError, _parse_serial

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


# --- Serial parsing tests ---


class TestParseSerial:
    """Tests for _parse_serial helper — decimal, hex, edge cases."""

    def test_int_passthrough(self):
        """YAML-parsed int values pass through unchanged."""
        assert _parse_serial(1234567890, "devices[0].serial") == 1234567890

    def test_decimal_string(self):
        """Decimal string is parsed as base-10 integer."""
        assert _parse_serial("1234567890", "devices[0].serial") == 1234567890

    def test_hex_string_no_prefix(self):
        """Hex string without 0x prefix is parsed as base-16 (the reported bug)."""
        assert _parse_serial("251017036F", "devices[0].serial") == 0x251017036F

    def test_hex_string_with_0x_prefix(self):
        """Hex string with 0x prefix is parsed as base-16."""
        assert _parse_serial("0x251017036F", "devices[0].serial") == 0x251017036F

    def test_hex_string_uppercase(self):
        """Uppercase hex string is accepted."""
        assert _parse_serial("DEADBEEF", "devices[0].serial") == 0xDEADBEEF

    def test_hex_string_lowercase(self):
        """Lowercase hex string is accepted."""
        assert _parse_serial("deadbeef", "devices[0].serial") == 0xDEADBEEF

    def test_non_numeric_raises_config_error(self):
        """Completely non-numeric string raises ConfigError."""
        with pytest.raises(ConfigError, match="must be a numeric value"):
            _parse_serial("not-a-number", "devices[0].serial")

    def test_negative_int_raises_config_error(self):
        """Negative integer raises ConfigError."""
        with pytest.raises(ConfigError, match="non-negative"):
            _parse_serial(-1, "devices[0].serial")

    def test_zero_is_valid(self):
        """Zero is a valid serial (protocol will auto-discover)."""
        assert _parse_serial(0, "devices[0].serial") == 0

    def test_max_32bit_is_valid(self):
        """Maximum 32-bit value (0xFFFFFFFF) is valid without warning."""
        assert _parse_serial(0xFFFFFFFF, "devices[0].serial") == 0xFFFFFFFF

    def test_exceeds_32bit_logs_warning(self, caplog):
        """Value exceeding 32 bits is accepted but logs a warning."""
        import logging
        with caplog.at_level(logging.WARNING):
            result = _parse_serial("251017036F", "devices[0].serial")
        assert result == 0x251017036F
        assert "exceeds 32-bit range" in caplog.text
        assert "auto-discover" in caplog.text

    def test_decimal_preferred_over_hex(self):
        """A string that is valid decimal is parsed as decimal, not hex."""
        # "123" is valid both as decimal (123) and hex (0x123=291).
        # Decimal should win.
        assert _parse_serial("123", "devices[0].serial") == 123


def test_hex_serial_in_full_config():
    """Integration test: load_config accepts a hex serial string in YAML."""
    import tempfile
    import yaml

    cfg_data = {
        "influxdb": {"url": "http://localhost:8086", "org": "o", "bucket": "b", "token": "t"},
        "defaults": {"poll_interval": 60},
        "devices": [
            {
                "name": "HexSerialDevice",
                "type": "inverter",
                "host": "192.168.1.100",
                "serial": "251017036F",
                "profile": "test.yaml",
            }
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(cfg_data, f)
        tmp_path = f.name

    try:
        cfg = load_config(tmp_path)
        assert cfg.devices[0].serial == 0x251017036F
    finally:
        os.unlink(tmp_path)


# --- Optional serial (auto-discovery) ---


def test_missing_serial_defaults_to_zero():
    """Device without serial field gets serial=0 (auto-discover from device)."""
    import tempfile
    import yaml

    cfg_data = {
        "influxdb": {"url": "http://localhost:8086", "org": "o", "bucket": "b", "token": "t"},
        "defaults": {"poll_interval": 60},
        "devices": [
            {
                "name": "AutoDiscoverDevice",
                "type": "inverter",
                "host": "192.168.1.100",
                "profile": "test.yaml",
                # serial intentionally omitted
            }
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(cfg_data, f)
        tmp_path = f.name

    try:
        cfg = load_config(tmp_path)
        assert cfg.devices[0].serial == 0
    finally:
        os.unlink(tmp_path)


def test_explicit_serial_still_works():
    """Device with explicit serial field still parses correctly."""
    import tempfile
    import yaml

    cfg_data = {
        "influxdb": {"url": "http://localhost:8086", "org": "o", "bucket": "b", "token": "t"},
        "defaults": {"poll_interval": 60},
        "devices": [
            {
                "name": "ExplicitSerialDevice",
                "type": "inverter",
                "host": "192.168.1.100",
                "serial": 2700000000,
                "profile": "test.yaml",
            }
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(cfg_data, f)
        tmp_path = f.name

    try:
        cfg = load_config(tmp_path)
        assert cfg.devices[0].serial == 2700000000
    finally:
        os.unlink(tmp_path)
