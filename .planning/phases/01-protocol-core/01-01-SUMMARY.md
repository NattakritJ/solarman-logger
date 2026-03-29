---
phase: 01-protocol-core
plan: "01"
subsystem: protocol-extraction
tags: [extraction, protocol, pysolarman, parser, standalone, no-ha]
dependency_graph:
  requires: []
  provides:
    - solarman_logger.const (pure-Python constants)
    - solarman_logger.common (pure-Python helpers + slugify)
    - solarman_logger.pysolarman.Solarman (async TCP client)
    - solarman_logger.parser.ParameterParser (register parser)
    - solarman_logger.pysolarman.umodbus (vendored Modbus library)
  affects:
    - All subsequent plans that build on the protocol layer
tech_stack:
  added:
    - python-slugify (replaces homeassistant.util.slugify)
    - aiofiles (retained from HA version for async YAML loading)
    - pyyaml (YAML parsing in yaml_open)
    - pytest (test framework, installed in .venv)
  patterns:
    - TDD RED/GREEN cycle for import verification
    - Copy-and-strip extraction from HA component
    - Verbatim copy of vendored library (umodbus) with zero changes
key_files:
  created:
    - solarman_logger/__init__.py
    - solarman_logger/const.py
    - solarman_logger/common.py
    - solarman_logger/parser.py
    - solarman_logger/pysolarman/__init__.py
    - solarman_logger/pysolarman/umodbus/ (full directory, 18 files)
    - solarman_logger/tests/__init__.py
    - solarman_logger/tests/test_imports.py
  modified: []
decisions:
  - "Copied pysolarman/__init__.py verbatim — the from ..common import line was already correct (resolves to solarman_logger.common in new location)"
  - "Kept entity_key() in common.py even though it calls slugify — preprocess_descriptions() uses it and parser.py needs it"
  - "Did NOT copy ast import to const.py — ast was only used in process_profile() which was stripped"
  - "CONF_ADDITIONAL_OPTIONS and CONF_BATTERY_* kept in const.py for DEFAULT_ completeness even though not strictly needed in Phase 1"
metrics:
  duration: "362 seconds (~6 minutes)"
  completed: "2026-03-29"
  tasks_completed: 2
  files_created: 8
  files_modified: 1
  tests_added: 5
  tests_passing: 5
requirements_delivered:
  - POLL-02
  - POLL-03
  - POLL-05
---

# Phase 01 Plan 01: Protocol Extraction Summary

**One-liner:** Extracted pysolarman async TCP client + ParameterParser + umodbus as a pure-Python `solarman_logger/` package by copying and stripping HA-specific imports, replacing `homeassistant.util.slugify` with python-slugify.

---

## What Was Built

The `solarman_logger/` Python package — the protocol and parsing foundation for the standalone logger. All files were copied from `custom_components/solarman/` and stripped of Home Assistant, aiohttp, and voluptuous dependencies. The result is a pure-Python package that imports cleanly in any Python 3.12 environment without HA installed.

### Package Structure

```
solarman_logger/
├── __init__.py                    # Package marker
├── const.py                       # Pure-Python constants (stripped)
├── common.py                      # Helpers + slugify (python-slugify backed)
├── parser.py                      # ParameterParser (verbatim from HA)
├── pysolarman/
│   ├── __init__.py                # Solarman async TCP client (verbatim)
│   └── umodbus/                   # Vendored Modbus library (18 files, no changes)
└── tests/
    ├── __init__.py
    └── test_imports.py            # 5 TDD import tests
```

---

## Tasks Executed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | Create package scaffold and copy umodbus | `c7dfc67` | ✅ Complete |
| TDD RED | Add failing import tests | `7d3d2b9` | ✅ Complete |
| 2 | Extract const.py, common.py, pysolarman, parser.py | `aa52671` | ✅ Complete |

---

## Verification Results

```
✅ PASS: No HA imports  (grep -r "homeassistant" solarman_logger/ returns nothing)
✅ All imports OK       (Solarman, FrameError, ParameterParser, slugify, retry, throttle, etc.)
✅ slugify OK           (slugify("Total Power", "sensor") == "total_power_sensor")
✅ 5/5 tests PASS       (pytest solarman_logger/tests/test_imports.py -v)
```

---

## Deviations from Plan

None — plan executed exactly as written.

The plan note that "pysolarman/__init__.py change is one line only" was accurate: the import `from ..common import retry, throttle, create_task, format` was already using a relative path that resolves correctly to `solarman_logger.common` in the new location. No line change was actually needed.

---

## Decisions Made

1. **Kept `entity_key()` in common.py** — it's called by `preprocess_descriptions()` which is needed by `parser.py`. Stripping it would break the parser.

2. **`ast` import not included in const.py** — `ast.literal_eval` was only used in `process_profile()` (which was stripped). No need to bring it along.

3. **pysolarman/__init__.py copied verbatim** — the relative import `from ..common import ...` already resolves to `solarman_logger.common` in the new package hierarchy. Zero changes needed.

4. **`CONF_BATTERY_*` and `CONF_ADDITIONAL_OPTIONS` kept in const.py** — these appear in `DEFAULT_` dict which `ParameterParser.__init__` uses. Removing them would break the default configuration dictionary.

---

## Known Stubs

None — all code wired to real implementations. No placeholder values that would prevent functionality.

---

## Self-Check: PASSED

```
FOUND: solarman_logger/__init__.py
FOUND: solarman_logger/const.py
FOUND: solarman_logger/common.py
FOUND: solarman_logger/parser.py
FOUND: solarman_logger/pysolarman/__init__.py
FOUND: solarman_logger/pysolarman/umodbus/functions.py
FOUND: solarman_logger/tests/test_imports.py
FOUND: c7dfc67 (git log)
FOUND: 7d3d2b9 (git log)
FOUND: aa52671 (git log)
```
