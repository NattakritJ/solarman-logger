"""Entry point for solarman_logger.

Loads config, validates InfluxDB connectivity, and starts the polling loop
with InfluxDB writes wired in.

Usage: python -m solarman_logger.main --config /path/to/config.yaml
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import load_config, ConfigError
from .logging_setup import setup_logging
from .poller import run_all
from .writer import InfluxDBWriter

_LOGGER = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solarman device data logger for InfluxDB")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config file (default: config.yaml)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    setup_logging()
    args = parse_args(argv)

    # Load and validate config (fail-fast per CONF-04 pattern)
    try:
        config = load_config(args.config)
    except ConfigError as e:
        _LOGGER.error(f"Configuration error: {e}")
        sys.exit(1)

    _LOGGER.info(f"Loaded config: {len(config.devices)} device(s)")

    # Initialize InfluxDB writer
    writer = InfluxDBWriter(config.influxdb)

    # Startup health check (fail-fast per D-04)
    try:
        writer.check_health()
    except RuntimeError as e:
        _LOGGER.error(str(e))
        writer.close()
        sys.exit(1)

    # Build device name -> type mapping for the callback
    device_types = {dev.name: dev.type for dev in config.devices}
    data_callback = writer.make_data_callback(device_types)

    # Run polling loop with writer wired in
    try:
        asyncio.run(run_all(config, data_callback, on_shutdown=writer.close))
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down (keyboard interrupt)")
    finally:
        writer.close()
        _LOGGER.info("Shutdown complete")


if __name__ == "__main__":
    main()
