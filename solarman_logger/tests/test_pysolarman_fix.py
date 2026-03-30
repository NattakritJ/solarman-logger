"""Regression tests for standalone pysolarman fixes."""

from __future__ import annotations

import asyncio
import struct

from unittest.mock import AsyncMock, Mock, patch

import pytest

from solarman_logger.pysolarman import Solarman, PROTOCOL
from solarman_logger.pysolarman.umodbus.exceptions import ServerDeviceBusyError


def _fake_task_factory(coro, *, name = None, context = None):
    """Close spawned coroutines and return a task-like mock."""
    coro.close()
    task = Mock()
    task.done.return_value = False
    task.cancel.return_value = None
    return task


# --- Serial setter: always use placeholder for auto-discovery ---


class TestSerialSetterAutoDiscovery:
    """The serial setter must always use PLACEHOLDER3 (00000000) when receiving
    an int so the first V5 frame goes out anonymous, avoiding session conflicts
    with the Solarman cloud."""

    def test_serial_int_below_threshold_uses_placeholder(self):
        """Serial below 0x80000000 gets placeholder (unchanged from original behavior)."""
        client = Solarman("192.168.1.1", 8899, "tcp", 1700000000, 1, 10)
        assert client.serial_bytes == PROTOCOL.PLACEHOLDER3
        assert client._serial == 1700000000

    def test_serial_int_above_threshold_now_uses_placeholder(self):
        """Serial >= 0x80000000 ALSO gets placeholder (this is the fix).

        Previously this would embed the real serial bytes in the frame,
        causing ServerDeviceBusy when the cloud already holds a session
        with the same serial.
        """
        high_serial = 2700000000  # 0xA0EEBB00 — above 0x80000000
        client = Solarman("192.168.1.1", 8899, "tcp", high_serial, 1, 10)
        assert client.serial_bytes == PROTOCOL.PLACEHOLDER3
        assert client._serial == high_serial

    def test_serial_int_max_32bit_uses_placeholder(self):
        """Even 0xFFFFFFFF gets placeholder when set via int."""
        client = Solarman("192.168.1.1", 8899, "tcp", 0xFFFFFFFF, 1, 10)
        assert client.serial_bytes == PROTOCOL.PLACEHOLDER3
        assert client._serial == 0xFFFFFFFF

    def test_serial_int_zero_uses_placeholder(self):
        """Serial 0 gets placeholder (auto-discover from device)."""
        client = Solarman("192.168.1.1", 8899, "tcp", 0, 1, 10)
        assert client.serial_bytes == PROTOCOL.PLACEHOLDER3
        assert client._serial == 0

    def test_serial_bytes_path_sets_real_bytes(self):
        """When serial is set via bytes (auto-discovery response), real bytes are used."""
        client = Solarman("192.168.1.1", 8899, "tcp", 0, 1, 10)
        real_serial_bytes = struct.pack("<I", 2700000000)
        client.serial = real_serial_bytes
        assert client.serial_bytes == real_serial_bytes
        assert client._serial == 2700000000

    def test_serial_bytes_path_works_for_any_value(self):
        """Bytes path always sets real bytes — no range check."""
        client = Solarman("192.168.1.1", 8899, "tcp", 0, 1, 10)
        low_serial_bytes = struct.pack("<I", 1234567890)
        client.serial = low_serial_bytes
        assert client.serial_bytes == low_serial_bytes
        assert client._serial == 1234567890


# --- Connection retry ---


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


@pytest.mark.asyncio
async def test_busy_retry_succeeds_after_transient_busy():
    """ServerDeviceBusyError is retried with delay and succeeds on a later attempt."""
    client = Solarman("192.168.1.1", 8899, "tcp", 2000000000, 1, 10)
    expected_data = [100, 200, 300]

    client.get_response = AsyncMock(
        side_effect = [ServerDeviceBusyError(), ServerDeviceBusyError(), expected_data]
    )

    with patch("solarman_logger.pysolarman.asyncio.sleep", new = AsyncMock()) as mock_sleep:
        result = await client.get_response_with_busy_retry(3, 0, count = 10)

    assert result == expected_data
    assert client.get_response.await_count == 3
    assert mock_sleep.await_count == 2
    mock_sleep.assert_awaited_with(client.BUSY_RETRY_DELAY)


@pytest.mark.asyncio
async def test_busy_retry_exhausted_raises():
    """ServerDeviceBusyError is re-raised after all retry attempts are exhausted."""
    client = Solarman("192.168.1.1", 8899, "tcp", 2000000000, 1, 10)

    client.get_response = AsyncMock(
        side_effect = ServerDeviceBusyError()
    )

    with patch("solarman_logger.pysolarman.asyncio.sleep", new = AsyncMock()):
        with pytest.raises(ServerDeviceBusyError):
            await client.get_response_with_busy_retry(3, 0, count = 10)

    assert client.get_response.await_count == client.BUSY_RETRY_ATTEMPTS


@pytest.mark.asyncio
async def test_busy_retry_does_not_catch_other_errors():
    """Non-busy exceptions propagate immediately without retry."""
    client = Solarman("192.168.1.1", 8899, "tcp", 2000000000, 1, 10)

    client.get_response = AsyncMock(
        side_effect = TimeoutError("connection timed out")
    )

    with patch("solarman_logger.pysolarman.asyncio.sleep", new = AsyncMock()) as mock_sleep:
        with pytest.raises(TimeoutError):
            await client.get_response_with_busy_retry(3, 0, count = 10)

    assert client.get_response.await_count == 1
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_busy_retry_succeeds_on_first_attempt():
    """When device is not busy, get_response_with_busy_retry returns immediately."""
    client = Solarman("192.168.1.1", 8899, "tcp", 2000000000, 1, 10)
    expected_data = [42]

    client.get_response = AsyncMock(return_value = expected_data)

    with patch("solarman_logger.pysolarman.asyncio.sleep", new = AsyncMock()) as mock_sleep:
        result = await client.get_response_with_busy_retry(3, 0, count = 1)

    assert result == expected_data
    assert client.get_response.await_count == 1
    mock_sleep.assert_not_awaited()
