"""
Unit tests for solarman_logger.logging_setup.

Tests:
- Test 1: After setup_logging("INFO"), a log message includes timestamp, level, and message text
- Test 2: get_device_logger("Deye Micro") returns a Logger; messages include "Deye Micro" in output
- Test 3: WARNING-level "unreachable" message is distinct from WARNING-level "invalid data" message (grep test)
"""
import io
import re
import logging
import pytest

from solarman_logger.logging_setup import setup_logging, get_device_logger


class TestLogFormat:
    """Test 1: log format includes timestamp, level, and message."""

    def test_log_contains_timestamp(self, capfd):
        """Log output must include ISO date-format timestamp (YYYY-MM-DD HH:MM:SS)."""
        setup_logging("DEBUG")
        logger = get_device_logger("TestDevice")
        logger.warning("Test timestamp message")
        captured = capfd.readouterr()
        # Check stdout (setup_logging writes to stdout)
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", captured.out), (
            f"Timestamp not found in log output: {captured.out!r}"
        )

    def test_log_contains_level_name(self, capfd):
        """Log output must include the level name (e.g. WARNING, INFO, DEBUG)."""
        setup_logging("DEBUG")
        logger = get_device_logger("TestDevice")
        logger.warning("Test level message")
        captured = capfd.readouterr()
        assert "WARNING" in captured.out, (
            f"Level name not found in log output: {captured.out!r}"
        )

    def test_log_contains_message_text(self, capfd):
        """Log output must include the message text."""
        setup_logging("DEBUG")
        logger = get_device_logger("TestDevice")
        logger.warning("Unique test message text 12345")
        captured = capfd.readouterr()
        assert "Unique test message text 12345" in captured.out, (
            f"Message text not found in log output: {captured.out!r}"
        )


class TestDeviceLogger:
    """Test 2: get_device_logger() returns a Logger; messages include device name."""

    def test_get_device_logger_returns_logger(self):
        """get_device_logger() should return a logging.Logger instance."""
        logger = get_device_logger("Deye Micro")
        assert isinstance(logger, logging.Logger), (
            f"get_device_logger returned {type(logger)}, expected logging.Logger"
        )

    def test_device_name_appears_in_output(self, capfd):
        """Messages from a device logger should include the device name in the output."""
        setup_logging("DEBUG")
        logger = get_device_logger("Deye Micro")
        logger.warning("Device unreachable: timeout")
        captured = capfd.readouterr()
        assert "Deye Micro" in captured.out, (
            f"Device name 'Deye Micro' not found in log output: {captured.out!r}"
        )

    def test_device_name_in_brackets(self, capfd):
        """The device name should appear in brackets [device_name] per LOG-01 spec."""
        setup_logging("DEBUG")
        logger = get_device_logger("Deye Micro")
        logger.info("Connected successfully")
        captured = capfd.readouterr()
        assert "[Deye Micro]" in captured.out, (
            f"Device name in brackets '[Deye Micro]' not found in log output: {captured.out!r}"
        )


class TestDistinctErrorMessages:
    """Test 3: Unreachable device error is distinct from invalid data error (grep test)."""

    def test_unreachable_message_contains_distinguishing_keyword(self, capfd):
        """An unreachable device message should contain 'unreachable', 'timeout', or 'connection'."""
        setup_logging("DEBUG")
        logger = get_device_logger("Deye Micro")
        logger.warning("Device unreachable: Connection refused")
        captured = capfd.readouterr()
        line = captured.out.strip()
        has_keyword = any(kw in line.lower() for kw in ("unreachable", "timeout", "connection"))
        assert has_keyword, (
            f"Unreachable message lacks distinguishing keyword: {line!r}"
        )

    def test_invalid_data_message_contains_distinguishing_keyword(self, capfd):
        """An invalid data message should contain 'invalid' or 'validation'."""
        setup_logging("DEBUG")
        logger = get_device_logger("Deye Micro")
        logger.warning("Invalid data received: register out of range")
        captured = capfd.readouterr()
        line = captured.out.strip()
        has_keyword = any(kw in line.lower() for kw in ("invalid", "validation"))
        assert has_keyword, (
            f"Invalid data message lacks distinguishing keyword: {line!r}"
        )

    def test_unreachable_and_invalid_messages_are_distinct(self, capfd):
        """The two message types must be distinguishable by keyword grep."""
        setup_logging("DEBUG")
        logger = get_device_logger("Deye Micro")
        logger.warning("Device unreachable: timeout")
        captured_unreachable = capfd.readouterr()
        logger.warning("Invalid data received: CRC mismatch")
        captured_invalid = capfd.readouterr()

        unreachable_line = captured_unreachable.out.lower()
        invalid_line = captured_invalid.out.lower()

        # The "unreachable" keyword should be in unreachable but not in invalid
        assert "unreachable" in unreachable_line, "Missing 'unreachable' in unreachable message"
        assert "unreachable" not in invalid_line, "'unreachable' should not appear in invalid data message"

        # The "invalid" keyword should be in invalid but not in unreachable
        assert "invalid" in invalid_line, "Missing 'invalid' in invalid data message"
        assert "invalid" not in unreachable_line, "'invalid' should not appear in unreachable message"
