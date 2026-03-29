"""Tests for solarman_logger.writer — InfluxDB v2 writer with health check and data callback."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, call

import pytest

from solarman_logger.config import InfluxConfig
from solarman_logger.writer import InfluxDBWriter


@pytest.fixture
def influx_config():
    return InfluxConfig(url="http://localhost:8086", org="myorg", bucket="solar", token="test-token")


@pytest.fixture
def mock_client():
    """Patch InfluxDBClient so no real connection is made."""
    with patch("solarman_logger.writer.InfluxDBClient") as MockClient:
        mock_instance = MagicMock()
        mock_write_api = MagicMock()
        mock_instance.write_api.return_value = mock_write_api
        mock_instance.ping.return_value = True
        MockClient.return_value = mock_instance
        yield {"Client": MockClient, "instance": mock_instance, "write_api": mock_write_api}


def test_write_callback_creates_correct_point(influx_config, mock_client):
    """write_callback with mixed numeric and string fields creates a Point with float-cast numerics, string preserved, and correct tags."""
    writer = InfluxDBWriter(influx_config)

    parsed = {
        "voltage": (236.9, None),
        "current": (1.5, None),
        "status": ("ok", None),
    }
    writer.write_callback("smart-meter", "meter", parsed)

    mock_client["write_api"].write.assert_called_once()
    record = mock_client["write_api"].write.call_args[1]["record"]

    assert record["measurement"] == "smart-meter"
    assert record["tags"]["device_name"] == "smart-meter"
    assert record["tags"]["device_type"] == "meter"
    assert record["fields"]["voltage"] == 236.9
    assert record["fields"]["current"] == 1.5
    assert record["fields"]["status"] == "ok"
    assert isinstance(record["fields"]["voltage"], float)
    assert isinstance(record["fields"]["current"], float)


def test_write_callback_casts_int_zero_to_float(influx_config, mock_client):
    """write_callback with parsed={'energy': (0, None)} writes field energy as float(0) i.e. 0.0, not int 0."""
    writer = InfluxDBWriter(influx_config)

    parsed = {"energy": (0, None)}
    writer.write_callback("inverter-1", "inverter", parsed)

    record = mock_client["write_api"].write.call_args[1]["record"]
    assert record["fields"]["energy"] == 0.0
    assert isinstance(record["fields"]["energy"], float)


def test_write_callback_swallows_write_errors(influx_config, mock_client):
    """write_callback that raises an InfluxDB API error logs a warning and does NOT re-raise."""
    mock_client["write_api"].write.side_effect = Exception("connection refused")
    writer = InfluxDBWriter(influx_config)

    parsed = {"voltage": (230.0, None)}

    # Should not raise
    writer.write_callback("meter-1", "meter", parsed)


def test_write_callback_logs_warning_on_failure(influx_config, mock_client):
    """write_callback logs a warning when write fails."""
    mock_client["write_api"].write.side_effect = Exception("connection refused")
    writer = InfluxDBWriter(influx_config)

    parsed = {"voltage": (230.0, None)}

    with patch("solarman_logger.writer._LOGGER") as mock_logger:
        writer.write_callback("meter-1", "meter", parsed)
        mock_logger.warning.assert_called_once()
        assert "meter-1" in str(mock_logger.warning.call_args)


def test_check_health_success(influx_config, mock_client):
    """check_health succeeds silently when ping returns True."""
    writer = InfluxDBWriter(influx_config)

    # Should not raise
    writer.check_health()
    mock_client["instance"].ping.assert_called_once()


def test_check_health_failure_raises(influx_config, mock_client):
    """check_health raises RuntimeError with URL when ping raises."""
    mock_client["instance"].ping.side_effect = Exception("unreachable")
    writer = InfluxDBWriter(influx_config)

    with pytest.raises(RuntimeError) as exc_info:
        writer.check_health()

    assert "http://localhost:8086" in str(exc_info.value)


def test_close_calls_both(influx_config, mock_client):
    """close() calls write_api.close() and client.close()."""
    writer = InfluxDBWriter(influx_config)

    writer.close()

    mock_client["write_api"].close.assert_called_once()
    mock_client["instance"].close.assert_called_once()


def test_make_data_callback_returns_async_callable(influx_config, mock_client):
    """make_data_callback returns an async function matching DataCallback signature."""
    writer = InfluxDBWriter(influx_config)
    device_configs = {"smart-meter": "meter", "inverter-1": "inverter"}
    callback = writer.make_data_callback(device_configs)

    # Must be a coroutine function
    assert asyncio.iscoroutinefunction(callback)


def test_make_data_callback_calls_write_callback(influx_config, mock_client):
    """make_data_callback async callable calls write_callback with correct device_type from lookup."""
    writer = InfluxDBWriter(influx_config)
    device_configs = {"smart-meter": "meter", "inverter-1": "inverter"}
    callback = writer.make_data_callback(device_configs)

    parsed = {"voltage": (236.9, None)}
    asyncio.get_event_loop().run_until_complete(callback("smart-meter", parsed))

    mock_client["write_api"].write.assert_called_once()
    record = mock_client["write_api"].write.call_args[1]["record"]
    assert record["tags"]["device_type"] == "meter"
    assert record["tags"]["device_name"] == "smart-meter"
