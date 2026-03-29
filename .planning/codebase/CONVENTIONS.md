# Coding Conventions

**Analysis Date:** 2026-03-29

## Naming Patterns

**Files:**
- Module files use `snake_case` matching the HA platform they implement: `sensor.py`, `binary_sensor.py`, `config_flow.py`, `coordinator.py`
- All Python files are lowercase with underscores
- YAML inverter definition files use `manufacturer_model.yaml` format: `deye_hybrid.yaml`, `sofar_string.yaml`

**Classes:**
- PascalCase throughout: `Coordinator`, `ParameterParser`, `ConfigFlowHandler`, `OptionsFlowHandler`
- HA entity classes are prefixed with `Solarman`: `SolarmanEntity`, `SolarmanSensor`, `SolarmanWritableEntity`, `SolarmanBatterySensor`
- Embedded protocol classes follow the same prefix pattern: `SolarmanCoordinatorEntity`
- Provider/helper classes are suffixed with `Provider`: `ConfigurationProvider`, `EndPointProvider`, `ProfileProvider`
- Exception classes are suffixed with `Error`: `FrameError`
- Protocol classes use `Protocol` suffix: `DiscoveryProtocol`

**Functions:**
- `snake_case` for all module-level and class functions
- HA lifecycle functions follow HA naming conventions: `async_setup`, `async_setup_entry`, `async_unload_entry`, `async_migrate_entry`
- HA callback functions prefixed `async_`: `async_step_user`, `async_select_option`, `async_press`, `async_turn_on`
- Private/internal functions prefixed with `_`: `_request`, `_read_registers`, `_read_registers_signed`, `_handle_protocol_frame`
- Decorator helpers use descriptive names: `retry`, `throttle`, `log_call`, `log_return`
- Parser methods use `try_parse_*` prefix: `try_parse_unsigned`, `try_parse_signed`, `try_parse_ascii`

**Variables:**
- `snake_case` for local variables and instance attributes
- Module-level logger always named `_LOGGER = getLogger(__name__)` (leading underscore, uppercase)
- Module-level platform detector always `_PLATFORM = get_current_file_name(__name__)`
- Constants in `UPPER_SNAKE_CASE`: `DOMAIN`, `DISCOVERY_PORT`, `TIMINGS_INTERVAL`
- Private instance attributes prefixed with `_`: `self._reader`, `self._lock`, `self._counter_value`
- Constants that are dict/namespace groupings use trailing underscore: `DEFAULT_`, `PARAM_`, `OLD_`
- Short walrus-operator temporaries use single lowercase letters: `v`, `f`, `d`, `e`, `r`, `s`

**Constants:**
- Module-wide string constants in `UPPER_SNAKE_CASE` in `const.py`
- Config key constants prefixed `CONF_`: `CONF_HOST`, `CONF_PORT`, `CONF_TRANSPORT`
- Service name constants prefixed `SERVICE_`: `SERVICE_READ_HOLDING_REGISTERS`
- Service param constants prefixed `SERVICES_PARAM_`: `SERVICES_PARAM_DEVICE`
- Deprecation constants prefixed `DEPRECATION_`: `DEPRECATION_SERVICE_WRITE_SINGLE_REGISTER`
- Request-related constants prefixed `REQUEST_`: `REQUEST_CODE`, `REQUEST_START`
- Autodetection constants prefixed `AUTODETECTION_`: `AUTODETECTION_DEYE`

## Code Style

**Formatting:**
- No automated formatter (no `.prettierrc`, `pyproject.toml`, `.flake8`, or `black` config detected)
- Indentation: 4 spaces (standard Python)
- Keyword arguments consistently use spaces around `=`: `timedelta(minutes = 15)`, `vol.Range(min = 0, max = 65535)` — **this is non-standard** compared to PEP 8, which recommends no spaces around `=` in keyword arguments
- Trailing commas not consistently used in multi-line structures
- Long single-line expressions are preferred over multi-line — many lines exceed 120+ characters (see `coordinator.py:66`, `const.py:87`, `common.py:56`)

**Line Length:**
- No enforced limit. Lines frequently exceed 120 characters, some reaching 200+
- Example: `custom_components/solarman/common.py:56` contains a 200+ character single expression

**String Formatting:**
- f-strings used throughout for log messages and string building
- No `.format()` style in the integration code (only found in vendored `pysolarman/umodbus/`)

## Import Organization

**Order (as observed):**
1. `from __future__ import annotations` — present in most main integration files
2. Standard library imports (grouped, no blank line between groups): `import re`, `import bisect`
3. Third-party library imports: `import voluptuous as vol`, `from aiohttp import ...`
4. HA framework imports: `from homeassistant.core import ...`
5. Local relative imports (dot notation): `from .const import *`, `from .common import *`, `from .coordinator import Coordinator`

**Example from `sensor.py`:**
```python
from __future__ import annotations

from logging import getLogger

from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
...

from .const import *
from .common import *
from .services import *
from .entity import SolarmanEntity, Coordinator
```

**Star Imports:**
- `from .const import *` and `from .common import *` are used in all platform files
- This is intentional — `const.py` and `common.py` serve as shared namespaces across the integration

**Path Aliases:**
- None. Relative imports only within `custom_components/solarman/`

## Type Annotations

**Usage Level:** Moderate — present on most public function signatures, absent on many internal/short functions.

