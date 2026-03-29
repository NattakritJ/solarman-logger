# Phase 2: Device Polling Loop — Research

**Researched:** 2026-03-30
**Phase:** 02-device-polling-loop
**Requirements:** POLL-01, POLL-04, POLL-06

---

## 1. Problem Statement

Phase 2 must build a standalone asyncio polling loop that:
- Polls N devices concurrently with error isolation (POLL-01)
- Honors per-group `update_interval` from YAML profiles using elapsed wall-clock time (POLL-04)
- Recovers from TCP failures without crashing (POLL-06)
- Fixes the recursive `_open_connection` bug in pysolarman

The HA reference uses `DataUpdateCoordinator` (a built-in HA polling framework) with a counter-based scheduling model. Our standalone version must replicate the scheduling semantics without any HA dependency.

---

## 2. Existing Code Analysis

### 2.1 HA's Scheduling Model (counter-based)

In HA, `Coordinator._async_update_data()` calls `device.get(self.counter)` where `counter` increments by `update_interval_seconds` on each successful poll. The parser's `is_scheduled(parameters, runtime)` checks:

```python
runtime % (parameters[REQUEST_UPDATE_INTERVAL] if REQUEST_UPDATE_INTERVAL in parameters else self._update_interval) == 0
```

For `deye_micro.yaml`:
- Default `update_interval: 5` → real-time groups schedule when `runtime % 5 == 0`
- Info group `update_interval: 3600` → schedules when `runtime % 3600 == 0`
- `runtime=0` triggers ALL groups (since `0 % anything == 0`)

**Key insight:** The counter isn't wall-clock seconds — it's a monotonically incrementing value where each step equals the base poll interval. In HA, `counter` resets to `_update_interval_seconds` on failure (see `coordinator.py:67`), which means failure resets the group scheduling clock.

### 2.2 Standalone Adaptation (D-09: elapsed wall-clock time)

User decision D-09 requires elapsed-time anchoring: "a group with `update_interval: 3600` means roughly once per hour on the clock, not once per N successful polls."

**Approach:** Track `time.monotonic()` per device. On each poll cycle, compute `elapsed_seconds = int(time.monotonic() - device_start_time)`. Pass this as `runtime` to `schedule_requests()`. Since `is_scheduled` uses modulo, the Info group fires when `elapsed_seconds % 3600 == 0` (or close to it given tick alignment).

**Edge case — tick alignment:** If `poll_interval=60` and `update_interval=3600`, the Info group fires at elapsed_seconds=0, 3600, 7200... but the poll only runs every 60s, so elapsed_seconds might be 3599 or 3601. **Fix:** Round `elapsed_seconds` to the nearest multiple of `poll_interval` before passing to `schedule_requests`. Or simply use a counter that increments by `poll_interval` each cycle (like HA does), but anchor the increment to wall-clock time. The simplest approach: use `cycle_count * poll_interval` as the runtime value, where `cycle_count` increments each successful tick. This preserves exact HA modulo semantics while being time-anchored (since each cycle takes approximately `poll_interval` seconds of wall-clock time).

**Recommended runtime computation:**
```python
# Each poll cycle increments by poll_interval
runtime = cycle_count * poll_interval  # 0, 60, 120, ..., 3600, ...
# Info group: 3600 % 3600 == 0 → fires at runtime=3600 (cycle 60 for poll_interval=60)
# Real-time group: 60 % 5 == 0 → fires every cycle (since poll_interval is always a multiple of default update_interval)
```

On failure, `cycle_count` still increments (because wall-clock time passed), ensuring the Info group doesn't drift.

### 2.3 The `_open_connection` Recursion Bug

In `pysolarman/__init__.py:213-225`:

```python
async def _open_connection(self) -> None:
    try:
        self._reader, self._writer = await asyncio.wait_for(...)
        self._keeper = create_task(self._keeper_loop())
        ...
    except Exception as e:
        if self._last_frame is None:
            raise ConnectionError("Cannot open connection") from e
        await self._open_connection()  # ← RECURSIVE CALL, no base case!
```

When `_last_frame is not None` (a request was in-flight) and every connection attempt fails, this recurses indefinitely → `RecursionError`.

**Fix (per D-13):** Replace recursion with a bounded retry loop:

