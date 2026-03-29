# Technology Stack

**Analysis Date:** 2026-03-29

## Languages

**Primary:**
- Python 3 - All integration logic, protocol handling, entity definitions, and tooling

**Secondary:**
- YAML - Inverter definition profiles (`custom_components/solarman/inverter_definitions/*.yaml`)
- JSON - Translations, manifest, HACS config (`custom_components/solarman/translations/*.json`, `custom_components/solarman/manifest.json`, `hacs.json`)

## Runtime

**Environment:**
- Python 3 (CPython) running inside Home Assistant's asyncio event loop
- All I/O is fully async (`asyncio`, `aiofiles`, `aiohttp`)

**Package Manager:**
- None (pip-level). Dependencies are declared in `manifest.json` and installed by HA's integration loader at runtime.
- No `requirements.txt`, `pyproject.toml`, or lockfile present — HA manages the dependency lifecycle.

## Frameworks

**Core:**
- Home Assistant Core ≥ 2025.2.0 — Integration host platform
  - Config entries, entity registry, device registry, coordinator pattern, service calls, DHCP discovery, diagnostics
  - Source: `hacs.json` `"homeassistant": "2025.2.0"`

**Home Assistant Integration Framework:**
- `homeassistant.helpers.update_coordinator.DataUpdateCoordinator` — Polling coordinator, subclassed in `custom_components/solarman/coordinator.py`
- `homeassistant.config_entries.ConfigFlow` / `OptionsFlow` — Config UI, in `custom_components/solarman/config_flow.py`
- `homeassistant.components.diagnostics` — Diagnostics endpoint, in `custom_components/solarman/diagnostics.py`

**Testing:**
- Not applicable — No test framework or test files are present in the repository.

**Build/Dev:**
- GitHub Actions — CI validation (`.github/workflows/ha.yaml`, `.github/workflows/assets.yaml`)
  - `home-assistant/actions/hassfest@master` — Validates HA integration manifest
  - `hacs/action@main` — Validates HACS compatibility
  - `softprops/action-gh-release@v1` — Attaches release ZIP assets
- Release packaging: bash + `zip` in `.github/workflows/assets.yaml` (creates `solarman.zip`)

## Key Dependencies

**Critical:**
- `aiofiles` — Async YAML profile file loading; declared in `custom_components/solarman/manifest.json` `"requirements": ["aiofiles"]`
  - Used in `custom_components/solarman/common.py` via `yaml_open()`

**Bundled (vendored, not installed via pip):**
- `pysolarman` — Custom async Solarman protocol client (vendored in `custom_components/solarman/pysolarman/__init__.py`)
  - Implements the proprietary Solarman V5 TCP framing protocol
  - Houses the `Solarman` class for async TCP connections to inverter stick loggers
- `umodbus` — Vendored Modbus library (in `custom_components/solarman/pysolarman/umodbus/`)
  - Provides Modbus RTU and TCP frame building/parsing
  - Implements function codes: FC01 (Read Coils), FC02 (Read Discrete Inputs), FC03 (Read Holding Registers), FC04 (Read Input Registers), FC05 (Write Single Coil), FC06 (Write Single Register), FC15 (Write Multiple Coils), FC16 (Write Multiple Registers)

**Implicit HA-provided (available in all integrations):**
- `aiohttp` (`ClientSession`, `BasicAuth`, `FormData`) — HTTP requests to stick logger web UI, used in `custom_components/solarman/common.py`
- `voluptuous` — Config flow schema validation, in `custom_components/solarman/config_flow.py` and `custom_components/solarman/services.py`
- `yaml` — YAML parsing (standard library wrapper via HA), used in `custom_components/solarman/common.py`
- `propcache` (`cached_property`) — Property caching in provider layer, used in `custom_components/solarman/provider.py`

**Standard Library:**
- `asyncio` — Async TCP connections, queues, locks, tasks
- `socket` — UDP broadcast discovery
- `struct` — Binary frame packing/unpacking for Modbus and Solarman protocols
- `re` — Regex parsing of stick logger web UI HTML responses
- `bisect` — Sorted register list maintenance in `custom_components/solarman/parser.py`

## Configuration

**Environment:**
- No `.env` files — Configuration is fully managed through HA's config entry system (UI-based)
- User configures: host IP, port (default 8899), transport mode, inverter profile YAML, Modbus slave ID, battery parameters
- Configuration stored in HA's config entries (JSON, managed by HA itself)

**Build:**
- `.github/workflows/assets.yaml` — Release zip packaging
- `.github/workflows/ha.yaml` — CI validation against hassfest and HACS
- `.github/workflows/butler.yaml` — Additional automation workflow

## Platform Requirements

**Development:**
- Home Assistant development environment (devcontainer or full install)
- Python 3 with `aiofiles` available
- No dedicated dev tooling config files (no `.nvmrc`, `.python-version`, `Makefile`, etc.)

**Production:**
- Home Assistant ≥ 2025.2.0 installed and running
- Integration installed via HACS or manual copy into `custom_components/solarman/`
- Network access from HA host to inverter stick logger (LAN, port 8899 by default)
- `iot_class: local_polling` — Communicates exclusively on the local network; no cloud dependency
- Installed via HACS as a zip release (`hacs.json` `"zip_release": true`, filename `solarman.zip`)
- Custom inverter profiles placed in `custom_components/solarman/inverter_definitions/custom/` (persisted across updates per `hacs.json` `"persistent_directory"`)

---

*Stack analysis: 2026-03-29*
