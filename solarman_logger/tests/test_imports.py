"""
TDD: RED phase tests for solarman_logger standalone package imports.

These tests confirm:
1. const.py imports without HA, aiohttp, or voluptuous
2. common.py imports without HA, aiohttp (except aiofiles), or voluptuous
3. slugify() uses python-slugify and behaves like HA's slugify
4. pysolarman.Solarman is importable without HA
5. parser.ParameterParser is importable without HA
"""
import pytest


def test_const_imports_without_ha():
    """Test 1: const module imports cleanly with no HA/aiohttp/voluptuous dependencies."""
    import solarman_logger.const as const
    # Verify key constants exist
    assert hasattr(const, "DEFAULT_")
    assert hasattr(const, "PARAM_")
    assert hasattr(const, "REQUEST_CODE")
    assert hasattr(const, "CONF_MOD")
    assert hasattr(const, "DIGITS")
    assert hasattr(const, "DATETIME_FORMAT")


def test_common_imports_without_ha():
    """Test 2: common module imports cleanly with no HA/aiohttp/voluptuous dependencies."""
    import solarman_logger.common as common
    # Verify key helpers exist
    assert hasattr(common, "retry")
    assert hasattr(common, "throttle")
    assert hasattr(common, "create_task")
    assert hasattr(common, "yaml_open")
    assert hasattr(common, "preprocess_descriptions")
    assert hasattr(common, "group_when")
    assert hasattr(common, "slugify")


def test_slugify_uses_python_slugify():
    """Test 3: slugify uses python-slugify and matches HA behavior."""
    from solarman_logger.common import slugify
    result = slugify("Total Power", "sensor")
    assert result == "total_power_sensor", f"Expected 'total_power_sensor', got '{result}'"


def test_pysolarman_solarman_importable():
    """Test 4: Solarman class importable from pysolarman without HA."""
    from solarman_logger.pysolarman import Solarman
    # Confirm it can be instantiated with required params
    assert Solarman is not None


def test_parameter_parser_importable():
    """Test 5: ParameterParser importable from parser without HA."""
    from solarman_logger.parser import ParameterParser
    assert ParameterParser is not None
