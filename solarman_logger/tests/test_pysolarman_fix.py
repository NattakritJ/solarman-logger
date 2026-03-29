"""Regression tests for standalone pysolarman fixes."""

from __future__ import annotations

import asyncio

from unittest.mock import AsyncMock, Mock, patch

import pytest

from solarman_logger.pysolarman import Solarman


def _fake_task_factory(coro, *, name = None, context = None):
    """Close spawned coroutines and return a task-like mock."""
    coro.close()
    task = Mock()
    task.done.return_value = False
    task.cancel.return_value = None
    return task


@pytest.mark.asyncio
async def test_open_connection_bounded_retry():
    """Open connection stops after three failed attempts."""
    client = Solarman("192.168.1.1", 8899, "tcp", 2000000000, 1, 10)
    client._last_frame = b"\x00"

    with patch("solarman_logger.pysolarman.asyncio.open_connection", new = AsyncMock(side_effect = OSError("Connection refused"))) as open_connection, \
         patch("solarman_logger.pysolarman.create_task", side_effect = _fake_task_factory):
        with pytest.raises(ConnectionError):
            await client._open_connection()

    assert open_connection.await_count == 3


@pytest.mark.asyncio
async def test_open_connection_succeeds_on_second_attempt():
    """Open connection retries once and succeeds on the second attempt."""
    client = Solarman("192.168.1.1", 8899, "tcp", 2000000000, 1, 10)
    client._last_frame = b"\x00"

    reader = Mock()
    writer = Mock()

    with patch("solarman_logger.pysolarman.asyncio.open_connection", new = AsyncMock(side_effect = [OSError("Connection refused"), (reader, writer)])) as open_connection, \
         patch("solarman_logger.pysolarman.create_task", side_effect = _fake_task_factory):
        await client._open_connection()

    assert open_connection.await_count == 2
    assert client._reader is reader
    assert client._writer is writer


@pytest.mark.asyncio
async def test_no_last_frame_replay_after_reconnect():
    """Reconnect does not replay the last in-flight request."""
    client = Solarman("192.168.1.1", 8899, "tcp", 2000000000, 1, 10)
    client._last_frame = b"\xAA\xBB"
    client._data_event.set()
    client._write = AsyncMock()

    with patch("solarman_logger.pysolarman.asyncio.open_connection", new = AsyncMock(return_value = (Mock(), Mock()))), \
         patch("solarman_logger.pysolarman.create_task", side_effect = _fake_task_factory):
        await client._open_connection()

    client._write.assert_not_awaited()


def test_data_event_is_asyncio_event():
    """Solarman uses asyncio.Event for in-flight frame coordination."""
    client = Solarman("192.168.1.1", 8899, "tcp", 2000000000, 1, 10)
    assert isinstance(client._data_event, asyncio.Event)
