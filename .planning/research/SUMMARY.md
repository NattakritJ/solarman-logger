# Research Summary: solarman-logger

**Synthesized:** 2026-03-29
**Source files:** STACK.md · FEATURES.md · ARCHITECTURE.md · PITFALLS.md
**Overall confidence:** HIGH — all four research files based on direct codebase audit + verified official docs

---

## TL;DR

- **This is a code-extraction project, not a greenfield build.** The ha-solarman HA integration already contains all the hard parts (Solarman V5 TCP client, Modbus parser, 30+ device profiles). The work is stripping HA coupling and wiring the core to InfluxDB, not writing protocol logic from scratch.
- **The pysolarman vendored copy has three critical bugs** that must be fixed during extraction: recursive `_open_connection` (crashes under network failure), `multiprocessing.Event` used as asyncio primitive (race conditions at scale), and `asyncio.wait_for` cancellation leak (FD exhaustion). These are rewrite-risk items, not optional polish.
- **InfluxDB field type conflict will silently corrupt your entire measurement** if any numeric field is ever written as `int` before being written as `float`. Cast everything to `float()` before building Points — no exceptions.
- **Default poll interval must be ≥ 60 seconds.** The Solarman Wi-Fi stick supports only one simultaneous TCP connection and can be physically locked up by overlapping poll cycles. This is a hardware constraint, not a config preference.
- **The `slugify` replacement must be validated before anything writes to InfluxDB.** If the standalone `slugify()` produces different output than `homeassistant.util.slugify` for any register key in the Deye/DDZY profiles, InfluxDB field names will be permanently inconsistent. Test this in Phase 1.

---

## Recommended Stack

| Component | Choice | Version | Note |
|-----------|--------|---------|------|
| Language | Python | 3.12 | Required: fixes `asyncio.wait_for` cancellation (C8); pydantic v2 + union syntax needs ≥3.10 |
| Protocol client | vendored `pysolarman` (adapted) | repo-local | Do NOT swap to PyPI `pysolarmanv5`; three bugs to fix during adaptation |
| InfluxDB write | `influxdb-client[async]` | 1.50.0 | Async client only — sync `WriteApi` blocks the event loop (M2) |
| Config parsing | `PyYAML` | 6.0.3 | `yaml.safe_load()` only; pair with pydantic for validation |
| Config validation | `pydantic` v2 | ≥2.0 | Fail-fast at startup; no pydantic-settings needed |
| Structured logging | `structlog` | 25.5.0 | Per-device context binding survives `await` via `contextvars` |
| Async runtime | `asyncio` (stdlib) | built-in | One task per device; no third-party framework |
| File I/O | `aiofiles` | 25.1.0 | Non-blocking YAML profile loading; already used in HA codebase |
| Packaging | `uv` + `pyproject.toml` | 0.11.2 | Fastest resolver; reproducible `uv.lock` |
| Container base | `python:3.12-slim` | 3.12.x | Not alpine (musl breaks `aiohttp`/`pydantic` wheels); not 3.13 (wheel gaps) |

**What NOT to use:** `influxdb` (v1 client), `pysolarmanv5` (PyPI), `python:3.12-alpine`, `aioinflux` (unmaintained), `loguru` (no async contextvars), sync `WriteApi` with batching.

---

## Table Stakes Features

These must be in v1 — the tool is broken or unusable without them:

| Feature | Notes |
|---------|-------|
| YAML config: N devices (host, port, serial, name, profile) | Every real deployment has >1 device |
| InfluxDB v2 config: URL, org, bucket, token | All four fields required by v2 API |
| One InfluxDB measurement per device, all register fields | Foundation for Grafana dashboards |
| Tags: `device_name` + `device_type` | Without tags, multi-device data is unqueryable |
| Configurable poll interval (global default + per-device override) | Deye micro = 5s; smart meter may differ |
| Graceful error handling: log-and-continue per device | Network blips must not crash the service |
| Continuous polling loop (runs forever) | This is a logger, not a one-shot script |
| TCP retry on transient failure | Solarman sticks drop connections on 6-min cloud sync |
| Structured logging with timestamps + device name | Unactionable without context in multi-device setup |
| Docker + docker-compose.yml | Stated hard deployment requirement |

