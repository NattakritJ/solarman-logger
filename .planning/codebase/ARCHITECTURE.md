# Architecture

**Analysis Date:** 2026-03-29

## Pattern Overview

**Overall:** Home Assistant Custom Component — Device-Centric Local Polling Integration

**Key Characteristics:**
- Single custom component (`solarman`) under `custom_components/` following HA integration conventions
- `ConfigEntry`-per-device model: each inverter/stick logger is one config entry with its own `Coordinator`
- All configuration stored in `ConfigEntry.options` (no `configuration.yaml` data)
- Platforms auto-discovered at runtime: any `{platform}.py` file that exists in the component directory is registered as a supported HA platform
- Data flows via a central `DataUpdateCoordinator` that polls on a fixed 5-second base interval; entity updates are triggered via HA's coordinator callback mechanism
- Modbus register definitions fully data-driven via YAML profiles; no hard-coded register addresses in Python

---

## Layers

**Integration Bootstrap (`__init__.py`):**
- Purpose: HA lifecycle entry point — setup, teardown, migration, and global service registration
- Location: `custom_components/solarman/__init__.py`
- Contains: `async_setup`, `async_setup_entry`, `async_unload_entry`, `async_migrate_entry`, `async_remove_config_entry_device`
- Depends on: `Coordinator`, `ConfigFlowHandler`, `services.register`, `discovery.discover`
- Dynamically builds `_PLATFORMS` list by scanning the component directory for `{platform}.py` files at import time

**Configuration Flow (`config_flow.py`):**
- Purpose: HA UI-driven setup and options management for each inverter device
- Location: `custom_components/solarman/config_flow.py`
- Contains: `ConfigFlowHandler` (VERSION=2, MINOR_VERSION=0), `OptionsFlowHandler`, schema definitions, validation helpers
- Supports: manual entry (`async_step_user`), integration discovery (`async_step_integration_discovery`), DHCP discovery (`async_step_dhcp`)
- All configuration is written to `ConfigEntry.options`; `ConfigEntry.data` remains empty

**Data Coordinator (`coordinator.py`):**
- Purpose: Orchestrates periodic polling and distributes data to all registered entities
- Location: `custom_components/solarman/coordinator.py`
- Contains: `Coordinator(DataUpdateCoordinator[dict[str, tuple]])`
- Key behavior: wraps a `Device` instance; increments an internal `counter` (used as `runtime` clock for request scheduling) on each successful poll; resets counter on failure
- `runtime_data`: `ConfigEntry.runtime_data` is typed as `Coordinator` — entities access it via `config_entry.runtime_data`

**Device (`device.py`):**
- Purpose: Manages the connection lifecycle and executes raw Modbus requests via the pysolarman client
- Location: `custom_components/solarman/device.py`
- Contains: `Device`, `DeviceState`
- Composed of three providers: `EndPointProvider` (network/discovery), `ProfileProvider` (YAML profile + parser), `Solarman` (Modbus TCP client)
- `Device.get(runtime)` → schedules requests via `ProfileProvider.parser.schedule_requests(runtime)` → calls `execute_bulk` → returns parsed dict

**Providers (`provider.py`):**
- Purpose: Configuration and initialization abstraction layer sitting between `ConfigEntry` and `Device`
- Location: `custom_components/solarman/provider.py`
- Contains:
  - `ConfigurationProvider` — thin `@dataclass` wrapping `ConfigEntry`; all fields `@cached_property`
  - `EndPointProvider` — manages host/IP resolution, serial number, MAC address via UDP discovery; can auto-reconfigure logger network settings via HTTP
  - `ProfileProvider` — loads and resolves YAML inverter definition, performs auto-detection if `lookup_file == "Auto"`, instantiates `ParameterParser`

