"""Regression coverage for database stalls and missed inverter read slots."""

import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from influxdb_client import Point

from solarman_logger.config import DeviceConfig, InfluxConfig
from solarman_logger.poller import create_device_worker
from solarman_logger.writer import InfluxDBWriter


async def _worker():
    profile_dir = Path(__file__).resolve().parents[2] / "config" / "inverter_definitions"
    config = DeviceConfig("west_2", "inverter", "192.0.2.1", 8899, 0, 1, 2,
                          str(profile_dir) + "/", "deye_micro.yaml")
    worker = await create_device_worker(config)
    worker.client.execute = AsyncMock(side_effect = lambda code, start, *, count: [0] * count)
    return worker


@pytest.mark.asyncio
async def test_database_stall_does_not_stop_callbacks_or_inverter_reads():
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def slow_write(**kwargs):
        started.set()
        release.wait(1)
        finished.set()

    with patch("solarman_logger.writer.InfluxDBClient") as factory:
        api = factory.return_value.write_api.return_value
        api.write.side_effect = slow_write
        writer = InfluxDBWriter(InfluxConfig("http://unused", "org", "db", "token"))
        callback = writer.make_data_callback({"west_2": "inverter", "east": "inverter"})
        try:
            await callback("east", {"power": (100, 100)})
            assert await asyncio.to_thread(started.wait, 1)
            assert not finished.is_set(), "The database call blocked the polling event loop"
            worker = await _worker()
            await asyncio.wait_for(worker._poll_cycle(callback), 0.5)
            worker.client.execute.assert_awaited()
            assert worker.health._online is True
            assert not finished.is_set(), "Inverter polling waited for the database"
        finally:
            release.set()
            writer.close()
        assert api.write.call_count == 2


@pytest.mark.asyncio
async def test_healthy_inverter_reads_after_missing_every_exact_slot():
    worker = await _worker()
    callback = AsyncMock()
    # The observed delayed wakes never land on a multiple of five after startup.
    for runtime in (0, 2, 4, 8, 8, 12, 14, 18, 18, 22, 24, 28):
        worker._get_runtime = Mock(return_value = runtime)
        await worker._poll_cycle(callback)
    assert callback.await_count == 6
    assert worker.health._online is True
    assert worker._consecutive_failures == 0


@pytest.mark.asyncio
async def test_profile_intervals_catch_up_once_without_early_metadata_reads():
    worker = await _worker()
    parser = worker.parser
    assert any(request["start"] == 0 for request in parser.schedule_requests(0))
    assert parser.schedule_requests(4) == []
    overdue = parser.schedule_requests(7)
    assert overdue
    assert all(request["start"] > 0 for request in overdue)
    assert parser.schedule_requests(8) == []
    assert parser.schedule_requests(12)
    assert any(request["start"] == 0 for request in parser.schedule_requests(3601))
    assert parser.schedule_requests(3602) == []


@pytest.mark.asyncio
async def test_slow_database_buffer_keeps_latest_samples_and_collection_times(monkeypatch, caplog):
    monkeypatch.setattr("solarman_logger.writer.WRITE_QUEUE_SIZE", 2)
    started, release = threading.Event(), threading.Event()
    records = []

    def slow_write(*, record, **kwargs):
        records.append(record)
        if len(records) == 1:
            started.set()
            release.wait(2)

    with patch("solarman_logger.writer.InfluxDBClient") as factory:
        api = factory.return_value.write_api.return_value
        api.write.side_effect = slow_write
        writer = InfluxDBWriter(InfluxConfig("http://unused", "org", "db", "token"))
        callback = writer.make_data_callback({"west_2": "inverter"})
        before = datetime.now(timezone.utc)
        try:
            await callback("west_2", {"power": (1, 1)})
            assert await asyncio.to_thread(started.wait, 1)
            await callback("west_2", {"power": (2, 2)})
            snapshot = {"power": (3, 3)}
            await callback("west_2", snapshot)
            snapshot["power"] = (999, 999)
            await callback("west_2", {"power": (4, 4)})
            after = datetime.now(timezone.utc)
        finally:
            release.set()
            writer.close()
        assert [record["fields"]["power"] for record in records] == [1.0, 3.0, 4.0]
        assert "dropped oldest" in caplog.text
        for record in records:
            assert before <= record["time"] <= after
            line = Point.from_dict(record).to_line_protocol()
            assert line.endswith(str(int(record["time"].timestamp()) * 1000000000 + record["time"].microsecond * 1000))
        writer.close()
        factory.return_value.close.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_does_not_close_client_while_request_is_in_flight(monkeypatch):
    monkeypatch.setattr("solarman_logger.writer.SHUTDOWN_WAIT_SECONDS", 0.01)
    started, release = threading.Event(), threading.Event()

    def slow_write(**kwargs):
        started.set()
        release.wait(2)

    with patch("solarman_logger.writer.InfluxDBClient") as factory:
        factory.return_value.write_api.return_value.write.side_effect = slow_write
        writer = InfluxDBWriter(InfluxConfig("http://unused", "org", "db", "token"))
        callback = writer.make_data_callback({"west_2": "inverter"})
        try:
            await callback("west_2", {"power": (1, 1)})
            assert await asyncio.to_thread(started.wait, 1)
            writer.close()
            factory.return_value.close.assert_not_called()
        finally:
            release.set()
            if writer._thread is not None:
                writer._thread.join(timeout = 2)
            writer.close()
        factory.return_value.close.assert_called_once()


@pytest.mark.asyncio
async def test_bad_reading_does_not_stop_following_database_writes():
    with patch("solarman_logger.writer.InfluxDBClient") as factory:
        writer = InfluxDBWriter(InfluxConfig("http://unused", "org", "db", "token"))
        callback = writer.make_data_callback({"west_2": "inverter"})
        try:
            await callback("west_2", {"power": (1,)})
            await callback("west_2", {"power": (2, 2)})
        finally:
            writer.close()
        api = factory.return_value.write_api.return_value
        api.write.assert_called_once()
        assert api.write.call_args.kwargs["record"]["fields"]["power"] == 2.0
