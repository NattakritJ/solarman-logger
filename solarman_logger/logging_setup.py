from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """
    Configure root logger to output structured lines to stdout.
    Format: YYYY-MM-DD HH:MM:SS LEVEL [name] message

    Devices write to logger named after their device name.
    Use get_device_logger(name) to get a per-device logger.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt = LOG_DATE_FORMAT))
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Avoid duplicate handlers if called multiple times
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout for h in root.handlers):
        root.addHandler(handler)


def get_device_logger(device_name: str) -> logging.Logger:
    """
    Return a logger that prefixes every message with [device_name].
    Usage: logger = get_device_logger("Deye Micro")
    The %(name)s format field in LOG_FORMAT will render as [device_name].
    """
    return logging.getLogger(device_name)
