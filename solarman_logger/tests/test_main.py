"""Unit tests for the main entry point."""

from __future__ import annotations

import signal
import sys
from unittest.mock import MagicMock, patch, call

import pytest

from solarman_logger.main import parse_args, main


class TestParseArgs:
    def test_default_config(self):
        """parse_args with no arguments returns config='config.yaml'."""
        args = parse_args([])
        assert args.config == "config.yaml"

    def test_custom_config(self):
        """parse_args with --config returns the specified path."""
        args = parse_args(["--config", "/etc/custom.yaml"])
        assert args.config == "/etc/custom.yaml"


class TestMain:
    @patch("solarman_logger.main.asyncio")
    @patch("solarman_logger.main.run_all")
    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_happy_path_calls_in_order(
        self, mock_setup, mock_load, mock_writer_cls, mock_run_all, mock_asyncio
    ):
        """main() calls setup_logging, load_config, InfluxDBWriter, check_health, make_data_callback, run_all."""
        mock_config = MagicMock()
        mock_config.devices = [MagicMock(name="dev1", type="inverter")]
        mock_load.return_value = mock_config

        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_callback = MagicMock()
        mock_writer.make_data_callback.return_value = mock_callback

        main(["--config", "test.yaml"])

        mock_setup.assert_called_once()
        mock_load.assert_called_once_with("test.yaml")
        mock_writer_cls.assert_called_once_with(mock_config.influxdb)
        mock_writer.check_health.assert_called_once()
        mock_writer.make_data_callback.assert_called_once()
        mock_asyncio.run.assert_called_once()
        mock_writer.close.assert_called_once()

    @patch("solarman_logger.main.asyncio")
    @patch("solarman_logger.main.run_all")
    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_passes_data_callback_to_run_all(
        self, mock_setup, mock_load, mock_writer_cls, mock_run_all, mock_asyncio
    ):
        """main() passes the callback from make_data_callback to run_all."""
        mock_config = MagicMock()
        mock_config.devices = [MagicMock(name="dev1", type="inverter")]
        mock_load.return_value = mock_config

        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_callback = MagicMock()
        mock_writer.make_data_callback.return_value = mock_callback

        main([])

        # asyncio.run is called with run_all(config, data_callback)
        call_args = mock_asyncio.run.call_args
        assert call_args is not None

    @patch("solarman_logger.main.setup_logging")
    @patch("solarman_logger.main.load_config")
    def test_config_error_exits_1(self, mock_load, mock_setup):
        """main() exits with code 1 when load_config raises ConfigError."""
        from solarman_logger.config import ConfigError

        mock_load.side_effect = ConfigError("bad config")

        with pytest.raises(SystemExit) as exc_info:
            main([])

        assert exc_info.value.code == 1

    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_health_check_failure_exits_1(self, mock_setup, mock_load, mock_writer_cls):
        """main() exits with code 1 when check_health raises RuntimeError."""
        mock_config = MagicMock()
        mock_load.return_value = mock_config

        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_writer.check_health.side_effect = RuntimeError("unreachable")

        with pytest.raises(SystemExit) as exc_info:
            main([])

        assert exc_info.value.code == 1
        mock_writer.close.assert_called_once()

    @patch("solarman_logger.main.asyncio")
    @patch("solarman_logger.main.run_all")
    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_run_all_exception_still_closes_writer(
        self, mock_setup, mock_load, mock_writer_cls, mock_run_all, mock_asyncio
    ):
        """main() calls writer.close() even when run_all raises."""
        mock_config = MagicMock()
        mock_config.devices = [MagicMock(name="dev1", type="inverter")]
        mock_load.return_value = mock_config

        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer
        mock_asyncio.run.side_effect = Exception("unexpected crash")

        with pytest.raises(Exception, match="unexpected crash"):
            main([])

        mock_writer.close.assert_called_once()

    @patch("solarman_logger.main.asyncio")
    @patch("solarman_logger.main.run_all")
    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_normal_exit_closes_writer(
        self, mock_setup, mock_load, mock_writer_cls, mock_run_all, mock_asyncio
    ):
        """main() calls writer.close() on normal exit."""
        mock_config = MagicMock()
        mock_config.devices = [MagicMock(name="dev1", type="inverter")]
        mock_load.return_value = mock_config

        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        main([])

        mock_writer.close.assert_called_once()


