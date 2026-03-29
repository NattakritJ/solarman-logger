# Codebase Concerns

**Analysis Date:** 2026-03-29

---

## Tech Debt

**`manifest.json` version hardcoded to `0.0.0`:**
- Issue: `version` field in `custom_components/solarman/manifest.json` is always `"0.0.0"` — not updated on release
- Files: `custom_components/solarman/manifest.json:14`
- Impact: HACS and integrations that inspect version cannot detect upgrades; rollback awareness is broken
- Fix approach: Wire version into CI/CD or bump manually before each tagged release

**Duplicate constant definition for `SERVICES_PARAM_QUANTITY`:**
- Issue: `SERVICES_PARAM_QUANTITY = "quantity"` is defined twice in `const.py` (lines 122 and 132), second definition silently overwrites the first
- Files: `custom_components/solarman/const.py:122`, `custom_components/solarman/const.py:132`
- Impact: The first definition is dead code; any future reordering could subtly change behavior
- Fix approach: Remove the duplicate definition at line 122

**Duplicate key in `OLD_` migration dict:**
- Issue: `OLD_` dict literal contains `"sn": "serial", "sn": "sn"` — the key `"sn"` appears twice; Python silently uses the last value
- Files: `custom_components/solarman/const.py:37`
- Impact: Migration of the first `"sn"` → `"serial"` mapping is silently discarded; old config entries using `sn` as serial may not migrate correctly
- Fix approach: Consolidate to a single `"sn"` key with the intended value, and add a comment explaining the migration intent

**Pervasive wildcard imports (`from .const import *`, `from .common import *`, `from .services import *`):**
- Issue: All platform modules use wildcard star imports from local modules. This makes it impossible to statically determine which names are in scope, breaks IDE analysis, and can cause silent name shadowing
- Files: Every `.py` in `custom_components/solarman/` (e.g. `sensor.py:11-13`, `entity.py:14-16`, `device.py:4-5`, `parser.py:9-10`)
- Impact: Refactoring difficulty, hidden coupling, shadowed builtins (see `format` below)
- Fix approach: Replace with explicit named imports; `common.py` and `const.py` are large utility modules that should export a well-defined public API

**`common.py` shadows Python built-in `format`:**
- Issue: `common.py:205` defines `def format(value: Any)`, shadowing the built-in `format()`. Because every module does `from .common import *`, this shadowing propagates everywhere
- Files: `custom_components/solarman/common.py:205`
- Impact: Any code using the built-in `format()` function in those modules will silently call this custom version instead
- Fix approach: Rename to `format_bytes` or similar; explicit imports would prevent the shadow from propagating

**Commented-out dead code (incomplete write-lock feature):**
- Issue: Multiple commented-out lines represent a partially-implemented write lock feature that was never finished or cleaned up
- Files: `custom_components/solarman/device.py:37`, `custom_components/solarman/entity.py:118`, `custom_components/solarman/entity.py:144`, `custom_components/solarman/entity.py:172-173`
- Impact: Cognitive overhead for contributors; unclear whether this is planned or abandoned
- Fix approach: Either implement the feature (there is a stub `_write_lock` attribute and a `check()` method) or delete all commented-out code entirely

**`_attr_name.replace()` result is discarded in `SolarmanNestedSensor`:**
- Issue: `sensor.py:97` calls `self._attr_name.replace(f"{sensor["group"]} ", '')` but does not assign the result — strings are immutable in Python, so this line has no effect
- Files: `custom_components/solarman/sensor.py:97`
- Impact: Nested sensor names always include the group prefix, which was presumably meant to be stripped
- Fix approach: Change to `self._attr_name = self._attr_name.replace(...)`

**`SolarmanAccessPoint.async_turn_` uses a generic/incomplete method name:**
- Issue: The shared helper is named `async_turn_` (trailing underscore), which is not a HA convention. The `async_turn_on` and `async_turn_off` methods both delegate to it but the semantics are inverted (mode 0 = on, mode 1 = off), with conditional logic that also contains a bug: `if self.is_on is False` prevents turning on when already on, but never turns off
- Files: `custom_components/solarman/switch.py:54-66`
- Impact: AccessPoint switch may not function correctly when toggling states
- Fix approach: Rename to `_async_set_mode`, review the condition logic, and validate against actual device behavior