```python
async def _open_connection(self) -> None:
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            self._reader, self._writer = await asyncio.wait_for(...)
            self._keeper = create_task(self._keeper_loop())
            if self._data_event.is_set():
                _LOGGER.debug(f"[{self.host}] Reconnected. Will retry last request")
                await self._write(self._last_frame)
            else:
                _LOGGER.debug(f"[{self.host}] Connected")
            return
        except Exception as e:
            if self._last_frame is None:
                raise ConnectionError("Cannot open connection") from e
            _LOGGER.debug(f"[{self.host}] Connection attempt {attempt + 1}/{max_attempts} failed")
    # All attempts exhausted — let caller handle the failure
    raise ConnectionError(f"Failed to connect after {max_attempts} attempts")
```

**Per D-14:** After reconnection, do NOT replay `_last_frame`. Remove the `if self._data_event.is_set(): await self._write(self._last_frame)` block. Wait for the next scheduled poll cycle.

### 2.4 The `_keeper_loop` Reconnect Chain

In `pysolarman/__init__.py:210`:
```python
self._keeper = create_task(self._open_connection())
```

When `_keeper_loop` detects a broken connection, it spawns `_open_connection` as a new task. This is fine in itself, but combined with the recursive bug creates cascading failures. With the recursion fixed (bounded retries), this becomes safe — if reconnect fails, the task completes, and `self.connected` returns `False`. The next `_send_receive_frame` call detects `not self.connected` and initiates a fresh connection attempt.

### 2.5 The `multiprocessing.Event` Issue

`pysolarman/__init__.py` uses `from multiprocessing import Event`. Per CONCERNS.md, this should be `asyncio.Event`. However, the usage pattern (`is_set()`, `set()`, `clear()`) is compatible with both. **Fix in this phase:** Replace with `asyncio.Event()` since we're in pure asyncio context. Note: `multiprocessing.Event` requires `Event()` constructor; `asyncio.Event` is the same.

### 2.6 Device Profile Sleep Detection (D-03, D-04)

User decisions require inverter-like devices to be treated as expected-to-sleep overnight, inferred from profile/parser metadata (not a new config field).

**Detection approach:** The `ParameterParser.info` dict contains `"manufacturer"` and `"model"` from the YAML profile's `info:` section. After `ParameterParser.init()`, check:
- If `info.get("manufacturer")` contains solar/inverter keywords → sleeper device
- More robust: check if profile has a "PV" group (solar-producing devices sleep at night)

**Simplest reliable heuristic:** Check if any group in the loaded profile has items with registers in the PV/DC voltage range. But this requires reaching into parser internals.

**Better approach:** Check `ParameterParser.info["filename"]` against known patterns (e.g., filenames containing "micro", "hybrid", "string", "inverter" → sleeper; "meter", "ddzy" → always-on). Or simply: if the profile has a group named "PV" or "Solar" → sleeper. This can be derived from the items list after `init()`.

**Recommended:** After `ParameterParser.init()`, scan `get_entity_descriptions()` for any item whose group contains "PV" or "Solar". If found → device is solar/sleeper type. If not → always-on type. Store as a boolean `is_solar_device` on the device worker.

---

## 3. Architecture: Standalone Polling Loop

### 3.1 Per-Device Worker Pattern

Each device gets an independent `asyncio.Task` running a poll loop:

```python
class DeviceWorker:
    """Manages polling for a single device."""
    
    def __init__(self, config: DeviceConfig, parser: ParameterParser, client: Solarman):
        self.config = config
        self.parser = parser
        self.client = client
        self.logger = get_device_logger(config.name)
        
        # Scheduling state
        self._cycle_count = 0
        self._poll_interval = config.poll_interval
        
        # Health state
        self._online = False
        self._consecutive_failures = 0
        self._backoff_interval = config.poll_interval
        
        # Device type (for logging policy)
        self._is_solar = False  # set after parser.init()
    
    async def run(self, data_callback):
        """Main poll loop — runs until cancelled."""
        while True:
            interval = self._backoff_interval if not self._online else self._poll_interval
            await asyncio.sleep(interval)
            await self._poll_cycle(data_callback)
    
    async def _poll_cycle(self, data_callback):
        runtime = self._cycle_count * self._poll_interval
        try:
            requests = self.parser.schedule_requests(runtime)
            if not requests:
                self._cycle_count += 1
                return
            
            result = await self._execute_requests(requests)
            parsed = self.parser.process(result)
            
            self._handle_success(parsed)
            await data_callback(self.config.name, parsed)
        except ValueError:
            self._handle_invalid_data()
        except (TimeoutError, ConnectionError, OSError) as e:
            self._handle_failure(e)
        finally:
            self._cycle_count += 1
```

### 3.2 Concurrency Model