**Protocol Client (`pysolarman/__init__.py`):**
- Purpose: Async TCP client implementing the Solarman V5 framing protocol over Modbus RTU/TCP
- Location: `custom_components/solarman/pysolarman/__init__.py`
- Contains: `Solarman` class; `PROTOCOL` namespace (frame constants); `FrameError`
- Supports three transport modes selected at runtime via `transport` setter:
  - `"tcp"` — Solarman V5 proprietary framing wrapping Modbus RTU (`_parse_adu_from_sol_response`)
  - `"modbus_tcp"` — plain Modbus TCP (`_parse_adu_from_tcp_response`)
  - `"modbus_rtu"` — plain Modbus RTU over TCP (`_parse_adu_from_rtu_response`)
- Maintains a persistent async TCP connection with a keeper loop (`_keeper_loop`) that auto-reconnects
- Frame operations use `@throttle` and `@retry` decorators from `common.py`

**Modbus Protocol Library (`pysolarman/umodbus/`):**
- Purpose: Vendored/embedded fork of the `umodbus` library providing Modbus PDU construction and parsing
- Location: `custom_components/solarman/pysolarman/umodbus/`
- Contains: `functions.py` (FUNCTION_CODE enum, PDU builders/parsers), `exceptions.py`, `client/tcp.py`, `client/serial/rtu.py`

**Parameter Parser (`parser.py`):**
- Purpose: Loads YAML inverter profiles, builds request schedules, and decodes raw register data into typed entity states
- Location: `custom_components/solarman/parser.py`
- Contains: `ParameterParser`
- Key methods:
  - `init(path, filename, parameters)` — async; loads YAML, preprocesses item definitions, builds lambda for request grouping
  - `schedule_requests(runtime)` — returns batched Modbus requests for the current `runtime` tick (respects per-item `update_interval`)
  - `process(data)` — dispatches to `try_parse_*` methods based on `rule` field (1–10); returns `{key: (state, value)}` dict
  - `get_entity_descriptions(platform)` — returns filtered item list for a given HA platform

**Entities (`entity.py`, platform files):**
- Purpose: HA entity implementations consuming coordinator data
- Location:
  - Base classes: `custom_components/solarman/entity.py`
  - Per-platform: `sensor.py`, `binary_sensor.py`, `switch.py`, `number.py`, `select.py`, `button.py`, `datetime.py`, `time.py`
- Hierarchy:
  - `SolarmanCoordinatorEntity(CoordinatorEntity[Coordinator])` — base; handles `_handle_coordinator_update`, `available`, `set_state`
  - `SolarmanEntity(SolarmanCoordinatorEntity)` — adds sensor dict unpacking (name, key, class, icon, options, attributes)
  - `SolarmanWritableEntity(SolarmanEntity)` — adds `write()` for Modbus write-back; used by `number`, `select`, `switch`, `button`, `datetime`, `time` platforms
- Each platform's `async_setup_entry` instantiates entities from `coordinator.device.profile.parser.get_entity_descriptions(platform)`

**Discovery (`discovery.py`):**
- Purpose: UDP-based LAN discovery of Solarman Stick Loggers
- Location: `custom_components/solarman/discovery.py`
- Contains: `DiscoveryProtocol(DatagramProtocol)`, `Discovery`, singleton `_get_discovery`
- Broadcasts `"WIFIKIT-214028-READ"` and `"HF-A11ASSISTHREAD"` to port 48899; responses contain `ip,mac,hostname`
- Singleton instance shared across all config entries via `@singleton.singleton(f"{DOMAIN}_discovery")`
- Also runs on a 15-minute interval from `async_setup` to update existing entries when device IPs change

**Services (`services.py`):**
- Purpose: Exposes raw Modbus read/write operations as HA services for automation use
- Location: `custom_components/solarman/services.py`
- Services: `read_holding_registers`, `read_input_registers`, `write_single_register`, `write_multiple_registers` (plus deprecated aliases)
- All services take a `device` entity ID, resolve it to the config entry's `Coordinator`, and call `Device.execute` directly

**Common Utilities (`common.py`):**
- Purpose: Shared helpers, decorators, HA-specific builders, YAML I/O
- Location: `custom_components/solarman/common.py`
- Key items: `retry()` decorator, `throttle()` decorator, `yaml_open()` (async aiofiles), `build_device_info()`, `slugify()`, `lookup_value()`, `group_when()`, `preprocess_descriptions()`, `postprocess_descriptions()`

