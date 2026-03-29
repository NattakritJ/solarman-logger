# Testing Patterns

**Analysis Date:** 2026-03-29

## Test Framework

**Runner:**
- **None detected.** No test runner configuration files are present in the repository.
- No `pytest.ini`, `setup.cfg`, `tox.ini`, `pyproject.toml`, or `vitest.config.*` found.
- No `requirements-test.txt` or test dependencies declared.

**Assertion Library:**
- Not applicable — no test suite exists.

**Run Commands:**
```bash
# No test commands defined in the project
# CI only runs structural/integration validation via external HA tooling (see CI/CD section)
```

## Test File Organization

**Location:**
- No test files exist anywhere in the repository.
- `glob("**/test_*.py")` and `glob("**/*.test.*")` both returned no results.

**Directory:**
- No `tests/` directory exists.

## Types of Tests

**Unit Tests:** None

**Integration Tests:** None

**End-to-End Tests:** None

**Structural/Validation Tests (CI only):**
The project relies exclusively on external Home Assistant validation tooling run in CI:

1. **`hassfest`** — validates the integration against HA integration standards
   - Checks `manifest.json` schema, platform files, translations, services definitions
   - Run via `home-assistant/actions/hassfest@master` GitHub Action
   - Config: `.github/workflows/ha.yaml`

2. **HACS Validation** — validates HACS compatibility (installability as a custom component)
   - Run via `hacs/action@main` GitHub Action
   - Config: `.github/workflows/ha.yaml`

## CI/CD Test Integration

**Workflow:** `.github/workflows/ha.yaml`

```yaml
on:
  push:
  pull_request:
  schedule:
    - cron: 0 0 * * *  # Daily at midnight
  workflow_dispatch:
```

**Jobs:**
- `hassfest` — runs `home-assistant/actions/hassfest@master` on every push/PR
- `hacs` — runs `hacs/action@main` on every push/PR, category: integration

**Release workflow:** `.github/workflows/assets.yaml`
- Triggered on GitHub Release creation
- Packages `custom_components/solarman/` as a zip file
- Injects version number into `manifest.json` via `sed`
- Uploads zip as release asset

**Issue management:** `.github/workflows/butler.yaml`
- Auto-closes stale issues (30 days inactive → stale, 14 more days → closed)
- PRs are exempt from stale closure

**No automated test step in CI.** There is no `pytest`, `unittest`, or any other test runner invocation in any workflow.

## Coverage

**Requirements:** None enforced — no coverage tooling configured.

**Coverage Report:** Not available.

## Mocking Strategies

No mocking framework or patterns exist — there are no tests.

## How to Run Tests

No tests exist to run. To add a test suite to this project, the standard Home Assistant custom component testing approach would be:

```bash
# Suggested setup (not currently in use):
pip install pytest pytest-homeassistant-custom-component pytest-asyncio

# Run tests
pytest tests/
```

The HA testing library `pytest-homeassistant-custom-component` provides:
- `hass` fixture for a real HA instance
- `MockConfigEntry` for config entry setup
- Tools for mocking HA services and platforms

## Test Coverage Gaps

All application code is untested:

**`custom_components/solarman/parser.py`** (`ParameterParser`)
- The register parsing logic (10 rule types: unsigned, signed, ASCII, bits, version, datetime, time, raw, etc.)
- Validation logic (`do_validate`, `in_range`)
- Request scheduling (`schedule_requests`)
- No tests exist for any parsing rules

**`custom_components/solarman/common.py`**
- All utility functions: `retry`, `throttle`, `bulk_inherit`, `bulk_migrate`, `group_when`, `lookup_value`, `get_number`, `slugify`, etc.
- These are pure/near-pure functions well-suited to unit testing

**`custom_components/solarman/pysolarman/__init__.py`** (`Solarman`)
- Frame construction and validation (`_protocol_header`, `_protocol_trailer`, `_received_frame_is_valid`)
- Checksum calculation (`_calculate_checksum`)
- ADU parsing (`_parse_adu_from_sol_response`, `_parse_adu_from_tcp_response`, `_parse_adu_from_rtu_response`)
- Protocol state machine (reconnect logic, sequence numbers)

**`custom_components/solarman/coordinator.py`** (`Coordinator`)
- Data update cycle
- Counter scheduling logic

**`custom_components/solarman/config_flow.py`**
- Config flow steps (`async_step_user`, `async_step_integration_discovery`, `async_step_dhcp`)
- `validate_connection`, `remove_defaults`, `data_schema`

**`custom_components/solarman/device.py`** (`Device`, `DeviceState`)
- `DeviceState.update` state machine
- `Device.execute_bulk` retry behavior
- Error handling/reconnection paths in `Device.get`

## Tools Utility Scripts (Not Tests)

`tools/` contains standalone diagnostic scripts — **these are not tests**:

- `tools/scheduler.py` — CLI script to simulate register scheduling from a YAML profile; useful for debugging inverter definitions
  - Usage: `py scheduler.py <path_to_yaml> [span] [runtime]`
- `tools/discovery.py` — CLI script to send UDP discovery broadcasts and print device responses
  - Usage: `python discovery.py [--address IP] [--timeout N] [--wait bool]`
- `tools/discovery_reply.py` — companion to `discovery.py`

These scripts duplicate portions of integration logic (`scheduler.py` copies `bulk_inherit`, `preprocess_descriptions`, `group_when` from `common.py`) and serve as manual integration debugging aids, not automated tests.

---

*Testing analysis: 2026-03-29*
