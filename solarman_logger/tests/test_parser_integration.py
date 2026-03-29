"""
Integration tests for ParameterParser against real YAML device profiles.

Tests:
- Test 1: ParameterParser.init() loads deye_micro.yaml without error
- Test 2: schedule_requests(runtime=0) returns a non-empty list
- Test 3: process(synthetic_data) returns a dict with string keys and tuple values
- Test 4: get_entity_descriptions() returns non-empty list (no HA entity types required)
"""
import os
import asyncio
import pytest

from solarman_logger.parser import ParameterParser
from solarman_logger.const import CONF_MOD, CONF_MPPT, CONF_PHASE, CONF_PACK

# Absolute path to inverter definitions directory (trailing slash required)
# Path: solarman_logger/tests/ -> ../../ -> repo root -> config/inverter_definitions/
PROFILE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../config/inverter_definitions/")
) + "/"

# Default parameters per D-07
PARAMETERS = {CONF_MOD: 0, CONF_MPPT: 4, CONF_PHASE: 3, CONF_PACK: -1}


@pytest.fixture
def parser():
    """Return a new (uninitialised) ParameterParser."""
    return ParameterParser()


def test_init_loads_deye_micro_without_error(parser):
    """Test 1: ParameterParser.init() with deye_micro.yaml completes without error."""
    async def run():
        result = await parser.init(PROFILE_DIR, "deye_micro.yaml", PARAMETERS)
        return result

    result = asyncio.run(run())
    assert result is not None
    assert isinstance(result, ParameterParser)


def test_schedule_requests_returns_nonempty_list(parser):
    """Test 2: schedule_requests(0) returns a non-empty list of request dicts."""
    async def run():
        await parser.init(PROFILE_DIR, "deye_micro.yaml", PARAMETERS)
        return parser.schedule_requests(0)

    requests = asyncio.run(run())
    assert isinstance(requests, list)
    assert len(requests) > 0
    # Each request dict should have code, start, end
    for r in requests:
        assert "code" in r
        assert "start" in r
        assert "end" in r


def test_process_returns_dict_with_tuple_values(parser):
    """Test 3: process(synthetic_data) returns dict[str, tuple[state, value]]."""
    async def run():
        await parser.init(PROFILE_DIR, "deye_micro.yaml", PARAMETERS)
        requests = parser.schedule_requests(0)
        # Build synthetic data: one register block covering the first request
        first_req = requests[0]
        synthetic_data = {
            (first_req["code"], first_req["start"]): [0] * first_req["count"]
        }
        return parser.process(synthetic_data)

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert len(result) > 0
    for key, value in result.items():
        assert isinstance(key, str), f"Key {key!r} should be a string"
        assert isinstance(value, tuple), f"Value for {key!r} should be a tuple, got {type(value)}"


def test_get_entity_descriptions_returns_nonempty_list(parser):
    """Test 4: get_entity_descriptions() returns non-empty list without requiring HA entity types."""
    async def run():
        await parser.init(PROFILE_DIR, "deye_micro.yaml", PARAMETERS)
        return parser.get_entity_descriptions()

    descriptions = asyncio.run(run())
    assert isinstance(descriptions, list)
    assert len(descriptions) > 0
    # Each description should at least have a 'name' and 'key'
    for desc in descriptions[:5]:  # sample first 5
        assert "name" in desc, f"Missing 'name' in description: {desc}"
        assert "key" in desc, f"Missing 'key' in description: {desc}"
