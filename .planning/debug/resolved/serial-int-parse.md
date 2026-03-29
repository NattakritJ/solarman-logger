---
status: resolved
trigger: "load_config crashes with ValueError: invalid literal for int() with base 10: '251017036F' because serial contains hex characters"
created: 2026-03-30T00:00:00Z
updated: 2026-03-30T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED — config.py line 140 uses int(dev_serial) which fails on hex chars; fix should try decimal first then hex, and validate 32-bit range with a warning
test: Implementing fix in config.py parse_serial() helper + adding tests
expecting: Serial "251017036F" parses as hex int; decimal serials still work; >32-bit serials get a warning log
next_action: Apply fix to config.py and add test cases

## Symptoms

expected: Config loads successfully with serial "251017036F" — the Solarman protocol should accept this serial
actual: Crash on startup with ValueError at config.py line 140: serial=int(dev_serial)
errors: ValueError: invalid literal for int() with base 10: '251017036F'
reproduction: Put a device with serial "251017036F" in config.yaml and run the container
started: First deployment attempt with this serial number

## Eliminated

## Evidence

- timestamp: 2026-03-30T00:05:00Z
  checked: config.py line 140
  found: `serial=int(dev_serial)` — uses int() with no base, defaults to base 10
  implication: Any serial containing hex chars (A-F) will crash with ValueError

- timestamp: 2026-03-30T00:06:00Z
  checked: pysolarman serial setter (lines 90-102)
  found: serial.setter accepts int|bytes; for int, packs as struct.pack("<I", value) ONLY when 2147483648 <= value <= 4294967295; otherwise uses zeros (PLACEHOLDER3) and auto-discovers from device response
  implication: Protocol packs serial as 32-bit unsigned int; values outside 2^31..2^32 range result in auto-discovery

- timestamp: 2026-03-30T00:07:00Z
  checked: "251017036F" as hex = 159,183,733,615 (37 bits); exceeds 32-bit max 4,294,967,295
  found: The value doesn't fit in 32 bits, so the protocol client would use zeros and auto-discover — which is valid behavior
  implication: Parsing as hex won't break protocol; the serial setter gracefully handles oversized values

- timestamp: 2026-03-30T00:08:00Z
  checked: YAML parsing behavior for serial values
  found: YAML auto-parses unquoted numeric-looking values as int. "251017036F" contains hex char F, so YAML loads it as string. Pure numeric serials like 1234567890 are loaded as int by YAML.
  implication: dev_serial can be either str or int depending on YAML auto-parsing; fix must handle both types

## Resolution

root_cause: config.py line 140 calls `int(dev_serial)` which assumes base-10 decimal. Serial numbers containing hex characters (like "251017036F") fail with ValueError because `int()` without a base parameter rejects A-F characters.
fix: Added `_parse_serial()` helper that tries decimal first, falls back to hex parsing, validates non-negative, and logs a warning if the value exceeds the 32-bit Solarman V5 protocol field width (in which case the protocol auto-discovers the serial from the device).
verification: 82/82 tests pass. 13 new serial parsing tests cover: int passthrough, decimal string, hex with/without 0x prefix, upper/lowercase hex, invalid strings, negative values, zero, 32-bit max, >32-bit warning, decimal-vs-hex priority, and full config integration with hex serial.
files_changed: [solarman_logger/config.py, solarman_logger/tests/test_config.py]