```python
async def run_all(config: Config):
    workers = []
    for device_cfg in config.devices:
        worker = await create_device_worker(device_cfg)
        workers.append(worker)
    
    tasks = [asyncio.create_task(w.run(data_callback), name=f"poll-{w.config.name}") for w in workers]
    
    # Wait for cancellation (SIGINT/SIGTERM)
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
```

Each device's task is fully independent — one device timing out has zero effect on other devices' tasks.

### 3.3 Backoff Strategy (D-05, D-06)

Per-device exponential backoff capped at 5 minutes:

```python
BASE_BACKOFF = poll_interval  # Start at normal interval
MAX_BACKOFF = 300  # 5 minutes (D-06)
BACKOFF_FACTOR = 2  # Double each failure

def _compute_backoff(self):
    self._consecutive_failures += 1
    self._backoff_interval = min(
        self._poll_interval * (BACKOFF_FACTOR ** self._consecutive_failures),
        MAX_BACKOFF
    )
```

On recovery: reset `_consecutive_failures = 0` and `_backoff_interval = self._poll_interval`.

### 3.4 Transition-Based Logging (D-02, D-12, D-15)

Track state transitions to avoid log spam:

```python
class DeviceHealth:
    """Tracks online/offline and valid/invalid transitions."""
    
    def __init__(self, is_solar: bool):
        self._online: bool | None = None  # None = never connected
        self._valid_data: bool | None = None
        self._is_solar = is_solar
    
    def report_success(self, logger):
        if self._online is not True:
            logger.info("Device online — connection recovered" if self._online is False else "Device online")
            self._online = True
        if self._valid_data is not True:
            if self._valid_data is False:
                logger.info("Valid data resumed")
            self._valid_data = True
    
    def report_failure(self, logger, error):
        if self._online is not False:
            if self._is_solar:
                logger.info(f"Device offline: {error} (solar device — may be expected at night)")
            else:
                logger.warning(f"Device offline: {error}")
            self._online = False
        else:
            logger.debug(f"Device still offline: {error}")
    
    def report_invalid_data(self, logger, reason):
        if self._valid_data is not False:
            logger.warning(f"Invalid data received: {reason}")
            self._valid_data = False
        else:
            logger.debug(f"Invalid data persists: {reason}")
```

### 3.5 Anti-Overlap Protection (D-07, D-08)

Use a simple flag or `asyncio.Lock` per device:

```python
async def _poll_cycle(self, ...):
    if self._polling_in_progress:
        self.logger.debug("Poll overrun — skipping this cycle")
        return
    self._polling_in_progress = True
    try:
        # ... do poll ...
    finally:
        self._polling_in_progress = False
```

Since each device has its own task and the sleep is at the top of the loop, overruns naturally push the next cycle forward. But with `asyncio.sleep(interval)` at the start, if the poll takes longer than `interval`, the next sleep(interval) still waits the full interval — so there's a natural gap. The flag is a safety net.

**Better approach:** Use `asyncio.wait_for` with a timeout on the entire poll cycle, and schedule the next cycle relative to `time.monotonic()`:

```python
async def run(self, data_callback):
    next_poll = time.monotonic()
    while True:
        next_poll += self._current_interval
        now = time.monotonic()
        if next_poll > now:
            await asyncio.sleep(next_poll - now)
        else:
            self.logger.debug(f"Poll overrun by {now - next_poll:.1f}s — scheduling immediately")
            next_poll = now  # Reset anchor to now
        await self._poll_cycle(data_callback)
```

### 3.6 Validation Handling (D-10, D-11)

The existing `ParameterParser.process()` already handles this:
- `do_validate()` with `invalidate_all` raises `ValueError` → caught in `execute_bulk`/`device.get`
- Individual field validation failures return `None` for that field → only invalid fields dropped

**In the standalone worker:**
- Catch `ValueError` from `parser.process()` → report via `DeviceHealth.report_invalid_data()`, drop entire cycle (D-10)
- Valid fields with some invalid → already handled by parser (D-11)

---

## 4. Module Structure

```
solarman_logger/
├── poller.py          # NEW — DeviceWorker, DeviceHealth, run_all()
├── pysolarman/
│   └── __init__.py    # MODIFIED — fix _open_connection recursion, replace multiprocessing.Event
├── config.py          # EXISTING (no changes)
├── parser.py          # EXISTING (no changes)
├── common.py          # EXISTING (no changes)
├── const.py           # EXISTING (no changes)
├── logging_setup.py   # EXISTING (no changes)
└── tests/
    ├── test_poller.py        # NEW — unit tests for DeviceWorker, DeviceHealth
    └── test_pysolarman_fix.py  # NEW — regression test for recursion fix
```