---

## Known Bugs

**`try_parse_datetime` only handles 3 or 6 register variants, silently drops others:**
- Symptoms: Datetime values with any register count other than 3 or 6 produce an empty string, causing a `strptime` exception silently caught and logged at DEBUG level — the sensor produces no value
- Files: `custom_components/solarman/parser.py:386-411`
- Trigger: Any inverter definition using an unsupported datetime register layout
- Workaround: None; parser silently returns nothing

**`ParameterParser.process` swallows `ValueError` silently in `device.py`:**
- Symptoms: Data validation errors raised by `do_validate` with `invalidate_all` propagate as `ValueError`, but `device.py:92-93` catches `ValueError` and does `pass` — the entire poll result is thrown away silently with no log at WARNING or above
- Files: `custom_components/solarman/device.py:92-93`, `custom_components/solarman/parser.py:137-138`
- Trigger: A register value triggers the `invalidate_all` validation rule
- Workaround: Enable DEBUG logging to see the validation message

**Known HA bug with `DateTimeEntity` timezone in device detail page:**
- Symptoms: Setting a datetime from the device detail page sends UTC timezone info regardless of HA timezone; setting via Automations/Actions works correctly
- Files: `custom_components/solarman/datetime.py:41-43`
- Trigger: Using the HA UI device detail page to set a `datetime` entity
- Workaround: Use Automations/Actions to set datetime values; code includes a workaround comment but the root cause is an upstream HA bug

**`common.py` postprocess fix is labeled "Temporary":**
- Symptoms: `common.py:305` has comment `# Temporary location of fix for latest HA changes regarding default precision behavior` with a hardcoded `suggested_display_precision = 1` for `kWh` energy sensors
- Files: `custom_components/solarman/common.py:305-307`
- Trigger: HA changed default precision behavior; this patches it inline
- Workaround: The patch is active; it should eventually be removed and replaced with YAML-level `suggested_display_precision` fields in inverter definitions

---

## Security Considerations

**Hardcoded default credentials for Solarman logger HTTP API:**
- Risk: `LOGGER_AUTH = BasicAuth("admin", "admin")` is used for all HTTP requests to the logger device at `const.py:39`. These are factory defaults for the Solarman Wi-Fi stick. If a user has changed the password, requests will fail silently; no mechanism exists to configure alternate credentials
- Files: `custom_components/solarman/const.py:39`, `custom_components/solarman/common.py:67`
- Current mitigation: The logger is a local LAN device on the user's network; no external exposure
- Recommendations: Add optional credential fields to the config flow and store in HA config entry options; fall back to defaults if not set

**Logger management API uses plain HTTP only:**
- Risk: All management requests to the logger (reading/writing network settings, restart, cloud config) use `http://` with Basic Auth. Credentials and configuration data are transmitted in plaintext
- Files: `custom_components/solarman/common.py:67`, `custom_components/solarman/common.py:164`
- Current mitigation: Limited to local LAN access; Solarman hardware does not support HTTPS on the logger
- Recommendations: Document this limitation; consider adding a config option to disable logger management features entirely if the user doesn't trust their LAN

**Provider mutates `cached_property` fields (`host`, `serial`) directly:**
- Risk: `EndPointProvider` declares `host` as a `@cached_property` (via `propcache`) but then reassigns `self.host = d["ip"]` in `discover()`. The `connection` property is also a `@cached_property` and captures `self.host` at first access — if `discover()` runs after `connection` is first read, the cached `connection` tuple will have a stale host, causing Modbus traffic to go to the wrong address
- Files: `custom_components/solarman/provider.py:70-76`, `custom_components/solarman/provider.py:89-90`
- Current mitigation: `discover()` is called during `init()` before `connection` is first accessed in normal flow
- Recommendations: Make `host` a plain instance attribute (not `cached_property`) and explicitly invalidate `connection` when host changes; add a guard or assertion

---

## Performance Bottlenecks

