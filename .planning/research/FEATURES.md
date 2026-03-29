# Features Research: solarman-logger

**Domain:** Solarman/Modbus-to-InfluxDB data logger (standalone Python service)
**Researched:** 2026-03-29
**Sources:**
- pysolarmanv5 (jmccrohan) — the canonical Python Solarman V5 protocol library, 166★
- StephanJoubert/home_assistant_solarman — original HA integration, 703★, config patterns
- davidrapan/ha-solarman — active fork of reference codebase, 430★, 97 releases
- schwatter/solarman_mqtt — real multi-inverter MQTT logger
- solis2mqtt (AndyTaylorTweet) — Solarman→MQTT with timing/recovery notes
- deye-controller (githubDante) — register write library
- influxdb-client-python (influxdata) — official InfluxDB v2 Python client
- Repo's own inverter_definitions/*.yaml — 30+ device profiles examined directly

---

## Table Stakes

Features users expect. Absence is a dealbreaker — the tool is broken or unusable without them.

| Feature | Why Expected | Complexity | Evidence |
|---------|-------------|------------|----------|
| **YAML config: N devices** | Every real project has more than one device; hardcoding is unacceptable | Low | schwatter/solarman_mqtt hardcodes 3 IPs/serials in a list — users immediately need to edit source. StephanJoubert uses YAML config. |
| **Per-device: host, port, serial, name, profile** | Minimum identity for a Solarman logger stick | Low | Universal across all ecosystem tools: `inverter_host`, `inverter_port`, `inverter_serial`, `lookup_file` (StephanJoubert); IP list + serial list (schwatter) |
| **InfluxDB v2 write: URL, org, bucket, token** | InfluxDB v2 API is token-auth only; all four fields required | Low | Official influxdb-client-python: `InfluxDBClient(url=..., token=..., org=...)` + `write_api.write(bucket=...)` |
| **One InfluxDB measurement per device** | Grafana dashboards filter by measurement; mixing devices in one measurement breaks queries | Low | Project decision; consistent with time-series best practices |
| **Tags: device name + device type** | Without tags, data from multiple devices is unqueryable | Low | influxdb-client `Point.tag()`; used universally in IoT logging patterns |
| **Fields: all register values from YAML profile** | The entire value of a profile-driven system is writing all parsed values | Medium | `deye_micro.yaml` has ~60 named fields across PV, Grid, Info groups; parser produces them all |
| **Configurable poll interval (global default + per-device override)** | Deye micro inverters report every 5s; smart meters may need different cadence | Low | `deye_micro.yaml` line 14: `update_interval: 5`; HA solarman's `scan_interval` param |
| **Graceful error handling: log-and-continue** | Network blips, device offline, logger stick busy — must not crash the service | Medium | solis2mqtt README explicitly documents this: "it will recover... if you see the last update count up past the expected 11 secs... it does that but it will self recover" |
| **Structured logging with timestamps and device name** | Without context, log lines are unactionable in a multi-device setup | Low | Universal expectation for any production service |
| **Docker + docker-compose.yml** | User's deployment target; without this, deployment is manual and fragile | Low | Stated hard requirement; pysolarmanv5 itself ships a Dockerfile |
| **Continuous polling loop (runs forever)** | This is a logger, not a one-shot script | Low | schwatter/solarman_mqtt runs a `while True` loop; HA coordinator is a periodic callback |
| **Retry on transient TCP failure** | Solarman sticks drop connections when their cloud sync fires (6-min cycle observed in the wild) | Medium | solis2mqtt: "The dongles appear to get locked from time to time (if this script attempts to get data at the same time the stick is due to send the 6 min update to solis cloud)" |

---

## Key Metrics Captured (from deye_micro.yaml + ddzy422-d2.yaml)

This is what the YAML profiles expose — table stakes for the InfluxDB payload.

