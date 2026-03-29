---
phase: 02-device-polling-loop
plan: "02"
subsystem: standalone-poller
tags: [poller, asyncio, scheduling, backoff, health, tdd]
dependency_graph:
  requires:
    - solarman_logger.config.DeviceConfig
    - solarman_logger.parser.ParameterParser
    - solarman_logger.pysolarman.Solarman
    - Plan 02-01 reconnect fixes
  provides:
    - solarman_logger.poller.DeviceHealth
    - solarman_logger.poller.DeviceWorker
    - solarman_logger.poller.create_device_worker
    - solarman_logger.poller.run_all
    - solarman_logger/tests/test_poller.py
  affects:
    - Phase 3 InfluxDB pipeline entry point
    - device runtime behavior and recovery logging
key_files:
  created:
    - solarman_logger/poller.py
    - solarman_logger/tests/test_poller.py
requirements_delivered:
  - POLL-01
  - POLL-04
---

# Phase 02 Plan 02: Poller Summary

The standalone polling runtime now lives in `solarman_logger/poller.py`, with one async worker per device, transition-based health logging, elapsed-time scheduling, and per-device backoff.

- `DeviceWorker` executes scheduled request batches independently, so one device failure does not block another
- runtime scheduling uses elapsed wall-clock ticks rounded to `poll_interval`, preserving hourly groups like `Info`
- `DeviceHealth` logs offline/recovery and invalid-data transitions without repeating warnings every cycle
- solar-style devices are inferred from profile metadata and PV-style item names, so expected overnight sleep is quieter than meter outages
- offline retries back off exponentially up to 300 seconds and reset after recovery
- `solarman_logger/tests/test_poller.py` covers transitions, backoff, runtime math, success/failure cycles, overlap prevention, and solar detection

Verification:

```text
.venv/bin/python -m pytest solarman_logger/tests -v
45 passed
```
