# Phase 3: InfluxDB Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 03-influxdb-pipeline
**Areas discussed:** Measurement & tagging, Startup health check, Field mapping, Writer lifecycle, Pre-flight test run

---

## Measurement & Tagging

### Measurement name

| Option | Description | Selected |
|--------|-------------|----------|
| Device name as measurement | Each device gets its own measurement (e.g. 'inverter_1', 'meter_1'). Simple Grafana queries per device. | ✓ |
| Single shared measurement | All devices write to a single measurement (e.g. 'solarman'). Filter by device_name tag in Grafana. | |
| Device type as measurement | Use device type as measurement (e.g. 'inverter', 'meter'). Same-type devices share a measurement. | |

**User's choice:** Device name as measurement
**Notes:** Maps naturally to 1 device = 1 measurement per INFL-01.

### Device type source

| Option | Description | Selected |
|--------|-------------|----------|
| New config field | Add a 'type' field to each device in config.yaml. Explicit, user controls it. | ✓ |
| Infer from profile | Derive from profile filename/metadata like _detect_solar() does now. | |

**User's choice:** New config field
**Notes:** Aligns with Phase 1 D-06 deferral. Simple and unambiguous.

### Type field requirement

| Option | Description | Selected |
|--------|-------------|----------|
| Required field | User must specify type for every device. Startup fails if missing. | ✓ |
| Optional with default | Defaults to 'unknown' if omitted. | |

**User's choice:** Required field
**Notes:** Consistent with InfluxDB requirement INFL-02 — every point must be tagged.

---

## Startup Health Check

### Behavior on unreachable InfluxDB

| Option | Description | Selected |
|--------|-------------|----------|
| Fail fast and exit | Ping InfluxDB at startup; if unreachable, log error and exit immediately. | ✓ |
| Warn and continue | Log a warning but start polling anyway. Retry writes each cycle. | |
| Retry then exit | Retry startup health check N times with backoff before giving up. | |

**User's choice:** Fail fast and exit
**Notes:** Matches Phase 1 config validation pattern. Prevents silent data loss.

### Validation method

| Option | Description | Selected |
|--------|-------------|----------|
| Health/ping endpoint | Use the influxdb-client health endpoint. Quick, doesn't require write permission. | ✓ |
| Test write | Attempt a dummy write to verify full write path works. | |

**User's choice:** Health/ping endpoint
**Notes:** Lightweight and standard.

---

## Field Mapping

### Which fields to write

| Option | Description | Selected |
|--------|-------------|----------|
| All parsed fields | Every key from parser output becomes an InfluxDB field. No data loss. | ✓ |
| Numeric only | Only write numeric fields. Skip strings like serial numbers. | |
| Configurable filter | Allow config-level include/exclude list. | |

**User's choice:** All parsed fields
**Notes:** Maximum flexibility — Grafana user picks what to dashboard.

### Field naming

| Option | Description | Selected |
|--------|-------------|----------|
| Slugified parser keys | Use slugified keys (e.g. 'daily_production', 'pv1_voltage'). Stable identifiers. | ✓ |
| Profile display names | Use human-readable names (e.g. 'Daily Production'). Prettier but requires quoting. | |

**User's choice:** Slugified parser keys
**Notes:** Stable, readable, matches profile definitions.

### Float enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| Cast all numerics to float | Cast every numeric value to float before writing. Strings stay as strings. | ✓ |
| Preserve original types | Write ints as int and floats as float. Risks type conflicts. | |

**User's choice:** Cast all numerics to float
**Notes:** Directly satisfies INFL-03.

---

## Writer Lifecycle

### Writer architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Single shared writer | One shared InfluxDB client for all devices. Simpler, fewer connections. | ✓ |
| Per-device writer | Each DeviceWorker gets its own InfluxDB write client. | |

**User's choice:** Single shared writer
**Notes:** Matches single-bucket config. Less overhead.

### Write failure handling

| Option | Description | Selected |
|--------|-------------|----------|
| Log and drop | Log warning, continue. Data for that cycle is lost. Next cycle writes fresh. | ✓ |
| Retry once then drop | Log warning, retry once before dropping. | |

**User's choice:** Log and drop
**Notes:** Directly matches INFL-05. Simple, no buffering complexity.

### Entry point

| Option | Description | Selected |
|--------|-------------|----------|
| New main.py module | Create main.py with argparse, startup validation, then run_all(). | ✓ |
| __main__.py module | Add __main__.py so package runs with 'python -m solarman_logger'. | |

**User's choice:** New main.py module
**Notes:** Clean separation, needed for Phase 4 Docker CMD.

### Shutdown cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Close in run_all finally | Close InfluxDB client in existing shutdown path. | ✓ |
| Signal handler in main | Register SIGTERM/SIGINT handler in main.py. | |

**User's choice:** Close in run_all finally
**Notes:** Integrates naturally with existing cleanup.

---

## Pre-flight Test Run

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-flight task in Phase 3 | Add a task in Phase 3 plan that runs app locally before wiring InfluxDB. | ✓ |
| Do it now | Run manually before creating CONTEXT.md. | (also done) |
| Skip | Trust Phase 2 tests. | |

**User's choice:** Pre-flight task in Phase 3 (Recommended) — also ran manually during session
**Notes:** Manual test confirmed smart meter at 10.20.30.60 returns 7 fields. Parser tuple shape confirmed: (state=numeric, value=None). Poll interval must be >= profile update_interval or cycles skip.

---

## Agent's Discretion

- Exact influxdb-client API usage (sync vs async, batching config)
- Internal module structure for the writer
- Exact error message wording for health check failure
- Whether to use influxdb-client[async] or sync client in executor

## Deferred Ideas

None — discussion stayed within phase scope.