### Deye SUN-M225G4 Microinverter Fields
| Group | Fields | Notes |
|-------|--------|-------|
| **PV (DC input)** | PV1–4 Voltage (V), PV1–4 Current (A), PV1–4 Power (W), PV Power (combined W) | Per-MPPT; SUN-M225G4 has 4 MPPTs |
| **Grid (AC output)** | Grid Voltage (V), Grid Current (A), Grid Frequency (Hz), Power (W), Power losses (W) | Output-side |
| **Energy** | Today Production (kWh), Total Production (kWh), Today/Total Production 1–4 per MPPT | State-class: `total_increasing` |
| **Device state** | Device State (Standby/Self-test/Normal/Alarm/Fault), Device Alarm (bitmask), Device Fault (bitmask) | Operational health |
| **Temperature** | Temperature (°C) | Inverter internal temp |
| **Info** (slow, 3600s) | Device type, firmware versions, serial, rated power, MPPT count | Static metadata |

### DDZY422-D2 Smart Meter Fields
| Group | Fields | Notes |
|-------|--------|-------|
| **Variable Data** | Voltage (V), Current (A), Power (W), Power Factor, Frequency (Hz) | Real-time |
| **Energy** | Total Import Energy (kWh), Total Export Energy (kWh) | Cumulative |

---

## Differentiators

Features that set the tool apart — not universally expected, but meaningfully better than alternatives.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Per-group update intervals from YAML profile** | `deye_micro.yaml` defines `update_interval: 3600` for Info group, `update_interval: 5` for real-time groups. Honoring this reduces load and avoids polling slow registers unnecessarily. | Medium | Requires reading `update_interval` per parameter group, not just a flat global interval. Currently done by HA coordinator; straightforward to replicate. |
| **Register validation / bad-data filtering** | YAML profiles define `validation: min/max/dev/invalidate_all`. Without honoring these, spurious values (e.g., 65535W power reading at startup) land in InfluxDB and corrupt Grafana charts | Medium | `invalidate_all` skips the whole poll when a sentinel value is detected. HA's `ParameterParser` already implements this — reuse it. |
| **Configurable InfluxDB measurement name** | Defaults to device name, but some users want `inverter` with device as a tag only | Low | One config field; prevents schema lock-in |
| **Multi-group batching per poll** | Writing all fields for a device in a single InfluxDB write (one Point with N fields) vs. N separate writes. Dramatically more efficient for Grafana queries and InfluxDB storage. | Low | influxdb-client `Point` supports multiple `.field()` calls; this is the right pattern |
| **Startup connectivity validation** | Log a clear error if InfluxDB is unreachable at startup rather than silently failing on first write | Low | Immediately surfaces misconfiguration; cheap to implement with a health-check write |
| **Explicit "offline" log entry when device unreachable** | Distinguishes "device polled but returned zero" from "device unreachable" in logs | Low | Significant for debugging; cheap to implement |
| **`update_interval: 0` / disabled groups** | Allow selectively skipping groups (e.g., skip Info group entirely in prod) | Low | Trivial config option with significant flexibility |

---

## Anti-Features

Things to deliberately NOT build. These are complexity traps that consume time without delivering the core value.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Register write-back / inverter control** | Dramatically increases blast radius (wrong write = inverter off). Zero value for a data logger. | Log-only. Read all registers, write none. |
| **MQTT output** | Duplicates complexity; user already has InfluxDB. MQTT-first tools (schwatter, solis2mqtt) require a separate broker and add latency to persistence. | Write directly to InfluxDB. Done. |
| **InfluxDB bucket / org provisioning** | User already has InfluxDB running. Auto-provisioning adds auth scope requirements (admin token) and error paths. | Document the required manual setup in README (one bucket, one token). |
| **Grafana dashboard provisioning** | User already has Grafana. Dashboard JSON is fragile across Grafana versions and opinionated. | Document example queries instead. |
| **Auto-discovery of logger sticks on LAN** | Brittle (relies on broadcast or ARP scanning), adds `netifaces`/network dependencies, fails on segmented networks. StephanJoubert warns: "only happens when the component starts and, if the logger is inaccessible at that point, entities will be unavailable until restart." | Require explicit IP + serial in config. |
| **Device-type auto-detection** | Sticks don't reliably advertise their device type over Solarman V5. deye-controller TODO list: "Support single phase inverters, eventually with auto detection." | Require explicit `profile` field in config. |
| **Web UI / REST API** | Adds a whole service layer (Flask/FastAPI, auth, port management) for zero gain over reading logs. | stdout logs + InfluxDB are the interface. |
| **Alert/notification system** | Email, Slack, PagerDuty integrations each require credentials, config, and failure modes of their own. | Log errors clearly. Grafana has its own alerting on the same data. |
| **Per-field InfluxDB tag customization** | Flexible but complex config; forces users to understand InfluxDB tag vs field semantics. | Fixed schema: measurement=device_name, tags={device, type}, fields=all register values. |
| **Cloud/remote access (tunneling, VPN setup)** | Out of scope. Local LAN only. | Document that the device must be on the same network as the container. |
| **Historical backfill on startup** | Requires storing last-known-good timestamps, diffing against register history. Solarman sticks don't expose historical data. | Write current readings only. Gaps are gaps. |

