# Codebase Structure

**Analysis Date:** 2026-03-29

## Directory Layout

```
ha-solarman/
├── custom_components/
│   └── solarman/                     # HA custom component root (all runtime code)
│       ├── __init__.py               # Integration lifecycle (setup/unload/migrate)
│       ├── manifest.json             # HA integration manifest (domain, dependencies, DHCP)
│       ├── const.py                  # All constants, defaults, autodetection tables
│       ├── common.py                 # Shared utilities, decorators, HA helpers
│       ├── config_flow.py            # UI config + options flow (ConfigFlowHandler v2)
│       ├── coordinator.py            # DataUpdateCoordinator wrapper
│       ├── device.py                 # Device connection + request orchestration
│       ├── provider.py               # ConfigurationProvider, EndPointProvider, ProfileProvider
│       ├── discovery.py              # UDP LAN discovery for Stick Loggers
│       ├── parser.py                 # YAML profile loader + register decoder
│       ├── entity.py                 # Base entity classes (read + writable)
│       ├── services.py               # HA service registrations (Modbus read/write)
│       ├── services.yaml             # Service schema descriptions for UI
│       ├── diagnostics.py            # HA diagnostics endpoint
│       ├── sensor.py                 # Sensor platform entities
│       ├── binary_sensor.py          # Binary sensor platform entities
│       ├── switch.py                 # Switch platform entities
│       ├── number.py                 # Number platform entities
│       ├── select.py                 # Select platform entities
│       ├── button.py                 # Button platform entities
│       ├── datetime.py               # DateTime platform entities
│       ├── time.py                   # Time platform entities
│       ├── inverter_definitions/     # YAML inverter register profiles (30 built-in)
│       │   ├── deye_hybrid.yaml
│       │   ├── deye_string.yaml
│       │   ├── deye_micro.yaml
│       │   ├── deye_p3.yaml
│       │   ├── sofar_hybrid.yaml
│       │   ├── sofar_g3.yaml
│       │   ├── solis_hybrid.yaml
│       │   ├── ... (30 total)
│       │   └── custom/               # User-added custom profiles (HACS persistent dir)
│       ├── pysolarman/               # Embedded Solarman V5 protocol + Modbus client
│       │   ├── __init__.py           # Solarman class (async TCP, V5 framing)
│       │   ├── license
│       │   └── umodbus/              # Vendored umodbus library
│       │       ├── __init__.py
│       │       ├── functions.py      # FUNCTION_CODE enum, PDU builders/parsers
│       │       ├── exceptions.py     # Modbus exception classes
│       │       ├── config.py
│       │       ├── route.py
│       │       ├── utils.py
│       │       ├── client/
│       │       │   ├── tcp.py        # Modbus TCP PDU construction
│       │       │   └── serial/
│       │       │       ├── rtu.py    # Modbus RTU PDU construction + CRC
│       │       │       └── redundancy_check.py
│       │       └── server/           # Server-side stubs (not used at runtime)
│       └── translations/             # UI translation strings (12 languages)
│           ├── en.json
│           ├── de.json
│           ├── zh-Hans.json
│           └── ... (12 total)
├── tools/                            # Standalone CLI development/debug utilities
│   ├── discovery.py                  # Standalone UDP discovery script
│   ├── discovery_reply.py            # Discovery reply simulator
│   └── scheduler.py                  # Request scheduling tester
├── .github/
│   ├── workflows/
│   │   ├── ha.yaml                   # HA validation CI workflow
│   │   ├── assets.yaml               # Release asset workflow
│   │   └── butler.yaml               # Repository maintenance workflow
│   └── ISSUE_TEMPLATE/
├── .planning/
│   └── codebase/                     # GSD analysis documents
├── hacs.json                         # HACS integration metadata
├── readme.md
└── license
```

---

## Directory Purposes

**`custom_components/solarman/`:**
- Purpose: The entire HA custom component; everything HA loads at runtime lives here
- Contains: Python integration code, YAML profiles, translations, service definitions
- Key files: `__init__.py` (lifecycle), `coordinator.py` (data hub), `device.py` (connection), `parser.py` (register decoding)

**`custom_components/solarman/inverter_definitions/`:**
- Purpose: Data-driven inverter register maps; one YAML file per inverter family
- Contains: 30 built-in `.yaml` profiles covering Deye, Sofar, Solis, SRNE, Kstar, Solarman, Pylontech, and others
- Key files: `deye_hybrid.yaml` (largest, 2491 lines), `sofar_hybrid.yaml`, `solis_hybrid.yaml`
- `custom/` subdirectory is HACS-persistent (survives updates); user-created profiles go here