**Style:**
- `from __future__ import annotations` used at the top of most files to enable PEP 563 deferred evaluation
- Return types annotated on HA lifecycle functions: `async def async_setup_entry(...) -> bool`
- Parameters annotated on public methods: `def __init__(self, host: str, port: int | str, transport: str, ...)`
- Union types use `|` syntax (Python 3.10+): `int | float | str | list`, `asyncio.Task | None`
- Complex nested generics on class-level signatures: `DataUpdateCoordinator[dict[str, tuple[int | float | str | list, int | float | None]]]`
- Many private/internal functions lack return type annotations: `def retry(ignore: tuple = ())` has no `-> Callable`
- Walrus operator variables (`:=`) are never annotated
- `dataclass` used in `provider.py` for `ConfigurationProvider`, `EndPointProvider`, `ProfileProvider`

**Common Type Patterns:**
```python
# Coordinator type-parameterized ConfigEntry
config_entry: ConfigEntry[Coordinator]

# Optional with None default
self._keeper: asyncio.Task | None = None

# Dict with complex value tuples
dict[str, tuple[int | float | str | list, int | float | None]]

# Typed parameters
def __init__(self, host: str, port: int | str, transport: str, serial: int, slave: int, timeout: int):
```

## Error Handling

**Patterns:**

**Broad exception catch + re-raise with context:**
```python
# coordinator.py
except Exception as e:
    raise UpdateFailed(strepr(e)) from e
```

**Selective exception suppression (TimeoutError passed through):**
```python
# coordinator.py / device.py
except TimeoutError:
    raise
except Exception as e:
    raise UpdateFailed(strepr(e)) from e
```

**Bare except (used sparingly in edge cases):**
```python
# config_flow.py — intentional swallow during discovery loop
except:
    continue
```

**ServiceValidationError for HA service failures:**
```python
# services.py
except Exception as e:
    raise ServiceValidationError(e, translation_domain = DOMAIN, translation_key = "call_failed")
```

**Debug-log and continue for non-critical failures:**
```python
# provider.py, discovery.py
except Exception as e:
    _LOGGER.debug(f"[{self.host}] Error", exc_info = True)
```

**ValueError silently discarded (invalid dataset):**
```python
# device.py
except ValueError:
    pass
```

**Custom exception class:**
```python
# pysolarman/__init__.py
class FrameError(Exception):
    """Frame Validation Error"""
```

**Walrus operator used for guard patterns:**
```python
if (value := source.get(key)) is not None:
    ...
```

## Logging

**Framework:** Python standard `logging` via `from logging import getLogger`

**Logger instantiation (always at module level):**
```python
_LOGGER = getLogger(__name__)
```

**Level usage:**
- `_LOGGER.debug(f"...")` — primary level; used for all entry/exit traces and data dumps
- `_LOGGER.info(f"...")` — used sparingly for version reporting on startup
- `_LOGGER.warning(f"...")` — rare; used for unexpected but non-fatal conditions
- `_LOGGER.error(f"...")` — used for parse failures in `parser.py`
- `_LOGGER.exception(f"...")` — used when full stack trace is needed

**f-string format for log messages:**
```python
_LOGGER.debug(f"async_setup_entry({config_entry.as_dict()})")
_LOGGER.debug(f"[{self.host}] PROTOCOL_MISMATCH: {frame.hex(" ")}")
_LOGGER.debug(f"[{self.endpoint.host}] Request {code:02} ❘ 0x{code:02X} ~ {address:04}")
```

**Host prefix convention for device-level logs:**
All messages in connection/protocol code are prefixed with `[{self.host}]`:
```python
_LOGGER.debug(f"[{self.host}] Connection is reset by the peer.")
```

## Comments

**When to Comment:**
- Block comments (`#`) used to label logical sections within functions — e.g., `# Initiaize coordinator...`, `# Migrations`, `# Forward setup`
- Protocol-level magic numbers and byte structures commented inline
- Commented-out code kept in place with `#` (not deleted): `#self._write_lock = True`, `#await self.coordinator.async_request_refresh()`
- `# TODO` markers present in vendored code (`pysolarman/umodbus/`), not in main integration code

**Docstrings:**
- **Not used in the main integration code** (`custom_components/solarman/`)
- Vendored `pysolarman/umodbus/` has comprehensive reStructuredText-style docstrings with `:param:`, `:return:`, `:raises:` fields — this is inherited from the upstream library

**Inline comments:**
- Used for context on non-obvious logic: `# Double CRC (XXXX0000) correction`, `# Skip...`, `# Bug in HA:`
- Protocol constant groups commented with names: `# Diagnostic functions, only available when using serial line.`

## Module Design

**Exports:**
- `const.py` and `common.py` use `from .X import *` pattern — all public names are implicitly exported
- No `__all__` lists defined anywhere in the integration

**Barrel Files:**
- Not used. Each module is imported directly by name where needed
- Exception: `from .const import *` and `from .common import *` function as de facto barrel imports

**Decorators:**
- Custom decorators defined in `common.py`: `retry`, `throttle`
- Custom decorators in `pysolarman/__init__.py`: `log_call`, `log_return`
- All decorators use `@wraps(f)` to preserve wrapped function metadata

**`from __future__ import annotations`:**
- Present in all main integration files except `device.py`, `diagnostics.py`, `discovery.py`

---

*Convention analysis: 2026-03-29*