**Blocking DNS resolution on the event loop:**
- Problem: `socket.gethostbyname(address)` in `common.py:90` and `socket.getaddrinfo(...)` in `config_flow.py:58` are synchronous blocking calls made directly on the asyncio event loop
- Files: `custom_components/solarman/common.py:90`, `custom_components/solarman/config_flow.py:58`
- Cause: Standard `socket` module calls block the entire HA event loop for the duration of DNS resolution; can cause visible latency or watchdog warnings on slow/unresponsive DNS
- Improvement path: Use `asyncio.get_event_loop().getaddrinfo()` (async wrapper) or wrap in `run_in_executor` via the existing `async_execute` helper

**`postprocess_descriptions` logs full descriptions dict at DEBUG every coordinator refresh:**
- Problem: `common.py:309` logs the entire `descriptions` list at DEBUG level every time `postprocess_descriptions` is called (once per coordinator `init()`)
- Files: `custom_components/solarman/common.py:309`
- Cause: Debug logging of large lists with many sensors can be expensive when DEBUG logging is enabled
- Improvement path: Gate behind `if _LOGGER.isEnabledFor(logging.DEBUG)` check, or remove entirely and rely on existing per-item debug logs

**Discovery closes transport after every discovery cycle:**
- Problem: `discovery.py:63-68` closes the UDP transport in the `finally` block of every `_context()` use, even for periodic background discovery. This means a new datagram endpoint is created every 15 minutes
- Files: `custom_components/solarman/discovery.py:50-68`
- Cause: Transport is closed unconditionally instead of being kept alive and reused
- Improvement path: Only close on error; reuse the transport for subsequent discoveries

---

## Fragile Areas

**`EndPointProvider.discover()` — complex single-line conditional on logger settings:**
- Files: `custom_components/solarman/provider.py:93`
- Why fragile: A single 200+ character line with 5 chained `next(iter(...)).group(1) != ...` comparisons connected by `or`. One `StopIteration` from a failed regex match raises an exception instead of gracefully skipping the reconfiguration. The operator precedence of `!=` vs `if/else` inline ternaries also creates subtle logic bugs (e.g., `!= "TCP" if "tcp" in self.transport else "UDP"` actually evaluates as `(!= "TCP") if ... else "UDP"` — the `!= "UDP"` case is an expression, not a comparison)
- Safe modification: Decompose into separate variables with explicit guards before touching this line
- Test coverage: None

**`retry` decorator in `common.py` retries any non-ignored exception exactly once with no delay:**
- Files: `custom_components/solarman/common.py:26-37`
- Why fragile: The `retry` decorator catches all exceptions (except those in `ignore`) and blindly retries once with no delay, no jitter, no max attempts, and no logging. This can mask transient errors that would self-correct or amplify load on a struggling device
- Safe modification: Before changing retry logic, assess all call sites (`pysolarman/__init__.py:310`, `device.py:73`); a two-attempt immediate retry is intentional for the Modbus protocol but should be documented
- Test coverage: None

**`SolarmanBatteryCapacitySensor.update()` — stateful capacity estimation algorithm:**
- Files: `custom_components/solarman/sensor.py:135-160`
- Why fragile: The algorithm maintains `self._temp` (recent samples) and `self._states` (historical capacity estimates) across updates. The loop that identifies monotone decreasing quadruples (`h > m > l > s`) is tightly coupled to sample ordering and has no protection against data corruption across HA restarts (only `_states` is persisted via `async_get_last_state`, not `_temp`)
- Safe modification: Do not modify without understanding the battery capacity estimation math; add unit tests before any change
- Test coverage: None

**`_received_frame_is_valid` mutates `self.transport` as a side-effect:**
- Files: `custom_components/solarman/pysolarman/__init__.py:144-147`
- Why fragile: When a TCP-formatted frame is detected mid-session, `self.transport = "modbus_tcp"` is set directly inside a validation method. This triggers the `transport` setter which rebinds `self._get_response` and `self._handle_frame`. This is a protocol auto-detection mechanism but is invisible from call sites and causes action-at-a-distance
- Safe modification: Extract transport switching to a dedicated method with logging and state checks
- Test coverage: None

**`_open_connection` recursively calls itself on repeated failures:**
- Files: `custom_components/solarman/pysolarman/__init__.py:213-225`
- Why fragile: If `self._last_frame is not None` and every connection attempt fails, `_open_connection` recurses indefinitely (no base case, no depth limit). Under persistent network issues this will eventually raise `RecursionError` or exhaust the asyncio task stack
- Safe modification: Replace recursive call with a loop or reschedule via `create_task`; add a retry counter/limit