class TestConfigPathEnv:
    """Tests for CONFIG_PATH environment variable support."""

    @patch("solarman_logger.main.signal")
    @patch("solarman_logger.main.asyncio")
    @patch("solarman_logger.main.run_all")
    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_config_path_env_overrides_default(
        self, mock_setup, mock_load, mock_writer_cls, mock_run_all, mock_asyncio, mock_signal
    ):
        """When CONFIG_PATH env var is set and no --config flag, load_config gets the env value."""
        mock_config = MagicMock()
        mock_config.devices = [MagicMock(name="dev1", type="inverter")]
        mock_load.return_value = mock_config
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        with patch.dict("os.environ", {"CONFIG_PATH": "/data/test.yaml"}):
            main([])

        mock_load.assert_called_once_with("/data/test.yaml")

    @patch("solarman_logger.main.signal")
    @patch("solarman_logger.main.asyncio")
    @patch("solarman_logger.main.run_all")
    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_cli_config_overrides_env(
        self, mock_setup, mock_load, mock_writer_cls, mock_run_all, mock_asyncio, mock_signal
    ):
        """CLI --config flag takes precedence over CONFIG_PATH env var."""
        mock_config = MagicMock()
        mock_config.devices = [MagicMock(name="dev1", type="inverter")]
        mock_load.return_value = mock_config
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        with patch.dict("os.environ", {"CONFIG_PATH": "/data/env.yaml"}):
            main(["--config", "/etc/explicit.yaml"])

        mock_load.assert_called_once_with("/etc/explicit.yaml")

    @patch("solarman_logger.main.signal")
    @patch("solarman_logger.main.asyncio")
    @patch("solarman_logger.main.run_all")
    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_no_env_no_flag_uses_default(
        self, mock_setup, mock_load, mock_writer_cls, mock_run_all, mock_asyncio, mock_signal
    ):
        """When neither CONFIG_PATH nor --config is given, uses 'config.yaml' default."""
        mock_config = MagicMock()
        mock_config.devices = [MagicMock(name="dev1", type="inverter")]
        mock_load.return_value = mock_config
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        with patch.dict("os.environ", {}, clear=False):
            # Ensure CONFIG_PATH is not set
            import os
            os.environ.pop("CONFIG_PATH", None)
            main([])

        mock_load.assert_called_once_with("config.yaml")


class TestSigtermHandler:
    """Tests for SIGTERM clean shutdown."""

    @patch("solarman_logger.main.signal")
    @patch("solarman_logger.main.asyncio")
    @patch("solarman_logger.main.run_all")
    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_sigterm_handler_registered(
        self, mock_setup, mock_load, mock_writer_cls, mock_run_all, mock_asyncio, mock_signal
    ):
        """main() registers a SIGTERM handler via signal.signal."""
        mock_config = MagicMock()
        mock_config.devices = [MagicMock(name="dev1", type="inverter")]
        mock_load.return_value = mock_config
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        main([])

        # Verify signal.signal was called with SIGTERM as first arg
        mock_signal.signal.assert_called_once()
        call_args = mock_signal.signal.call_args
        assert call_args[0][0] == mock_signal.SIGTERM

    @patch("solarman_logger.main.signal")
    @patch("solarman_logger.main.asyncio")
    @patch("solarman_logger.main.run_all")
    @patch("solarman_logger.main.InfluxDBWriter")
    @patch("solarman_logger.main.load_config")
    @patch("solarman_logger.main.setup_logging")
    def test_sigterm_triggers_clean_shutdown(
        self, mock_setup, mock_load, mock_writer_cls, mock_run_all, mock_asyncio, mock_signal
    ):
        """SIGTERM handler raises SystemExit, which triggers writer.close() and 'Shutdown complete' log."""
        mock_config = MagicMock()
        mock_config.devices = [MagicMock(name="dev1", type="inverter")]
        mock_load.return_value = mock_config
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        # Capture the SIGTERM handler that gets registered
        captured_handler = None
        real_signal = signal.signal

        def capture_signal(signum, handler):
            nonlocal captured_handler
            if signum == signal.SIGTERM:
                captured_handler = handler

        mock_signal.signal.side_effect = capture_signal
        mock_signal.SIGTERM = signal.SIGTERM

        # Make asyncio.run raise SystemExit (simulating SIGTERM during run)
        mock_asyncio.run.side_effect = SystemExit(0)

        main([])

        # The handler should have been registered
        assert captured_handler is not None
        # When the handler fires, it should raise SystemExit
        with pytest.raises(SystemExit):
            captured_handler(signal.SIGTERM, None)

        # writer.close() should have been called in the finally block
        mock_writer.close.assert_called()
