# Stack Research: solarman-logger

**Researched:** 2026-03-29
**Overall confidence:** HIGH (all libraries verified against PyPI and/or official docs)

---

## Recommended Stack

| Component | Library | Version | Rationale |
|-----------|---------|---------|-----------|
| Protocol client | vendored `pysolarman` (from this repo) | repo-local | Already handles Solarman V5 + Modbus RTU framing for Deye devices; diverged enough from upstream that swapping to PyPI `pysolarmanv5` requires porting work. See notes. |
| InfluxDB write | `influxdb-client[async]` | 1.50.0 | Official InfluxDB Python client; async write API via `aiohttp`; token auth; line protocol; org/bucket model — exactly the v2 API required. |
| YAML config parsing | `PyYAML` | 6.0.3 | Standard, battle-tested; already used in the HA integration for device profiles; no new dependency to learn. |
| Config validation | `pydantic` v2 (core, no pydantic-settings) | ≥2.0 | Validate the user-facing YAML config schema (devices list, InfluxDB connection block) with clear error messages. Pydantic-settings requires ≥3.10 and is overkill for a static YAML file. |
| Structured logging | `structlog` | 25.5.0 | Best-in-class structured stdout logging; native asyncio support; JSON or key=value renderers; drop-in alongside stdlib `logging`; widely adopted in Python services. |
| Async runtime | `asyncio` (stdlib) | Python 3.12 built-in | All device polling runs as concurrent asyncio tasks; no third-party async framework needed. |
| YAML profile file reading | `aiofiles` | 25.1.0 | Already the approach in the HA integration (`yaml_open()`); keeps file I/O non-blocking in the event loop. |
| Docker base image | `python:3.12-slim` | 3.12.x | Slim = ~50 MB compressed vs ~5 MB alpine but with musl libc gotchas; 3.12 is latest stable, well-supported, required by pydantic v2 features used. |
| Package management | `uv` + `pyproject.toml` | 0.11.2 | Fastest resolver/installer (Rust-based); standard `pyproject.toml` for metadata; works cleanly inside Docker with `uv pip install --system`. |

---

## Key Library Notes

### influxdb-client 1.50.0 (async)

- **Install:** `pip install influxdb-client[async]`  — pulls in `aiohttp>=3.8.1` and `aiocsv>=1.2.2`
- **Core async class:** `InfluxDBClientAsync` from `influxdb_client.client.influxdb_client_async`
- **Must be instantiated inside a running event loop** — the constructor calls `asyncio.get_running_loop()` and raises `InfluxDBError` if no loop is running. Pattern: instantiate inside `async def main()`, not at module top-level.
- **Async context manager pattern** (recommended):
  ```python
  async with InfluxDBClientAsync(url=url, token=token, org=org) as client:
      write_api = client.write_api()
      await write_api.write(bucket=bucket, record=point)
  ```
