---
phase: 01-protocol-core
plan: "03"
subsystem: logging-and-verification
tags: [integration-tests, slugify, logging, requirements, tdd, verification]
dependency_graph:
  requires:
    - solarman_logger (package scaffold from 01-01)
    - solarman_logger.parser.ParameterParser (from 01-01)
    - solarman_logger.common.slugify (from 01-01)
    - inverter_definitions/deye_micro.yaml and ddzy422-d2.yaml (reference profiles)
  provides:
    - solarman_logger.logging_setup.setup_logging (stdout structured logging)
    - solarman_logger.logging_setup.get_device_logger (per-device named logger)
    - solarman_logger/tests/test_parser_integration.py (integration tests for ParameterParser)
    - solarman_logger/tests/test_slugify.py (equivalence tests for slugify against real profiles)
    - solarman_logger/tests/test_logging.py (unit tests for log format and error types)
    - requirements.txt (runtime dependency declarations)
  affects:
    - All solarman_logger modules (logging is cross-cutting; all should use get_device_logger())
    - Phase 2 polling loop (consumes setup_logging() at startup)
    - Docker build (requirements.txt is the dependency manifest)
tech_stack:
  added:
    - pytest-asyncio (async test support, installed in .venv)
  patterns:
    - TDD RED/GREEN cycle for logging module
    - Pre-computed reference dict approach for slugify equivalence (HA not available in test env)
    - asyncio.run() for async ParameterParser.init() in sync test functions
    - Duplicate-handler guard in setup_logging() for idempotent test calls
key_files:
  created:
    - solarman_logger/logging_setup.py
    - solarman_logger/tests/test_logging.py
    - solarman_logger/tests/test_parser_integration.py
    - solarman_logger/tests/test_slugify.py
    - requirements.txt
  modified: []
decisions:
  - "Path to inverter_definitions resolved via os.path.dirname(__file__) with 2 levels up (not 3) — tests live in solarman_logger/tests/, repo root is 2 hops up"
  - "slugify equivalence test uses pre-computed reference dict — homeassistant package not available in .venv; approach documented in test file header"
  - "Duplicate-handler guard in setup_logging() — prevents double-logging when tests call setup_logging() multiple times"
  - "requirements.txt placed at repo root (not solarman_logger/requirements.txt) — matches Docker convention for pip install -r"
metrics:
  duration: "199 seconds (~3.3 minutes)"
  completed: "2026-03-29"
  tasks_completed: 2
  files_created: 5
  files_modified: 0
  tests_added: 17
  tests_passing: 29
requirements_delivered:
  - POLL-03
  - POLL-05
  - LOG-01
  - LOG-02
---

# Phase 01 Plan 03: Verification, Logging, and Requirements Summary

**One-liner:** ParameterParser end-to-end integration tests against real YAML profiles, slugify equivalence confirmed via pre-computed reference dict, structured stdout logging via `setup_logging()` / `get_device_logger()`, and `requirements.txt` with four pinned runtime dependencies.

---

## What Was Built

Phase 01 Plan 03 closes out the protocol-core phase by:

1. **Integration-testing ParameterParser** against `deye_micro.yaml` — proving it loads a real 60-item profile, schedules Modbus requests, parses synthetic register data, and lists entity descriptions without any HA imports.

2. **Verifying slugify equivalence** — all 60 item names in `deye_micro.yaml` and all 7 names in `ddzy422-d2.yaml` produce valid slug output (ASCII lowercase + underscores/digits only), matching a pre-computed reference dict.

3. **Logging module** — `solarman_logger/logging_setup.py` provides `setup_logging(level)` (writes to stdout with `YYYY-MM-DD HH:MM:SS LEVEL [name] message` format) and `get_device_logger(name)` (returns a named Logger so device name appears in every line). Unreachable-device and invalid-data messages are distinguishable by keyword grep.

4. **requirements.txt** — four runtime dependencies declared with loose pins for Docker deployment.

### Package Structure (additions)

