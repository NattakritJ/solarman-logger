# Architecture Research: solarman-logger

**Researched:** 2026-03-29
**Confidence:** HIGH — based on direct codebase analysis + official Python asyncio docs + verified InfluxDB client docs + Docker Compose official reference

---

## Recommended Architecture

A single-process async Python service with one long-lived `asyncio` event loop. Each configured device runs as an independent polling loop (one `asyncio.Task` per device). All tasks share a single InfluxDB writer. The main coroutine starts all device tasks and waits; `SIGINT`/`SIGTERM` cancels them cleanly.

```
┌─────────────────────────────────────────────────────────────┐
│                      solarman-logger                         │
│                                                             │
│  main()                                                     │
│    └── asyncio.run(run())                                   │
│          ├── ConfigLoader.load("config.yaml")               │
│          ├── InfluxWriter(influx_cfg)                       │
│          └── for each device:                               │
│                asyncio.create_task(device_loop(device_cfg,  │
│                                                writer))      │
│                                                             │
│  device_loop(cfg, writer)          [one task per device]    │
│    └── loop forever:                                        │
│          ├── DevicePoller.poll()   ← pysolarman + parser    │
│          ├── InfluxWriter.write()                           │
│          └── asyncio.sleep(interval)                        │
└─────────────────────────────────────────────────────────────┘
```

**Key structural properties:**
- Each device loop is isolated — an exception in one task does not affect others
- `asyncio.create_task()` is used (not `TaskGroup`): `TaskGroup` cancels all siblings on any exception, which violates the error-isolation requirement
- Device tasks are kept in a set with `add_done_callback` to hold strong references (Python asyncio GC safety requirement)
- Graceful shutdown via `loop.add_signal_handler(SIGINT/SIGTERM, cancel_all_tasks)`

---

## Component Breakdown

### 1. `config.py` — ConfigLoader

**Responsibility:** Load and validate the YAML config file. Return typed dataclasses for devices and InfluxDB connection.

**Interface:**
```python
@dataclass
class DeviceConfig:
    name: str
    host: str
    port: int          # default 8899
    serial: int
    profile: str       # filename in inverter_definitions/
    poll_interval: int # seconds; falls back to global default

@dataclass
class InfluxConfig:
    url: str
    org: str
    bucket: str
    token: str
    timeout_ms: int    # default 10000

@dataclass
class AppConfig:
    devices: list[DeviceConfig]
    influx: InfluxConfig
    poll_interval: int  # global default, overridden per device

def load(path: str) -> AppConfig: ...
```

**Key decisions:**
- Parse-and-fail-fast at startup: if config is missing required fields, raise with a clear message and exit before any network connections are attempted
- `poll_interval` defaults to 60s globally; devices can override per-entry
- Profile path is relative to a configurable `profiles_dir` (defaults to `/app/inverter_definitions/`)
- No `voluptuous` dependency — use simple `dataclasses` + manual validation; removes HA dependency

**What NOT to copy from HA:** `ConfigEntry`, `OptionsFlowHandler`, all `CONF_*` HA constants — use plain dict keys from YAML instead.

---

### 2. `poller.py` — DevicePoller

**Responsibility:** Wrap the extracted `Device`+`ProfileProvider`+`Solarman` stack. Provide a single `poll() -> dict[str, tuple]` coroutine that returns parsed register values.

**Interface:**
```python
class DevicePoller:
    def __init__(self, cfg: DeviceConfig, profiles_dir: str): ...
    async def setup(self) -> None: ...        # connect + load profile
    async def poll(self, runtime: int) -> dict[str, tuple]: ...
    async def close(self) -> None: ...
```

