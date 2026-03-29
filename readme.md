# solarman-logger

A standalone Python data logger that polls Solarman-protocol devices (inverters, smart meters) over your local network and writes their readings to InfluxDB v2. Runs as a Docker container with no dependency on Home Assistant.

## Features

- Polls any number of Solarman V5 / Modbus devices on a configurable schedule
- Writes all readings to InfluxDB v2 (token auth, org/bucket model)
- 31 built-in inverter profiles (Deye, Sofar, Solis, Afore, and more)
- Automatic exponential backoff on device failures (capped at 5 minutes)
- Solar-aware logging: suppresses noisy offline warnings for solar devices that sleep overnight
- Graceful Docker shutdown via SIGTERM handling
- Fail-fast startup: validates config and InfluxDB connectivity before polling begins

## Requirements

- Docker and Docker Compose
- InfluxDB v2 instance (accessible from the host running the container)
- One or more Solarman-protocol devices on your LAN (default TCP port 8899)

## Quick Start

### 1. Clone the repository

```bash
git clone <repo-url> solarman-logger
cd solarman-logger
```

### 2. Create your configuration

```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml` with your InfluxDB credentials and device details:

```yaml
influxdb:
  url: "http://192.168.1.50:8086"
  org: "my-org"
  bucket: "solar"
  token: "my-influxdb-token"

defaults:
  poll_interval: 30   # seconds -- global default, can be overridden per device

devices:
  - name: "Inverter 1"
    type: "inverter"
    host: "192.168.1.100"
    port: 8899
    serial: 1234567890
    slave: 1
    profile: "deye_micro.yaml"

  - name: "Smart Meter"
    type: "meter"
    host: "192.168.1.101"
    port: 8899
    serial: 9876543210
    slave: 1
    poll_interval: 60    # override: poll meter every 60s
    profile: "ddzy422-d2.yaml"
```

### 3. Start the container

```bash
docker compose up -d
```

View logs:

```bash
docker compose logs -f
```

## Configuration Reference

### `influxdb` (required)

| Field    | Type   | Description                        |
|----------|--------|------------------------------------|
| `url`    | string | InfluxDB v2 URL (e.g. `http://host:8086`) |
| `org`    | string | InfluxDB organization              |
| `bucket` | string | Target bucket for writes           |
| `token`  | string | InfluxDB API token                 |

### `defaults` (required)

| Field           | Type | Description                               |
|-----------------|------|-------------------------------------------|
| `poll_interval` | int  | Global polling interval in seconds        |

### `devices[]` (required, at least one)

| Field           | Type   | Required | Default        | Description                                   |
|-----------------|--------|----------|----------------|-----------------------------------------------|
| `name`          | string | Yes      |                | Device display name (used as InfluxDB measurement name) |
| `type`          | string | Yes      |                | Device type tag (e.g. `inverter`, `meter`)    |
| `host`          | string | Yes      |                | Device IP address on your LAN                 |
| `port`          | int    | No       | `8899`         | Solarman TCP port                             |
| `serial`        | int    | Yes      |                | Solarman stick logger serial number           |
| `slave`         | int    | No       | `1`            | Modbus slave ID                               |
| `poll_interval` | int    | No       | global default | Per-device polling interval override (seconds)|
| `profile`       | string | Yes      |                | Inverter definition YAML filename             |

## Supported Inverter Profiles

The `config/inverter_definitions/` directory contains 31 built-in profiles:

| Manufacturer   | Profiles                                                              |
|----------------|-----------------------------------------------------------------------|
| Afore          | `afore_2mppt.yaml`, `afore_BNTxxxKTL-2mppt.yaml`, `afore_hybrid.yaml` |
| Anenji         | `anenji_hybrid.yaml`                                                  |
| Astro Energy   | `astro-energy_micro.yaml`                                             |
| Chint          | `chint_cps-scetl.yaml`                                                |
| Deye           | `deye_hybrid.yaml`, `deye_micro.yaml`, `deye_p3.yaml`, `deye_string.yaml` |
| Hinen          | `hinen_hybrid.yaml`                                                   |
| INVT           | `invt_xd-tl.yaml`                                                    |
| KStar          | `kstar_hybrid.yaml`                                                   |
| MaxGe          | `maxge_string.yaml`                                                   |
| Megarevo       | `megarevo_r-3h.yaml`                                                  |
| Pylontech      | `pylontech_force.yaml`                                                |
| Renon          | `renon_ifl.yaml`                                                      |
| Sofar          | `sofar_g3.yaml`, `sofar_g3hyd.yaml`, `sofar_hybrid.yaml`, `sofar_string.yaml` |
| Solarman       | `solarman_dtsd422-d3.yaml`, `ddzy422-d2.yaml`                        |
| Solis          | `solis_1p-5g.yaml`, `solis_3p-4g.yaml`, `solis_3p-5g.yaml`, `solis_hybrid.yaml`, `solis_s6-gr1p.yaml` |
| SRNE           | `srne_asf.yaml`                                                       |
| Swatten        | `swatten_sih-th.yaml`                                                 |
| TSUN           | `tsun_tsol-ms.yaml`                                                   |