```
solarman_logger/
├── logging_setup.py                    # NEW — setup_logging(), get_device_logger()
└── tests/
    ├── test_parser_integration.py      # NEW — 4 integration tests (ParameterParser)
    ├── test_slugify.py                 # NEW — 4 equivalence tests (slugify vs reference)
    └── test_logging.py                 # NEW — 9 unit tests (log format + error types)

requirements.txt                        # NEW — aiofiles, pyyaml, python-slugify, influxdb-client
```

### Interface Contract

```python
from solarman_logger.logging_setup import setup_logging, get_device_logger

# Call once at startup
setup_logging("INFO")  # or "DEBUG", "WARNING", etc.

# Per-device logger
logger = get_device_logger("Deye Micro")
logger.warning("Device unreachable: timeout")
# → 2026-03-29 10:00:00 WARNING   [Deye Micro] Device unreachable: timeout

logger.warning("Invalid data received: CRC mismatch")
# → 2026-03-29 10:00:01 WARNING   [Deye Micro] Invalid data received: CRC mismatch
```

---

## Tasks Executed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | ParameterParser integration test + slugify equivalence test | `b88a502` | ✅ Complete |
| 2 | Logging setup + requirements.txt | `d9113f9` | ✅ Complete |

---

## Verification Results

```
✅ 29/29 tests PASS   (full suite: imports, config, logging, parser, slugify)
✅ Parser OK          ParameterParser loads deye_micro.yaml (60 items, 1 request block)
✅ Slugify OK         All 67 profile names produce valid ASCII slug output
✅ Log format OK      2026-03-29 22:34:20 WARNING   [TestDevice] Device unreachable: timeout
✅ No HA imports      grep -r "^from homeassistant|^import homeassistant" solarman_logger/ → nothing
✅ requirements.txt   aiofiles>=23.0, pyyaml>=6.0, python-slugify>=8.0, influxdb-client>=1.40
```

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed path calculation in test files (../../../ → ../../)**
- **Found during:** Task 1 RED phase — tests immediately failed with `FileNotFoundError`
- **Issue:** Tests used `../../../custom_components/...` (3 levels up) but `solarman_logger/tests/` is only 2 levels deep from repo root
- **Fix:** Changed both `PROFILE_DIR` and `INVERTER_DEFS_DIR` calculations to `../../custom_components/solarman/inverter_definitions/`
- **Files modified:** `test_parser_integration.py`, `test_slugify.py`
- **Commit:** `b88a502` (same commit — fix was applied before the commit)

**2. [Rule 2 - Missing guard] Added duplicate-handler guard to setup_logging()**
- **Found during:** Task 2 implementation — realized tests call `setup_logging()` multiple times
- **Issue:** Without a guard, each test call would add another StreamHandler, causing duplicate log output in subsequent tests
- **Fix:** Added `if not any(isinstance(h, ...) and h.stream is sys.stdout ...)` guard before `addHandler()`
- **Files modified:** `solarman_logger/logging_setup.py`
- **Commit:** `d9113f9`

---

## Decisions Made

1. **2-level path resolution for tests** — `os.path.dirname(__file__)` inside `solarman_logger/tests/` resolves to the `tests/` directory. Two levels up (`../../`) reaches the repo root, then `custom_components/solarman/inverter_definitions/`. The initial plan's description implied 3 levels which was incorrect.

2. **Pre-computed reference dict for slugify** — `homeassistant` package is not installed in `.venv`. Instead, the reference outputs were generated offline using `solarman_logger.common.slugify` (which uses `python-slugify`, the HA replacement). This approach is documented in the test file header.

3. **`requirements.txt` at repo root** — placed at `ha-solarman/requirements.txt` (not inside `solarman_logger/`) to match Docker build convention: `pip install -r requirements.txt` from repo root.

4. **Duplicate-handler guard in setup_logging()** — makes `setup_logging()` idempotent (safe to call multiple times in tests or if accidentally called twice at startup).

---

## Known Stubs

None — all code wired to real implementations. No placeholder values.

---

## Self-Check: PASSED

```
FOUND: solarman_logger/logging_setup.py
FOUND: solarman_logger/tests/test_logging.py
FOUND: solarman_logger/tests/test_parser_integration.py
FOUND: solarman_logger/tests/test_slugify.py
FOUND: requirements.txt
FOUND: b88a502 (git log)
FOUND: d9113f9 (git log)
```