**Key principle:** Only 2 files change/create in the `solarman_logger/` package:
1. `pysolarman/__init__.py` — bug fixes only (recursion, multiprocessing.Event, last-frame replay)
2. `poller.py` — new module containing all polling logic

---

## 5. Risk Analysis

### 5.1 Parser `schedule_requests` Mutation

`schedule_requests(runtime)` mutates `self._result = {}` at the start. This is safe in our single-task-per-device model because only one coroutine calls it per device. But it means the parser instance is NOT thread-safe and MUST NOT be shared between devices.

### 5.2 Connection Lifecycle

The `Solarman` client maintains persistent TCP connections with a keeper loop. The standalone worker must:
1. Create a `Solarman` instance per device (already planned via `DeviceConfig`)
2. Call `client.close()` on shutdown (for clean Docker stop)
3. Not interfere with the keeper loop's reconnection logic

### 5.3 Profile Initialization is Async

`ParameterParser.init()` uses `yaml_open()` which is async (aiofiles). This must be called during worker setup, before the poll loop starts.

### 5.4 `execute_bulk` Pattern

From `device.py:74-80`, the pattern is:
```python
for request in scheduled:
    responses[(code, address)] = await self.execute(code, address, count=count)
return self.profile.parser.process(responses)
```

The standalone worker must replicate this: iterate over scheduled requests, call `client.execute()` for each, collect responses, then call `parser.process(responses)`.

---

## 6. Testing Strategy

### 6.1 Unit Tests (no network, no real devices)

**DeviceHealth transitions:**
- Online → offline → online (warning, debug suppressed, info on recovery)
- Solar vs non-solar logging levels
- Invalid data transitions

**Backoff computation:**
- Exponential progression: poll_interval → 2x → 4x → ... → cap at 300s
- Reset on recovery

**Runtime/scheduling math:**
- cycle_count=0 → runtime=0 → all groups fire
- cycle_count=60, poll_interval=60 → runtime=3600 → Info group fires
- cycle_count=1, poll_interval=60 → runtime=60 → only real-time groups

### 6.2 Integration Tests (mocked client)

**Poll cycle with mock Solarman client:**
- Success path: client.execute returns register data → parser.process → callback called
- Failure path: client.execute raises TimeoutError → health transitions → backoff increases
- ValueError path: parser.process raises ValueError → health reports invalid data

### 6.3 Regression Test for Recursion Fix

- Mock `asyncio.open_connection` to always raise → verify no `RecursionError`
- Verify `ConnectionError` is raised after max attempts

---

## 7. Standard Stack Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Concurrency | `asyncio.create_task` per device | Standard asyncio, no threads needed — all I/O is already async via pysolarman |
| Backoff | Simple exponential × 2 | Per D-05/D-06; no library needed for such simple logic |
| Scheduling | Counter × poll_interval as runtime | Preserves HA's modulo-based `is_scheduled` semantics exactly |
| Logging | Existing `get_device_logger()` | Already built in Phase 1; transition-based wrapper is pure Python |
| Testing | pytest + pytest-asyncio | Already in project from Phase 1 |
| Sleep detection | Profile filename/group heuristic | Per D-04; no new config field |

---

## 8. Don't Hand-Roll

- **Don't build a generic task scheduler** — `asyncio.sleep` in a loop is sufficient
- **Don't add a retry library** — existing `@retry` decorator + simple backoff counter is enough
- **Don't create an abstract Device interface** — there's only one kind of device (Solarman protocol)
- **Don't add state persistence** — device state is ephemeral; InfluxDB is the persistence layer (Phase 3)

---

## 9. Common Pitfalls

1. **Forgetting `runtime=0` fires all groups** — first poll cycle must include Info group
2. **Parser instance sharing** — each device MUST have its own `ParameterParser` instance (stateful `_result`)
3. **`asyncio.CancelledError` propagation** — `run()` loop must let `CancelledError` propagate for clean shutdown
4. **`Solarman.close()` must be called** — the keeper loop task must be cancelled, or the event loop won't exit cleanly
5. **Profile path resolution** — already solved in Phase 1 (`DeviceConfig.profile_dir` + `DeviceConfig.profile_filename`)

---

## RESEARCH COMPLETE

**Key findings:**
- The HA counter-based scheduling model adapts cleanly to standalone by using `cycle_count * poll_interval` as runtime
- The `_open_connection` recursion fix is straightforward: bounded loop with max 3 attempts
- Per-device `asyncio.Task` provides complete error isolation with zero framework overhead
- Only 2 files need changes: fix pysolarman bugs + create new poller.py module
- All testing can be done with mocked clients (no real hardware needed)
