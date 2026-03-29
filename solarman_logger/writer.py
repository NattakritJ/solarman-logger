"""InfluxDB v2 writer for solarman_logger.

Converts parsed device readings into InfluxDB Points and writes them.
All numeric values are cast to float to prevent InfluxDB type conflicts (per D-08).
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from .config import InfluxConfig

_LOGGER = logging.getLogger(__name__)


class InfluxDBWriter:
    """Writes parsed device data to InfluxDB v2.

    Each device gets its own measurement (device name). All numeric fields
    are cast to float. Write failures are logged and dropped, never re-raised.
    """

    def __init__(self, config: InfluxConfig) -> None:
        self._config = config
        self._client = InfluxDBClient(url=config.url, token=config.token, org=config.org)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self._bucket = config.bucket
        self._org = config.org

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

    def write_callback(self, device_name: str, device_type: str, parsed: dict[str, tuple]) -> None:
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
            self.write_callback(device_name, device_type, parsed)

        return _callback

    def close(self) -> None:
        """Flush and close the InfluxDB client (per D-11)."""
        self._write_api.close()
        self._client.close()
        _LOGGER.debug("InfluxDB writer closed")
