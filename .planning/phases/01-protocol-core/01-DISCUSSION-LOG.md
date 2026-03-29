# Phase 1: Protocol Core - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 01-protocol-core
**Areas discussed:** Extraction strategy, YAML config structure, Parameters dict for ParameterParser, Slugify replacement, Profile loading (device config)

---

## Extraction Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Copy-and-strip HA imports | Copy pysolarman/__init__.py, parser.py, and needed helpers from common.py. Strip ~5 HA import lines, replace with pure-Python equivalents. Minimal diff from reference. | ✓ |
| Rewrite from scratch | New clean module reimplementing only what's needed. Smaller but higher risk of behavioral differences. | |
| Shim HA imports | Make pysolarman importable as-is by satisfying HA imports with shims. Avoids copying but couples app to HA component directory. | |

**User's choice:** Copy-and-strip HA imports

---

## App Location

| Option | Description | Selected |
|--------|-------------|----------|
| New top-level directory in this repo | Create a new package alongside `custom_components/` inside this repo. | ✓ |
| Separate project directory | Sibling repo outside this repo, referenced via Dockerfile COPY or volume mount. | |

**User's choice:** New top-level directory in this repo

---

## YAML Config Structure (top level)

| Option | Description | Selected |
|--------|-------------|----------|
| Nested sections (influxdb + devices) | `influxdb:` section + `devices:` list + optional `defaults:`. Clean, readable. | ✓ |
| Flat structure | Flat top-level keys only. Simpler but less extensible. | |
| Env-vars-first | Most values as env vars, YAML only for device list. Adds complexity. | |

**User's choice:** Nested sections (influxdb + devices)

---

## Device Entry Fields

| Option | Description | Selected |
|--------|-------------|----------|
| host/port/serial/name/profile + optional overrides | Required: host, port, serial, name, profile. Optional: poll_interval, slave. | ✓ |
| Include device_type as required | Same fields plus mandatory device_type for InfluxDB tagging. | |
| Minimal (host + serial + profile only) | Minimal required fields. Name derived from profile. | |

**User's choice:** host/port/serial/name/profile + optional overrides (device_type deferred to Phase 3)

---

## Profile Path Resolution

| Option | Description | Selected |
|--------|-------------|----------|
| Relative to config file | Profile filename resolved from config file's directory. Most portable. | ✓ |
| Absolute or working-dir relative | Full path or relative to working dir. Less portable. | |
| Name only, app resolves path | App searches built-in definitions dir first, then custom path. | |

**User's choice:** Relative to config file

---

## ParameterParser Parameters Dict

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcode HA defaults for all devices | mod=0, mppt=4, phase=3, pack=-1 for all devices. Works for Deye micro and DDZY profiles. | ✓ |
| Expose as optional per-device fields | Allow mod/mppt/phase/pack per-device in config.yaml. More flexible, more complexity. | |
| Auto-derive from profile info | Read from YAML profile's `info` section, fall back to defaults. | |

**User's choice:** Hardcode HA defaults for all devices

---

## Slugify Replacement

| Option | Description | Selected |
|--------|-------------|----------|
| python-slugify library | Install python-slugify (pip), configure to match HA output. Well-tested, easy to verify. | ✓ |
| Copy HA's slugify logic directly | Copy the ~10-line core from homeassistant/util/__init__.py. Zero extra deps, exact match. | |
| Custom minimal implementation | Minimal regex-based function that passes all profile key test cases. | |

**User's choice:** python-slugify library

---

## Profile Loading (Device Config, follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Profile filename resolved from config dir | `profile: deye_micro.yaml` resolves relative to config file location. Matches HA's path+filename split in ParameterParser.init(). | ✓ |
| Full absolute path in profile field | Full path required. Less portable. | |
| Separate definitions_dir + profile name | Separate `definitions_dir` config key + profile filename only. | |

**User's choice:** Profile filename resolved from config dir
**Notes:** User explicitly requested that device config must follow the same config pattern as inverter_definitions/ to ensure the program works like as-is (identical to HA behavior).

---

## the agent's Discretion

- Exact directory and module names within the new top-level package
- Whether yaml_open stays async (aiofiles) or switches to sync yaml.safe_load for config loading
- Internal module split (e.g. one file vs separate config.py / protocol.py / parser.py)
- Log format string details (beyond: timestamp + level + device name)

## Deferred Ideas

None — discussion stayed within phase scope.
