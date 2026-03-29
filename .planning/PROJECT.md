# solarman-logger

## What This Is

A standalone Python data logger that polls any number of Solarman-protocol devices (inverters, smart meters) defined in a YAML config file and writes their readings to an existing InfluxDB v2 instance. It runs as a Docker container (with docker-compose.yml) and has no dependency on Home Assistant. It uses this repository (ha-solarman) as a reference for the Solarman/Modbus protocol client and YAML device definition format.

## Core Value

Every configured device is polled on schedule and its data lands in InfluxDB — reliably, without crashing, continuously.

## Requirements

### Validated

- ✓ Solarman V5 protocol client (pysolarman) — existing in repo
- ✓ Modbus register definitions in YAML (inverter_definitions/*.yaml) — existing in repo
- ✓ ParameterParser — parses raw register values into named, typed fields — existing in repo
- ✓ Async TCP polling loop (DataUpdateCoordinator pattern) — existing in repo
- ✓ Per-device config entry model (host, port, serial, profile) — existing in repo

### Active

- [ ] YAML configuration file — define N devices (host, port, serial, name, type, profile) + InfluxDB connection
- [ ] Configurable poll interval per device (or global default)
- [ ] Reuse ha-solarman's YAML device profile definitions for register mapping
- [ ] Write measurements to InfluxDB v2 — one measurement per device, tagged with device name + type
- [ ] Docker image + docker-compose.yml for deployment
- [ ] Graceful error handling — log and retry on device unreachable or bad data, never crash
- [ ] Structured stdout logging (timestamps, device name, log level)

### Out of Scope

- Home Assistant integration — not needed, completely independent
- Grafana setup/provisioning — user already has it running
- InfluxDB provisioning — user already has it running; only connection config needed
- Cloud/remote access — local network only
- Write-back to devices / inverter control commands
- Alert/notification system on failure — log and retry is sufficient

## Context

**Reference codebase:** ha-solarman (`custom_components/solarman/`) contains:
- A vendored `pysolarman` async TCP client (Solarman V5 framing over Modbus RTU)
- A vendored `umodbus` library for Modbus frame building/parsing
- `ParameterParser` — data-driven register parsing from YAML profiles
- `inverter_definitions/*.yaml` — register maps for Deye and other inverters (including SUN-M225G4)
- These components will be extracted/adapted rather than re-implemented from scratch

**Target devices:**
- 2× Deye SUN-M225G4 micro-inverters (profile already exists in repo)
- 1× DDZY422-D2-W smart meter (on its own Solarman logger stick)
- All on local LAN, each with their own stick logger (host IP + serial number)
- System is N-device: any number of devices defined in config will be polled

**Infrastructure already in place:**
- InfluxDB v2 on user's server (URL, org, bucket, token needed in config)
- Grafana connected to that InfluxDB instance

**Existing patterns to reuse:**
- Async polling loop — adapt from `coordinator.py`
- Protocol client — extract from `pysolarman/`
- Register parsing — extract `ParameterParser` from `parser.py`
- Device YAML profiles — copy from `inverter_definitions/`

## Constraints

- **Language:** Python — same as reference codebase, no extra translation layer
- **Runtime:** Docker container; docker-compose.yml is a hard requirement
- **Config format:** YAML file mounted into container
- **InfluxDB:** v2 API only (token auth, org/bucket model)
- **Network:** Local LAN only; devices speak Solarman V5 over TCP port 8899 by default
- **No HA dependency:** Must run without Home Assistant installed

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Reuse pysolarman + umodbus from repo | Already proven, handles Solarman V5 framing correctly | — Pending |
| Reuse ParameterParser + YAML profiles | Eliminates register mapping work; profiles already exist for Deye | — Pending |
| Per-device measurements in InfluxDB | Cleanest Grafana dashboard structure; easy to query per device | — Pending |
| YAML config file | Human-readable, easy to add/remove devices without code changes | — Pending |
| Docker + docker-compose.yml | Matches user's existing server setup; portable, restartable | — Pending |
| Log-and-retry on failure | Never crash; one broken device shouldn't stop others | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-29 after initialization*
