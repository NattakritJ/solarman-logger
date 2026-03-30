from __future__ import annotations

import asyncio
import logging
import time

from logging import getLogger
from typing import Awaitable, Callable

from .config import Config, DeviceConfig
from .const import CONF_MOD, CONF_MPPT, CONF_PACK, CONF_PHASE, REQUEST_CODE, REQUEST_COUNT, REQUEST_START
from .logging_setup import get_device_logger
from .parser import ParameterParser
from .pysolarman import Solarman
from .pysolarman.umodbus.exceptions import ServerDeviceBusyError

_LOGGER = getLogger(__name__)

PARSER_PARAMETERS = {
    CONF_MOD: 0,
    CONF_MPPT: 4,
    CONF_PHASE: 3,
    CONF_PACK: -1,
}
MAX_BACKOFF = 300
BACKOFF_FACTOR = 2

DataCallback = Callable[[str, dict[str, tuple]], Awaitable[None]]


class DeviceHealth:
    def __init__(self, is_solar: bool):
        self._is_solar = is_solar
        self._online: bool | None = None
        self._valid_data: bool | None = None

    def report_success(self, logger: logging.Logger) -> None:
        if self._online is None:
            logger.info("Device online")
        elif self._online is False:
            logger.info("Device recovered")

        if self._valid_data is False:
            logger.info("Valid data resumed")

        self._online = True
        self._valid_data = True

    def report_failure(self, logger: logging.Logger, error: Exception) -> None:
        if self._online is not False:
            message = f"Device offline: {error}"
            if self._is_solar:
                logger.info(f"{message} (expected overnight sleep possible)")
            else:
                logger.warning(message)
        else:
            logger.debug(f"Device still offline: {error}")

        self._online = False

    def report_invalid_data(self, logger: logging.Logger, reason: str) -> None:
        if self._valid_data is not False:
            logger.warning(f"Invalid data received: {reason}")
        else:
            logger.debug(f"Invalid data persists: {reason}")

        self._valid_data = False


class DeviceWorker:
    def __init__(self, config: DeviceConfig, parser: ParameterParser, client: Solarman, is_solar: bool):
        self.config = config
        self.parser = parser
        self.client = client
        self.logger = get_device_logger(config.name)
        self.health = DeviceHealth(is_solar)

        self._poll_interval = config.poll_interval
        self._cycle_count = 0
        self._consecutive_failures = 0
        self._backoff_interval = config.poll_interval
        self._polling_in_progress = False
        self._started_at = time.monotonic()

    @property
    def _current_interval(self) -> int:
        return self._backoff_interval if self._consecutive_failures > 0 else self._poll_interval

    def _get_runtime(self, now: float | None = None) -> int:
        current = time.monotonic() if now is None else now
        elapsed = max(0.0, current - self._started_at)
        return int(elapsed // self._poll_interval) * self._poll_interval

    async def run(self, data_callback: DataCallback) -> None:
        next_poll = self._started_at

        while True:
            now = time.monotonic()
            if next_poll > now:
                await asyncio.sleep(next_poll - now)

            poll_started = time.monotonic()
            await self._poll_cycle(data_callback)
            interval = self._current_interval
            scheduled_next = next_poll + interval
            poll_finished = time.monotonic()

            if poll_finished > scheduled_next:
                self.logger.debug(f"Poll overrun by {poll_finished - scheduled_next:.1f}s - scheduling from now")
                next_poll = poll_finished + interval
            else:
                next_poll = scheduled_next

    async def _poll_cycle(self, data_callback: DataCallback) -> None:
        if self._polling_in_progress:
            self.logger.debug("Poll overlap prevented - skipping this cycle")
            return

        self._polling_in_progress = True

        try:
            runtime = self._get_runtime()
            requests = self.parser.schedule_requests(runtime)

            if not requests:
                return

            responses = {}

            for request in requests:
                code = request[REQUEST_CODE]
                start = request[REQUEST_START]
                count = request[REQUEST_COUNT]
                responses[(code, start)] = await self.client.execute(code, start, count = count)

            parsed = self.parser.process(responses)
            self._handle_success()
            await data_callback(self.config.name, parsed)
        except ValueError as e:
            self.health.report_invalid_data(self.logger, str(e))
        except asyncio.CancelledError:
            raise
        except (TimeoutError, ConnectionError, OSError, ServerDeviceBusyError) as e:
            self._handle_failure(e)
        except Exception as e:
            self.logger.error(f"Unexpected error during poll: {e!r}")
            self._handle_failure(e)
        finally:
            self._cycle_count += 1
            self._polling_in_progress = False

    def _handle_success(self) -> None:
        self.health.report_success(self.logger)
        self._consecutive_failures = 0
        self._backoff_interval = self._poll_interval

    def _handle_failure(self, error: Exception) -> None:
        self.health.report_failure(self.logger, error)
        self._consecutive_failures += 1
        self._backoff_interval = min(self._poll_interval * (BACKOFF_FACTOR ** self._consecutive_failures), MAX_BACKOFF)


def _detect_solar(parser: ParameterParser) -> bool:
    descriptions = parser.get_entity_descriptions()
    if any("pv" in str(item.get("name", "")).lower() or "solar" in str(item.get("name", "")).lower() for item in descriptions):
        return True

    filename = parser.info.get("filename", "").lower()
    return any(token in filename for token in ("micro", "hybrid", "string", "inverter"))


async def create_device_worker(config: DeviceConfig) -> DeviceWorker:
    parser = await ParameterParser().init(config.profile_dir, config.profile_filename, dict(PARSER_PARAMETERS))
    client = Solarman(config.host, config.port, "tcp", config.serial, config.slave, timeout = 10)
    return DeviceWorker(config, parser, client, is_solar = _detect_solar(parser))


async def _noop_callback(name: str, data: dict[str, tuple]) -> None:
    return None


async def run_all(config: Config, data_callback: DataCallback | None = None, on_shutdown: Callable[[], None] | None = None) -> None:
    callback = data_callback or _noop_callback
    workers: list[DeviceWorker] = []

    for device in config.devices:
        try:
            worker = await create_device_worker(device)
        except Exception as e:
            get_device_logger(device.name).error(f"Failed to initialize device: {e!r} - skipping")
            continue

        workers.append(worker)
        worker.logger.info(
            f"Initialized (poll_interval={device.poll_interval}s, profile={device.profile_filename}, solar={'yes' if worker.health._is_solar else 'no'})"
        )

    if not workers:
        _LOGGER.error("No devices initialized - nothing to poll")
        return

    tasks = [asyncio.create_task(worker.run(callback), name = f"poll-{worker.config.name}") for worker in workers]

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions = True)

        for worker in workers:
            try:
                await worker.client.close()
            except Exception as e:
                worker.logger.debug(f"Error closing client: {e!r}")

        if on_shutdown is not None:
            try:
                on_shutdown()
            except Exception as e:
                _LOGGER.debug(f"Error in shutdown callback: {e!r}")
