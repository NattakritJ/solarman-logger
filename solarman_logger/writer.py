"""InfluxDB v2 writer for solarman_logger.

Converts parsed device readings into InfluxDB Points and writes them.
All numeric values are cast to float to prevent InfluxDB type conflicts (per D-08).
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from .config import InfluxConfig

_LOGGER = logging.getLogger(__name__)
WRITE_QUEUE_SIZE = 128
SHUTDOWN_WAIT_SECONDS = 3


class InfluxDBWriter:
    """Writes parsed device data to InfluxDB v2.

    Each device gets its own measurement (device name). All numeric fields
    are cast to float. Polling enqueues snapshots for one database thread.
    Write failures are logged and dropped, never re-raised.
    """

    def __init__(self, config: InfluxConfig) -> None:
        self._config = config
        self._client = InfluxDBClient(url=config.url, token=config.token, org=config.org)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self._bucket = config.bucket
        self._org = config.org
        self._queue = queue.Queue(maxsize = WRITE_QUEUE_SIZE)
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._shutdown_deadline: float | None = None

    def check_health(self) -> None:
        """Ping InfluxDB and raise RuntimeError if unreachable (per D-04, D-05)."""
        try:
            result = self._client.ping()
            if not result:
                raise RuntimeError(f"InfluxDB health check failed: cannot reach {self._config.url}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"InfluxDB health check failed: cannot reach {self._config.url}") from e
        _LOGGER.info(f"InfluxDB health check passed: {self._config.url}")

    def write_callback(self, device_name: str, device_type: str, parsed: dict[str, tuple],
                       collected_at: datetime | None = None) -> None:
        """Convert parsed data to an InfluxDB Point and write it (per D-01 through D-10).

        All numeric values are cast to float. String values are kept as-is.
        Write failures are logged as warnings and dropped — never re-raised.
        """
        fields: dict[str, Any] = {}
        for key, (state, _value) in parsed.items():
            if isinstance(state, (int, float)):
                fields[key] = float(state)
            elif isinstance(state, str):
                fields[key] = state
            # Skip None or other types

        if not fields:
            return

        record = {
            "measurement": device_name,
            "tags": {
                "device_name": device_name,
                "device_type": device_type,
            },
            "fields": fields,
        }
        if collected_at is not None:
            record["time"] = collected_at

        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=record)
        except Exception as e:
            _LOGGER.warning(f"InfluxDB write failed for {device_name}: {e}")

    def make_data_callback(self, device_configs: dict[str, str]) -> Callable[[str, dict[str, tuple]], Awaitable[None]]:
        """Return an async callback matching the DataCallback signature.

        Args:
            device_configs: mapping of device_name -> device_type, built from Config.devices
        """
        async def _callback(device_name: str, parsed: dict[str, tuple]) -> None:
            device_type = device_configs[device_name]
            self._enqueue(device_name, device_type, parsed)

        return _callback

    def _enqueue(self, device_name: str, device_type: str, parsed: dict[str, tuple]) -> None:
        # Only this bounded buffer is shared with polling; HTTP runs in one thread.
        record = (device_name, device_type, dict(parsed), datetime.now(timezone.utc))
        with self._state_lock:
            if self._closed:
                return
            if self._thread is None:
                self._thread = threading.Thread(target = self._write_loop, name = "influxdb-writer", daemon = True)
                self._thread.start()
            try:
                self._queue.put_nowait(record)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    pass
                self._queue.put_nowait(record)
                _LOGGER.warning("InfluxDB write buffer full; dropped oldest pending reading")

    def _write_loop(self) -> None:
        try:
            while self._shutdown_deadline is None or time.monotonic() < self._shutdown_deadline:
                if self._closed and self._queue.empty():
                    break
                record = self._queue.get()
                try:
                    if record is None:
                        break
                    self.write_callback(*record)
                except Exception as e:
                    _LOGGER.warning("Database worker could not write reading: %r", e)
                finally:
                    self._queue.task_done()
        finally:
            dropped = 0
            while True:
                try:
                    if self._queue.get_nowait() is not None:
                        dropped += 1
                    self._queue.task_done()
                except queue.Empty:
                    break
            if dropped:
                _LOGGER.warning("Discarded %s pending database readings during shutdown", dropped)
            self._close_client()

    def close(self) -> None:
        """Drain within the service stop grace period; never close an in-flight client."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._shutdown_deadline = time.monotonic() + SHUTDOWN_WAIT_SECONDS
            thread = self._thread
            if thread is not None:
                try:
                    self._queue.put_nowait(None)
                except queue.Full:
                    pass
        if thread is None:
            self._close_client()
        else:
            thread.join(timeout = SHUTDOWN_WAIT_SECONDS)
            if thread.is_alive():
                _LOGGER.warning("Database writer is still finishing an in-flight request during shutdown")

    def _close_client(self) -> None:
        if self._client is None:
            return
        try:
            self._write_api.close()
        except Exception:
            pass
        try:
            self._client.close()
        except Exception:
            pass
        self._client = None
        _LOGGER.debug("InfluxDB writer closed")