**Key decisions:**
- Thin adapter over the existing `Device` class — mostly pass-through; the goal is to decouple `DeviceConfig` (our dataclass) from `ConfigurationProvider` (HA-coupled)
- `runtime` counter increments with each successful poll, matching ParameterParser's `schedule_requests(runtime)` schedule logic exactly
- On `TimeoutError`: log, increment error counter, re-raise to trigger retry sleep in `device_loop`
- On other exceptions: log + swallow (same as HA's `Device.get` behaviour); return `{}` so writer skips this cycle
- Persistent connection: `Solarman` maintains its own keeper loop — `DevicePoller` does not manage TCP reconnect, it's handled by `pysolarman` internally

**Direct reuse:** `Device.get()`, `Device.execute_bulk()`, `Device.setup()`, `Device.shutdown()` — all can be used nearly verbatim after stripping `EndPointProvider`'s UDP discovery calls (not needed on fixed-IP LAN).

---

### 3. `writer.py` — InfluxWriter

**Responsibility:** Receive a parsed data dict from a device, transform it into InfluxDB `Point` objects, and write them. One shared instance across all device tasks.

**Interface:**
```python
class InfluxWriter:
    def __init__(self, cfg: InfluxConfig): ...
    async def setup(self) -> None: ...   # verify connection / health check
    async def write(self, device: DeviceConfig, data: dict[str, tuple]) -> None: ...
    async def close(self) -> None: ...
```

**Data shape — input:**
```python
# From ParameterParser.process():
# { "battery_power_sensor": (value, raw_register_value), ... }
# tuple[0] = typed state (int, float, str, list)
# tuple[1] = raw value or None
```

**Data shape — InfluxDB Point:**
```python
Point(measurement=device.name)           # one measurement per device
    .tag("device_type", device.profile)  # e.g. "deye_micro"
    .tag("device_name", device.name)     # e.g. "inverter_east"
    .field(key, value)                   # one field per register key
    .time(datetime.utcnow())
```

**Key decisions:**
- Use `influxdb-client[async]` (`influxdb_client.client.influxdb_client_async.InfluxDBClientAsync`) — keeps everything on the same event loop; no thread pool needed
- Use `WriteApi` in synchronous mode per-write rather than batching mode: the service writes infrequently (one batch per device per 60s) so batching complexity adds no value; synchronous write simplifies error handling
- Skip `None` values and non-numeric types (lists, strings for lookup values) — only write `int` and `float` fields; string/enum fields can be added in Phase 2 if needed
- On `InfluxDB` write failure: log warning, do not crash — data loss for one cycle is acceptable per the "log and retry" requirement
- One `InfluxDBClientAsync` instance created at startup, shared across all device task writes (thread-safe for async use per official docs)

---

### 4. `device_loop()` — Per-Device Polling Coroutine

**Responsibility:** Infinite polling loop for one device. Manages its own `DevicePoller` lifetime, runtime counter, error back-off, and calls to `InfluxWriter`.

**Pseudocode:**
```python
async def device_loop(cfg: DeviceConfig, writer: InfluxWriter, profiles_dir: str):
    logger = getLogger(f"solarman.{cfg.name}")
    poller = DevicePoller(cfg, profiles_dir)
    runtime = 0
    backoff = cfg.poll_interval

    await poller.setup()        # raises on hard failure; caught by caller

    while True:
        start = asyncio.get_event_loop().time()
        try:
            data = await poller.poll(runtime)
            if data:
                await writer.write(cfg, data)
                runtime += 1
                backoff = cfg.poll_interval   # reset on success
        except asyncio.CancelledError:
            break                             # clean shutdown
        except TimeoutError:
            logger.warning(f"[{cfg.name}] Timeout — retry in {backoff}s")
            backoff = min(backoff * 2, MAX_BACKOFF)  # exponential, cap at e.g. 300s
        except Exception as e:
            logger.exception(f"[{cfg.name}] Unexpected error: {e}")
        elapsed = asyncio.get_event_loop().time() - start
        await asyncio.sleep(max(0, backoff - elapsed))

    await poller.close()
```

**Error isolation proof:** Each device task catches its own exceptions. `asyncio.CancelledError` propagates cleanly for shutdown. Other exceptions are logged and the loop continues after sleep. A device that is permanently broken will log every `backoff` seconds and never affect other device tasks.

**Key decisions:**
- `asyncio.CancelledError` must NOT be caught and swallowed — re-raise or `break`; it is the shutdown signal
- Exponential backoff on `TimeoutError`; reset to `poll_interval` on success — avoids hammering an unreachable device
- `runtime` counter only increments on successful poll, matching HA's `Coordinator.counter` semantics exactly

---

### 5. `main.py` — Entry Point

**Responsibility:** Parse CLI args, load config, set up logging, create tasks, handle signals, run event loop.

**Structure:**
```python
import asyncio, signal, logging
from .config import load
from .writer import InfluxWriter
from .device_loop import device_loop

async def run(config_path: str):
    cfg = load(config_path)
    setup_logging(cfg)

    writer = InfluxWriter(cfg.influx)
    await writer.setup()

    tasks: set[asyncio.Task] = set()
    for dev in cfg.devices:
        task = asyncio.create_task(
            device_loop(dev, writer, cfg.profiles_dir),
            name=f"device:{dev.name}"
        )
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set_result, None)

    await stop
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await writer.close()

if __name__ == "__main__":
    asyncio.run(run("/app/config.yaml"))
```

**Key decisions:**
- `tasks.discard` callback keeps a strong reference set — prevents GC mid-execution (official Python asyncio pattern)
- `asyncio.gather(*tasks, return_exceptions=True)` on shutdown — collects `CancelledError` without raising, ensures all tasks finish before process exits
- Config path defaults to `/app/config.yaml` (matches Docker mount target); overridable via `--config` arg

---

## Data Flow

```
YAML config
    │
    ▼
ConfigLoader.load()
    │
    ├──► InfluxWriter(influx_cfg).setup()
    │         │
    │         └── InfluxDBClientAsync(url, token, org)
    │
    └──► for each DeviceConfig:
              │
              ▼
         device_loop(cfg, writer)
              │
              ├── DevicePoller.setup()
              │       ├── ProfileProvider.init()  ← loads YAML profile
              │       └── Solarman(*endpoint)     ← TCP connect deferred
              │
              └── [every poll_interval seconds]:
                    │
                    ├── DevicePoller.poll(runtime)
                    │       ├── ParameterParser.schedule_requests(runtime)
                    │       ├── Device.execute_bulk(requests)
                    │       │       └── Solarman.execute(code, addr, count)
                    │       │               └── [Solarman V5 TCP frame → device]
                    │       └── ParameterParser.process(raw_responses)
                    │               └── returns dict[str, tuple[value, raw]]
                    │
                    └── InfluxWriter.write(cfg, data)
                            ├── build Point per field
                            └── InfluxDBClientAsync.write_api().write(...)
```

**What crosses component boundaries:**
- `ConfigLoader → device_loop`: `DeviceConfig` dataclass (plain data, no HA types)
- `ConfigLoader → InfluxWriter`: `InfluxConfig` dataclass
- `DevicePoller → device_loop`: `dict[str, tuple[value, raw]]` — same shape as HA's `coordinator.data`
- `device_loop → InfluxWriter`: `(DeviceConfig, dict[str, tuple])` — device identity + parsed values

---

## Docker Structure

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy vendored protocol code
COPY custom_components/solarman/pysolarman/ ./pysolarman/
COPY custom_components/solarman/inverter_definitions/ ./inverter_definitions/

# Copy logger source
COPY logger/ ./logger/

# Install dependencies
RUN pip install --no-cache-dir \
    aiofiles \
    aiohttp \
    pyyaml \
    influxdb-client[async]

# Config is mounted at runtime — do not COPY it
# ENTRYPOINT: exec form for clean signal propagation
ENTRYPOINT ["python", "-m", "logger.main"]
CMD ["--config", "/app/config.yaml"]
```

**Signal propagation:** `ENTRYPOINT` exec form (list syntax) means Python is PID 1 in the container. `SIGTERM` from `docker stop` reaches the Python process directly. The `signal.SIGTERM` handler in `main.py` triggers the clean-shutdown path. **Do NOT use shell form** (`ENTRYPOINT "python ..."`) — it spawns a shell as PID 1 which swallows signals and prevents clean shutdown.

**`init: true` in docker-compose:** Adds `tini` as PID 1, which properly reaps zombie processes and forwards signals — recommended for robustness even with exec-form entrypoint.

### docker-compose.yml

```yaml
version: "3.9"

services:
  solarman-logger:
    build: .
    container_name: solarman-logger
    restart: unless-stopped
    init: true                         # tini PID 1 — signal forwarding + zombie reaping
    volumes:
      - type: bind
        source: ./config.yaml          # host path — edit without rebuild
        target: /app/config.yaml
        read_only: true
    environment:
      - TZ=Asia/Bangkok                # match local timezone for log timestamps
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    # No ports needed — outbound TCP only (to devices + InfluxDB)
    # No depends_on for influxdb — assumed to be already running externally

networks:
  default:
    name: solarman-net
```

**Config mounting rationale:**
- Bind mount (not volume) — user edits `config.yaml` on the host with a text editor; changes take effect on container restart (`restart: unless-stopped` handles this)
- `read_only: true` — logger never writes back to config; prevents accidental mutation
- Long syntax (`type: bind`) preferred over short syntax (`./config.yaml:/app/config.yaml`) — explicit, self-documenting, and required if `read_only` is desired per Docker Compose spec
- No `env_file` for InfluxDB credentials — keep all config in the YAML file for simplicity; secrets section can be added in a later phase if needed

**What NOT to include in docker-compose:**
- An InfluxDB service — user already has one running externally; adding it couples the compose file to InfluxDB lifecycle management
- Grafana service — explicitly out of scope
- Health checks for InfluxDB — the writer's startup health check (`await writer.setup()`) handles this; if InfluxDB is unreachable at start, the service logs and keeps retrying on each write

---

## Extraction Strategy (from ha-solarman)

### Copy verbatim (zero changes needed)

| Source file | Destination | Notes |
|-------------|-------------|-------|
| `custom_components/solarman/pysolarman/__init__.py` | `logger/pysolarman/__init__.py` | The `Solarman` TCP client; no HA imports |
| `custom_components/solarman/pysolarman/umodbus/` | `logger/pysolarman/umodbus/` | Full vendored library; no HA imports |
| `custom_components/solarman/inverter_definitions/*.yaml` | `logger/inverter_definitions/` | Data files; no changes needed |

**Confidence:** HIGH — both `pysolarman/__init__.py` and `umodbus/` have zero HA imports (confirmed via STRUCTURE.md import dependency graph: `umodbus → pysolarman → common` for only `retry`/`throttle`/`create_task`/`format` helpers).

### Adapt with targeted changes

| Source file | What to copy | What to drop / replace |
|-------------|-------------|------------------------|
| `common.py` | `retry()`, `throttle()`, `yaml_open()`, `create_task()`, `ensure_list_safe_len()`, `group_when()`, `preprocess_descriptions()`, `postprocess_descriptions()`, `slugify()`, `get_request_code()`, `create_request()`, `enforce_parameters()`, `all_same()`, `unwrap()` | Drop: `build_device_info()`, `voluptuous` imports, `homeassistant.*` imports, `request()` (HTTP logger config) |
| `parser.py` | `ParameterParser` class in full — `init()`, `schedule_requests()`, `process()`, all `try_parse_*` methods | Drop: `get_entity_descriptions()` — this returns HA entity descriptions; not needed. Replace `const.*` and `common.*` imports with local versions |
| `device.py` | `Device` class — `setup()`, `get()`, `execute()`, `execute_bulk()`, `shutdown()`, `DeviceState` | Drop: `ProfileProvider` (simplify — inline profile loading), `EndPointProvider` (replace UDP discovery with direct config), all `provider.py` imports |
| `const.py` | All `REQUEST_*`, `DEFAULT_*`, `PARAM_*`, `REGISTERS_*`, `DIGITS`, `UPDATE_INTERVAL`, `IS_SINGLE_CODE` constants | Drop: all HA-specific constants (`CONF_*`, `DOMAIN`, `PLATFORMS`, `AUTODETECTION_*`, `PROFILE_REDIRECT`, `LOGGER_AUTH`, service names) |

### Drop entirely (HA-specific, no equivalent needed)

| File | Why dropped |
|------|-------------|
| `__init__.py` | HA integration lifecycle — replaced by `main.py` |
| `config_flow.py` | HA UI config — replaced by YAML config file |
| `coordinator.py` | HA `DataUpdateCoordinator` — replaced by `device_loop()` |
| `provider.py` | `ConfigurationProvider` wraps `ConfigEntry` (HA-only); `EndPointProvider` UDP discovery not needed (fixed IPs); `ProfileProvider` logic inlined into `DevicePoller.setup()` |
| `entity.py` + all `{platform}.py` | HA entity model — replaced by `InfluxWriter` |
| `discovery.py` | UDP discovery — not needed for fixed-IP devices |
| `services.py` | HA service registration — not applicable |
| `translations/` | UI localization — not applicable |

### Critical adaptation: removing the HA `slugify` dependency

`common.py` imports `from homeassistant.util import slugify`. This is used throughout `parser.py` and `common.py` for entity key generation. The logger still needs consistent key names (for InfluxDB field names), but does not need HA's specific slugify implementation.

**Fix:** Replace with Python's built-in:
```python
import re
def slugify(*parts: str) -> str:
    return "_".join(re.sub(r"[^a-z0-9]", "_", p.lower()).strip("_") for p in parts if p)
```
This produces the same output for all ASCII inputs. Test against `parser.py`'s generated keys before Phase 1 completion.

### Critical adaptation: removing the `aiofiles` dependency

`common.py`'s `yaml_open()` uses `aiofiles`. This is a dependency declared in `manifest.json`. For the standalone service, `aiofiles` is a legitimate dependency (it's a standard async file I/O library) — **keep it** and add to `requirements.txt`.

### The `EndPointProvider` simplification

`EndPointProvider` in `provider.py` handles:
1. Host/IP resolution (from config or UDP discovery)  ← replace with `cfg.host` directly
2. Serial number extraction  ← take from `cfg.serial`
3. UDP LAN discovery and auto-reconfiguration  ← **drop entirely**

`Solarman(*endpoint.connection)` takes `(host, port, serial, transport)`. In `DevicePoller.setup()`:
```python
self._solarman = Solarman(cfg.host, cfg.port, cfg.serial, "tcp")
```
No discovery needed — fixed IPs from config.

---

## Build Order Implications

The dependency graph of components drives the phase order:

```
Phase 1: Protocol core
  pysolarman (copy) + umodbus (copy)
  const.py (adapter — strip HA constants)
  common.py (adapter — strip HA imports, replace slugify)
  parser.py (adapter — drop get_entity_descriptions)
  → Deliverable: can load a YAML profile and decode raw register bytes

Phase 2: Device polling
  device.py (adapter — simplify providers, strip EndPointProvider UDP)
  DevicePoller wrapper
  → Deliverable: can poll a real device and get back a parsed dict

Phase 3: Config + main loop
  config.py (new — YAML config loader)
  device_loop() coroutine (new — per-device async loop with error isolation)
  main.py entry point (new — asyncio.run + signal handling)
  → Deliverable: polls all configured devices, logs results to stdout

Phase 4: InfluxDB writer
  writer.py (new — InfluxDBClientAsync + Point construction)
  → Deliverable: full end-to-end pipeline writing to InfluxDB

Phase 5: Docker packaging
  Dockerfile + docker-compose.yml
  → Deliverable: `docker compose up` runs the complete service
```

**Why this order:**
- Protocol correctness must be validated before InfluxDB concerns are introduced — a broken parser means bad data silently in the DB
- Config loading is trivial but needs the protocol layer to validate device profiles at load time
- InfluxDB writer is isolated from polling logic — can be developed and tested independently (mock the input `dict`)
- Docker is last: packaging concerns should not influence architecture decisions made in earlier phases

**Cross-phase risk:** The `slugify` replacement must produce identical output to `homeassistant.util.slugify` for all register keys in the Deye and DDZY profiles. This should be verified in Phase 1 with a unit test that compares outputs. If there is a mismatch, InfluxDB field names will be inconsistent with what Phase 4 writes — correcting this after Phase 4 requires a data migration.

---

## Sources

- Python asyncio official docs — `asyncio.create_task`, `asyncio.TaskGroup`, `asyncio.gather`, signal handling: https://docs.python.org/3/library/asyncio-task.html (HIGH confidence — official, current)
- InfluxDB Python client README — `InfluxDBClientAsync`, `WriteOptions`, `Point` API: https://github.com/influxdata/influxdb-client-python (HIGH confidence — official, current)
- Docker Compose official spec — `volumes.bind`, `read_only`, `init`, `restart`: https://docs.docker.com/reference/compose-file/services/ (HIGH confidence — official, current)
- Direct codebase analysis — `coordinator.py`, `device.py`, `parser.py`, `common.py`, `pysolarman/__init__.py` (HIGH confidence — primary source)
- `ARCHITECTURE.md` + `STRUCTURE.md` codebase analysis documents (HIGH confidence — first-party)
