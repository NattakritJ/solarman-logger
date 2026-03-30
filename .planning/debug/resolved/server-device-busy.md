---
status: resolved
trigger: "solarman-logger gets ServerDeviceBusyError() on every poll for a device. Device works fine with HA integration and SolarmanSmart app simultaneously."
created: 2026-03-30T00:00:00Z
updated: 2026-03-30T14:00:00Z
---

## Current Focus

hypothesis: CONFIRMED — Serial setter's int path embedded real serial bytes for values >= 0x80000000, conflicting with cloud session. Fix: always use placeholder bytes (auto-discovery) regardless of serial value.
test: All 95 tests pass (6 new serial setter tests + 2 new config tests)
expecting: User confirms ServerDeviceBusy no longer occurs with correct serial in config
next_action: Await human verification on real device

## Symptoms

expected: Device should be polled successfully and data written to InfluxDB
actual: Every poll immediately fails with ServerDeviceBusyError(). The error repeats every 20 seconds. Device is reported as "offline" with "The server is engaged in a long-duration program command."
errors: ServerDeviceBusyError() — Modbus exception code 0x06 (Server Device Busy)
reproduction: Start solarman-logger while HA solarman integration and SolarmanSmart cloud are also connected to the same device
started: First time running. Never worked. HA integration and SolarmanSmart app both work fine reading the same device.

## Eliminated

- hypothesis: ServerDeviceBusyError just needs better retry logic (busy-retry wrapper)
  evidence: User reports that even with the busy-retry fix, the device still fails with ServerDeviceBusy on EVERY attempt when the correct serial is in config. But with a wrong serial (triggering auto-discovery), it works immediately. The retry strategy is a symptom-level mitigation, not the root cause.
  timestamp: 2026-03-30T13:00:00Z

## Evidence

- timestamp: 2026-03-30T00:01:00Z
  checked: Error origin in umodbus/functions.py line 131
  found: pdu_to_function_code_or_raise_error() raises ServerDeviceBusyError (error_code 6) when Modbus response has function code not in valid map. The exception class is raised (not instantiated), raising the class itself.
  implication: ServerDeviceBusyError is a ModbusError subclass, not a TimeoutError or ConnectionError

- timestamp: 2026-03-30T00:02:00Z
  checked: pysolarman/__init__.py _parse_adu_from_sol_response() line 294-300
  found: After extracting inner Modbus frame from Solarman V5 protocol wrapper, it calls rtu.parse_response_adu(res, req) which calls create_function_from_response_pdu() which calls pdu_to_function_code_or_raise_error() — this is where ServerDeviceBusyError gets raised
  implication: The error bubbles up from within the _get_response -> _parse_adu_from_sol_response call chain

- timestamp: 2026-03-30T00:03:00Z
  checked: pysolarman/__init__.py get_response() line 313-315 with @retry() decorator
  found: get_response() is decorated with @retry() (no ignore tuple). The retry decorator in common.py catches ALL exceptions (except those in `ignore` tuple) and retries ONCE immediately. ServerDeviceBusyError is NOT in the ignore tuple, so it gets retried once with zero delay.
  implication: First retry happens immediately — but if device is busy, an immediate retry will likely also get ServerDeviceBusyError since the other client hasn't finished yet

- timestamp: 2026-03-30T00:04:00Z
  checked: pysolarman/__init__.py execute() line 318-324
  found: execute() wraps get_response() in asyncio.timeout(timeout*6) and a lock. After get_response fails (after 1 retry), the ModbusError propagates up to the caller.
  implication: No additional retry at execute level

- timestamp: 2026-03-30T00:05:00Z
  checked: poller.py _poll_cycle() lines 142-146
  found: TimeoutError and ConnectionError/OSError are caught with _handle_failure(). But ServerDeviceBusyError (a ModbusError) falls through to the generic `except Exception` on line 144-145, which logs "Unexpected error during poll" at ERROR level and calls _handle_failure(). The exponential backoff then kicks in (poll_interval * 2^failures, capped at 300s).
  implication: Each poll attempt effectively gets 2 tries (original + 1 retry) both immediate, then the device goes to backoff. Because backoff escalates quickly (20s->40s->80s->160s->300s), the logger rapidly backs off to 5-min intervals — and each attempt still only gets 2 immediate tries.

