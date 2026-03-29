---
phase: 03-influxdb-pipeline
plan: 02
subsystem: entry-point
tags: [main, argparse, asyncio, lifecycle, shutdown, influxdb]

# Dependency graph
requires:
  - phase: 01-protocol-core
    provides: "Config loader (load_config, ConfigError, Config), logging_setup"
  - phase: 02-device-polling-loop
    provides: "run_all() with DataCallback, DeviceWorker polling lifecycle"
  - phase: 03-influxdb-pipeline/plan-01
    provides: "InfluxDBWriter class with check_health, make_data_callback, close"
provides:
  - "main.py entry point: config loading, InfluxDB health check, polling with writer wired in"
  - "__main__.py for python -m solarman_logger invocation"
  - "on_shutdown callback in run_all() for decoupled writer cleanup"
  - "Idempotent writer.close() safe for double-close from both poller and main"
affects: [04-docker-packaging]

# Tech tracking
tech-stack:
  added: []
  patterns: [on-shutdown-callback-decoupling, idempotent-close, fail-fast-startup-exit]

key-files:
  created:
    - solarman_logger/main.py
    - solarman_logger/__main__.py
    - solarman_logger/tests/test_main.py
  modified:
    - solarman_logger/poller.py
    - solarman_logger/writer.py
    - solarman_logger/tests/test_poller.py

key-decisions:
  - "on_shutdown callback parameter keeps poller.py decoupled from writer.py (no direct import)"
  - "writer.close() called in both poller finally block and main finally block for defense-in-depth"
  - "writer.close() made idempotent by checking self._client is None to support double-close safely"

patterns-established:
  - "on_shutdown callback: run_all accepts optional cleanup function, called in finally block"
  - "Fail-fast startup: ConfigError and RuntimeError from health check both exit(1) with clear message"
  - "Idempotent close: set self._client = None after closing, check before repeat close"

requirements-completed: [INFL-01, INFL-04, INFL-05]

# Metrics
duration: 3min
completed: 2026-03-30
---

# Phase 03 Plan 02: Entry Point & Writer Wiring Summary

**main.py entry point with config → InfluxDB health check → polling loop, writer close wired into both poller and main shutdown paths**

## Performance

- **Duration:** 3 min (185s)
- **Started:** 2026-03-29T19:43:14Z
- **Completed:** 2026-03-29T19:46:23Z
- **Tasks:** 2
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments
- Created main.py entry point that orchestrates setup_logging → load_config → InfluxDBWriter → check_health → make_data_callback → run_all
- ConfigError and InfluxDB unreachable both log clear errors and exit(1) — fail-fast startup
- Writer is closed on all shutdown paths: normal exit, exception, keyboard interrupt, and from poller's finally block
- Added on_shutdown callback to run_all() for decoupled writer cleanup (backwards-compatible)
- Made writer.close() idempotent to support double-close from both poller and main

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: Create main.py entry point** - `1d3ab6d` (test: failing tests) → `7dc73bf` (feat: implementation)
2. **Task 2: Wire writer.close() into poller shutdown** - `3cac90a` (feat: on_shutdown callback + idempotent close + test fix)

## Files Created/Modified
- `solarman_logger/main.py` - Entry point: argparse, config loading, InfluxDB health check, polling loop, shutdown
- `solarman_logger/__main__.py` - One-liner enabling `python -m solarman_logger`
- `solarman_logger/tests/test_main.py` - 8 unit tests: parse_args, happy path, ConfigError exit, health check exit, finally close
- `solarman_logger/poller.py` - Added on_shutdown callback parameter to run_all(), called in finally block
- `solarman_logger/writer.py` - Made close() idempotent with self._client None check
- `solarman_logger/tests/test_poller.py` - Fixed missing type field in _device_config() helper

## Decisions Made
- on_shutdown callback parameter keeps poller.py decoupled from writer.py — no import dependency
- writer.close() called in both poller finally block and main finally block for defense-in-depth
- writer.close() made idempotent by setting self._client = None after closing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed missing type field in test_poller.py _device_config()**
- **Found during:** Task 2 (full test suite run)
- **Issue:** DeviceConfig gained a required `type` field in Plan 03-01, but `_device_config()` test helper in test_poller.py was not updated — 6 poller tests failed with TypeError
- **Fix:** Added `type = "inverter"` to `_device_config()` helper
- **Files modified:** solarman_logger/tests/test_poller.py
- **Verification:** All 64 tests pass
- **Committed in:** 3cac90a (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Pre-existing test issue from Plan 03-01 that wasn't caught. Trivial fix, no scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `python -m solarman_logger --config config.yaml` is a working entry point for Docker CMD
- All 64 tests pass across 8 test modules
- Phase 03 (InfluxDB Pipeline) is complete — ready for Phase 04 (Docker Packaging)

## Self-Check: PASSED

All 3 created files verified present. All 3 commit hashes verified in git log.

---
*Phase: 03-influxdb-pipeline*
*Completed: 2026-03-30*
