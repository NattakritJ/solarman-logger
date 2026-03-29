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