---

## Scaling Limits

**Single `asyncio.Lock` serializes all Modbus requests:**
- Current behavior: `pysolarman/__init__.py:75` uses a single `asyncio.Lock` per `Solarman` instance. All `execute()` calls queue behind this lock
- Limit: For inverters with many registered sensors across multiple request groups, polls execute strictly sequentially. At 5-second poll intervals with many requests, the effective polling rate degrades
- Scaling path: Pipelining is not possible over Modbus; design is correct but document expected throughput limits per inverter definition

**`SolarmanBatteryCapacitySensor` stores unbounded historical states in HA state attributes:**
- Current capacity: `_nstates` defaults to 1000 samples, stored in `_attr_extra_state_attributes["states"]` which is written to HA's state machine
- Limit: HA limits state attribute size; storing 1000 float values per state write may trigger warnings or be truncated by HA
- Scaling path: Reduce default `_nstates`, or store only the computed aggregate rather than the full sample buffer in state attributes

---

## Dependencies at Risk

**`propcache` is an uncommon dependency not listed in HA requirements:**
- Risk: `provider.py:6` imports `from propcache import cached_property`. This library is not part of standard Python, not listed in `manifest.json` requirements (only `aiofiles` is listed), and may not be available in all HA environments
- Impact: `ImportError` at startup in environments where `propcache` is not installed
- Files: `custom_components/solarman/provider.py:6`, `custom_components/solarman/manifest.json:13`
- Migration plan: Add `propcache` to `requirements` in `manifest.json`, or replace `propcache.cached_property` with `functools.cached_property` (stdlib, Python 3.8+) which has equivalent behavior for this usage

**Bundled `pysolarman/umodbus` is a vendored fork, not a PyPI package:**
- Risk: `custom_components/solarman/pysolarman/umodbus/` contains a forked/vendored copy of `umodbus`. Any upstream security fixes or bug patches require manual integration. The vendored copy contains multiple `# TODO Raise proper exception.` comments indicating known unfinished error handling
- Impact: Maintenance burden; umodbus upstream bugs silently inherited
- Files: `custom_components/solarman/pysolarman/umodbus/functions.py:288,495,693,870,1038,1187`, `custom_components/solarman/pysolarman/umodbus/utils.py:40`
- Migration plan: Either periodically sync with upstream umodbus, or document the fork point and known divergences

**`multiprocessing.Event` used in async code:**
- Risk: `pysolarman/__init__.py:10` imports `from multiprocessing import Event` and creates `self._data_event = Event()`. `multiprocessing.Event` uses OS-level synchronization primitives (shared memory), not asyncio primitives. In an asyncio context, `asyncio.Event` should be used instead
- Impact: Potential thread-safety issues; `multiprocessing.Event` is designed for cross-process communication and has unnecessary overhead for single-process async use; `is_set()` / `set()` / `clear()` calls work but bypass asyncio's cooperative scheduling
- Files: `custom_components/solarman/pysolarman/__init__.py:10,77`
- Migration plan: Replace `from multiprocessing import Event` with `asyncio.Event` and update `_data_event` usage accordingly

---

## Missing Critical Features

**Deprecated services have no deprecation warning logged:**
- Problem: `write_holding_register` and `write_multiple_holding_registers` (deprecated service names) are still registered and functional but no deprecation warning is emitted to alert users
- Blocks: Users on old automations won't know to migrate
- Files: `custom_components/solarman/services.py:75-76`, `custom_components/solarman/const.py:133-134`

**No user-configurable credentials for logger HTTP management:**
- Problem: The logger management API (network settings, cloud toggle, restart) only works with the factory default `admin/admin` credentials
- Blocks: Users who have changed their logger password cannot use Mode, Cloud, AccessPoint or Restart entities
- Files: `custom_components/solarman/const.py:39`, `custom_components/solarman/common.py:67`

**Autodetection only supports Deye inverter family:**
- Problem: The profile autodetection logic in `common.py:128-146` only queries Deye-specific registers. Non-Deye inverters always require manual profile selection
- Blocks: Streamlined onboarding for non-Deye devices
- Files: `custom_components/solarman/common.py:128-146`, `custom_components/solarman/const.py:76-90`