**Constants (`const.py`):**
- Purpose: All domain-wide constants, defaults, autodetection tables, config key names
- Location: `custom_components/solarman/const.py`

**Inverter Definitions (`inverter_definitions/`):**
- Purpose: YAML data files defining all Modbus registers and entity mappings for each supported inverter model
- Location: `custom_components/solarman/inverter_definitions/`
- 30 built-in profiles; user-custom profiles go in `inverter_definitions/custom/` (HACS persistent directory)
- Profile schema: `info` (manufacturer/model), `default` (update_interval, code, min_span, max_size, digits), `requests` (optional fine-control), `parameters` (groups of items with register definitions)

---

## Data Flow

**Polling Cycle (read path):**

1. HA timer fires every 5 seconds → `Coordinator._async_update_data()` called
2. `Device.get(runtime=counter)` called with current tick counter
3. `ProfileProvider.parser.schedule_requests(runtime)` — returns list of Modbus request dicts for registers due at this tick
4. `Device.execute_bulk(requests, scheduled)` — fires each request via `Solarman.execute(code, address, count=N)`
5. `Solarman` constructs frame (V5/TCP/RTU depending on transport), sends via async TCP, receives response
6. `ParameterParser.process(raw_responses)` — decodes register bytes into typed `{key: (state, value)}` dict
7. `Coordinator.data` updated; `DataUpdateCoordinator` notifies all subscribed entities
8. Each entity's `_handle_coordinator_update` calls `entity.update()` → reads from `coordinator.data[self._attr_key]` → calls `set_state` → `async_write_ha_state()`

**Write Path (writable entities):**

1. User action triggers `async_set_native_value` / `async_select_option` / `async_turn_on` etc.
2. Entity calls `self.write(value, state)` (on `SolarmanWritableEntity`)
3. `write()` reads current register value via `Device.execute(code_read, register)` (for writeback support)
4. Optionally merges with `writeback` block data
5. Calls `Device.execute(code_write, register, data=value)`
6. On success, calls `set_state(state)` and `async_write_ha_state()` immediately (no coordinator re-poll)

**Device Setup Sequence:**

1. `async_setup_entry` → `Coordinator(hass, config_entry).init()`
2. `Coordinator._async_setup()` → `Device.setup()`
3. `EndPointProvider.init()` → UDP discovery (if TCP transport and private IP) → HTTP logger config check
4. `Solarman(*endpoint.connection)` instantiated (no connection yet)
5. `ProfileProvider.init(device.get)` → auto-detect device type via Modbus if `filename == "Auto"` → loads YAML → `ParameterParser.init()`
6. `async_config_entry_first_refresh()` → first poll → `Coordinator.init()` post-processes descriptions, builds `DeviceInfo`
7. Entity unique IDs migrated via `async_migrate_entries`
8. `hass.config_entries.async_forward_entry_setups(config_entry, _PLATFORMS)` → each platform's `async_setup_entry` creates entities

**State Management:**
- `Coordinator.data`: `dict[str, tuple[state, value]]` — the single source of truth for all entity states; keyed by slugified entity key
- `DeviceState.value`: connection state (-1 = never connected, 0 = error, 1 = connected); drives `SolarmanCoordinatorEntity.available`
- Counter-based scheduling: `Coordinator.counter` increments with each successful poll; `ParameterParser.is_scheduled` checks `runtime % update_interval == 0`

---

## Key Abstractions

**YAML Inverter Profiles:**
- Purpose: Data-driven register map for each inverter model; decouples hardware differences from Python code
- Location: `custom_components/solarman/inverter_definitions/*.yaml`
- Pattern: each profile item defines `name`, `platform`, `rule` (parse type 1–10), `registers` (Modbus addresses), optional `lookup` table, `scale`/`offset`/`divide`, `validation`, `attributes`

