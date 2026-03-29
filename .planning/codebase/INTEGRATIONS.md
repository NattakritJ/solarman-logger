# External Integrations

**Analysis Date:** 2026-03-29

## Overview

This is a Home Assistant custom component with `iot_class: local_polling`. All communication is local-network-only — no cloud APIs, no external services, no webhooks. The integration communicates directly with solar inverter hardware over a LAN.

---

## Hardware Protocols

### Solarman V5 Protocol (Primary)
- **What it is:** Proprietary binary framing protocol used by Solarman "Stick Logger" WiFi data loggers attached to inverters
- **Implementation:** `custom_components/solarman/pysolarman/__init__.py` — the `Solarman` class
- **Transport:** Async TCP over `asyncio.open_connection()` (persistent connection with keep-alive loop)
- **Default port:** `8899` (configurable, defined in `custom_components/solarman/const.py` `DEFAULT_[CONF_PORT]`)
- **Frame structure:**
  - Start byte: `0xA5`
  - End byte: `0x15`
  - Contains: 2-byte length, control code, sequence number, 4-byte serial number, embedded Modbus PDU, checksum
  - Control codes: HANDSHAKE (0x41), DATA (0x42), INFO (0x43), REQUEST (0x45), HEARTBEAT (0x47), REPORT (0x48)
- **Transport modes** (selectable per device):
  - `tcp` — Solarman V5 wrapped Modbus RTU frames (default)
  - `modbus_tcp` — Standard Modbus TCP (MBAP header, no V5 wrapper)
  - `modbus_rtu` — Raw Modbus RTU frames over TCP

### Modbus RTU / TCP (Underlying Protocol)
- **What it is:** Standard Modbus protocol for reading/writing inverter registers
- **Implementation:** `custom_components/solarman/pysolarman/umodbus/` (vendored)
  - RTU frame builder/parser: `custom_components/solarman/pysolarman/umodbus/client/serial/rtu.py`
  - TCP frame builder/parser: `custom_components/solarman/pysolarman/umodbus/client/tcp.py`
  - CRC calculation: `custom_components/solarman/pysolarman/umodbus/client/serial/redundancy_check.py`
- **Supported function codes:**
  - FC01: Read Coils
  - FC02: Read Discrete Inputs
  - FC03: Read Holding Registers (default read code: `0x03`)
  - FC04: Read Input Registers
  - FC05: Write Single Coil
  - FC06: Write Single Register
  - FC15: Write Multiple Coils
  - FC16: Write Multiple Registers
- **Slave ID:** Configurable via `CONF_MB_SLAVE_ID`, default `1`

---

## Device Discovery

### UDP Broadcast Discovery
- **Protocol:** Custom UDP broadcast on port `48899`
- **Implementation:** `custom_components/solarman/discovery.py` — `Discovery` and `DiscoveryProtocol` classes
- **Trigger messages:** `"WIFIKIT-214028-READ"` and `"HF-A11ASSISTHREAD"` (defined in `custom_components/solarman/const.py`)
- **Response format:** Comma-separated: `IP,MAC,hostname` (hostname contains the device serial number)
- **Interval:** Every 15 minutes (defined as `DISCOVERY_INTERVAL = timedelta(minutes=15)`)
- **Scope:** Broadcasts to all enabled non-loopback, non-global LAN adapters via `homeassistant.components.network`

### DHCP Discovery
- **Mechanism:** HA's built-in DHCP watcher
- **Trigger:** MAC address prefix `E8FDF8*` (Solarman devices) or any registered device
- **Declared in:** `custom_components/solarman/manifest.json` `"dhcp"` array

---

