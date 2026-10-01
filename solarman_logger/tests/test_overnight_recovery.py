import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest

from solarman_logger.pysolarman import Solarman
from solarman_logger.config import DeviceConfig
from solarman_logger.poller import DeviceWorker


@pytest.mark.asyncio
@pytest.mark.parametrize('disconnect', ['eof', 'reset'])
async def test_sunrise_reopens_after_sunset_reconnect_failed(disconnect, caplog):
    client = Solarman('test-inverter', 8899, 'tcp', 0, 1, 1)
    client._last_frame = b'previous-read'
    old_reader = Mock()
    old_reader.read = AsyncMock(return_value=b'') if disconnect == 'eof' else AsyncMock(side_effect=ConnectionResetError())
    old_writer = Mock()
    old_writer.is_closing.return_value = True
    old_writer.write.side_effect = ConnectionResetError('sunset: old socket closed')
    old_writer.wait_closed = AsyncMock()
    client._reader, client._writer = old_reader, old_writer

    with patch('solarman_logger.pysolarman.asyncio.open_connection', new=AsyncMock(side_effect=OSError('night: inverter asleep'))) as connect:
        await client._keeper_loop()
        with pytest.raises(ConnectionError):
            await client._keeper
        assert connect.await_count == 3

    parser = Mock()
    parser.schedule_requests.return_value = [{'code': 3, 'start': 0, 'count': 1}]
    parser.process.return_value = {'power': (100, 100)}
    config = DeviceConfig('solar-test', 'inverter', 'test-inverter', 8899, 0, 1, 2, '', 'deye_micro.yaml')
    worker = DeviceWorker(config, parser, client, is_solar=True)
    callback = AsyncMock()
    async def get_read_response(*args, **kwargs):
        await client._send_receive_frame(b'new-read')
        return [4]
    client._get_response = get_read_response
    caplog.set_level(logging.DEBUG)
    with patch('solarman_logger.pysolarman.asyncio.open_connection', new=AsyncMock(side_effect=OSError('night: inverter asleep'))):
        for _ in range(8):
            await worker._poll_cycle(callback)
    assert worker.health._online is False
    assert worker._backoff_interval == 300
    callback.assert_not_awaited()
    offline = [r for r in caplog.records if r.name == 'solar-test' and 'Device offline:' in r.message]
    assert len(offline) == 1
    assert offline[0].levelno == logging.INFO
    assert 'expected overnight sleep possible' in offline[0].message

    # The device now accepts connections again, exactly as at sunrise.
    new_reader, new_writer = Mock(), Mock()
    async def read_forever(*args):
        await asyncio.Future()
    async def respond():
        client._data_queue.put_nowait(b'valid-response')
    new_reader.read = read_forever
    new_writer.drain = respond
    new_writer.wait_closed = AsyncMock()
    new_writer.is_closing.return_value = False
    with patch('solarman_logger.pysolarman.asyncio.open_connection', new=AsyncMock(return_value=(new_reader, new_writer))) as connect:
        try:
            await worker._poll_cycle(callback)
            callback.assert_awaited_once()
            assert worker.health._online is True
            assert worker._consecutive_failures == 0
            assert worker._backoff_interval == 2
            assert connect.await_count == 1
            assert any(r.name == 'solar-test' and r.message == 'Device recovered' for r in caplog.records)
        finally:
            await client.close()
