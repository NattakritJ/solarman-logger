# Phase 3: InfluxDB Pipeline - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Write parsed device readings to InfluxDB v2 — one Point per device per poll cycle containing all parsed fields, tagged with device name and type. All numeric values stored as float. Startup validates InfluxDB connectivity (fail-fast). Write failures are logged and dropped without crashing. A `main.py` entry point ties config loading, health check, and polling together.

Requirements: INFL-01, INFL-02, INFL-03, INFL-04, INFL-05

</domain>

<decisions>
## Implementation Decisions

### Measurement & Tagging
- **D-01:** Each device gets its own InfluxDB measurement, named after the device's `name` from config (e.g. measurement `smart-meter` for a device named `smart-meter`). One measurement = one device, per INFL-01.
- **D-02:** Device type comes from a new **required** `type` config field on each device entry (e.g. `type: meter`, `type: inverter`). Startup fails if missing. This satisfies INFL-02 and resolves the Phase 1 D-06 deferral.
- **D-03:** Each InfluxDB Point is tagged with `device_name` (from config `name`) and `device_type` (from config `type`).

### Startup Health Check
- **D-04:** At startup, after config validation succeeds, ping InfluxDB using the `influxdb-client` health/ping endpoint. If unreachable, log a clear error and **exit immediately** (fail-fast). No retry loop. User fixes InfluxDB, restarts the service. This matches the Phase 1 config validation pattern (CONF-04) and prevents silent data loss.
- **D-05:** The health check uses the lightweight ping endpoint — it does not require write permission and does not write test data.

### Field Mapping
- **D-06:** All parsed fields from the parser output are written to InfluxDB. No filtering, no exclusions. The Grafana user picks what to dashboard. Maximum flexibility.
- **D-07:** Field names are the slugified parser keys (e.g. `daily_production`, `pv1_voltage`, `voltage_sensor`). These are stable identifiers derived from YAML profile register names.
- **D-08:** All numeric values are cast to `float()` before writing, regardless of original type (int or float). String values stay as strings. This directly satisfies INFL-03 and prevents InfluxDB type conflicts when a field is `0` on first write then `0.5` later.

### Writer Lifecycle
- **D-09:** A single shared InfluxDB write client is created at startup and used by all devices. The writer implements the `DataCallback` signature (`Callable[[str, dict[str, tuple]], Awaitable[None]]`) and is passed to `run_all(config, data_callback)`.
- **D-10:** On InfluxDB write failure during operation, log a warning with device name and error, then continue. Data for that cycle is dropped — no buffering, no retry. Next cycle writes fresh. Directly satisfies INFL-05.
- **D-11:** The InfluxDB client is closed (flush + close) in the existing `run_all()` finally block, alongside the existing client cleanup. This ensures pending writes are flushed on shutdown.

### Entry Point
- **D-12:** Create a new `solarman_logger/main.py` module as the application entry point. It handles: argparse for config path, config loading, InfluxDB health check, writer initialization, and `run_all()` invocation. This is the target for Docker `CMD` in Phase 4.

### Pre-flight Validation
- **D-13:** Phase 3 plan should include a pre-flight task that runs the app locally against a real device to verify end-to-end connectivity (config → poll → data callback) before wiring InfluxDB writes. This was validated during context gathering — the smart meter returned 7 fields successfully.

### Agent's Discretion
- Exact `influxdb-client` API usage (sync vs async write client, batching config)
- Internal module structure for the writer (inline in main.py vs separate writer.py)
- Exact error message wording for InfluxDB health check failure
- Whether to add `influxdb-client[async]` or use the sync client in an executor

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project and Phase Scope
- `.planning/PROJECT.md` — Product intent, reliability goal, InfluxDB v2 constraint (token auth, org/bucket model)
- `.planning/REQUIREMENTS.md` — Phase 3 requirements INFL-01 through INFL-05, plus out-of-scope boundaries
- `.planning/ROADMAP.md` — Phase 3 goal and success criteria (measurement per device, float enforcement, startup check, error-tolerant writes)
- `.planning/STATE.md` — Existing decisions from Phases 1-2, current progress

### Prior Phase Context
- `.planning/phases/01-protocol-core/01-CONTEXT.md` — Config structure (InfluxConfig), parser initialization, slugify replacement, profile loading conventions
- `.planning/phases/02-device-polling-loop/02-CONTEXT.md` — DataCallback pattern, DeviceWorker/DeviceHealth, run_all() lifecycle, error isolation decisions

### Existing Standalone Code To Extend
- `solarman_logger/config.py` — `InfluxConfig` (url/org/bucket/token), `DeviceConfig`, `Config`, `load_config()`. Device `type` field needs to be added here.
- `solarman_logger/poller.py` — `DataCallback` type alias, `run_all(config, data_callback)`, `DeviceWorker`, shutdown cleanup in finally block. The InfluxDB writer plugs into `data_callback`.
- `solarman_logger/parser.py` — `ParameterParser` returns `dict[str, tuple[state, value]]` where numeric readings are in the `state` (first) element.
- `solarman_logger/logging_setup.py` — Existing stdout logging baseline for writer log messages.

### InfluxDB Client Library
- `influxdb-client` Python package (already in `requirements.txt`) — InfluxDB v2 write API, health check endpoint, Point construction

### Device Profiles (for understanding field output)
- `custom_components/solarman/inverter_definitions/deye_micro.yaml` — Deye SUN-M225G4 micro-inverter profile
- `custom_components/solarman/inverter_definitions/ddzy422-d2.yaml` — DDZY422-D2-W smart meter profile (validated during pre-flight: returns 7 fields)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `solarman_logger/poller.py:27` — `DataCallback = Callable[[str, dict[str, tuple]], Awaitable[None]]` type alias already defined; writer implements this signature
- `solarman_logger/poller.py:181` — `run_all(config, data_callback)` already accepts an optional callback; wire the InfluxDB writer here
- `solarman_logger/config.py:20` — `InfluxConfig` dataclass already holds url/org/bucket/token; no changes needed for connection config
- `requirements.txt:4` — `influxdb-client>=1.40` already listed as dependency

### Established Patterns
- Fail-fast config validation at startup (Phase 1) — InfluxDB health check follows the same pattern: validate early, exit on failure
- `DataCallback` as the integration seam between polling and output — clean separation, writer knows nothing about Solarman protocol
- Parser output tuple: `(state, value)` where `state` holds the numeric reading and `value` is `None` — the writer reads from element 0
- Transition-based logging (Phase 2) — write failure logging should follow the same pattern if repeated failures occur

### Integration Points
- `config.py:DeviceConfig` — needs new required `type: str` field added
- `config.py:load_config()` — needs validation for the new `type` field
- `poller.py:run_all()` finally block — add InfluxDB client close alongside existing client cleanup
- New `main.py` — becomes the application entry point, orchestrating config → health check → writer init → run_all()

</code_context>

<specifics>
## Specific Ideas

- Pre-flight test confirmed the smart meter at 10.20.30.60 returns 7 fields (voltage, current, power, frequency, power factor, total import/export energy) — all numeric, all suitable for InfluxDB float storage.
- Parser tuple shape: `(state, value)` where state=numeric reading, value=None. Confirmed by live test output showing e.g. `voltage_sensor: 236.9 (type=NoneType)` — the 236.9 is `state`, the NoneType is `value`.
- Poll interval must be >= the profile's `update_interval` or cycles will be skipped (empty request list). The ddzy422-d2 profile works with 10s+ intervals.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-influxdb-pipeline*
*Context gathered: 2026-03-30*
