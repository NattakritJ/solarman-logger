# Phase 2: Device Polling Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 02-device-polling-loop
**Areas discussed:** Startup failure policy, Overrun handling, Bad data handling, Connection recovery style

---

## Startup failure policy

| Option | Description | Selected |
|--------|-------------|----------|
| Start anyway | Bring the service up, keep polling reachable devices, and log warnings for the failed device until it recovers. | ✓ |
| Fail if any device fails | Abort startup unless every configured device answers successfully on the first cycle. | |
| Fail only if all fail | Stay up if at least one device is reachable, but total startup failure is fatal. | |

**User's choice:** Start anyway
**Notes:** User explained this is required because micro-inverters normally go offline at sunset when PV input disappears, while the meter remains online 24/7.

| Option | Description | Selected |
|--------|-------------|----------|
| Warn once, then quiet | Warn when the device first goes offline, then suppress or downgrade repeats until recovery. | ✓ |
| Warn every cycle | Emit a warning on every failed poll. | |
| Info for repeats | Warn on first offline transition, then log repeated failures at INFO. | |

**User's choice:** Warn once, then quiet
**Notes:** Repeated warnings every cycle would be too noisy for nightly sleeping inverters.

| Option | Description | Selected |
|--------|-------------|----------|
| All devices same | Use the same offline logging policy for every configured device. | |
| By device type | Treat solar/micro-inverter devices as expected-to-sleep while meters stay more visible when offline. | ✓ |
| Per-device config | Add a new per-device YAML flag for expected sleep behavior. | |

**User's choice:** By device type
**Notes:** User wants meters treated as always-on infrastructure and inverters treated as naturally sleep-prone.

| Option | Description | Selected |
|--------|-------------|----------|
| Infer from profile | Use profile filename and/or parser metadata to classify sleep-expected devices. | ✓ |
| Add config flag | Add an explicit per-device config field. | |
| Same runtime behavior | Do not distinguish at runtime yet. | |

**User's choice:** Infer from profile
**Notes:** User preferred no new config surface in this phase.

| Option | Description | Selected |
|--------|-------------|----------|
| Per-device backoff | Lengthen retry interval only for the failing device while healthy devices stay normal. | ✓ |
| Always same interval | Retry forever at the normal poll interval. | |
| Offline mode by type | Switch sleep-expected devices to a slower fixed interval but leave always-on devices unchanged. | |

**User's choice:** Per-device backoff
**Notes:** User explicitly asked about retry frequency for offline devices.

| Option | Description | Selected |
|--------|-------------|----------|
| Cap around 5 minutes | Quiet overnight behavior with still-reasonable recovery time. | ✓ |
| Cap around 1 minute | More responsive, but still noisy overnight. | |
| Cap around 15 minutes | Very quiet, but slower recovery. | |

**User's choice:** Cap around 5 minutes
**Notes:** Chosen as the operational balance between recovery and overnight noise.

---

## Overrun handling

| Option | Description | Selected |
|--------|-------------|----------|
| Skip overlap | Never run two polls for the same device at once; skip missed intervals and schedule from current time. | ✓ |
| Queue backlog | Run every missed poll in order. | |
| Run immediately after | Start the next due poll immediately after an overrun completes. | |

**User's choice:** Skip overlap
**Notes:** User preferred non-overlapping per-device execution over catch-up behavior.

| Option | Description | Selected |
|--------|-------------|----------|
| Debug summary | Record skipped/late-cycle details at DEBUG. | ✓ |
| Info on every overrun | Log overruns at INFO. | |
| Warning on every overrun | Log overruns at WARNING. | |

**User's choice:** Debug summary
**Notes:** Keeps normal operation quiet while still allowing schedule verification.

| Option | Description | Selected |
|--------|-------------|----------|
| Real elapsed time | Group intervals mean real wall-clock elapsed time per device. | ✓ |
| Successful poll count | Advance group timing only after completed polls. | |
| Attempt count | Advance group timing on every scheduled attempt. | |

**User's choice:** Real elapsed time
**Notes:** User first asked what per-group scheduling meant, then chose real elapsed time so hourly groups remain hourly even across delays/offline periods.

---

## Bad data handling

| Option | Description | Selected |
|--------|-------------|----------|
| Drop full cycle on invalidate_all | Honor profile invalidation rules and discard the whole poll result when requested. | ✓ |
| Always keep partial fields | Keep whatever parsed successfully even if the profile requests full invalidation. | |
| Reuse last-good values | Fill invalid fields from previous data. | |

**User's choice:** Drop full cycle on invalidate_all
**Notes:** User wanted profile-driven safety rules preserved.

| Option | Description | Selected |
|--------|-------------|----------|
| Warning on transition, debug on repeats | Warn when invalid full datasets begin, then quiet repeated drops until recovery. | ✓ |
| Warning every time | Emit a warning on every dropped cycle. | |
| Info only | Keep invalid datasets lower-noise. | |

**User's choice:** Warning on transition, debug on repeats
**Notes:** Matches the same transition-based visibility requested for offline devices.

| Option | Description | Selected |
|--------|-------------|----------|
| Keep valid fields, drop invalid ones | Preserve usable data when the profile does not request full invalidation. | ✓ |
| Drop whole cycle anyway | Discard the entire poll if any field fails validation. | |
| Keep all fields with flags | Retain invalid values with additional marking. | |

**User's choice:** Keep valid fields, drop invalid ones
**Notes:** User wants partial retention only when the YAML profile permits it.

---

## Connection recovery style

| Option | Description | Selected |
|--------|-------------|----------|
| Background reconnect loop | Use a task/loop with retry logic instead of recursive self-calls. | ✓ |
| Retry inside execute | Reconnect synchronously inside each request path. | |
| Reconnect only next cycle | Wait until the next scheduled poll to try reconnecting. | |

**User's choice:** Background reconnect loop
**Notes:** Chosen to satisfy the roadmap requirement to eliminate `RecursionError` under sustained failure.

| Option | Description | Selected |
|--------|-------------|----------|
| Wait for next poll | Do not replay the interrupted request automatically after reconnect. | ✓ |
| Replay last request | Resend the last in-flight request automatically. | |
| Replay only reads | Retry interrupted reads but not writes. | |

**User's choice:** Wait for next poll
**Notes:** User preferred fresh scheduling over automatic replay of possibly stale in-flight work.

| Option | Description | Selected |
|--------|-------------|----------|
| Warn on offline, info on recovery | Offline transition is a warning; recovery is logged at INFO. | ✓ |
| Info both ways | Both transitions are informational. | |
| Warn both ways | Both transitions are warnings. | |

**User's choice:** Warn on offline, info on recovery
**Notes:** User wanted clear operational visibility without treating recovery as an error.

## the agent's Discretion

- Exact backoff curve before reaching the 5-minute cap
- Exact thresholds for log-level downgrades on repeated offline or invalid-data events
- Internal elapsed-time scheduling implementation details
- Exact message text for overrun/offline/recovery logs

## Deferred Ideas

None - discussion stayed within phase scope.