## Stick Logger Web UI (HTTP)
- **What it is:** HTTP interface to read and reconfigure the Solarman stick logger's network settings
- **Implementation:** `custom_components/solarman/common.py` (`request()` function) and `custom_components/solarman/provider.py` (`EndPointProvider.discover()`)
- **Client:** `aiohttp.ClientSession` with `BasicAuth("admin", "admin")` (hardcoded default credentials in `custom_components/solarman/const.py` as `LOGGER_AUTH`)
- **Endpoints accessed:**
  - `GET http://{host}/hide_set_edit.html` (`LOGGER_SET`) — Read current network settings
  - `POST http://{host}/do_cmd.html` (`LOGGER_CMD`) — Apply new settings
  - `GET http://{host}/success.html` (`LOGGER_SUCCESS`) — Confirm success
  - `POST http://{host}/restart.html` (`LOGGER_RESTART`) — Restart the logger
- **Config URL exposed in HA:** `http://{host}/config_hide.html` (shown in device info)
- **Purpose:** Auto-configures logger to listen on port 8899 in TCP server mode if misconfigured

---

## Home Assistant Platform Integration

### Config Entry System
- **Type:** `config_flow: true`, `integration_type: device`
- **Version:** 2 (minor version 0); migration logic in `custom_components/solarman/__init__.py`
- **Implementation:** `custom_components/solarman/config_flow.py`
- **Flow:** User enters host/port/transport/profile → `ConfigFlowHandler` → `OptionsFlowHandler` for reconfiguration

### Entity Platforms
All entity platforms are auto-detected by scanning for `{platform}.py` files at load time (`custom_components/solarman/__init__.py`):
- `custom_components/solarman/sensor.py` — `SensorEntity`, `RestoreSensor` (primary data platform)
- `custom_components/solarman/binary_sensor.py` — Binary sensor entities
- `custom_components/solarman/number.py` — Writable numeric entities
- `custom_components/solarman/select.py` — Writable select/enum entities
- `custom_components/solarman/switch.py` — Writable switch entities
- `custom_components/solarman/button.py` — Writable button entities
- `custom_components/solarman/time.py` — Time entities
- `custom_components/solarman/datetime.py` — Datetime entities

### DataUpdateCoordinator
- **Update cycle:** 5-second base tick (`TIMINGS_INTERVAL = 5` in `custom_components/solarman/const.py`)
- **Request scheduling:** Profile-driven — individual sensors declare their own `update_interval` (e.g., power sensors: 5s, static info: 1 hour)
- **Implementation:** `custom_components/solarman/coordinator.py`

### HA Services (Exposed to Automations)
Registered in `custom_components/solarman/services.py`, described in `custom_components/solarman/services.yaml`:
- `solarman.read_holding_registers` — Read FC03 registers by address/count
- `solarman.read_input_registers` — Read FC04 registers by address/count
- `solarman.write_single_register` — Write FC06 single register
- `solarman.write_multiple_registers` — Write FC16 multiple registers
- `solarman.write_holding_register` (deprecated alias)
- `solarman.write_multiple_holding_registers` (deprecated alias)

### HA Dependencies
- `network` — Used for LAN adapter enumeration during UDP discovery
- `dhcp` — Used for DHCP-triggered auto-discovery of new devices

### Diagnostics
- **Implementation:** `custom_components/solarman/diagnostics.py`
- Redacts: `identifiers`, `connections`, `serial_number`, `mac`, `device_serial_number_sensor`

---

## Inverter Device Profiles

