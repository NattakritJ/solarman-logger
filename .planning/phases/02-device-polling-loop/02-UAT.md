---
status: complete
phase: 02-device-polling-loop
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md]
started: 2026-03-30T12:00:00Z
updated: 2026-03-30T12:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Bounded Reconnect Failure
expected: After 3 failed connection attempts, the Solarman client raises ConnectionError cleanly instead of recursing until RecursionError. Test: `.venv/bin/python -m pytest solarman_logger/tests/test_pysolarman_fix.py::test_open_connection_bounded_retry -v`
result: pass

### 2. Reconnect Retry Then Success
expected: When connection fails then recovers within the retry cap, the client reconnects successfully without error. Test: `.venv/bin/python -m pytest solarman_logger/tests/test_pysolarman_fix.py::test_open_connection_succeeds_on_second_attempt -v`
result: pass

### 3. No Last-Frame Replay After Reconnect
expected: After a reconnect, the client does not replay the previous frame. The next poll cycle issues fresh work instead. Test: `.venv/bin/python -m pytest solarman_logger/tests/test_pysolarman_fix.py::test_no_last_frame_replay_after_reconnect -v`
result: pass

### 4. Independent Per-Device Polling
expected: When multiple devices are configured, one device going offline does not block polling of other devices. Each DeviceWorker runs independently. Test: `.venv/bin/python -m pytest solarman_logger/tests/test_poller.py -k "test_" -v`
result: pass

### 5. Health Transition Logging
expected: DeviceHealth logs state transitions (online->offline, offline->online) without repeating the same warning every poll cycle. Only transitions produce log output. Test: `.venv/bin/python -m pytest solarman_logger/tests/test_poller.py -k "transition" -v`
result: pass

### 6. Exponential Backoff on Offline Retries
expected: When a device is offline, retry interval increases exponentially up to 300 seconds, then resets to base interval on recovery. Test: `.venv/bin/python -m pytest solarman_logger/tests/test_poller.py -k "backoff" -v`
result: pass

### 7. Solar Device Quiet Mode
expected: Devices inferred as solar (from profile metadata and PV-style item names) produce quieter logging during expected overnight sleep periods compared to meter outages. Test: `.venv/bin/python -m pytest solarman_logger/tests/test_poller.py -k "solar" -v`
result: pass

### 8. Full Test Suite Passes
expected: All Phase 2 tests pass cleanly: `.venv/bin/python -m pytest solarman_logger/tests/ -v` — expecting 45+ tests passed, 0 failures, 0 errors.
result: pass

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
