# Pitfalls Research: solarman-logger

**Domain:** Solarman/Modbus-to-InfluxDB data logger (Python, asyncio, Docker)
**Researched:** 2026-03-29
**Confidence:** HIGH — based on direct codebase audit of pysolarman/__init__.py, parser.py, CONCERNS.md, InfluxDB v2 official docs, and line-protocol spec

---

## Critical Pitfalls

### C1: Solarman Serial Number Must Be in Range 2147483648–4294967295

**What goes wrong:** The `serial` setter in `pysolarman/__init__.py:100` silently replaces any integer outside `[2147483648, 4294967295]` with `PROTOCOL.PLACEHOLDER3` (12 zero bytes). If the serial from YAML config is zero, too small, or typed as a string, the first Solarman frame is sent with an all-zero serial. The inverter will still respond on the first attempt (the protocol auto-discovers the serial from the response at line 279), but only if `transport == "tcp"`. For other transports, the all-zero serial produces frames the stick logger silently ignores — no error is raised, no data is received.

**Why it happens:** The V5 Solarman frame header embeds the device serial number in bytes 7–10 (little-endian uint32). The serial is not the device IP. It is the 10-digit number printed on the Wi-Fi stick label (format: `17xxxxxxxx`). It is commonly confused with the device's ModBus slave ID.

**Consequences:** Zero data written to InfluxDB with no obvious error; DEBUG logging shows `SERIAL_SET` only on the first successful response, masking misconfiguration.

**Warning signs:**
- All polls return empty data but no exceptions are logged
- `SERIAL_SET` log line never appears
- `serial_bytes` shown as `00 00 00 00` in DEBUG frame dumps

**Prevention:**
- YAML validation: require serial to be an integer, min 2147483648 (≥ 0x80000000)
- Log an explicit WARNING if serial is in placeholder range at startup
- Cross-reference with auto-discovery flow: only rely on auto-discovery (serial=0 first poll) if transport is explicitly `tcp`

**Phase:** Config/startup validation — Phase 1 (YAML config loading)

---

### C2: Recursive `_open_connection` Causes `RecursionError` Under Persistent Network Failure

**What goes wrong:** `pysolarman/__init__.py:222–225` — when a connection attempt fails and `self._last_frame is not None`, the exception handler calls `await self._open_connection()` recursively with no base case and no retry limit. Under a flapping or unreachable network, this recurses until Python raises `RecursionError` (default stack limit ~1000), crashing the asyncio task entirely. The task crash is not propagated to the polling loop, so the device silently stops being polled.

**Why it happens:** The intent is to keep retrying until a connection is made. But asyncio coroutine recursion is direct call-stack recursion, not tail-call recursion. Each await adds a stack frame.

**Consequences:** Device polling silently stops; container logs show an unhandled exception deep in asyncio; other devices continue polling normally, masking the failure.

**Warning signs:**
- `RecursionError: maximum recursion depth exceeded` in logs
- Device missing from InfluxDB after a network event (router reboot, DHCP change)
- The failed device never recovers without container restart

**Prevention:**
- Replace recursive call with `asyncio.create_task(self._open_connection())` (non-blocking task reschedule)
- Add a retry counter with exponential backoff and a maximum wait cap (e.g., 60s)
- Wrap the polling task in a top-level try/except that logs and reschedules on any unhandled exception

**Phase:** Protocol client extraction — Phase 1 or Phase 2 (adapt pysolarman)

---

### C3: `multiprocessing.Event` Used as asyncio Synchronization Primitive

**What goes wrong:** `pysolarman/__init__.py:10,77` uses `from multiprocessing import Event` to create `self._data_event`. `multiprocessing.Event` uses OS-level semaphores (shared memory), not asyncio primitives. In the asyncio context, `is_set()`, `set()`, and `clear()` work, but they do not interact with asyncio's event loop. This means `asyncio.wait_for` cannot await the event; the code instead uses a polling queue (`_data_queue`) as the actual await point, making `_data_event` a boolean guard only. The problem is that `set()` and `clear()` do not yield to the event loop, causing subtle ordering races if the keeper loop fires between the `set()` call and the queue `get()`.

**Why it happens:** `asyncio.Event` was not used — likely an oversight from porting synchronous code.

**Consequences:** Rare race conditions where data arrives before the event is set, causing "Data received too late" logs and dropped poll responses under high concurrency (multiple devices polling simultaneously).