### YAML Profile System
- **Location:** `custom_components/solarman/inverter_definitions/` (bundled), `custom_components/solarman/inverter_definitions/custom/` (user-provided, HACS-persistent)
- **Parser:** `custom_components/solarman/parser.py` — `ParameterParser` class
- **Format:** YAML files defining `info`, `default`, `requests`, and `parameters` (groups of sensor items)
- **Supported inverter families (bundled profiles):**
  - Deye: `deye_hybrid.yaml`, `deye_string.yaml`, `deye_micro.yaml`, `deye_p3.yaml`
  - Sofar: `sofar_hybrid.yaml`, `sofar_g3.yaml`, `sofar_g3hyd.yaml`, `sofar_string.yaml`
  - Solis: `solis_hybrid.yaml`, `solis_1p-5g.yaml`, `solis_3p-4g.yaml`, `solis_3p-5g.yaml`, `solis_s6-gr1p.yaml`
  - Afore: `afore_hybrid.yaml`, `afore_2mppt.yaml`, `afore_BNTxxxKTL-2mppt.yaml`
  - Kstar: `kstar_hybrid.yaml`
  - Hinen: `hinen_hybrid.yaml`
  - Pylontech: `pylontech_force.yaml`
  - Anenji: `anenji_hybrid.yaml`
  - Renon: `renon_ifl.yaml`
  - INVT: `invt_xd-tl.yaml`
  - MegaRevo: `megarevo_r-3h.yaml`
  - Swatten: `swatten_sih-th.yaml`
  - SRNE: `srne_asf.yaml`
  - CHINT: `chint_cps-scetl.yaml`
  - MaxGE: `maxge_string.yaml`
  - TSUN: `tsun_tsol-ms.yaml`
  - AstroEnergy: `astro-energy_micro.yaml`
  - Solarman (meter): `solarman_dtsd422-d3.yaml`

### Auto-Detection
- **Mechanism:** Reads Deye-specific registers (`0x0000`–`0x0016`) to identify device type
- **Implementation:** `custom_components/solarman/common.py` (`lookup_profile()`) and constants in `custom_components/solarman/const.py` (`AUTODETECTION_*`)
- **Supported auto-detected families:** Deye String, Deye Hybrid (P1), Deye Micro, Deye P3 (3-phase)
- **Profile redirects:** Legacy profile names mapped to current ones via `PROFILE_REDIRECT` in `custom_components/solarman/const.py`

---

## Authentication & Identity

**Auth Provider:** None — No user authentication. HA handles all access control.
**Device identification:** Serial number (from UDP discovery response hostname field) + MAC address (from UDP discovery or DHCP)
**Unique ID strategy:** Derived from `config_entry.entry_id` — no cloud account required

---

## Data Storage

**Databases:** None — No direct database connections. State persistence uses HA's built-in recorder.
**File Storage:** YAML profile files on the HA filesystem (read async via `aiofiles`)
**Caching:** `propcache.cached_property` for configuration provider properties; in-memory result caching in `ParameterParser`
**State restore:** `RestoreSensor` / `SolarmanPersistentSensor` for energy accumulation sensors (survives HA restarts)

---

## Monitoring & Observability

**Error Tracking:** None — No external error tracking service.
**Logs:** Python `logging` via `getLogger(__name__)` throughout all modules; all entries tagged with `[{host}]` prefix for device correlation.
**Diagnostics:** HA diagnostics endpoint (`custom_components/solarman/diagnostics.py`) — exposes config, device info, and current data with PII redacted.

---

## CI/CD & Deployment

**Hosting:** HACS (Home Assistant Community Store)
- `hacs.json` declares `"zip_release": true` with filename `solarman.zip`

**CI Pipeline:** GitHub Actions
- `.github/workflows/ha.yaml` — Runs `hassfest` (HA integration validation) and `hacs` validation on push/PR/daily schedule
- `.github/workflows/assets.yaml` — On release, patches version into `manifest.json` and attaches zip to GitHub release
- `.github/workflows/butler.yaml` — Additional release automation

**Distribution:** GitHub Releases as `solarman.zip` — installed via HACS

---

## Webhooks & Callbacks

**Incoming:** None
**Outgoing:** None — Integration initiates all communication to the inverter; no push/callback mechanism exists.

---

## Tools Directory

Standalone Python scripts for development/debugging (not part of the HA integration):
- `tools/discovery.py` — Standalone UDP discovery tool
- `tools/discovery_reply.py` — Discovery reply simulator
- `tools/scheduler.py` — Request scheduling utility

---

*Integration audit: 2026-03-29*