**`custom_components/solarman/pysolarman/`:**
- Purpose: Self-contained async Modbus client with Solarman V5 framing; no external `pysolarman` package dependency
- Contains: `Solarman` TCP client class, embedded `umodbus` library
- Note: This is NOT installed from PyPI; it is vendored directly into the component

**`custom_components/solarman/translations/`:**
- Purpose: HA UI localization strings for config flow, entity names, service labels
- Contains: JSON files; `en.json` is the canonical reference
- Supported languages: English, German, Chinese (Simplified), Czech, Catalan, Estonian, Finnish, Italian, Polish, Portuguese (BR), Slovenian, Ukrainian

**`tools/`:**
- Purpose: Development and debugging utilities; not loaded by HA at runtime
- Contains: Standalone Python scripts for testing discovery and scheduler logic

---

## Key File Locations

**Entry Points:**
- `custom_components/solarman/__init__.py`: HA integration lifecycle (`async_setup`, `async_setup_entry`, `async_unload_entry`, `async_migrate_entry`)
- `custom_components/solarman/config_flow.py`: User-facing configuration UI (`ConfigFlowHandler`, `OptionsFlowHandler`)

**Configuration:**
- `custom_components/solarman/manifest.json`: Integration metadata — domain name, HA version requirements, DHCP MAC patterns, external Python requirements (`aiofiles`)
- `custom_components/solarman/const.py`: All constants — domain ID, defaults dict, autodetection tables, config key names, service names, timing constants
- `custom_components/solarman/services.yaml`: Service UI descriptions consumed by HA frontend
- `hacs.json`: HACS release config — zip packaging, minimum HA version (`2025.2.0`), persistent directory declaration

**Core Logic:**
- `custom_components/solarman/coordinator.py`: `Coordinator` — tick-counter-based polling orchestrator
- `custom_components/solarman/device.py`: `Device` — connection lifecycle + request execution
- `custom_components/solarman/provider.py`: `ConfigurationProvider`, `EndPointProvider`, `ProfileProvider` — initialization chain
- `custom_components/solarman/parser.py`: `ParameterParser` — profile loading, request scheduling, register decoding
- `custom_components/solarman/common.py`: Shared utilities — `retry`, `throttle`, `yaml_open`, `build_device_info`, `slugify`, `preprocess_descriptions`, `postprocess_descriptions`, `lookup_profile`
- `custom_components/solarman/pysolarman/__init__.py`: `Solarman` — async TCP client with V5/Modbus protocol support
- `custom_components/solarman/pysolarman/umodbus/functions.py`: `FUNCTION_CODE` enum + Modbus PDU construction/parsing

**Entity Base Classes:**
- `custom_components/solarman/entity.py`: `SolarmanCoordinatorEntity`, `SolarmanEntity`, `SolarmanWritableEntity`

**Platform Implementations:**
- `custom_components/solarman/sensor.py`: 173 lines — most complex; includes battery capacity estimation, restore/persistent sensors, nested device sensors
- `custom_components/solarman/select.py`: 144 lines — includes `SolarmanMode` and `SolarmanCloud` for logger management
- `custom_components/solarman/switch.py`: 107 lines — includes `SolarmanAccessPoint` for logger WiFi AP control
- `custom_components/solarman/button.py`: 67 lines — includes `SolarmanRestart` for logger reboot
- `custom_components/solarman/binary_sensor.py`: 60 lines — includes `SolarmanConnectionSensor`
- `custom_components/solarman/number.py`: 68 lines — scale/offset/range support
- `custom_components/solarman/datetime.py`: 60 lines — multi-register datetime packing
- `custom_components/solarman/time.py`: 62 lines — hex/decimal time format handling

**Support:**
- `custom_components/solarman/discovery.py`: `Discovery` singleton + `DiscoveryProtocol` (UDP datagram)
- `custom_components/solarman/services.py`: HA service handler functions + `register()` entry point
- `custom_components/solarman/diagnostics.py`: HA diagnostics integration

**Inverter Profiles (representative):**
- `custom_components/solarman/inverter_definitions/deye_hybrid.yaml`: Deye hybrid inverters; 2491 lines; most complete reference
- `custom_components/solarman/inverter_definitions/deye_string.yaml`: Deye string inverters
- `custom_components/solarman/inverter_definitions/sofar_hybrid.yaml`: Sofar hybrid inverters
- `custom_components/solarman/inverter_definitions/sofar_g3.yaml`: Sofar G3 series

**Testing:**
- No test files present in this repository

---

## Module Organization

**Import Dependency Order (bottom → top):**

