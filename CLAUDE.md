<!-- GSD:project-start source:PROJECT.md -->
## Project

**solarman-logger**

A standalone Python data logger that polls any number of Solarman-protocol devices (inverters, smart meters) defined in a YAML config file and writes their readings to an existing InfluxDB v2 instance. It runs as a Docker container (with docker-compose.yml) and has no dependency on Home Assistant. It uses this repository (ha-solarman) as a reference for the Solarman/Modbus protocol client and YAML device definition format.

**Core Value:** Every configured device is polled on schedule and its data lands in InfluxDB — reliably, without crashing, continuously.

### Constraints

- **Language:** Python — same as reference codebase, no extra translation layer
- **Runtime:** Docker container; docker-compose.yml is a hard requirement
- **Config format:** YAML file mounted into container
- **InfluxDB:** v2 API only (token auth, org/bucket model)
- **Network:** Local LAN only; devices speak Solarman V5 over TCP port 8899 by default
- **No HA dependency:** Must run without Home Assistant installed
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3 - All integration logic, protocol handling, entity definitions, and tooling
- YAML - Inverter definition profiles (`custom_components/solarman/inverter_definitions/*.yaml`)
- JSON - Translations, manifest, HACS config (`custom_components/solarman/translations/*.json`, `custom_components/solarman/manifest.json`, `hacs.json`)
## Runtime
- Python 3 (CPython) running inside Home Assistant's asyncio event loop
- All I/O is fully async (`asyncio`, `aiofiles`, `aiohttp`)
- None (pip-level). Dependencies are declared in `manifest.json` and installed by HA's integration loader at runtime.
- No `requirements.txt`, `pyproject.toml`, or lockfile present — HA manages the dependency lifecycle.
## Frameworks
- Home Assistant Core ≥ 2025.2.0 — Integration host platform
- `homeassistant.helpers.update_coordinator.DataUpdateCoordinator` — Polling coordinator, subclassed in `custom_components/solarman/coordinator.py`
- `homeassistant.config_entries.ConfigFlow` / `OptionsFlow` — Config UI, in `custom_components/solarman/config_flow.py`
- `homeassistant.components.diagnostics` — Diagnostics endpoint, in `custom_components/solarman/diagnostics.py`
- Not applicable — No test framework or test files are present in the repository.
- GitHub Actions — CI validation (`.github/workflows/ha.yaml`, `.github/workflows/assets.yaml`)
- Release packaging: bash + `zip` in `.github/workflows/assets.yaml` (creates `solarman.zip`)
## Key Dependencies
- `aiofiles` — Async YAML profile file loading; declared in `custom_components/solarman/manifest.json` `"requirements": ["aiofiles"]`
- `pysolarman` — Custom async Solarman protocol client (vendored in `custom_components/solarman/pysolarman/__init__.py`)
- `umodbus` — Vendored Modbus library (in `custom_components/solarman/pysolarman/umodbus/`)
- `aiohttp` (`ClientSession`, `BasicAuth`, `FormData`) — HTTP requests to stick logger web UI, used in `custom_components/solarman/common.py`
- `voluptuous` — Config flow schema validation, in `custom_components/solarman/config_flow.py` and `custom_components/solarman/services.py`
- `yaml` — YAML parsing (standard library wrapper via HA), used in `custom_components/solarman/common.py`
- `propcache` (`cached_property`) — Property caching in provider layer, used in `custom_components/solarman/provider.py`
- `asyncio` — Async TCP connections, queues, locks, tasks
- `socket` — UDP broadcast discovery
- `struct` — Binary frame packing/unpacking for Modbus and Solarman protocols
- `re` — Regex parsing of stick logger web UI HTML responses
- `bisect` — Sorted register list maintenance in `custom_components/solarman/parser.py`
## Configuration
- No `.env` files — Configuration is fully managed through HA's config entry system (UI-based)
- User configures: host IP, port (default 8899), transport mode, inverter profile YAML, Modbus slave ID, battery parameters
- Configuration stored in HA's config entries (JSON, managed by HA itself)
- `.github/workflows/assets.yaml` — Release zip packaging
- `.github/workflows/ha.yaml` — CI validation against hassfest and HACS
- `.github/workflows/butler.yaml` — Additional automation workflow
## Platform Requirements
- Home Assistant development environment (devcontainer or full install)
- Python 3 with `aiofiles` available
- No dedicated dev tooling config files (no `.nvmrc`, `.python-version`, `Makefile`, etc.)
- Home Assistant ≥ 2025.2.0 installed and running
- Integration installed via HACS or manual copy into `custom_components/solarman/`
- Network access from HA host to inverter stick logger (LAN, port 8899 by default)
- `iot_class: local_polling` — Communicates exclusively on the local network; no cloud dependency
- Installed via HACS as a zip release (`hacs.json` `"zip_release": true`, filename `solarman.zip`)
- Custom inverter profiles placed in `custom_components/solarman/inverter_definitions/custom/` (persisted across updates per `hacs.json` `"persistent_directory"`)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module files use `snake_case` matching the HA platform they implement: `sensor.py`, `binary_sensor.py`, `config_flow.py`, `coordinator.py`
- All Python files are lowercase with underscores
- YAML inverter definition files use `manufacturer_model.yaml` format: `deye_hybrid.yaml`, `sofar_string.yaml`
- PascalCase throughout: `Coordinator`, `ParameterParser`, `ConfigFlowHandler`, `OptionsFlowHandler`
- HA entity classes are prefixed with `Solarman`: `SolarmanEntity`, `SolarmanSensor`, `SolarmanWritableEntity`, `SolarmanBatterySensor`
- Embedded protocol classes follow the same prefix pattern: `SolarmanCoordinatorEntity`
- Provider/helper classes are suffixed with `Provider`: `ConfigurationProvider`, `EndPointProvider`, `ProfileProvider`
- Exception classes are suffixed with `Error`: `FrameError`
- Protocol classes use `Protocol` suffix: `DiscoveryProtocol`
- `snake_case` for all module-level and class functions
- HA lifecycle functions follow HA naming conventions: `async_setup`, `async_setup_entry`, `async_unload_entry`, `async_migrate_entry`
- HA callback functions prefixed `async_`: `async_step_user`, `async_select_option`, `async_press`, `async_turn_on`
- Private/internal functions prefixed with `_`: `_request`, `_read_registers`, `_read_registers_signed`, `_handle_protocol_frame`
- Decorator helpers use descriptive names: `retry`, `throttle`, `log_call`, `log_return`
- Parser methods use `try_parse_*` prefix: `try_parse_unsigned`, `try_parse_signed`, `try_parse_ascii`
- `snake_case` for local variables and instance attributes
- Module-level logger always named `_LOGGER = getLogger(__name__)` (leading underscore, uppercase)
- Module-level platform detector always `_PLATFORM = get_current_file_name(__name__)`
- Constants in `UPPER_SNAKE_CASE`: `DOMAIN`, `DISCOVERY_PORT`, `TIMINGS_INTERVAL`
- Private instance attributes prefixed with `_`: `self._reader`, `self._lock`, `self._counter_value`
- Constants that are dict/namespace groupings use trailing underscore: `DEFAULT_`, `PARAM_`, `OLD_`
- Short walrus-operator temporaries use single lowercase letters: `v`, `f`, `d`, `e`, `r`, `s`
- Module-wide string constants in `UPPER_SNAKE_CASE` in `const.py`
- Config key constants prefixed `CONF_`: `CONF_HOST`, `CONF_PORT`, `CONF_TRANSPORT`
- Service name constants prefixed `SERVICE_`: `SERVICE_READ_HOLDING_REGISTERS`
- Service param constants prefixed `SERVICES_PARAM_`: `SERVICES_PARAM_DEVICE`
- Deprecation constants prefixed `DEPRECATION_`: `DEPRECATION_SERVICE_WRITE_SINGLE_REGISTER`
- Request-related constants prefixed `REQUEST_`: `REQUEST_CODE`, `REQUEST_START`
- Autodetection constants prefixed `AUTODETECTION_`: `AUTODETECTION_DEYE`
## Code Style
- No automated formatter (no `.prettierrc`, `pyproject.toml`, `.flake8`, or `black` config detected)
- Indentation: 4 spaces (standard Python)
- Keyword arguments consistently use spaces around `=`: `timedelta(minutes = 15)`, `vol.Range(min = 0, max = 65535)` — **this is non-standard** compared to PEP 8, which recommends no spaces around `=` in keyword arguments
- Trailing commas not consistently used in multi-line structures
- Long single-line expressions are preferred over multi-line — many lines exceed 120+ characters (see `coordinator.py:66`, `const.py:87`, `common.py:56`)
- No enforced limit. Lines frequently exceed 120 characters, some reaching 200+
- Example: `custom_components/solarman/common.py:56` contains a 200+ character single expression
- f-strings used throughout for log messages and string building
- No `.format()` style in the integration code (only found in vendored `pysolarman/umodbus/`)
## Import Organization
- `from .const import *` and `from .common import *` are used in all platform files
- This is intentional — `const.py` and `common.py` serve as shared namespaces across the integration
- None. Relative imports only within `custom_components/solarman/`
## Type Annotations
- `from __future__ import annotations` used at the top of most files to enable PEP 563 deferred evaluation
- Return types annotated on HA lifecycle functions: `async def async_setup_entry(...) -> bool`
- Parameters annotated on public methods: `def __init__(self, host: str, port: int | str, transport: str, ...)`
- Union types use `|` syntax (Python 3.10+): `int | float | str | list`, `asyncio.Task | None`
- Complex nested generics on class-level signatures: `DataUpdateCoordinator[dict[str, tuple[int | float | str | list, int | float | None]]]`
- Many private/internal functions lack return type annotations: `def retry(ignore: tuple = ())` has no `-> Callable`
- Walrus operator variables (`:=`) are never annotated
- `dataclass` used in `provider.py` for `ConfigurationProvider`, `EndPointProvider`, `ProfileProvider`
## Error Handling
## Logging
- `_LOGGER.debug(f"...")` — primary level; used for all entry/exit traces and data dumps
- `_LOGGER.info(f"...")` — used sparingly for version reporting on startup
- `_LOGGER.warning(f"...")` — rare; used for unexpected but non-fatal conditions
- `_LOGGER.error(f"...")` — used for parse failures in `parser.py`
- `_LOGGER.exception(f"...")` — used when full stack trace is needed
## Comments
- Block comments (`#`) used to label logical sections within functions — e.g., `# Initiaize coordinator...`, `# Migrations`, `# Forward setup`
- Protocol-level magic numbers and byte structures commented inline
- Commented-out code kept in place with `#` (not deleted): `#self._write_lock = True`, `#await self.coordinator.async_request_refresh()`
- `# TODO` markers present in vendored code (`pysolarman/umodbus/`), not in main integration code
- **Not used in the main integration code** (`custom_components/solarman/`)
- Vendored `pysolarman/umodbus/` has comprehensive reStructuredText-style docstrings with `:param:`, `:return:`, `:raises:` fields — this is inherited from the upstream library
- Used for context on non-obvious logic: `# Double CRC (XXXX0000) correction`, `# Skip...`, `# Bug in HA:`
- Protocol constant groups commented with names: `# Diagnostic functions, only available when using serial line.`
## Module Design
- `const.py` and `common.py` use `from .X import *` pattern — all public names are implicitly exported
- No `__all__` lists defined anywhere in the integration
- Not used. Each module is imported directly by name where needed
- Exception: `from .const import *` and `from .common import *` function as de facto barrel imports
- Custom decorators defined in `common.py`: `retry`, `throttle`
- Custom decorators in `pysolarman/__init__.py`: `log_call`, `log_return`
- All decorators use `@wraps(f)` to preserve wrapped function metadata
- Present in all main integration files except `device.py`, `diagnostics.py`, `discovery.py`
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Single custom component (`solarman`) under `custom_components/` following HA integration conventions
- `ConfigEntry`-per-device model: each inverter/stick logger is one config entry with its own `Coordinator`
- All configuration stored in `ConfigEntry.options` (no `configuration.yaml` data)
- Platforms auto-discovered at runtime: any `{platform}.py` file that exists in the component directory is registered as a supported HA platform
- Data flows via a central `DataUpdateCoordinator` that polls on a fixed 5-second base interval; entity updates are triggered via HA's coordinator callback mechanism
- Modbus register definitions fully data-driven via YAML profiles; no hard-coded register addresses in Python
## Layers
- Purpose: HA lifecycle entry point — setup, teardown, migration, and global service registration
- Location: `custom_components/solarman/__init__.py`
- Contains: `async_setup`, `async_setup_entry`, `async_unload_entry`, `async_migrate_entry`, `async_remove_config_entry_device`
- Depends on: `Coordinator`, `ConfigFlowHandler`, `services.register`, `discovery.discover`
- Dynamically builds `_PLATFORMS` list by scanning the component directory for `{platform}.py` files at import time
- Purpose: HA UI-driven setup and options management for each inverter device
- Location: `custom_components/solarman/config_flow.py`
- Contains: `ConfigFlowHandler` (VERSION=2, MINOR_VERSION=0), `OptionsFlowHandler`, schema definitions, validation helpers
- Supports: manual entry (`async_step_user`), integration discovery (`async_step_integration_discovery`), DHCP discovery (`async_step_dhcp`)
- All configuration is written to `ConfigEntry.options`; `ConfigEntry.data` remains empty
- Purpose: Orchestrates periodic polling and distributes data to all registered entities
- Location: `custom_components/solarman/coordinator.py`
- Contains: `Coordinator(DataUpdateCoordinator[dict[str, tuple]])`
- Key behavior: wraps a `Device` instance; increments an internal `counter` (used as `runtime` clock for request scheduling) on each successful poll; resets counter on failure
- `runtime_data`: `ConfigEntry.runtime_data` is typed as `Coordinator` — entities access it via `config_entry.runtime_data`
- Purpose: Manages the connection lifecycle and executes raw Modbus requests via the pysolarman client
- Location: `custom_components/solarman/device.py`
- Contains: `Device`, `DeviceState`
- Composed of three providers: `EndPointProvider` (network/discovery), `ProfileProvider` (YAML profile + parser), `Solarman` (Modbus TCP client)
- `Device.get(runtime)` → schedules requests via `ProfileProvider.parser.schedule_requests(runtime)` → calls `execute_bulk` → returns parsed dict
- Purpose: Configuration and initialization abstraction layer sitting between `ConfigEntry` and `Device`
- Location: `custom_components/solarman/provider.py`
- Contains:
- Purpose: Async TCP client implementing the Solarman V5 framing protocol over Modbus RTU/TCP
- Location: `custom_components/solarman/pysolarman/__init__.py`
- Contains: `Solarman` class; `PROTOCOL` namespace (frame constants); `FrameError`
- Supports three transport modes selected at runtime via `transport` setter:
- Maintains a persistent async TCP connection with a keeper loop (`_keeper_loop`) that auto-reconnects
- Frame operations use `@throttle` and `@retry` decorators from `common.py`
- Purpose: Vendored/embedded fork of the `umodbus` library providing Modbus PDU construction and parsing
- Location: `custom_components/solarman/pysolarman/umodbus/`
- Contains: `functions.py` (FUNCTION_CODE enum, PDU builders/parsers), `exceptions.py`, `client/tcp.py`, `client/serial/rtu.py`
- Purpose: Loads YAML inverter profiles, builds request schedules, and decodes raw register data into typed entity states
- Location: `custom_components/solarman/parser.py`
- Contains: `ParameterParser`
- Key methods:
- Purpose: HA entity implementations consuming coordinator data
- Location:
- Hierarchy:
- Each platform's `async_setup_entry` instantiates entities from `coordinator.device.profile.parser.get_entity_descriptions(platform)`
- Purpose: UDP-based LAN discovery of Solarman Stick Loggers
- Location: `custom_components/solarman/discovery.py`
- Contains: `DiscoveryProtocol(DatagramProtocol)`, `Discovery`, singleton `_get_discovery`
- Broadcasts `"WIFIKIT-214028-READ"` and `"HF-A11ASSISTHREAD"` to port 48899; responses contain `ip,mac,hostname`
- Singleton instance shared across all config entries via `@singleton.singleton(f"{DOMAIN}_discovery")`
- Also runs on a 15-minute interval from `async_setup` to update existing entries when device IPs change
- Purpose: Exposes raw Modbus read/write operations as HA services for automation use
- Location: `custom_components/solarman/services.py`
- Services: `read_holding_registers`, `read_input_registers`, `write_single_register`, `write_multiple_registers` (plus deprecated aliases)
- All services take a `device` entity ID, resolve it to the config entry's `Coordinator`, and call `Device.execute` directly
- Purpose: Shared helpers, decorators, HA-specific builders, YAML I/O
- Location: `custom_components/solarman/common.py`
- Key items: `retry()` decorator, `throttle()` decorator, `yaml_open()` (async aiofiles), `build_device_info()`, `slugify()`, `lookup_value()`, `group_when()`, `preprocess_descriptions()`, `postprocess_descriptions()`
- Purpose: All domain-wide constants, defaults, autodetection tables, config key names
- Location: `custom_components/solarman/const.py`
- Purpose: YAML data files defining all Modbus registers and entity mappings for each supported inverter model
- Location: `custom_components/solarman/inverter_definitions/`
- 30 built-in profiles; user-custom profiles go in `inverter_definitions/custom/` (HACS persistent directory)
- Profile schema: `info` (manufacturer/model), `default` (update_interval, code, min_span, max_size, digits), `requests` (optional fine-control), `parameters` (groups of items with register definitions)
## Data Flow
- `Coordinator.data`: `dict[str, tuple[state, value]]` — the single source of truth for all entity states; keyed by slugified entity key
- `DeviceState.value`: connection state (-1 = never connected, 0 = error, 1 = connected); drives `SolarmanCoordinatorEntity.available`
- Counter-based scheduling: `Coordinator.counter` increments with each successful poll; `ParameterParser.is_scheduled` checks `runtime % update_interval == 0`
## Key Abstractions
- Purpose: Data-driven register map for each inverter model; decouples hardware differences from Python code
- Location: `custom_components/solarman/inverter_definitions/*.yaml`
- Pattern: each profile item defines `name`, `platform`, `rule` (parse type 1–10), `registers` (Modbus addresses), optional `lookup` table, `scale`/`offset`/`divide`, `validation`, `attributes`
- Purpose: Connection resilience and rate limiting
- Location: `custom_components/solarman/common.py`
- `@retry(ignore=TimeoutError)` — retries once on any non-ignored exception; used on `execute_bulk`
- `@throttle(delay)` — enforces minimum delay between calls; used on `_open_connection` (0.2s) and `_send_receive_frame` (0.1s)
- Purpose: Identify inverter model by reading device type register (0x0000) before loading profile
- Location: `custom_components/solarman/common.py` (`lookup_profile`), `custom_components/solarman/const.py` (AUTODETECTION_* constants)
- Reads Modbus register 0x0000 via Function Code 0x03; maps to a YAML filename via `AUTODETECTION_DEYE` dict
- Purpose: Maintains backwards compatibility when profile filenames change; also allows parameterized profile variants
- Location: `custom_components/solarman/const.py` (`PROFILE_REDIRECT`)
- `process_profile()` in `common.py` resolves redirects and applies URL-like query param overrides (e.g., `sofar_hybrid.yaml:mod=1`)
## Entry Points
- Location: `custom_components/solarman/__init__.py:31`
- Triggers: HA loading the integration domain
- Responsibilities: registers HA services, launches background UDP discovery, sets up 15-minute periodic discovery
- Location: `custom_components/solarman/__init__.py:51`
- Triggers: HA loading a config entry (on HA start or after user adds device)
- Responsibilities: initializes `Coordinator` + `Device`, runs first data refresh, migrates entity unique IDs, forwards platform setup, registers update listener (triggers reload on options change)
- Location: `custom_components/solarman/{platform}.py`
- Pattern: identical across all platforms — queries `coordinator.device.profile.parser.get_entity_descriptions(platform)`, instantiates appropriate entity subclasses, calls `async_add_entities`
## Error Handling
- `Device.get`: catches `ValueError` (invalidated dataset) silently; `TimeoutError` and other exceptions trigger `DeviceState.update(exception=e)` — if state was already failing, error is logged but not re-raised (except on `runtime == 0`)
- `Coordinator._async_update_data`: re-raises `TimeoutError`; wraps other exceptions in `UpdateFailed`
- `Device.execute`: on `TimeoutError`, calls `endpoint.discover()` to refresh IP before re-raising
- `SolarmanWritableEntity.write`: wraps `Device.execute` calls; skips write if current and desired values match
- Services: wrap `Device.execute` in `ServiceValidationError` with translation keys
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