## InfluxDB Data Format

Each poll cycle writes a single point per device:

- **Measurement**: device `name` from config
- **Tags**: `device_name`, `device_type`
- **Fields**: all numeric readings as floats, string readings as strings
- **Timestamp**: InfluxDB server time (write time)

Example Flux query:

```flux
from(bucket: "solar")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "Inverter 1")
  |> filter(fn: (r) => r._field == "ac_power_sensor")
```

## Adding a Custom Inverter Profile

If your device is not covered by the built-in profiles, you can create a custom one.

### 1. Profile structure

Create a YAML file in `config/inverter_definitions/` following this structure:

```yaml
info:
  manufacturer: "YourBrand"
  model: "YourModel"

default:
  update_interval: 5    # base scheduling interval in seconds
  code: 0x03            # default Modbus function code (0x03 = read holding registers, 0x04 = read input registers)
  min_span: 25          # max gap between registers before splitting into separate requests
  max_size: 125         # max registers per single Modbus request
  digits: 6             # decimal precision for numeric values

parameters:
  - group: "Solar Production"
    update_interval: 5   # override update interval for this group (optional)
    items:
      - name: "PV Power"
        platform: "sensor"       # entity type: sensor, binary_sensor, number, switch, etc.
        rule: 1                  # parse rule (see below)
        registers: [0x006A]      # Modbus register address(es)
        uom: "W"                 # unit of measurement
        scale: 0.1               # multiply raw value by this

      - name: "Daily Production"
        platform: "sensor"
        rule: 1
        registers: [0x003C]
        uom: "kWh"
        scale: 0.1
        divide: 10
```

### 2. Parse rules

| Rule | Type             | Description                                    |
|------|------------------|------------------------------------------------|
| 1    | Unsigned integer | Standard unsigned register read                |
| 2    | Signed integer   | Two's complement signed read                   |
| 3    | Unsigned (custom)| Unsigned with multi-sensor composite            |
| 4    | Signed (custom)  | Signed with multi-sensor composite              |
| 5    | ASCII            | Decode registers as ASCII characters            |
| 6    | Bits             | Return hex representation of register bits      |
| 7    | Version          | Parse as firmware version string                |
| 8    | Datetime         | Parse registers as date/time value              |
| 9    | Time             | Parse registers as time-only value              |
| 10   | Raw              | Return raw register values as list              |

### 3. Optional field modifiers

- `scale`: multiply raw value (e.g. `0.1` to convert deciWatts to Watts)
- `offset`: subtract from raw value before scaling
- `divide`: integer division of raw value
- `mask`: bitwise AND mask
- `bit`: extract a single bit position
- `lookup`: map raw values to human-readable strings
- `validation`: min/max range checks, deviation detection
- `range`: min/max with optional default fallback

### 4. Finding your register addresses

- Check your inverter's Modbus protocol documentation (usually a PDF from the manufacturer)
- Use the existing profiles as reference -- find a similar inverter model and adapt
- Common register ranges: `0x0000-0x000F` for device info, `0x003C-0x0070` for production data, `0x0070+` for grid/load data

### 5. Reference the profile in your config

```yaml
devices:
  - name: "My Custom Inverter"
    type: "inverter"
    host: "192.168.1.200"
    serial: 1122334455
    profile: "my_custom_inverter.yaml"
```

## Running Without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Option A: use --config flag
python -m solarman_logger --config config/config.yaml

# Option B: use environment variable
CONFIG_PATH=config/config.yaml python -m solarman_logger
```

## Running Tests

```bash
pip install pytest
pytest solarman_logger/tests/
```

## Architecture

```
solarman_logger/
  __main__.py          # Package entry point
  main.py              # CLI parsing, startup, shutdown orchestration
  config.py            # YAML config loading and validation
  poller.py            # Per-device async polling loop with backoff
  writer.py            # InfluxDB v2 write adapter
  parser.py            # Register data parsing (ported from ha-solarman)
  common.py            # Shared helpers: retry, throttle, YAML I/O, slugify
  const.py             # Constants and defaults
  logging_setup.py     # Structured logging to stdout
  pysolarman/          # Async Solarman V5 protocol client (vendored)
    umodbus/           # Modbus PDU library (vendored)

config/
  config.example.yaml          # Example configuration
  inverter_definitions/        # YAML register maps for supported devices
```

### Data Flow

```
config.yaml
    |
    v
main.py  -->  config.py (validate)  -->  InfluxDBWriter (health check)
    |
    v
poller.run_all()
    |
    +-- DeviceWorker (per device)
    |       |
    |       +-- ParameterParser (load profile, schedule requests)
    |       +-- Solarman client (TCP connect, send/receive frames)
    |       |
    |       +-- poll cycle:
    |             schedule_requests(runtime) -> execute Modbus -> parse response
    |             |
    |             v
    |       data_callback(device_name, parsed_data)
    |             |
    |             v
    +--------> InfluxDBWriter.write_callback()  -->  InfluxDB v2
```

## License

This project uses code from [ha-solarman](https://github.com/davidrapan/ha-solarman) as a reference for the Solarman/Modbus protocol client and YAML device definition format.