```
umodbus/          (no internal deps)
    ↓
pysolarman/       (imports umodbus; imports common for retry/throttle/create_task/format)
    ↓
const.py          (no internal deps)
    ↓
common.py         (imports const)
    ↓
discovery.py      (imports const, common)
parser.py         (imports const, common)
    ↓
provider.py       (imports const, common, discovery, parser)
    ↓
device.py         (imports const, common, provider, pysolarman)
    ↓
coordinator.py    (imports const, common, device, provider)
    ↓
entity.py         (imports const, common, services, coordinator, pysolarman.umodbus.functions)
    ↓
services.py       (imports const, coordinator, pysolarman.umodbus.functions)
    ↓
{platform}.py     (imports const, common, services, entity, coordinator)
    ↓
__init__.py       (imports const, common, services, discovery, coordinator, config_flow)
```

**Wildcard imports:** `__init__.py`, `entity.py`, `services.py`, and all platform files use `from .const import *` and `from .common import *`. These are the only two modules that are star-imported; all other modules are imported by name.

---

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `config_flow.py`, `binary_sensor.py`)
- YAML profiles: `{manufacturer}_{model}.yaml` in lowercase with underscores (e.g., `deye_hybrid.yaml`, `sofar_g3.yaml`)
- Translation files: BCP-47 locale codes (e.g., `en.json`, `zh-Hans.json`, `pt-BR.json`)

**Classes:**
- Integration classes: `Solarman{Role}` prefix (e.g., `SolarmanEntity`, `SolarmanWritableEntity`, `SolarmanSensor`)
- Provider classes: `{Role}Provider` (e.g., `ConfigurationProvider`, `EndPointProvider`, `ProfileProvider`)
- Special built-in entities (not from YAML): `Solarman{Name}` where Name is functional (e.g., `SolarmanConnectionSensor`, `SolarmanAccessPoint`, `SolarmanRestart`, `SolarmanIntervalSensor`)

**Platform detection:**
- Each platform file sets `_PLATFORM = get_current_file_name(__name__)` at module level; this string is passed to `parser.get_entity_descriptions(_PLATFORM)` to filter items by platform

**Entity keys:**
- Generated by `entity_key(item)` → `slugify(item["name"], item["platform"])` (e.g., `"Battery Power"` + `"sensor"` → `"battery_power_sensor"`)
- Unique IDs: `slugify(config_entry.entry_id, entity_key)` — e.g., `"{entry_id}_battery_power_sensor"`

---

## Where to Add New Code

**New inverter support:**
- Add a YAML file to `custom_components/solarman/inverter_definitions/` following the profile schema
- If it is a redirect/variant of an existing profile, add an entry to `PROFILE_REDIRECT` in `custom_components/solarman/const.py`
- If it is a new Deye device type, add entries to `AUTODETECTION_DEYE` in `custom_components/solarman/const.py`

**New HA platform (e.g., `event.py`):**
- Create `custom_components/solarman/{platform}.py` with `async_setup_entry` and `async_unload_entry` functions
- The platform is automatically discovered and registered by `__init__.py` (no manual `_PLATFORMS` list update needed)
- Add entity class inheriting from `SolarmanEntity` or `SolarmanWritableEntity` plus the HA platform base

**New entity type within an existing platform:**
- Add item definitions to the relevant YAML profile with the correct `platform` field
- If special Python behavior is needed (like `SolarmanBatterySensor`), add a subclass in the platform file and update the `_create_entity` factory function

**New utility functions:**
- Generic Python helpers: `custom_components/solarman/common.py`
- Domain constants: `custom_components/solarman/const.py`

**New HA service:**
- Add handler function to `custom_components/solarman/services.py`
- Call `hass.services.async_register` inside the `register(hass)` function
- Add schema description block to `custom_components/solarman/services.yaml`
- Add service name constant to `custom_components/solarman/const.py`

**User-facing text / translations:**
- Add keys to `custom_components/solarman/translations/en.json` first
- Mirror keys to other language files as needed

**Custom user profiles:**
- Users place `.yaml` files in `{config_dir}/custom_components/solarman/inverter_definitions/custom/`
- These are listed in the config flow with a `custom/` prefix

---

## Special Directories

**`custom_components/solarman/inverter_definitions/custom/`:**
- Purpose: User-provided inverter profile overrides and additions
- Generated: No — created by user
- Committed: No — excluded from repo; HACS marks it as `persistent_directory` so it survives HACS updates

**`custom_components/solarman/pysolarman/`:**
- Purpose: Vendored protocol library (Solarman V5 + umodbus); no external PyPI dependency
- Generated: No
- Committed: Yes — full source is in the repo

**`.planning/`:**
- Purpose: GSD analysis and planning documents
- Generated: Yes — by GSD tooling
- Committed: Per project convention

---

*Structure analysis: 2026-03-29*