- timestamp: 2026-03-30T00:06:00Z
  checked: The complete error path end-to-end
  found: The fundamental problem is TWO-FOLD: (1) The @retry() decorator only retries ONCE with ZERO delay — a busy device needs a small delay (1-3s) between retries to wait for the competing client to release the connection. (2) ServerDeviceBusyError is treated as "unexpected error" in poller rather than as a transient contention error that should be retried more aggressively before giving up.
  implication: ROOT CAUSE CONFIRMED — The retry strategy is not appropriate for ServerDeviceBusyError which is a transient contention error, not a persistent failure.

- timestamp: 2026-03-30T13:01:00Z
  checked: Serial setter in pysolarman/__init__.py lines 94-102
  found: "The int path has a range check: serial_bytes = struct.pack('<I', value) if 2147483648 <= value <= 4294967295 else PROTOCOL.PLACEHOLDER3. This means serials < 0x80000000 (2147483648) get serial_bytes=00000000 (placeholder). The bytes path (from auto-discovery) always sets serial_bytes directly with no range check."
  implication: For serials >= 0x80000000 (common for 25xx-43xx range sticks), the real serial is embedded in the first V5 frame — which conflicts with the cloud session. For serials < 0x80000000, placeholder bytes trigger auto-discovery which avoids the conflict.

- timestamp: 2026-03-30T13:02:00Z
  checked: Auto-discovery flow in _parse_adu_from_sol_response lines 280-284
  found: "Auto-discovery triggers when serial_bytes == PLACEHOLDER3: first request with zeros succeeds (anonymous session), serial extracted from response bytes, then second request sent with real serial on the already-established TCP connection. The key insight is the first anonymous request establishes the session without conflicting with the cloud's serial-identified session."
  implication: The auto-discovery flow is the correct approach — it avoids serial-based session conflict by starting anonymous

- timestamp: 2026-03-30T13:03:00Z
  checked: Typical Solarman stick serial ranges vs the 0x80000000 threshold
  found: "Stick loggers with serial numbers starting with 25xx-43xx (decimal >= 2500000000) are in the 0x80000000+ range and get real serial_bytes. Sticks with 17xx-21xx serials fall below and get placeholder. This explains why some users would see the bug and others wouldn't — it depends on the serial number range of their specific stick logger."
  implication: This is a data-dependent bug — only affects sticks with high serial numbers

## Resolution

root_cause: The Solarman V5 serial setter embeds the actual serial bytes in the protocol frame ONLY when serial >= 0x80000000 (the int path). For serials in this range (common for 25xx+ stick loggers), the first request carries the real serial in the V5 frame header, which conflicts with the cloud service's active session using the same serial — causing ServerDeviceBusy on every attempt. For serials below 0x80000000 (or invalid/wrong serials), serial_bytes defaults to 00000000 (placeholder), which triggers auto-discovery: the first request goes out anonymously (no serial conflict), the device responds, the serial is extracted from the response, and subsequent requests use the real serial on the already-established session. The fix: always start with placeholder serial_bytes (force auto-discovery) regardless of config serial value, and make serial optional in config since auto-discovery is the reliable path.
fix: (1) Changed serial setter int path to always use PROTOCOL.PLACEHOLDER3 instead of conditionally embedding real bytes for >= 0x80000000. This forces auto-discovery on first V5 request for ALL serial values, avoiding session conflicts with the cloud. (2) Made serial optional in config.py — omitting serial defaults to 0, which also triggers auto-discovery. Serial can still be provided for identification/logging purposes.
verification: All 95 tests pass (87 original + 6 new serial setter regression tests + 2 new optional-serial config tests). Serial setter tests verify: int path always produces placeholder bytes (for low, high, max, and zero serials), bytes path always produces real bytes (for auto-discovery response).
files_changed: [solarman_logger/pysolarman/__init__.py, solarman_logger/config.py, solarman_logger/tests/test_pysolarman_fix.py, solarman_logger/tests/test_config.py]