**`@retry` and `@throttle` Decorators:**
- Purpose: Connection resilience and rate limiting
- Location: `custom_components/solarman/common.py`
- `@retry(ignore=TimeoutError)` — retries once on any non-ignored exception; used on `execute_bulk`
- `@throttle(delay)` — enforces minimum delay between calls; used on `_open_connection` (0.2s) and `_send_receive_frame` (0.1s)

**Auto-Detection:**
- Purpose: Identify inverter model by reading device type register (0x0000) before loading profile
- Location: `custom_components/solarman/common.py` (`lookup_profile`), `custom_components/solarman/const.py` (AUTODETECTION_* constants)
- Reads Modbus register 0x0000 via Function Code 0x03; maps to a YAML filename via `AUTODETECTION_DEYE` dict

**Profile Redirect:**
- Purpose: Maintains backwards compatibility when profile filenames change; also allows parameterized profile variants
- Location: `custom_components/solarman/const.py` (`PROFILE_REDIRECT`)
- `process_profile()` in `common.py` resolves redirects and applies URL-like query param overrides (e.g., `sofar_hybrid.yaml:mod=1`)

---

## Entry Points

**`async_setup(hass, config)` — Domain Setup:**
- Location: `custom_components/solarman/__init__.py:31`
- Triggers: HA loading the integration domain
- Responsibilities: registers HA services, launches background UDP discovery, sets up 15-minute periodic discovery

**`async_setup_entry(hass, config_entry)` — Per-Device Setup:**
- Location: `custom_components/solarman/__init__.py:51`
- Triggers: HA loading a config entry (on HA start or after user adds device)
- Responsibilities: initializes `Coordinator` + `Device`, runs first data refresh, migrates entity unique IDs, forwards platform setup, registers update listener (triggers reload on options change)

**Platform `async_setup_entry` functions:**
- Location: `custom_components/solarman/{platform}.py`
- Pattern: identical across all platforms — queries `coordinator.device.profile.parser.get_entity_descriptions(platform)`, instantiates appropriate entity subclasses, calls `async_add_entities`

---

## Error Handling

**Strategy:** Errors are caught at multiple layers; `TimeoutError` is always re-raised to let HA's coordinator retry logic handle it; other exceptions are logged and swallowed at the device level after the first failure

**Patterns:**
- `Device.get`: catches `ValueError` (invalidated dataset) silently; `TimeoutError` and other exceptions trigger `DeviceState.update(exception=e)` — if state was already failing, error is logged but not re-raised (except on `runtime == 0`)
- `Coordinator._async_update_data`: re-raises `TimeoutError`; wraps other exceptions in `UpdateFailed`
- `Device.execute`: on `TimeoutError`, calls `endpoint.discover()` to refresh IP before re-raising
- `SolarmanWritableEntity.write`: wraps `Device.execute` calls; skips write if current and desired values match
- Services: wrap `Device.execute` in `ServiceValidationError` with translation keys

---

## Cross-Cutting Concerns

**Logging:** Standard Python `logging.getLogger(__name__)` in every module; debug-level logging of all frames sent/received via `@log_call`/`@log_return` decorators in `pysolarman/__init__.py`

**Validation:** `voluptuous` schemas in `config_flow.py` and `services.py`; data-level validation in `ParameterParser.do_validate` (range + deviation checks per register item)

**Authentication:** No HA auth; Stick Logger HTTP interface uses hardcoded Basic Auth `admin:admin` (defined in `const.py` as `LOGGER_AUTH`)

**Unique IDs:** Entities use `slugify(entry_id, key)` format; migration logic in `async_setup_entry` normalizes legacy formats via `async_migrate_entries`

**Translations:** JSON translation files in `custom_components/solarman/translations/` (12 languages); platform-level translation keys derived from entity names via `slugify`

**Diagnostics:** `diagnostics.py` exposes config entry state via HA diagnostics, redacting `identifiers`, `connections`, `serial_number`, `mac`

---

*Architecture analysis: 2026-03-29*