**Defer to v2:** per-group update intervals (honoring profile's `update_interval` per group), register `invalidate_all` validation, configurable InfluxDB measurement name.

**Never build:** register write-back, MQTT output, auto-discovery, web UI, alert/notification system, historical backfill, Grafana dashboard provisioning.

---

## Architecture in Brief

- **Single-process async Python service.** One `asyncio` event loop; one `asyncio.Task` per configured device; one shared `InfluxDBClientAsync` instance.
- **Five components:** `config.py` (load/validate YAML → typed dataclasses), `poller.py` (thin adapter over extracted `Device`+`ParameterParser`), `writer.py` (build `Point` objects + write to InfluxDB), `device_loop()` (infinite per-device coroutine with error isolation + exponential backoff), `main.py` (entry point: config → writer → tasks → signal handling).
- **Use `asyncio.create_task()`, NOT `TaskGroup`.** `TaskGroup` cancels all siblings on any exception — violates the error-isolation requirement. Each device task catches its own exceptions and keeps running.
- **Keep strong task references.** `tasks.add(task); task.add_done_callback(tasks.discard)` — prevents GC mid-execution (official Python asyncio requirement).
- **Graceful shutdown:** `SIGINT`/`SIGTERM` handlers cancel tasks, `asyncio.gather(*tasks, return_exceptions=True)` collects `CancelledError`, then `writer.close()` is called before process exits.
- **InfluxDB Point schema:** `measurement=device.name`, `tag(device_type, profile)`, `tag(device_name, name)`, one `field()` per register key. Always `float()` cast numeric values before writing.
- **Docker:** exec-form `ENTRYPOINT` (not shell form) for clean `SIGTERM` propagation; `init: true` (`tini` as PID 1); `network_mode: host` on Linux to reach LAN inverters; config.yaml bind-mounted read-only.
- **Extraction strategy:** copy `pysolarman/` + `umodbus/` + `inverter_definitions/` verbatim; adapt `common.py`, `parser.py`, `device.py`, `const.py`; drop all HA-specific files (`__init__.py`, `config_flow.py`, `coordinator.py`, `entity.py`, `provider.py`, all platform files).
- **`slugify` replacement:** swap `homeassistant.util.slugify` with a stdlib `re`-based equivalent; validate output against all existing profile keys before Phase 1 completes.
- **`propcache.cached_property`** must be replaced with `functools.cached_property` (stdlib since 3.8) — `propcache` is not in `manifest.json` and will cause `ImportError`.

---

## Watch Out For

| # | Pitfall | One-Line Prevention |
|---|---------|---------------------|
| 1 | **Recursive `_open_connection` → `RecursionError`** under sustained network failure; task silently dies | Replace recursive call with `asyncio.create_task(self._open_connection())` + retry counter + backoff cap |
| 2 | **InfluxDB field type conflict** (int `0` written before float `0.5`) silently drops all subsequent writes | Always `float(value)` before building any `Point` field |
| 3 | **Polling too fast locks Solarman Wi-Fi stick** hardware (one TCP connection limit) | Default poll interval ≥ 60s; log WARNING if poll duration approaches interval |
| 4 | **Serial number out of range** (< 2147483648) → silent all-zero frames → zero data, no errors | Pydantic config: `serial` field with `ge=2147483648` constraint + startup WARNING |
| 5 | **`asyncio.Task` exception silencing** — task crashes with no visible error, device stops logging | `task.add_done_callback(lambda t: logger.error(...) if t.exception() else None)` on every device task |

**Honourable mentions:** `multiprocessing.Event` → `asyncio.Event` (C3), line protocol escaping via `Point` API not raw strings (C6), Docker bridge network can't reach LAN devices → `network_mode: host` (M1).

---

## Build Order

Based on the component dependency graph from ARCHITECTURE.md + pitfall phase mapping from PITFALLS.md:

```
Phase 1 — Protocol Core (extraction + adaptation)
  ├── Copy: pysolarman/__init__.py, umodbus/, inverter_definitions/
  ├── Adapt: common.py (strip HA imports, replace slugify + propcache)
  ├── Adapt: const.py (strip CONF_* / HA constants)
  ├── Adapt: parser.py (drop get_entity_descriptions)
  ├── New: config.py (YAML load → pydantic AppConfig; serial range validation)
  └── Deliverable: load any YAML profile + decode raw register bytes; serial validation passes
  └── Pitfalls addressed: C1 (serial range), M3 (None fields), m2 (safe_load), m4 (propcache), C7 (int16/uint16)

Phase 2 — Device Polling
  ├── Fix: recursive _open_connection → task-based retry (C2)
  ├── Fix: multiprocessing.Event → asyncio.Event (C3)
  ├── Fix: wait_for cancellation / FD leak (C8)
  ├── Fix: ValueError swallow in parser (M4)
  ├── Adapt: device.py (simplify EndPointProvider → direct cfg.host/port/serial)
  ├── New: DevicePoller wrapper (setup/poll/close)
  ├── New: device_loop() coroutine (error isolation, exponential backoff, runtime counter)
  └── Deliverable: polls a real device, returns parsed dict, logs to stdout
  └── Pitfalls addressed: C2, C3, C4 (poll rate/throttle), C8, M4, M5 (shutdown close), M7 (task exception)

Phase 3 — InfluxDB Writer
  ├── New: writer.py (InfluxDBClientAsync, Point construction, startup health check)
  ├── Enforce: float() cast on all numeric fields (C5)
  ├── Enforce: Point API only — no raw line protocol strings (C6)
  ├── Enforce: WritePrecision.SECONDS globally (m1)
  └── Deliverable: full end-to-end pipeline; data flowing into InfluxDB
  └── Pitfalls addressed: C5, C6, M2 (async client), m1 (precision)

Phase 4 — Main Entry Point + Config Polish
  ├── New: main.py (asyncio.run, signal handlers, task supervision, writer.close)
  ├── Validate: slugify() output matches HA slugify for all profile keys
  ├── Test: multi-device config, per-device poll interval override
  └── Deliverable: production-ready service polling all configured devices

Phase 5 — Docker Packaging
  ├── Dockerfile (python:3.12-slim, uv install, exec-form ENTRYPOINT)
  ├── docker-compose.yml (network_mode: host, init: true, bind-mount config, log rotation)
  ├── Test: docker stop → clean exit (M5 shutdown), container reaches inverter IPs (M1)
  └── Deliverable: `docker compose up` runs the complete service
  └── Pitfalls addressed: M1 (Docker bridge networking), m3 (container timezone), M5 (shutdown)
```

**Why this order:**
- Protocol correctness must be proven before InfluxDB ever sees data — a broken parser writes silent garbage permanently
- Config loading is a prerequisite for device polling (needs `DeviceConfig` typed data)
- InfluxDB writer is independently testable with mocked input dicts — no need to block it on protocol work
- Docker is last — packaging decisions should not constrain architectural choices

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Stack choices | HIGH | All packages verified against PyPI + official docs; versions confirmed 2026-03-29 |
| Features / MVP scope | HIGH | Cross-validated against 6 real ecosystem projects + direct profile inspection |
| Architecture patterns | HIGH | Direct codebase analysis + official asyncio/InfluxDB/Docker Compose docs |
| Pitfall identification | HIGH | Direct audit of `pysolarman/__init__.py`, `parser.py`, `CONCERNS.md`; InfluxDB line protocol spec |
| Slugify equivalence | MEDIUM | Replacement proposed; correctness for all profile keys must be validated in Phase 1 |
| Per-group update interval semantics | MEDIUM | Documented in YAML profiles; exact HA coordinator scheduling behavior needs Phase 1 code read |
| Smart meter (DDZY422-D2) register correctness | MEDIUM | Profile exists in repo; int16/uint16 signedness for each field needs cross-reference with device manual |

**Gaps to address during planning:**
1. Read `parser.py` fully before writing the extraction plan — HA coupling surface may be larger than the research summary suggests
2. Confirm `deye_micro.yaml`'s group-level `update_interval` semantics match HA coordinator's scheduling logic before designing the Phase 2 scheduler
3. Validate slugify replacement against all register keys before any InfluxDB writes are attempted

---

## Sources (aggregated)

- vendored `pysolarman/__init__.py` — direct audit (ground truth for C1–C3, C8)
- `parser.py`, `device.py`, `common.py`, `const.py`, `coordinator.py` — direct audit
- `CONCERNS.md`, `STRUCTURE.md` — first-party codebase docs
- PyPI: `influxdb-client` 1.50.0, `pysolarmanv5` 3.0.6, `structlog` 25.5.0, `PyYAML` 6.0.3, `aiofiles` 25.1.0, `uv` 0.11.2
- influxdata/influxdb-client-python — async API source + README
- pysolarmanv5 changelog — readthedocs.io
- InfluxDB v2 line protocol spec + write optimization docs
- Python asyncio official docs — task, signal handling, wait_for cancellation
- Docker Compose official spec — volumes.bind, init, restart, network_mode
- Docker Hub `python` tags — 3.12.x confirmed current
- Ecosystem projects: schwatter/solarman_mqtt, solis2mqtt, StephanJoubert/home_assistant_solarman, davidrapan/ha-solarman, deye-controller