**Warning signs:**
- Sporadic `Data received too late` in DEBUG logs
- Occasional missing data points in InfluxDB for one poll cycle
- Symptoms worsen as number of devices increases

**Prevention:**
- Replace `from multiprocessing import Event` with `asyncio.Event`
- Update `_data_event` usage: `await self._data_event.wait()` instead of queue polling where appropriate
- Must be done before multi-device scaling

**Phase:** Protocol client adaptation — Phase 2

---

### C4: Polling Too Fast Locks Up the Solarman Wi-Fi Stick

**What goes wrong:** The Solarman Wi-Fi stick logger (IGEN Tech hardware) has a firmware-level connection limit of **one simultaneous TCP connection** and a maximum request rate of approximately **1 request per 2–3 seconds**. If two poll cycles overlap (e.g., a 30s interval with a 35s device timeout), the stick enters a locked state and stops responding entirely. Recovery requires waiting ~60 seconds or power-cycling the stick.

**Why it happens:** The stick is a simple embedded device. The Solarman cloud poller (if still enabled) and the local logger both attempt connections, consuming the stick's single connection slot. Additionally, the register map for some Deye inverters spans many non-contiguous groups, generating 10–15 separate Modbus requests per poll — each taking ~1–2 seconds. A 30s interval is too short if the device definition produces 15 requests × 2s = 30s of polling time.

**Consequences:** Device goes offline entirely; InfluxDB shows no data; the stick may also lose its cloud connection.

**Warning signs:**
- Poll duration approaching or exceeding the configured poll interval
- Connection timeouts increasing in logs even when device is physically online
- Stick's LED stops blinking normally after a few minutes of operation

**Prevention:**
- Default poll interval to **60 seconds** minimum (not 30s)
- Log WARNING if estimated poll duration (request count × avg latency) exceeds 80% of poll interval
- Disable Solarman cloud connection on the stick if local polling is the primary use (reduces connection conflicts)
- Implement per-device semaphore to prevent overlapping polls
- The `@throttle(0.1)` on `_send_receive_frame` already adds 100ms inter-frame delays — do not remove this

**Phase:** Polling loop design — Phase 2 (coordinator/scheduler)

---

### C5: InfluxDB Field Type Conflict Corrupts Measurement Schema

**What goes wrong:** InfluxDB v2 infers field types from the first write. If a register value is ever written as an integer (e.g., `power=0i`) and then later written as a float (e.g., `power=0.5`), InfluxDB returns HTTP 400 `field type conflict` and **silently drops the entire write batch**. The default `influxdb-client` batching mode swallows the error without re-raising it unless error callbacks are configured.

**Why it happens:** The `ParameterParser` uses `scale` and `divide` to produce floats from raw integer register values. If a field is ever zero (scale × 0 = 0 in Python = integer `0`, not float `0.0`), it may be written as an integer on the first write. Once the type is locked, fractional values cause type conflicts.

**Consequences:** Silent data loss for entire measurement after the first non-zero reading; no error visible unless InfluxDB write error callbacks are implemented.

**Warning signs:**
- InfluxDB shows data for ~1 minute then nothing
- HTTP 400 response body: `{"code":"invalid","message":"... field type conflict"}`
- Grafana panel shows data up to a timestamp, then flat line

**Prevention:**
- Always write numeric fields as floats: `float(value)` before building the Point
- Use the `influxdb_client.Point` API — it enforces type-safe field writes
- Always configure `error_callback` on the WriteApi batching mode
- Test schema on first startup: attempt a dry-run write or verify bucket field types

**Phase:** InfluxDB writer implementation — Phase 3

---

### C6: InfluxDB Line Protocol Special Character Escaping

