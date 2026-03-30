# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## serial-int-parse — ValueError when config serial contains hex characters
- **Date:** 2026-03-30
- **Error patterns:** ValueError, invalid literal for int(), base 10, serial, hex, 251017036F
- **Root cause:** `config.py` line 140 calls `int(dev_serial)` without specifying a base, so serial numbers containing hex characters (A-F) crash with ValueError.
- **Fix:** Added `_parse_serial()` helper that tries decimal first, falls back to `int(text, 16)` for hex strings, validates non-negative, and logs a warning when value exceeds 32-bit Solarman V5 protocol field width.
- **Files changed:** solarman_logger/config.py, solarman_logger/tests/test_config.py
---

## server-device-busy — ServerDeviceBusyError on every poll with correct serial in config
- **Date:** 2026-03-30
- **Error patterns:** ServerDeviceBusyError, Modbus exception code 0x06, Server Device Busy, device offline, serial, cloud session conflict
- **Root cause:** The Solarman V5 serial setter embedded real serial bytes in the protocol frame for serials >= 0x80000000 (common for 25xx+ stick loggers). This conflicted with the cloud service's active session using the same serial, causing ServerDeviceBusy on every attempt. Serials below the threshold defaulted to placeholder bytes (auto-discovery), which worked because the first anonymous request avoids the serial conflict.
- **Fix:** (1) Serial setter int path always uses placeholder bytes (forces auto-discovery for all serial values). (2) Serial made optional in config since auto-discovery is the reliable path. (3) ServerDeviceBusyError handled as transient failure in poller.
- **Files changed:** solarman_logger/pysolarman/__init__.py, solarman_logger/config.py, solarman_logger/poller.py, solarman_logger/tests/test_pysolarman_fix.py, solarman_logger/tests/test_config.py, solarman_logger/tests/test_poller.py
---
