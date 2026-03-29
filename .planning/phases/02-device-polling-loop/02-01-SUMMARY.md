---
phase: 02-device-polling-loop
plan: "01"
subsystem: pysolarman-fixes
tags: [pysolarman, retry, reconnect, asyncio, regression-tests, tdd]
dependency_graph:
  requires:
    - solarman_logger.pysolarman.Solarman (from 01-01)
  provides:
    - bounded _open_connection retry loop
    - asyncio.Event-based in-flight coordination
    - no last-frame replay after reconnect
    - solarman_logger/tests/test_pysolarman_fix.py
  affects:
    - Phase 2 poller reliability
    - future runtime recovery behavior
key_files:
  created:
    - solarman_logger/tests/test_pysolarman_fix.py
  modified:
    - solarman_logger/pysolarman/__init__.py
requirements_delivered:
  - POLL-06
---

# Phase 02 Plan 01: pysolarman Fixes Summary

Bounded reconnect handling is now in `solarman_logger/pysolarman/__init__.py`, so sustained connection failure raises `ConnectionError` after three attempts instead of recursing until `RecursionError`.

- `self._data_event` now uses `asyncio.Event`, matching the standalone asyncio runtime
- `_open_connection()` now retries in a loop, logs failed attempts, and exits cleanly after the cap
- reconnect success no longer replays `self._last_frame`; the next poll cycle issues fresh work instead
- `solarman_logger/tests/test_pysolarman_fix.py` covers bounded failure, retry-then-success, no replay, and event type

Verification:

```text
.venv/bin/python -m pytest solarman_logger/tests/test_pysolarman_fix.py -v
4 passed
```
