# Roadmap: solarman-logger

**Generated:** 2026-03-29
**Granularity:** coarse
**Total phases:** 4
**Requirements mapped:** 20/20

---

## Phases

- [ ] **Phase 1: Protocol Core** — Extract and adapt pysolarman/ParameterParser, load and validate YAML config, verify slugify replacement
- [ ] **Phase 2: Device Polling Loop** — Concurrent per-device polling with error isolation, per-group scheduling, and fixed pysolarman bugs
- [ ] **Phase 3: InfluxDB Pipeline** — Write parsed readings to InfluxDB with float enforcement, startup health check, and error-tolerant writes
- [ ] **Phase 4: Docker Packaging** — Dockerfile, docker-compose.yml, config path env var, and verified clean shutdown

---

## Phase Details

### Phase 1: Protocol Core
**Goal**: Config is loaded, validated, and fail-fast at startup; pysolarman and ParameterParser are extracted from HA coupling and correctly parse raw register bytes into named fields; slugify replacement is validated against all profile keys.
**Depends on**: Nothing (first phase)
**Requirements**: CONF-01, CONF-02, CONF-03, CONF-04, POLL-02, POLL-03, POLL-05, LOG-01, LOG-02
**Success Criteria** (what must be TRUE):
  1. Starting the service with a missing required config field (e.g. no `influxdb.token`) prints a clear error and exits immediately — no network connections attempted
  2. Starting the service with a valid config file succeeds; all N devices are parsed into typed `DeviceConfig` objects with per-device poll intervals resolved
  3. Loading a YAML inverter profile and feeding it raw register bytes via `ParameterParser` returns a `dict[str, tuple]` of named, typed, unit-annotated fields — no HA imports required
  4. The standalone `slugify()` replacement produces identical output to `homeassistant.util.slugify` for every register key across the Deye micro and DDZY YAML profiles (verified by comparison test)
  5. All stdout log output includes timestamp, log level, and device name context; unreachable-device errors and invalid-data errors produce distinct log messages
**Plans**: TBD

### Phase 2: Device Polling Loop
**Goal**: All configured devices are polled concurrently on schedule; one device failing does not affect others; per-group update intervals from YAML profiles are honoured; pysolarman critical bugs are fixed.
**Depends on**: Phase 1
**Requirements**: POLL-01, POLL-04, POLL-06
**Success Criteria** (what must be TRUE):
  1. With two devices configured, disconnecting one inverter from the network does not interrupt or delay polls to the other — it logs a timeout warning and retries on the next cycle
  2. Registers in the `Info` group (update_interval 3600s) are only polled once per hour; real-time registers poll at the configured interval — verified by log output showing request batches
  3. A device that is unreachable for N cycles continues logging a warning every cycle and recovers automatically (without container restart) when the device comes back online
  4. No `RecursionError` occurs under sustained network failure (recursive `_open_connection` bug is replaced with task-based retry)
**Plans**: TBD

### Phase 3: InfluxDB Pipeline
**Goal**: Every successful poll cycle results in a correctly-typed InfluxDB Point written per device, tagged with device name and type; write failures are logged without crashing; InfluxDB connectivity is validated at startup.
**Depends on**: Phase 2
**Requirements**: INFL-01, INFL-02, INFL-03, INFL-04, INFL-05
**Success Criteria** (what must be TRUE):
  1. After a full poll cycle, InfluxDB contains one measurement per device with fields for all parsed registers, tagged with `device_name` and `device_type`
  2. All numeric field values in InfluxDB are stored as float (never int) — a field that is zero on the first write does not cause a type conflict on subsequent fractional writes
  3. Starting the service when InfluxDB is unreachable logs a clear error at startup; the service either exits or retries without crashing — no silent failure
  4. A write failure during operation (e.g. InfluxDB restart mid-run) logs a warning; the next poll cycle writes normally — no data from the failed cycle is buffered or retried
**Plans**: TBD

### Phase 4: Docker Packaging
**Goal**: The complete service runs as a Docker container started with `docker compose up`; it reaches LAN inverters, loads config from a bind-mounted file, and exits cleanly on `docker stop`.
**Depends on**: Phase 3
**Requirements**: DEPL-01, DEPL-02, DEPL-03
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts the service; logs show devices being polled and data written to InfluxDB — no Python import errors or missing dependency errors
  2. `docker stop` triggers a clean shutdown — logs show graceful task cancellation and `writer.close()` called; container exits within 5 seconds (no SIGKILL)
  3. The container reaches inverter IPs on the LAN (requires `network_mode: host`); setting `CONFIG_PATH=/data/my-config.yaml` via environment variable loads that file instead of the default
**Plans**: TBD

---

## Coverage Validation

| Requirement | Phase |
|-------------|-------|
| CONF-01 | Phase 1 |
| CONF-02 | Phase 1 |
| CONF-03 | Phase 1 |
| CONF-04 | Phase 1 |
| POLL-01 | Phase 2 |
| POLL-02 | Phase 1 |
| POLL-03 | Phase 1 |
| POLL-04 | Phase 2 |
| POLL-05 | Phase 1 |
| POLL-06 | Phase 2 |
| INFL-01 | Phase 3 |
| INFL-02 | Phase 3 |
| INFL-03 | Phase 3 |
| INFL-04 | Phase 3 |
| INFL-05 | Phase 3 |
| LOG-01 | Phase 1 |
| LOG-02 | Phase 1 |
| DEPL-01 | Phase 4 |
| DEPL-02 | Phase 4 |
| DEPL-03 | Phase 4 |

**All 20 v1 requirements mapped ✓**

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Protocol Core | 0/? | Not started | — |
| 2. Device Polling Loop | 0/? | Not started | — |
| 3. InfluxDB Pipeline | 0/? | Not started | — |
| 4. Docker Packaging | 0/? | Not started | — |

---
*Roadmap generated: 2026-03-29*