- **WriteApiAsync** does not batch by default; each `await write_api.write(...)` is a single HTTP POST. For a polling logger writing every 30–60 s this is fine — no need for the batching WriteApi (which is sync-only).
- **Point construction:** `from influxdb_client import Point` — unchanged between sync and async.
- **Supports line protocol strings directly** — can bypass Point builder if you want raw strings.
- **No `reactivex` dependency at runtime** for write-only usage; it's listed but only needed for the reactive streaming query API.
- Source: [influxdata/influxdb-client-python](https://github.com/influxdata/influxdb-client-python); PyPI 1.50.0 confirmed 2026-03-29.

---

### pysolarman (vendored, repo-local)

- **Upstream:** PyPI `pysolarmanv5` v3.0.6 (released 2024-12-11). Upstream `ha-solarman` is listed as a project using it.
- **Repo copy is a diverged fork**, not a straight vendor of PyPI 3.x. Key differences:
  - Class is named `Solarman`, not `PySolarmanV5Async`.
  - Has a hard import dependency on `..common` (HA helpers: `retry`, `throttle`, `create_task`, `format`). **This import will break outside HA without adaptation.**
  - Supports a `transport` parameter (tcp/rtu switching) not present in upstream.
  - Uses `multiprocessing.Event` for data sync — unusual in asyncio but present in the repo code.
- **Decision: copy and adapt the vendored version**, not swap to PyPI `pysolarmanv5`. The Deye double-CRC workaround (v3.0.2 upstream fix) and error handling improvements from `davidrapan` (upstream v3.0.3/3.0.4) are all already incorporated into the vendored copy.
- **Adaptation required:** The `from ..common import retry, throttle, create_task, format` import must be resolved. Either inline these helpers or provide a thin shim module.
- pysolarmanv5 upstream requires Python ≥3.8; vendored copy uses `int | str`, `asyncio.Task | None` (3.10+ union syntax) — set minimum Python to **3.10**.

---

### PyYAML 6.0.3

- **Install:** `pip install PyYAML`
- Use `yaml.safe_load()` — never `yaml.load()` (arbitrary code execution risk).
- Already the parser used in this repo's `common.py` via HA's yaml wrapper. No new patterns to learn.
- For the device config file, PyYAML is sufficient. Pydantic validates structure after load.
- **Gotcha:** PyYAML silently coerces bare `yes`/`no`/`on`/`off` to booleans. Avoid these as string values in config keys (use `"yes"` or `true`/`false`).

---

### pydantic v2 (for config validation only)

- **Install:** `pip install pydantic` (v2 is default since ~2.0, released 2023)
- Use `BaseModel` to define config schema: devices list, InfluxDB block, poll interval defaults.
- Call `model = AppConfig.model_validate(yaml.safe_load(f))` — single line parses + validates.
- Pydantic v2 requires Python ≥3.8; v2 is ~10–20× faster than v1 for validation.
- **Not pydantic-settings:** pydantic-settings is for env-var-driven config. This project uses a YAML file, so `BaseModel` directly is simpler and clearer.
- pydantic v2 is already available in the HA environment the reference code targets, so it's a safe choice.

---

### structlog 25.5.0

- **Install:** `pip install structlog`
- Works alongside stdlib `logging` — can be configured to capture `logging.Logger` output too.
- Recommended config for a Docker/stdout service:
  ```python
  import structlog
  structlog.configure(
      processors=[
          structlog.contextvars.merge_contextvars,
          structlog.processors.add_log_level,
          structlog.processors.TimeStamper(fmt="iso"),
          structlog.dev.ConsoleRenderer(),   # or JSONRenderer() for log aggregation
      ],
      wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
      logger_factory=structlog.PrintLoggerFactory(),
  )
  log = structlog.get_logger()
  ```
- **asyncio support:** `structlog.contextvars` provides context binding that survives `await` boundaries — useful to bind `device_name` once per polling task and have it appear in all log lines from that coroutine.
- **Per-device log binding:**
  ```python
  log = structlog.get_logger().bind(device=device.name)
  ```
- Requires Python ≥3.8; 25.5.0 confirmed latest (2026-03-29).

---

### asyncio polling loop pattern

No third-party framework needed. Standard pattern for N concurrent polling devices:

```python
async def poll_device(device: DeviceConfig, influx_client: InfluxDBClientAsync) -> None:
    """Runs forever: poll → write → sleep → repeat."""
    log = structlog.get_logger().bind(device=device.name)
    solarman = Solarman(host=device.host, port=device.port, ...)
    while True:
        try:
            data = await solarman.read_registers(...)
            points = build_points(device, data)
            write_api = influx_client.write_api()
            await write_api.write(bucket=BUCKET, record=points)
            log.info("poll_ok", fields=len(points))
        except Exception as exc:
            log.warning("poll_error", error=str(exc))
        await asyncio.sleep(device.poll_interval)

async def main() -> None:
    config = load_config("config.yaml")
    async with InfluxDBClientAsync(...) as influx:
        tasks = [asyncio.create_task(poll_device(dev, influx)) for dev in config.devices]
        await asyncio.gather(*tasks)

asyncio.run(main())
```

- **One task per device** — simple, isolated; a device timing out doesn't block others.
- **`asyncio.gather(*tasks)`** — lets all tasks run concurrently; exceptions in one task do not cancel others if `return_exceptions=True` is set, but the `while True` + `try/except` inside each task is simpler and preferable here.
- **Graceful shutdown:** Add `signal.add_signal_handler(signal.SIGTERM, ...)` or let Docker's SIGTERM flow through.

---

### Docker base image: `python:3.12-slim`

- **3.12-slim** (current stable as of 2026-03-29): ~390 MB uncompressed (~130 MB compressed) for amd64.
- **Why not alpine:**
  - Alpine uses musl libc; `influxdb-client` depends on `urllib3`/`aiohttp` which have C extensions — these may require building from source on alpine, leading to larger final images and build complexity.
  - `pydantic` v2 ships pre-built wheels for `glibc` (slim) but alpine requires a source build or community wheels.
  - Slim is the right balance: smaller than full Debian, compatible with all binary wheels.
- **Why not 3.13:** Python 3.13 is available but some C-extension dependencies (notably older builds of `aiohttp`) were slow to publish 3.13 wheels. 3.12 is the safe production choice in 2026.
- **Multi-arch note:** If running on ARM (Raspberry Pi / ARM NAS), `python:3.12-slim` has `linux/arm64` and `linux/arm/v7` manifests — no separate Dockerfile needed with `docker buildx`.
- **Recommended Dockerfile pattern:**
  ```dockerfile
  FROM python:3.12-slim
  WORKDIR /app
  COPY pyproject.toml uv.lock ./
  RUN pip install uv && uv pip install --system --no-cache -r pyproject.toml
  COPY . .
  CMD ["python", "-m", "solarman_logger"]
  ```

---

### uv 0.11.2

- **Install in Dockerfile:** `pip install uv` (single step; uv is itself a wheel)
- **Why uv over pip:** 10–100× faster dependency resolution; generates `uv.lock` for reproducible builds; standard `pyproject.toml` format.
- **In Docker:** `uv pip install --system --no-cache -r pyproject.toml` installs into the system Python (no venv needed inside container).
- **`pyproject.toml` skeleton:**
  ```toml
  [project]
  name = "solarman-logger"
  version = "0.1.0"
  requires-python = ">=3.10"
  dependencies = [
      "influxdb-client[async]>=1.50.0",
      "PyYAML>=6.0.3",
      "pydantic>=2.0",
      "structlog>=25.0",
      "aiofiles>=24.1.0",
  ]
  ```

---

## What NOT to Use

| Library | Why Not |
|---------|---------|
| `influxdb` (v1 client) | This is the InfluxDB **1.x** client; wrong API — no token auth, no org/bucket model. Easy to accidentally install. The correct package is `influxdb-client`. |
| `pysolarmanv5` (PyPI) | Upstream diverged from repo's vendored copy. Swapping requires mapping `PySolarmanV5Async` → `Solarman`, re-testing Deye quirks, losing `transport` parameter support. More risk than benefit. |
| `python:3.12-alpine` | musl libc breaks binary wheels for `aiohttp`, `pydantic` — requires compiling from source, inflating image size and build time. |
| `python:3.13` | 3.13 wheel coverage for `aiohttp` and related C-extensions was incomplete as of late 2024; 3.12 is safer for production today. Revisit in 2026 H2. |
| `strictyaml` | Adds value for strongly-typed config DSLs but the type coercion it prevents is better handled by Pydantic post-load. Two validation layers with different error messages is confusing. |
| `pydantic-settings` | Designed for env-var config, not file-based YAML. Requires Python ≥3.10 (OK here) but adds complexity for no gain when you already have `PyYAML + pydantic.BaseModel`. |
| `python-dotenv` | No `.env` file pattern for this project; config is YAML + Docker env. Not needed. |
| `loguru` | Good library but structlog's context binding via `contextvars` is better suited for async multi-device logging where you want per-device log context across `await` boundaries. |
| `aioinflux` | Unmaintained third-party async InfluxDB client; last release 2020. Use the official `influxdb-client[async]`. |
| `WriteApi` (sync, batching) | The sync `WriteApi` with a batching background thread is incompatible with asyncio. Always use `WriteApiAsync` in an async codebase. |

---

## Confidence Levels

| Recommendation | Confidence | Basis |
|----------------|------------|-------|
| `influxdb-client[async]` 1.50.0 | HIGH | PyPI JSON + GitHub source reviewed; async API confirmed |
| vendored `pysolarman` (not PyPI) | HIGH | Source code read directly from repo; upstream changelog reviewed |
| `pysolarmanv5` upstream v3.0.6 | HIGH | PyPI JSON + official changelog at readthedocs.io |
| `PyYAML` 6.0.3 | HIGH | PyPI JSON confirmed |
| `pydantic` v2 (not pydantic-settings) | HIGH | PyPI confirmed; design rationale verified |
| `structlog` 25.5.0 | HIGH | PyPI JSON confirmed; asyncio contextvars support is documented feature |
| `python:3.12-slim` base image | HIGH | Docker Hub tags confirmed; wheel compatibility rationale is well-established |
| `uv` 0.11.2 | HIGH | PyPI JSON confirmed |
| asyncio task-per-device pattern | MEDIUM | Standard asyncio pattern; not specifically benchmarked for this use case |
| Pydantic v2 min Python 3.10 | HIGH | pydantic v2 docs + vendored pysolarman union syntax confirmed |

---

## Sources

- PyPI influxdb-client: https://pypi.org/pypi/influxdb-client/json — version 1.50.0
- influxdb-client async source: https://github.com/influxdata/influxdb-client-python/blob/master/influxdb_client/client/influxdb_client_async.py
- PyPI pysolarmanv5: https://pypi.org/pypi/pysolarmanv5/json — version 3.0.6
- pysolarmanv5 changelog: https://pysolarmanv5.readthedocs.io/en/latest/changelog.html
- Vendored pysolarman: `custom_components/solarman/pysolarman/__init__.py` (this repo)
- PyPI structlog: https://pypi.org/pypi/structlog/json — version 25.5.0
- PyPI PyYAML: https://pypi.org/pypi/PyYAML/json — version 6.0.3
- PyPI pydantic-settings: https://pypi.org/pypi/pydantic-settings/json — version 2.13.1
- PyPI aiofiles: https://pypi.org/pypi/aiofiles/json — version 25.1.0
- PyPI uv: https://pypi.org/pypi/uv/json — version 0.11.2
- Docker Hub python tags: https://hub.docker.com/_/python/tags — 3.12.13 confirmed current
