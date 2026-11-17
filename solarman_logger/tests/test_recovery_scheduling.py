"""Recovery must read real profile registers despite backoff timing offsets."""

import logging
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from solarman_logger.config import DeviceConfig
from solarman_logger.poller import create_device_worker


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [2, 4, 6, 8])
async def test_offline_retries_read_deye_profile_at_every_backoff_phase(offset, caplog):
    profile_dir = Path(__file__).resolve().parents[2] / "config" / "inverter_definitions"
    config = DeviceConfig(
        name = "recovery-scheduling-test",
        type = "inverter",
        host = "192.0.2.1",
        port = 8899,
        serial = 0,
        slave = 1,
        poll_interval = 2,
        profile_dir = str(profile_dir) + "/",
        profile_filename = "deye_micro.yaml",
    )
    worker = await create_device_worker(config)
    worker._get_runtime = Mock(return_value = 0)
    worker.client.execute = AsyncMock(side_effect = TimeoutError("inverter asleep"))
    callback = AsyncMock()
    caplog.set_level(logging.INFO, logger = worker.logger.name)

    # Sunset: a real scheduled poll fails and marks the device offline.
    worker.health.report_success(worker.logger)
    await worker._poll_cycle(callback)
    assert worker.health._online is False
    assert worker.client.execute.await_count == 1

    # These are the live failure's timing offsets, repeated every five minutes.
    for attempt in range(8):
        runtime = 161190 + offset + 300 * attempt
        worker._get_runtime.return_value = runtime
        await worker._poll_cycle(callback)
        assert worker.client.execute.await_count == attempt + 2

    callback.assert_not_awaited()
    assert worker.health._online is False
    assert worker._current_interval == 300
    offline = [record for record in caplog.records if "Device offline:" in record.message]
    assert len(offline) == 1
    assert offline[0].levelno == logging.INFO
    assert "expected overnight sleep possible" in offline[0].message

    # Sunrise: the same off-boundary retry must now read and recover.
    worker.client.execute.side_effect = lambda code, start, *, count: [0] * count
    worker._get_runtime.return_value = 161190 + offset + 300 * 8
    await worker._poll_cycle(callback)
    callback.assert_awaited_once()
    assert callback.await_args.args[1]
    assert worker.health._online is True
    assert worker._consecutive_failures == 0
    assert worker._current_interval == 2
    assert any(record.message == "Device recovered" for record in caplog.records)

    # Healthy devices retain the profile's usual schedule, including idle ticks.
    worker.client.execute.reset_mock()
    callback.reset_mock()
    await worker._poll_cycle(callback)
    worker.client.execute.assert_not_awaited()
    callback.assert_not_awaited()
    worker._get_runtime.return_value += 10
    await worker._poll_cycle(callback)
    assert worker.client.execute.await_count > 0
    callback.assert_awaited_once()