---

## Feature Complexity Notes

### What's genuinely easy (do not over-engineer)
- **YAML config parsing** — standard PyYAML, flat structure with Pydantic validation. One file, N device entries, one InfluxDB block.
- **InfluxDB writes** — `influxdb-client[async]` with `Point("device_name").tag(...).field(...).field(...)` per poll. Synchronous write is fine at 5s intervals; async write_api available if needed.
- **Poll loop** — `asyncio.gather()` over N device coroutines, each with `asyncio.sleep(interval)`. Independent per device.

### What needs care
- **`ParameterParser` extraction from HA** — The parser is tightly coupled to HA's entity model (`hass`, `entity`, `unique_id`). Must strip HA-specific hooks cleanly without breaking parsing logic (scale, rule, validation, multi-register). Medium complexity.
- **Per-group update intervals** — Tracking "last polled" per group per device requires a small scheduler. Not complex, but needs explicit design: a dict of `{(device, group): last_poll_ts}` and comparison on each main loop tick.
- **Register validation / `invalidate_all`** — The YAML `validation` blocks (min, max, dev, invalidate_all) exist specifically to filter bad readings at startup and during grid disturbances. Skipping this means garbage in InfluxDB. Must reuse `ParameterParser`'s existing validation logic.
- **TCP error recovery** — Solarman V5 connections are stateful TCP. Must catch `ConnectionRefusedError`, `TimeoutError`, `OSError` and backoff without crashing the main loop. One device's failure must not block other devices' polls.

### What's a trap
- **Async vs sync writes to InfluxDB** — The default `WriteApi` in batching mode is a singleton with internal threads. For a simple N-device poller at 5–60s intervals, `SYNCHRONOUS` write mode is cleaner and avoids the "flush on close" footgun. Switch to async only if write latency becomes measurable.
- **One measurement per field vs. one measurement per device** — The per-device measurement (all fields in one Point) is strongly preferred for Grafana: `from(bucket: "solar") |> filter(r => r._measurement == "inverter_1")` is natural. Per-field measurements require a pivot or separate queries per metric.

### Validation before coding
- **ParameterParser HA coupling depth** — Read `parser.py` fully before writing extraction plan. The HA dependency surface may be smaller (or larger) than expected.
- **deye_micro.yaml group `update_interval` behavior** — Confirm whether `update_interval` at the group level means "poll this group every N seconds" or "poll this group every N main-loop ticks." Must match HA coordinator behavior.

---

## MVP Feature Set (Minimum to Ship)

Based on the above, the minimal viable logger that delivers on the core value:

1. YAML config: N devices (host, port, serial, name, profile) + InfluxDB connection
2. Poll loop: per-device async polling, configurable interval
3. ParameterParser reuse: parse all register values from YAML profile
4. InfluxDB write: one Point per device per poll, all fields, device name + type as tags
5. Error handling: log-and-continue, TCP errors are caught per device
6. Docker + docker-compose.yml

**Deferred but not far:**
- Per-group update intervals (honoring profile's `update_interval` per group)
- Register validation / `invalidate_all` (important for data quality but can be added in phase 2)

**Never:**
- Write-back, MQTT, auto-discovery, web UI, cloud access
