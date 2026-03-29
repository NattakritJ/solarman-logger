---
phase: 01-protocol-core
plan: "02"
subsystem: config-loader
tags: [config, yaml, validation, dataclass, tdd, startup]
dependency_graph:
  requires:
    - solarman_logger (package scaffold from 01-01)
  provides:
    - solarman_logger.config.load_config (startup config loader)
    - solarman_logger.config.Config (typed config dataclass)
    - solarman_logger.config.DeviceConfig (per-device config dataclass)
    - solarman_logger.config.InfluxConfig (InfluxDB connection config dataclass)
    - solarman_logger.config.ConfigError (startup validation exception)
  affects:
    - Phase 2 polling loop (consumes DeviceConfig for each device)
    - Phase 3 InfluxDB pipeline (consumes InfluxConfig)
tech_stack:
  added:
    - pyyaml (yaml.safe_load for config parsing — already in .venv from 01-01)
  patterns:
    - TDD RED/GREEN cycle (fail-first, then implement)
    - Dataclass-based typed config objects
    - Fail-fast startup validation (ConfigError on first missing field)
    - Profile path resolved relative to config file directory
key_files:
  created:
    - solarman_logger/config.py
    - solarman_logger/tests/test_config.py
    - solarman_logger/tests/fixtures/valid_config.yaml
    - solarman_logger/tests/fixtures/missing_token_config.yaml
  modified: []
decisions:
  - "Used yaml.safe_load (sync) for config loading — config is read once at startup, sync is simpler and sufficient"
  - "ConfigError message format 'Missing required config: {field_path}' (e.g. 'influxdb.token') — names the field for fast debuggability"
  - "profile_dir = str(abs_path.parent) + '/' — trailing slash matches how ParameterParser.init(path, filename) expects its arguments"
  - "No HA dependencies introduced — pure stdlib + pyyaml only"
metrics:
  duration: "153 seconds (~2.5 minutes)"
  completed: "2026-03-29"
  tasks_completed: 2
  files_created: 4
  files_modified: 0
  tests_added: 7
  tests_passing: 7
requirements_delivered:
  - CONF-01
  - CONF-02
  - CONF-03
  - CONF-04
---

# Phase 01 Plan 02: Config Loader Summary

**One-liner:** YAML config loader with fail-fast startup validation — `load_config()` returns typed `Config`/`DeviceConfig`/`InfluxConfig` dataclasses, raising `ConfigError` (naming the missing field) on any invalid input.

---

## What Was Built

`solarman_logger/config.py` — the single startup entry point for all configuration. It:

1. Reads a YAML file from disk (sync, once at startup)
2. Validates every required field in order, raising `ConfigError` with the exact field path on the first missing value
3. Resolves device profile paths relative to the config file's directory (matching `ParameterParser.init(path, filename)` expectations)
4. Returns a fully-typed `Config` dataclass with `InfluxConfig` and a list of `DeviceConfig` objects

### Package Structure (additions)

```
solarman_logger/
├── config.py                           # NEW — load_config(), Config, DeviceConfig, InfluxConfig, ConfigError
└── tests/
    ├── test_config.py                  # NEW — 7 TDD tests
    └── fixtures/
        ├── valid_config.yaml           # NEW — 2-device config (one with overrides, one without)
        └── missing_token_config.yaml   # NEW — valid except influxdb.token absent
```

### Interface Contract

```python
from solarman_logger.config import load_config, Config, DeviceConfig, InfluxConfig, ConfigError

# Raises ConfigError if any required field is missing
cfg = load_config("/config/config.yaml")

cfg.influxdb.url       # "http://localhost:8086"
cfg.influxdb.token     # "my-secret-token"
cfg.poll_interval      # 60 (global default)

d = cfg.devices[0]
d.name                 # "Deye Micro"
d.poll_interval        # 30 (per-device override, or global default)
d.slave                # 1 (default) or explicit value
d.profile_dir          # "/config/"  (absolute dir + trailing slash)
d.profile_filename     # "deye_micro.yaml"
```

---

## Tasks Executed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | Write config loader tests (RED phase) | `8a953ec` | ✅ Complete |
| 2 | Implement config.py until all tests pass (GREEN phase) | `bd136ef` | ✅ Complete |

---

## Verification Results

```
✅ All 7 tests PASS  (pytest solarman_logger/tests/test_config.py -v)
✅ All 12 tests PASS (full suite including 5 from 01-01)
✅ ConfigError OK: Config file not found: nonexistent.yaml
✅ Profile resolution OK: profile_dir ends with /, profile_filename is bare name
✅ No HA imports     (grep -r "homeassistant" solarman_logger/config.py returns nothing)
```

---

## Deviations from Plan

None — plan executed exactly as written.

The `tests/__init__.py` was already created in Plan 01-01, so it didn't need to be recreated (not a deviation — just a no-op).

---

## Decisions Made

1. **Used `yaml.safe_load` (sync) for config** — config is loaded once at startup before the async polling loop starts. Sync is simpler and perfectly appropriate here.

2. **ConfigError message format: `"Missing required config: {field_path}"`** — consistent, machine-readable format that names the exact field path (e.g. `"influxdb.token"`, `"devices[0].serial"`). Fast to debug in logs.

3. **`profile_dir = str(abs_path.parent) + "/"`** — the trailing slash matches the calling convention that `ParameterParser.init(path, filename)` expects. This was explicit in the plan interface contract and verified in tests.

4. **Validation order:** influxdb fields first, then `defaults.poll_interval`, then `devices` section — fail at the earliest missing field for fastest feedback.

---

## Known Stubs

None — all fields are validated and wired to real data. No placeholder values.

---

## Self-Check: PASSED

```
FOUND: solarman_logger/config.py
FOUND: solarman_logger/tests/test_config.py
FOUND: solarman_logger/tests/fixtures/valid_config.yaml
FOUND: solarman_logger/tests/fixtures/missing_token_config.yaml
FOUND: 8a953ec (git log — RED commit)
FOUND: bd136ef (git log — GREEN commit)
```
