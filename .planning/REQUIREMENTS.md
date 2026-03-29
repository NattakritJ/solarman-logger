# Requirements: solarman-logger

**Defined:** 2026-03-29
**Core Value:** Every configured device is polled on schedule and its data lands in InfluxDB — reliably, without crashing, continuously.

## v1 Requirements

### Configuration

- [ ] **CONF-01**: User can define N devices in a YAML file (host, port, serial, name, type, profile path)
- [ ] **CONF-02**: User can configure a global poll interval and optionally override it per device
- [ ] **CONF-03**: User can configure InfluxDB v2 connection (URL, org, bucket, token) in the same YAML file
- [ ] **CONF-04**: Service fails fast with a clear error message on invalid or missing config at startup

### Device Polling

- [ ] **POLL-01**: Service polls all configured devices concurrently; one device failing does not affect others
- [x] **POLL-02**: Service reuses ha-solarman's YAML inverter definition profiles for register mapping
- [x] **POLL-03**: Service parses raw Modbus register values into named, typed, unit-annotated fields using ParameterParser
- [ ] **POLL-04**: Service honours per-group `update_interval` from YAML profiles (e.g., Info group at 3600s, real-time at 5s)
- [x] **POLL-05**: Service applies YAML profile register validation (min/max/invalidate_all) to filter bad readings before writing
- [ ] **POLL-06**: On TCP failure, service logs the error and retries on the next poll cycle without crashing

### InfluxDB Writing

- [ ] **INFL-01**: Service writes one InfluxDB Point per device per poll cycle containing all parsed fields
- [ ] **INFL-02**: Each Point is tagged with device name and device type
- [ ] **INFL-03**: All numeric field values are written as float (never int) to prevent permanent InfluxDB type conflicts
- [ ] **INFL-04**: Service validates InfluxDB connectivity at startup and logs a clear error if unreachable
- [ ] **INFL-05**: On InfluxDB write failure, service logs the error and continues polling (data for that cycle is dropped, not buffered)

### Logging

- [ ] **LOG-01**: All log output goes to stdout with timestamps, log level, and device name context
- [ ] **LOG-02**: Service logs a distinct message when a device is unreachable vs when a device returns invalid data

### Deployment

- [ ] **DEPL-01**: Service ships as a Docker image built from a `Dockerfile` using `python:3.12-slim`
- [ ] **DEPL-02**: A `docker-compose.yml` is provided with `network_mode: host` and config file bind-mount
- [ ] **DEPL-03**: Config file path is configurable via an environment variable (default: `/config/config.yaml`)

## v2 Requirements

### Observability

- **OBS-01**: Expose a `/health` HTTP endpoint for Docker health checks
- **OBS-02**: Log a summary of poll results (fields written, duration) at DEBUG level per cycle

### Resilience

- **RES-01**: Exponential backoff on repeated TCP failures per device (cap at configurable max interval)
- **RES-02**: Persist last-known-good timestamp per device to detect extended offline periods

### Configuration

- **CONF-05**: Support environment variable substitution in YAML config (e.g., `${INFLUXDB_TOKEN}`)
- **CONF-06**: Hot-reload config without container restart on SIGHUP

## Out of Scope

| Feature | Reason |
|---------|--------|
| Register write-back / inverter control | Zero value for a data logger; high risk of device damage |
| MQTT output | User has InfluxDB; adding MQTT duplicates complexity without benefit |
| InfluxDB bucket/org provisioning | User's infrastructure already exists; admin token scope not needed |
| Grafana dashboard provisioning | User already has Grafana; dashboard JSON is fragile across versions |
| Auto-discovery of logger sticks | Brittle, fails on segmented networks; explicit IP + serial required |
| Device-type auto-detection | Sticks don't reliably advertise type over Solarman V5 |
| Web UI / REST API | stdout + InfluxDB are the interface |
| Alert/notification system | Grafana handles alerting on the same data |
| Cloud/remote access | Local LAN only |
| Historical backfill | Solarman sticks don't expose historical data; gaps are gaps |
| Home Assistant integration | Completely independent service |

## Traceability

Updated: 2026-03-29 (roadmap created)

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONF-01 | Phase 1 | Pending |
| CONF-02 | Phase 1 | Pending |
| CONF-03 | Phase 1 | Pending |
| CONF-04 | Phase 1 | Pending |
| POLL-01 | Phase 2 | Pending |
| POLL-02 | Phase 1 | Complete |
| POLL-03 | Phase 1 | Complete |
| POLL-04 | Phase 2 | Pending |
| POLL-05 | Phase 1 | Complete |
| POLL-06 | Phase 2 | Pending |
| INFL-01 | Phase 3 | Pending |
| INFL-02 | Phase 3 | Pending |
| INFL-03 | Phase 3 | Pending |
| INFL-04 | Phase 3 | Pending |
| INFL-05 | Phase 3 | Pending |
| LOG-01 | Phase 1 | Pending |
| LOG-02 | Phase 1 | Pending |
| DEPL-01 | Phase 4 | Pending |
| DEPL-02 | Phase 4 | Pending |
| DEPL-03 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 20 ✓
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-29*
*Last updated: 2026-03-29 after initial definition*
