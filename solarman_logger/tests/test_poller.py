"""Unit tests for standalone device polling."""

from __future__ import annotations

import logging

from unittest.mock import AsyncMock, Mock

import pytest

from solarman_logger.config import DeviceConfig
from solarman_logger.poller import DeviceHealth, DeviceWorker, _detect_solar
from solarman_logger.pysolarman.umodbus.exceptions import ServerDeviceBusyError


def _device_config() -> DeviceConfig:
    return DeviceConfig(
        name = "Test Device",
        type = "inverter",
        host = "192.168.1.10",
        port = 8899,
        serial = 2000000000,
        slave = 1,
        poll_interval = 60,
        profile_dir = "/tmp/",
        profile_filename = "deye_micro.yaml",
    )


def _worker(*, is_solar: bool = False) -> DeviceWorker:
    parser = Mock()
    parser.schedule_requests.return_value = []
    parser.process.return_value = {"power": (1.0, 1.0)}

    client = AsyncMock()
    client.execute.return_value = [0] * 11

    return DeviceWorker(_device_config(), parser, client, is_solar = is_solar)


def test_device_health_logs_online_once(caplog):
    """First success logs online, repeated success stays quiet."""
    health = DeviceHealth(is_solar = False)
    logger = logging.getLogger("test-device-health-online")

    with caplog.at_level(logging.INFO, logger = logger.name):
        health.report_success(logger)
        health.report_success(logger)

    records = [record for record in caplog.records if record.name == logger.name]
    assert len(records) == 1
    assert "Device online" in records[0].message


def test_device_health_logs_offline_transition_for_non_solar(caplog):
    """Non-solar devices warn once, then downgrade repeats to debug."""
    health = DeviceHealth(is_solar = False)
    logger = logging.getLogger("test-device-health-offline")

    with caplog.at_level(logging.DEBUG, logger = logger.name):
        health.report_failure(logger, TimeoutError("timeout"))
        health.report_failure(logger, TimeoutError("timeout"))
        health.report_failure(logger, TimeoutError("timeout"))

    records = [record for record in caplog.records if record.name == logger.name]
    assert records[0].levelno == logging.WARNING
    assert records[1].levelno == logging.DEBUG
    assert records[2].levelno == logging.DEBUG


def test_device_health_logs_expected_offline_for_solar(caplog):
    """Solar devices log expected offline transitions at info."""
    health = DeviceHealth(is_solar = True)
    logger = logging.getLogger("test-device-health-solar")

    with caplog.at_level(logging.INFO, logger = logger.name):
        health.report_failure(logger, TimeoutError("timeout"))

    record = next(record for record in caplog.records if record.name == logger.name)
    assert record.levelno == logging.INFO
    assert "expected" in record.message.lower()


def test_device_health_logs_recovery(caplog):
    """Success after an offline period logs recovery."""
    health = DeviceHealth(is_solar = False)
    logger = logging.getLogger("test-device-health-recovery")

    with caplog.at_level(logging.INFO, logger = logger.name):
        health.report_failure(logger, TimeoutError("timeout"))
        caplog.clear()
        health.report_success(logger)

    record = next(record for record in caplog.records if record.name == logger.name)
    assert record.levelno == logging.INFO
    assert "recovered" in record.message.lower()


def test_device_health_logs_invalid_data_transition(caplog):
    """Invalid data warns once, then resumes cleanly on success."""
    health = DeviceHealth(is_solar = False)
    logger = logging.getLogger("test-device-health-invalid")
    health.report_success(logger)

    with caplog.at_level(logging.DEBUG, logger = logger.name):
        caplog.clear()
        health.report_invalid_data(logger, "bad data")
        health.report_invalid_data(logger, "bad data")
        health.report_success(logger)

    records = [record for record in caplog.records if record.name == logger.name]
    assert records[0].levelno == logging.WARNING
    assert records[1].levelno == logging.DEBUG
    assert any("valid data resumed" in record.message.lower() for record in records)


