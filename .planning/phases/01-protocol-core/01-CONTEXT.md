# Phase 1: Protocol Core - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Extract pysolarman and ParameterParser from the HA component, strip all HA imports, build a YAML config loader with startup validation, set up structured stdout logging — all as a standalone Python package inside a new top-level directory in this repo. No Home Assistant dependency at runtime.

Requirements: CONF-01, CONF-02, CONF-03, CONF-04, POLL-02, POLL-03, POLL-05, LOG-01, LOG-02

</domain>

<decisions>
## Implementation Decisions

### Extraction Strategy
- **D-01:** Copy-and-strip: copy `pysolarman/__init__.py`, `parser.py`, and the needed pure-Python helpers from `common.py` into a new standalone package. Strip the ~5 HA-coupled import lines and replace with pure-Python equivalents. Do not rewrite from scratch and do not shim HA imports.
- **D-02:** The new standalone app lives in a new top-level directory inside this repo (alongside `custom_components/`). Exact name TBD by planner (e.g. `solarman_logger/`).

### YAML Config Structure
- **D-03:** Nested top-level sections: `influxdb:` (url, org, bucket, token) + `defaults:` (poll_interval) + `devices:` list.
- **D-04:** Each device entry requires: `host`, `port`, `serial`, `name`, `profile`. Optional per-device override: `poll_interval`, `slave` (default 1).
- **D-05:** The `profile` field is a filename (e.g. `deye_micro.yaml`) resolved relative to the config file's directory. This matches how HA resolves profiles internally via `path + filename` split in `ParameterParser.init()`.
- **D-06:** Device type for InfluxDB tagging is NOT a required config field in Phase 1 (InfluxDB writing is Phase 3). It can be introduced then.

### ParameterParser Parameters Dict
- **D-07:** Use the same hardcoded HA defaults for all devices: `mod=0, mppt=4, phase=3, pack=-1`. No per-device overrides in config.yaml. This works correctly for the Deye SUN-M225G4 micro-inverter and DDZY422-D2-W profiles without customization.

### Slugify Replacement
- **D-08:** Use the `python-slugify` library (pip dependency) configured to match HA's `homeassistant.util.slugify` output. The success criteria requires identical output verified against all register keys in `deye_micro.yaml` and `ddzy422-d2.yaml`.

### Logging
- **D-09:** Structured stdout logging with timestamp, log level, and device name context on every line (LOG-01). Unreachable-device errors and invalid-data errors produce distinct log messages (LOG-02). Standard Python `logging` module with a custom formatter.

### the agent's Discretion
- Exact directory and module names within the new top-level package
- Whether `yaml_open` stays async (aiofiles) or switches to sync `yaml.safe_load` for config loading
- Internal module split (e.g. one file vs separate config.py / protocol.py / parser.py)
- Log format string details (beyond: timestamp + level + device name)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Protocol and Parser (files to copy-and-strip)
- `custom_components/solarman/pysolarman/__init__.py` — Solarman V5 async TCP client; the primary file to extract. Note: imports `retry`, `throttle`, `create_task`, `format` from `..common` — these must be moved alongside it.
- `custom_components/solarman/parser.py` — ParameterParser; register-to-field parsing logic. Imports from `.const` and `.common`; HA-coupling is minimal (only `slugify` in `common.py`).
- `custom_components/solarman/common.py` — Source of `retry`, `throttle`, `create_task`, `format`, `yaml_open`, `enforce_parameters`, `preprocess_descriptions`, `slugify`. HA-specific imports: `homeassistant.util.slugify` (replace with python-slugify), `homeassistant.helpers.device_registry` (strip — not needed), `aiohttp`/`voluptuous` (strip — not needed in standalone).
- `custom_components/solarman/const.py` — Constants consumed by parser.py and common.py (`DEFAULT_`, `PARAM_`, `REQUEST_*`, `CONF_MOD/MPPT/PHASE/PACK`). Mostly pure Python — read carefully to identify which constants are actually needed.
- `custom_components/solarman/pysolarman/umodbus/` — Vendored Modbus library; copy as-is (no HA imports).

### Device Profiles (reference for config structure and slugify validation)
- `custom_components/solarman/inverter_definitions/deye_micro.yaml` — Profile for Deye SUN-M225G4 micro-inverter; used to validate slugify output and verify ParameterParser parsing.
- `custom_components/solarman/inverter_definitions/ddzy422-d2.yaml` — Profile for DDZY422-D2-W smart meter; same validation role.

### HA slugify source (for equivalence testing)
- `homeassistant/util/__init__.py` (HA installed package) — The `slugify()` implementation to match; researcher should read this to configure python-slugify correctly.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `custom_components/solarman/pysolarman/__init__.py`: `Solarman` class — async TCP client; copy with minimal changes (strip 1 import line referencing `..common`).
- `custom_components/solarman/pysolarman/umodbus/`: vendored Modbus library — copy as-is, zero HA coupling.
- `custom_components/solarman/parser.py`: `ParameterParser` class — copy with minimal changes (strip HA-specific const imports that aren't needed, keep pure-Python logic intact).
- From `common.py`: `retry()`, `throttle()`, `create_task()`, `format()`, `yaml_open()`, `enforce_parameters()`, `preprocess_descriptions()`, `group_when()`, `slugify()` — all copy-eligible with HA imports stripped.
- From `const.py`: `DEFAULT_`, `PARAM_`, `REQUEST_*` constants, `CONF_MOD/MPPT/PHASE/PACK` — read carefully, copy only what parser.py and pysolarman actually reference.

### Established Patterns
- Async TCP with `asyncio.StreamReader/StreamWriter`, connection keeper loop, `asyncio.Lock` for thread safety — established in pysolarman, carry forward unchanged.
- `@retry` and `@throttle` decorators from common.py — used on `execute_bulk` and `_open_connection`/`_send_receive_frame`; keep this pattern.
- `ParameterParser.init()` receives `(path: str, filename: str, parameters: dict)` — the standalone app must call it the same way, splitting the profile path into directory + filename.

### Integration Points
- Profile loading: `ParameterParser.init(path, filename, parameters)` where `path` is the directory (with trailing `/`) and `filename` is the YAML file name. The standalone config loader must resolve `profile` field to this split form.
- `parameters` dict shape: `{CONF_MOD: 0, CONF_MPPT: 4, CONF_PHASE: 3, CONF_PACK: -1}` — the standalone app passes these hardcoded defaults.

</code_context>

<specifics>
## Specific Ideas

- The device config must follow the same config pattern as `inverter_definitions/` to ensure the program works as-is — profiles are loaded and parsed identically to how HA does it.
- Profile `profile` field in `config.yaml` references a filename (e.g. `deye_micro.yaml`) resolved relative to the config file's own directory — so profiles can be placed alongside `config.yaml` in the mounted volume.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-protocol-core*
*Context gathered: 2026-03-29*
