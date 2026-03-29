# Phase 2: Device Polling Loop - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Poll all configured devices concurrently and independently, honor YAML per-group `update_interval` behavior during standalone runtime, and recover cleanly from TCP failure without crashing or blocking healthy devices.

Requirements: POLL-01, POLL-04, POLL-06

</domain>

<decisions>
## Implementation Decisions

### Startup and Offline Policy
- **D-01:** Service startup does not fail when one device is unreachable. It should start anyway and continue polling reachable devices independently.
- **D-02:** Repeated offline logging is transition-based: warn when a device first goes offline, then suppress repeated warnings until recovery.
- **D-03:** Offline logging policy is device-type aware. Inverter-like devices are treated as expected-to-sleep overnight, while always-on devices such as meters should remain more operationally visible when offline.
- **D-04:** Expected-sleep behavior should be inferred from the configured profile or parser/profile metadata rather than adding a new YAML config field in this phase.
- **D-05:** Offline devices use per-device backoff so only the failing device slows down; healthy devices remain on their normal cadence.
- **D-06:** Per-device offline backoff should cap at about 5 minutes.

### Scheduling and Overruns
- **D-07:** A device must never run overlapping polls. If a poll overruns its interval, skip missed overlap and schedule the next run from current time rather than queueing backlog.
- **D-08:** Overrun visibility belongs in DEBUG summaries, not INFO/WARNING spam during normal operation.
- **D-09:** Per-group profile scheduling should be anchored to real elapsed time per device, so a group with `update_interval: 3600` means roughly once per hour on the clock, not once per N successful polls.

### Bad Data Handling
- **D-10:** Honor profile validation strictly: if a rule triggers `invalidate_all`, drop that entire device poll cycle rather than emitting partial data.
- **D-11:** If validation fails for only some fields and the profile does not request full invalidation, keep valid fields and drop only invalid fields.
- **D-12:** Invalid-dataset logging is transition-based: warn when a device first starts returning invalid full datasets, then downgrade repeats to DEBUG until recovery.

### Connection Recovery
- **D-13:** Replace the recursive `pysolarman._open_connection()` behavior with a background reconnect loop/task per device so sustained failure cannot produce `RecursionError`.
- **D-14:** After reconnection succeeds, do not replay the last in-flight request automatically. Wait for the next scheduled poll cycle to issue a fresh request set.
- **D-15:** Connection state transitions should log as warning on offline transition and info on recovery.

### the agent's Discretion
- Exact backoff curve shape before the 5-minute cap (for example exponential vs stepped), as long as it remains per-device and capped.
- Exact thresholds for when repeated offline or invalid-data logs downgrade from warning to DEBUG.
- Internal scheduler structure for translating elapsed-time decisions into parser request selection.
- Exact wording and structured fields for offline, invalid-data, overrun, and recovery log messages.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project and Phase Scope
- `.planning/PROJECT.md` — Product intent, reliability goal, active requirements, and the project-level `log-and-retry` direction.
- `.planning/REQUIREMENTS.md` — Phase 2 requirements `POLL-01`, `POLL-04`, and `POLL-06`, plus out-of-scope boundaries.
- `.planning/ROADMAP.md` — Phase 2 goal and success criteria, including concurrent polling, per-group schedule honoring, automatic recovery, and no `RecursionError`.
- `.planning/STATE.md` — Existing extracted decisions from Phase 1 and current project progress.
- `.planning/phases/01-protocol-core/01-CONTEXT.md` — Locked prior decisions about config structure, parser initialization, hardcoded parser parameters, and logging baseline that Phase 2 must build on.

### Existing Standalone Code To Extend
- `solarman_logger/config.py` — Existing `DeviceConfig.poll_interval` model and current config surface; confirms no device-type or sleep-policy field exists yet.
- `solarman_logger/parser.py` — `ParameterParser.schedule_requests(runtime)` and validation behavior that Phase 2 must adapt to elapsed-time scheduling and invalid-data policy.
- `solarman_logger/pysolarman/__init__.py` — Current connection lifecycle, recursive `_open_connection()` bug, `_last_frame` replay behavior, and protocol client interfaces.
- `solarman_logger/logging_setup.py` — Existing stdout logging baseline that Phase 2 polling and recovery logs should use.

### Reference Behavior From HA Source
- `custom_components/solarman/coordinator.py` — HA counter-based polling model being adapted away from `DataUpdateCoordinator` into standalone per-device loops.
- `custom_components/solarman/device.py` — Reference device orchestration path (`get()`, bulk execution, parser processing, failure handling) to preserve where sensible.
- `custom_components/solarman/parser.py` — Original per-group scheduling and validation semantics used by the extracted standalone parser.

### Known Risk Notes
- `.planning/codebase/ARCHITECTURE.md` — Reference description of the original HA polling/data flow and parser scheduling semantics.
- `.planning/codebase/CONCERNS.md` — Documents the recursive `_open_connection()` fragility and silent invalid-dataset behavior that this phase must resolve intentionally.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `solarman_logger/pysolarman/__init__.py`: standalone `Solarman` client already exists; Phase 2 should repair its reconnect strategy instead of replacing the client.
- `solarman_logger/parser.py`: `ParameterParser` already loads profiles, builds request batches, and applies validation rules; Phase 2 should reuse it for request selection and bad-data policy.
- `solarman_logger/config.py`: `DeviceConfig` already provides per-device `poll_interval`, host, port, serial, slave, and profile path inputs needed for a polling worker.
- `solarman_logger/logging_setup.py`: root/stdout logging is already in place for device-scoped operational messages.

### Established Patterns
- Current extracted code still mirrors HA's parser/runtime model, especially `schedule_requests(runtime)`, so planner should account for adapting that model to elapsed-time-based standalone scheduling.
- The project already chose copy-and-adapt over rewrite in Phase 1, so Phase 2 should keep extending extracted modules rather than inventing a parallel polling stack.
- Validation behavior is profile-driven, including `invalidate_all`; this phase should preserve profile authority rather than overriding YAML semantics.

### Integration Points
- A standalone per-device polling worker will need to combine `DeviceConfig.poll_interval`, profile-derived request batches from `ParameterParser`, and `Solarman.execute(...)` / connection state from `solarman_logger/pysolarman/__init__.py`.
- Offline/recovery state tracking must sit above the protocol client so logging transitions, backoff, and non-overlap are managed per device.
- Device-type-aware quiet logging likely needs to derive from profile filename and/or parser profile metadata because config currently lacks an explicit device type field.

</code_context>

<specifics>
## Specific Ideas

- The user expects micro-inverters to disappear overnight at sunset when PV input is gone; that should be treated as a normal operational pattern rather than a warning every poll forever.
- Smart meters are expected to be available 24/7, so their offline behavior should stay more visible than sleeping solar devices.
- The user explicitly wants retry frequency for offline devices to slow down over time instead of hammering unreachable devices continuously.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 02-device-polling-loop*
*Context gathered: 2026-03-30*