**What goes wrong:** InfluxDB line protocol requires backslash-escaping of `,`, `=`, and space in tag keys and tag values; and escaping of `"` and `\` in string field values. Device names from YAML config (used as tag values) may contain spaces (`"Inverter 1"`) or special characters. Field names derived from register YAML keys may contain spaces or special characters. Passing unescaped strings as raw line protocol causes a parse error on the entire write batch.

**Why it happens:** When using raw line protocol strings (not the Point API), escaping is the caller's responsibility. The InfluxDB Python client's `Point` API handles escaping automatically, but using f-string line protocol building bypasses this.

**Consequences:** Write HTTP 400 error; entire batch dropped silently if error callback not configured.

**Warning signs:**
- HTTP 400 response body mentioning "unable to parse" or "invalid line protocol"
- Spaces in YAML device names → silent write failure

**Prevention:**
- **Always use `influxdb_client.Point` API** — never build line protocol strings manually
- Normalize device names in config: strip/replace spaces with underscores at parse time, or sanitize before use as tag values
- Add a startup validation step that writes a test point with each device's tag values

**Phase:** InfluxDB writer implementation — Phase 3

---

### C7: int16 vs uint16 Register Misidentification Produces Garbage Values

**What goes wrong:** Modbus registers are 16-bit unsigned raw values. Some fields (temperature below zero, signed power direction, reactive power) are stored as two's-complement signed int16. The `ParameterParser` differentiates via `rule` field: rule 1/3 = unsigned, rule 2/4 = signed. Using unsigned parsing for a signed register produces values like `65450` instead of `-86`. Using signed parsing for an unsigned register produces negative values that pass range validation if no bounds are set.

**Why it happens:** Copy-paste errors in YAML profile definitions. The Deye SUN-M225G4 profile (already in repo) has been validated, but any custom register additions or other device profiles (smart meter) require careful attention to signedness.

**Consequences:** Physically impossible values (temperature = 65000°C) written to InfluxDB; pollutes historical data permanently (InfluxDB has no update/delete by field value).

**Warning signs:**
- Register values near 65535 or 32768 when physical reality requires small numbers
- Energy values going negative unexpectedly
- Smart meter reading `65000` for a field expected to be under 500

**Prevention:**
- Always specify both `rule: 1` (unsigned) or `rule: 2` (signed) explicitly in YAML
- For any new register definition, cross-reference the device's official Modbus register map
- Add post-parse range validation: flag values outside physical plausibility (e.g., temperature > 200°C or < -50°C)
- The `range` key in YAML definitions is available for this — use it

**Phase:** Device profile validation — Phase 1 (profile loading) and Phase 4 (smart meter profile)

---

### C8: asyncio `wait_for` Timeout Does Not Cancel the Underlying TCP Operation

**What goes wrong:** `asyncio.wait_for(asyncio.open_connection(...), timeout)` correctly raises `TimeoutError` when the timeout expires, but in Python 3.11 and earlier, the underlying `open_connection` coroutine is not guaranteed to be immediately cancelled — it may continue running in the background, holding the socket and file descriptor. If poll failures occur rapidly (e.g., device unreachable), leaked tasks accumulate until the event loop runs out of file descriptors.

**Why it happens:** `asyncio.wait_for` cancels the wrapped coroutine, but cancellation is cooperative — `open_connection` may not reach a cancellation point before the `wait_for` wrapper returns. Fixed more robustly in Python 3.12+.

**Consequences:** Gradual file descriptor leak; eventually container crashes with `OSError: [Errno 24] Too many open files`; only seen with many devices or rapid failure cycles.

**Warning signs:**
- Long-running container accumulates file descriptors (`lsof -p <pid>` shows increasing sockets in CLOSE_WAIT)
- `OSError: [Errno 24] Too many open files` after hours/days of operation
- Resource exhaustion coincides with device going offline

**Prevention:**
- Use Python 3.12+ in the Docker image (3.12 fixes `wait_for` cancellation semantics)
- After each `TimeoutError`, explicitly cancel the keeper task and close writer before retry
- The existing `_close()` method does this — ensure it is always called in the timeout branch

**Phase:** Protocol client / Docker image — Phase 2 (Python version pinning)

---

## Moderate Pitfalls

### M1: Docker Bridge Network Cannot Reach LAN Devices by Default

**What goes wrong:** A Docker container on the default `bridge` network cannot reach devices on the host's LAN (e.g., `192.168.1.x`) without explicit port mapping or network configuration. For a data logger that connects outbound to multiple inverters on the local network, the standard solution is `network_mode: host` in docker-compose.yml. However, `host` networking is Linux-only — it is silently ignored on Docker Desktop for Mac/Windows.

**Why it happens:** Docker bridge creates an isolated network namespace. The inverters are on the host's LAN, not in any Docker network. `network_mode: host` removes the isolation on Linux, allowing direct LAN access.

**Consequences:** Container starts successfully, but all `asyncio.open_connection(host, 8899)` calls fail with `ConnectionRefusedError` or `TimeoutError`; misleading because the host machine can ping the inverter fine.

**Warning signs:**
- Container logs show connection failures to known-good inverter IPs
- `ping inverter-ip` works from host but not from inside `docker exec` on bridge network
- Symptom disappears when running outside Docker

**Prevention:**
- In `docker-compose.yml`, always use `network_mode: host` (Linux target deployment)
- Document clearly: `network_mode: host` does not work on Docker Desktop for Mac/Windows — for local development, run the script directly outside Docker
- Do NOT use bridge + port-forwarding for outbound connections (port-forwarding is for inbound only)

**Phase:** Docker deployment — Phase 5

---

### M2: InfluxDB Async Client in asyncio Context

**What goes wrong:** The `influxdb-client` Python package's standard `WriteApi` is synchronous. Using `SYNCHRONOUS` write mode inside an asyncio polling loop blocks the event loop during the HTTP request (typically 50–200ms). With 3 devices, this adds 150–600ms of blocking per poll cycle. Over time, this accumulates and causes poll jitter that can exceed the poll interval.

**Why it happens:** `influxdb-client[async]` is a separate installation target. The default package does not pull in `aiohttp`. Many implementations mistakenly use synchronous client in async contexts.

**Consequences:** Polling intervals drift; with many devices, the event loop appears "frozen" during writes; DEBUG logs show polls starting late.

**Prevention:**
- Use `influxdb-client[async]` and `InfluxDBClientAsync` with `write_api = client.write_api()` (async WriteApi)
- Or use `loop.run_in_executor(None, write_api.write, ...)` to offload synchronous writes to a thread pool
- Recommended: `influxdb-client[async]` is cleaner; install with `pip install influxdb-client[async]`

**Phase:** InfluxDB writer implementation — Phase 3

---

### M3: YAML Config Validation: Silent `None` for Missing Required Fields

**What goes wrong:** Python's PyYAML parses missing YAML keys as `None` without raising an error. If a required field (e.g., `host`, `serial`, `influxdb.token`) is absent from the config file, the service starts, and the `None` value propagates until the first poll attempt, producing a confusing `TypeError` deep in a network call rather than a clear startup error.

**Why it happens:** PyYAML/ruamel.yaml does not support schema validation natively. Without an explicit validation step, `None` values silently pass through config parsing.

**Consequences:** Misleading error messages at runtime; hard to diagnose which config field is missing; if the missing field is for InfluxDB token, polls succeed but writes fail silently.

**Prevention:**
- Use **pydantic v2** or **jsonschema** to validate the config dict immediately after YAML load
- Raise `SystemExit` with a clear message (e.g., "Config error: device[0].serial is required") before any TCP connections are attempted
- Minimum required fields to validate at startup: `host`, `port`, `serial`, `profile`, `influxdb.url`, `influxdb.token`, `influxdb.org`, `influxdb.bucket`

**Phase:** Config loading — Phase 1

---

### M4: `ParameterParser.process` Silently Swallows `ValueError` (Inherited Bug)

**What goes wrong:** `device.py:92–93` in the reference codebase catches `ValueError` with `pass` — this means any `invalidate_all` validation failure from `ParameterParser.do_validate` silently discards the entire poll result with zero log output at WARNING or above. When adapting this code, this pattern must not be carried forward.

**Why it happens:** The HA coordinator catches exceptions broadly to prevent HA from marking the device unavailable. In a standalone logger, this behavior is wrong — a ValueError from a bad register value should log at WARNING and skip the write, not silently discard data.

**Consequences:** Register validation failures → entire poll discarded → InfluxDB receives no update for that cycle → Grafana shows gaps that look like connectivity issues.

**Warning signs:**
- Gaps in InfluxDB data not correlated with network events
- No ERROR or WARNING logs but data is missing
- Only visible at DEBUG log level

**Prevention:**
- In the new service, replace the `except ValueError: pass` with `except ValueError as e: logger.warning(...)` and continue with partial data or skip write
- Log the specific field that failed validation, not just the exception

**Phase:** Protocol/parser adaptation — Phase 2

---

### M5: InfluxDB `SYNCHRONOUS` WriteApi Must Be Explicitly Closed

**What goes wrong:** The `influxdb-client` `WriteApi` in `SYNCHRONOUS` mode (and the default batching mode) holds an internal background thread and RxPY subject. If the client is not closed with `write_api.close()` and `client.close()` on shutdown, the background thread keeps the process alive after `asyncio.run()` returns, causing the container to hang indefinitely instead of exiting cleanly (which blocks `docker stop` → Docker sends SIGKILL after 10s).

**Why it happens:** The `WriteApi.__del__` finalizer is not reliable in CPython. `contextmanager` usage (`with client.write_api() as write_api`) is the correct pattern, but code that stores the `write_api` as an instance variable must call `.close()` in a shutdown handler.

**Consequences:** `docker stop` hangs for 10 seconds, then SIGKILL; data in the batching buffer that hasn't been flushed is lost.

**Prevention:**
- Register `asyncio` signal handlers (`SIGTERM`, `SIGINT`) that call `write_api.close()` and `client.close()`
- Use `with InfluxDBClient(...) as client, client.write_api(...) as write_api:` pattern where possible
- Test `docker stop` explicitly and verify clean exit in logs

**Phase:** Service lifecycle / shutdown — Phase 2 or Phase 5

---

### M6: Modbus Register Address Off-by-One (0-indexed vs 1-indexed)

**What goes wrong:** The Deye and other inverter Modbus documentation uses 1-based register addresses (Register 1 = address 0x0001). The Modbus protocol itself uses 0-based addresses. Some firmware and some documentation use mixed conventions. A register listed as "Register 33" in the manual may be accessed as address `0x0020` (32 decimal) or `0x0021` (33 decimal) depending on the convention. The umodbus library and pysolarman both use 0-based protocol addresses.

**Why it happens:** Register map documentation inconsistency. The ha-solarman YAML profiles encode the correct addresses for known devices, but any new device profile added for the smart meter or other hardware requires careful verification.

**Consequences:** Reading the wrong register produces plausible-looking but incorrect values (e.g., voltage reading that is off by one register reads the adjacent current value); the error is not detectable from the data alone.

**Warning signs:**
- Smart meter values that are "almost right" but consistently wrong
- Values that look like they belong to a different field

**Prevention:**
- When adding new register definitions, verify against both the device manual AND a known-good reading (e.g., compare inverter panel display to logged value)
- Cross-reference with the umodbus function code — `read_holding_registers` address 0 reads register 1 in most Modbus conventions

**Phase:** Smart meter profile addition — Phase 4

---

### M7: asyncio Task Exception Silencing

**What goes wrong:** `asyncio.create_task()` schedules a coroutine as a fire-and-forget task. If an unhandled exception occurs in the task, Python emits a `Task exception was never retrieved` warning to stderr but does **not** propagate the exception to the parent coroutine. In production, this is easy to miss. The reference codebase's `create_task` helper (from `common.py`) may not attach exception handlers.

**Why it happens:** asyncio tasks are designed to be independent — exceptions do not bubble up to the creator by default.

**Consequences:** Device polling task crashes silently; device stops logging; container health check (if any) sees the container as healthy; InfluxDB receives no new data but no alert is raised.

**Prevention:**
- Always attach a `done_callback` to polling tasks that logs unhandled exceptions at ERROR level and reschedules the task
- Pattern: `task.add_done_callback(lambda t: logger.error(...) if t.exception() else None)`
- Or use a task supervisor pattern: a top-level loop that recreates failed device tasks

**Phase:** Polling loop design — Phase 2

---

## Minor Pitfalls

### m1: InfluxDB Write Precision Mismatch

**What goes wrong:** The default InfluxDB write precision is nanoseconds. The logger writes data at 60-second intervals — second precision is sufficient. Writing with nanosecond timestamps (Python's `time.time_ns()`) is correct but requires consistent usage. Mixing `write_precision='s'` on the client and `write_precision='ns'` on individual Points causes InfluxDB to misinterpret timestamps (a second-level timestamp interpreted as nanoseconds appears as 1970).

**Prevention:**
- Pick one precision (recommend `WritePrecision.SECONDS`) and set it globally on the `WriteApi`; never mix per-point and per-client precision

**Phase:** Phase 3

---

### m2: YAML `safe_load` vs `full_load` Security Non-Issue (But Know the Difference)

**What goes wrong:** Using `yaml.load()` without `Loader=yaml.SafeLoader` allows YAML to instantiate arbitrary Python objects, a known security risk. For a service reading local config files, this is low risk, but it is a code quality issue that linters will flag.

**Prevention:**
- Always use `yaml.safe_load()` or `ruamel.yaml` in safe mode for user-supplied config files

**Phase:** Phase 1

---

### m3: Docker Container Time Zone for Timestamps

**What goes wrong:** The polling service timestamps data with `datetime.utcnow()` or `time.time()`. If the Docker container's system clock is not synchronized (no NTP in container), or if the container uses a non-UTC timezone, timestamps written to InfluxDB may be incorrect or skewed relative to Grafana's display timezone.

**Prevention:**
- Always use `time.time()` (Unix epoch) for InfluxDB timestamps — timezone-agnostic
- Ensure the Docker image includes `tzdata` and sets `TZ=UTC`
- Add `docker-compose.yml` volume mount: `/etc/localtime:/etc/localtime:ro` (optional, for local time logs)

**Phase:** Phase 5

---

### m4: `propcache` Dependency Not in Standard Library

**What goes wrong:** The reference codebase's `provider.py` imports `from propcache import cached_property`. `propcache` is not in Python's standard library and is not listed in `manifest.json` requirements. If extracted without auditing dependencies, the standalone service will fail with `ImportError` at startup.

**Prevention:**
- Replace all `propcache.cached_property` with `functools.cached_property` (stdlib since Python 3.8)
- Audit all imports in extracted files before first run

**Phase:** Phase 1 (extraction/adaptation)

---

### m5: `ParameterParser.try_parse_datetime` Silent Failure for Non-3/Non-6 Register Counts

**What goes wrong:** `parser.py:386–411` — the datetime parser only handles registers_count == 3 or == 6. Any other count produces an empty string, which then fails `strptime` silently (caught and logged only at DEBUG). This is a known bug in the reference codebase.

**Prevention:**
- Add explicit handling for unsupported register counts: log at WARNING, return without setting state
- Relevant only if smart meter or other devices have datetime registers with unusual layouts

**Phase:** Phase 4 (if smart meter has datetime registers)

---

## Phase Mapping

| Phase | Topic | Pitfall(s) to Address |
|-------|--------|-----------------------|
| **Phase 1** | YAML config loading & validation | C1 (serial range), M3 (None fields), m2 (safe_load), m4 (propcache) |
| **Phase 1** | pysolarman/ParameterParser extraction | C7 (int16/uint16), m5 (datetime parser) |
| **Phase 2** | Protocol client adaptation | C2 (recursive reconnect), C3 (multiprocessing.Event), C8 (wait_for leak) |
| **Phase 2** | Polling loop & scheduler | C4 (polling rate), M4 (ValueError swallow), M7 (task exception silence), M5 (shutdown/close) |
| **Phase 3** | InfluxDB writer | C5 (field type conflict), C6 (line protocol escaping), M2 (sync vs async client), M1 (write precision) |
| **Phase 4** | Smart meter profile | C7 (int16/uint16 again), M6 (register addressing off-by-one) |
| **Phase 5** | Docker deployment & lifecycle | M1 (Docker bridge networking), m3 (container timezone), M5 (shutdown) |

### Highest Priority (rewrite risk)
1. **C2** — recursive reconnect: will crash the task under any sustained network failure
2. **C5** — field type conflict: silently corrupts InfluxDB measurement schema permanently
3. **C4** — polling rate: will physically lock up the Solarman stick hardware

### Second Priority (silent data loss)
4. **C1** — serial number: zero-data operation with no error
5. **C6** — line protocol escaping: entire batch lost if device names have spaces
6. **M4** — ValueError swallow: poll results silently discarded

### Third Priority (operational issues)
7. **C3** — multiprocessing.Event: intermittent dropped responses under load
8. **M1** — Docker networking: container cannot reach inverters
9. **M2** — sync write client: event loop blocking

---

## Sources

- Direct codebase audit: `pysolarman/__init__.py` (lines 10, 77, 100, 212–225, 253–264) — HIGH confidence
- Direct codebase audit: `parser.py` (lines 127–142, 386–414) — HIGH confidence
- Direct codebase audit: `CONCERNS.md` (all sections) — HIGH confidence
- InfluxDB v2 line protocol spec: https://docs.influxdata.com/influxdb/v2/reference/syntax/line-protocol/ — HIGH confidence
- InfluxDB v2 write optimization: https://docs.influxdata.com/influxdb/v2/write-data/best-practices/optimize-writes/ — HIGH confidence
- influxdb-client Python API: https://influxdb-client.readthedocs.io/en/stable/api.html — HIGH confidence
- Solarman V5 frame format: inferred from pysolarman source constants (PROTOCOL.START = 0xA5, serial range check) — HIGH confidence (code is ground truth)
- Docker host networking: well-established Docker documentation behavior — MEDIUM confidence (Linux-specific, version-independent)
- asyncio `wait_for` cancellation semantics: Python 3.11 vs 3.12 behavior difference — MEDIUM confidence (known community-reported issue)