---

## Test Coverage Gaps

**No test suite exists — zero test files in the repository:**
- What's not tested: Everything — protocol framing, register parsing, entity state logic, coordinator lifecycle, config flow, migration
- Files: All files under `custom_components/solarman/`
- Risk: Any refactoring has no safety net; bugs in parser rules or protocol handling are only caught by real hardware testing
- Priority: High

**Parser register decoding has no unit tests:**
- What's not tested: All 10 `try_parse_*` methods, validation logic, `_read_registers` / `_read_registers_signed` / `_read_registers_custom`, lookup table resolution, range enforcement
- Files: `custom_components/solarman/parser.py`
- Risk: Register parsing is the most complex and critical path; silent regressions are easy to introduce
- Priority: High

**Protocol frame handling has no unit tests:**
- What's not tested: `_received_frame_is_valid`, `_parse_adu_from_sol_response`, frame checksum, serial auto-detection, TCP detection side-effect, sequence number handling
- Files: `custom_components/solarman/pysolarman/__init__.py`
- Risk: Protocol changes or edge cases (short frames, double CRC, sequence mismatch) are only validated against real hardware
- Priority: High

**Config flow migration (`async_migrate_entry`) has no tests:**
- What's not tested: `OLD_` key migration, `CONF_ADDITIONAL_OPTIONS` promotion, `modbus_tcp` transport upgrade from `sn == 0`, unique_id migration
- Files: `custom_components/solarman/__init__.py:103-122`
- Risk: Breaking config migrations silently corrupts existing HA configuration entries
- Priority: High

---

## Home Assistant Compatibility Concerns

**`quality_scale: "custom"` — integration bypasses HA quality gates:**
- Risk: Setting `quality_scale: "custom"` in the manifest opts out of all HA quality scale requirements. The integration is not validated against Silver/Gold/Platinum standards (e.g., no config entry diagnostics test, no strict type hints, no test coverage requirement)
- Files: `custom_components/solarman/manifest.json:12`
- Recommendation: Aspire toward Silver quality scale over time; it requires tests and better error handling, both of which are needed

**`_PLATFORMS` dynamically discovers platform files at runtime:**
- Risk: `__init__.py:27` scans the filesystem at startup to find `.py` platform files: `[i for i in Platform._member_map_.values() if _DIRECTORY.joinpath(i.value + ".py").is_file()]`. This is fragile if HA changes `Platform._member_map_` structure or if platform file naming conventions diverge
- Files: `custom_components/solarman/__init__.py:27`
- Recommendation: Declare platforms statically in `manifest.json` or as a constant list to match HA best practices

**`_attr_state` set directly alongside `_attr_native_value`:**
- Risk: `entity.py:54` sets both `self._attr_native_value` and `self._attr_state` to the same value. HA entity base classes derive `state` from `native_value` through unit conversion — setting `_attr_state` directly bypasses this and can cause mismatches when HA applies unit conversions (e.g., kWh → MWh)
- Files: `custom_components/solarman/entity.py:54`
- Recommendation: Only set `_attr_native_value`; remove direct assignment to `_attr_state`

**`MINOR_VERSION = 0` in `ConfigFlowHandler` — no minor version migration path:**
- Risk: Config entry `minor_version` is always 0. The `async_migrate_entry` function in `__init__.py` does not check `minor_version` before applying migrations, meaning all migrations run on every version bump regardless of which fields actually changed
- Files: `custom_components/solarman/config_flow.py:86`, `custom_components/solarman/__init__.py:103-122`
- Recommendation: Implement version-guarded migration blocks (e.g., `if config_entry.version < 2`) to make migration idempotent and safe

**`hacs.json` requires HA ≥ 2025.2.0:**
- Risk: `hacs.json` sets `"homeassistant": "2025.2.0"`. This pins the minimum HA version tightly. HA internal APIs used (e.g., `config_entry.runtime_data`, `DataUpdateCoordinator` with `config_entry` param, `propcache`) were introduced around this version. Any changes that use newer HA APIs without updating this constraint could silently break for users on older HA
- Files: `hacs.json`
- Recommendation: Review each HA API call against its introduction version; keep `hacs.json` constraint in sync

---

*Concerns audit: 2026-03-29*