def test_backoff_is_exponential_and_capped():
    """Failures double the poll delay until the five minute cap."""
    worker = _worker()

    worker._handle_failure(TimeoutError("timeout"))
    assert worker._backoff_interval == 120

    worker._handle_failure(TimeoutError("timeout"))
    assert worker._backoff_interval == 240

    worker._handle_failure(TimeoutError("timeout"))
    assert worker._backoff_interval == 300

    worker._handle_failure(TimeoutError("timeout"))
    assert worker._backoff_interval == 300

    worker._handle_success()
    assert worker._backoff_interval == 60


def test_runtime_is_rounded_to_poll_interval():
    """Elapsed runtime stays anchored to poll interval ticks."""
    worker = _worker()
    worker._started_at = 100.0

    assert worker._get_runtime(now = 100.0) == 0
    assert worker._get_runtime(now = 160.0) == 60
    assert worker._get_runtime(now = 3700.0) == 3600


@pytest.mark.asyncio
async def test_poll_cycle_success_calls_callback():
    """Successful polls execute requests, parse responses, and emit data."""
    worker = _worker()
    worker.parser.schedule_requests.return_value = [{"code": 3, "start": 0, "count": 11}]
    worker.parser.process.return_value = {"power": (1.0, 1.0)}
    callback = AsyncMock()

    await worker._poll_cycle(callback)

    worker.client.execute.assert_awaited_once_with(3, 0, count = 11)
    worker.parser.process.assert_called_once_with({(3, 0): [0] * 11})
    callback.assert_awaited_once_with("Test Device", {"power": (1.0, 1.0)})
    assert worker._cycle_count == 1


@pytest.mark.asyncio
async def test_poll_cycle_timeout_updates_health_and_backoff():
    """Timeouts do not emit data and move the worker offline."""
    worker = _worker()
    worker.parser.schedule_requests.return_value = [{"code": 3, "start": 0, "count": 11}]
    worker.client.execute.side_effect = TimeoutError("timeout")
    callback = AsyncMock()

    await worker._poll_cycle(callback)

    callback.assert_not_awaited()
    assert worker._consecutive_failures == 1
    assert worker._backoff_interval == 120
    assert worker.health._online is False


@pytest.mark.asyncio
async def test_poll_cycle_invalid_data_drops_cycle():
    """Validation failures drop the full cycle and keep advancing time."""
    worker = _worker()
    worker.parser.schedule_requests.return_value = [{"code": 3, "start": 0, "count": 11}]
    worker.parser.process.side_effect = ValueError("invalid dataset")
    callback = AsyncMock()

    await worker._poll_cycle(callback)

    callback.assert_not_awaited()
    assert worker._cycle_count == 1
    assert worker.health._valid_data is False


@pytest.mark.asyncio
async def test_poll_cycle_prevents_overlap():
    """Concurrent poll attempts are skipped when one is already running."""
    worker = _worker()
    worker._polling_in_progress = True
    callback = AsyncMock()

    await worker._poll_cycle(callback)

    worker.parser.schedule_requests.assert_not_called()
    worker.client.execute.assert_not_called()


def test_detect_solar_uses_profile_metadata():
    """Solar detection keys off PV-style item names or filename hints."""
    parser = Mock()
    parser.info = {"filename": "ddzy422-d2.yaml"}
    parser.get_entity_descriptions.return_value = [{"name": "Grid Voltage"}]
    assert _detect_solar(parser) is False

    parser.info = {"filename": "deye_micro.yaml"}
    parser.get_entity_descriptions.return_value = [{"name": "PV1 Voltage"}]
    assert _detect_solar(parser) is True


@pytest.mark.asyncio
async def test_poll_cycle_server_busy_updates_health_and_backoff():
    """ServerDeviceBusyError is treated as a transient failure, not an unexpected error."""
    worker = _worker()
    worker.parser.schedule_requests.return_value = [{"code": 3, "start": 0, "count": 11}]
    worker.client.execute.side_effect = ServerDeviceBusyError()
    callback = AsyncMock()

    await worker._poll_cycle(callback)

    callback.assert_not_awaited()
    assert worker._consecutive_failures == 1
    assert worker._backoff_interval == 120
    assert worker.health._online is False
