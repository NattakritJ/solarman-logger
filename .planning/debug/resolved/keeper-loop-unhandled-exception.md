---
status: resolved
trigger: "Investigate issue: keeper-loop-unhandled-exception"
created: 2026-04-02T00:00:00Z
updated: 2026-04-02T00:03:00Z
---

## Current Focus
<!-- OVERWRITE on each update - reflects NOW -->

hypothesis: CONFIRMED AND FIXED
test: Applied done_callback to the fire-and-forget create_task in _keeper_loop; verified _send_receive_frame path unchanged
expecting: No more "Task exception was never retrieved" errors during overnight device sleep
next_action: Await human confirmation that the fix resolves the issue in production

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected: When a device goes offline (inverter nighttime shutdown), the connection failure should be caught silently. An INFO log like "[Device] Device offline: (expected overnight sleep possible)" is correct. No traceback or asyncio error should appear.

actual: Most of the time the offline path works correctly (INFO log only). But intermittently, the same `ConnectionError` from `_open_connection` leaks as an unhandled task exception. Appears to come from `_keeper_loop` spawning `_open_connection` as a fire-and-forget task whose exception is never awaited.

errors: |
  ERROR    [asyncio] Task exception was never retrieved
  future: <Task finished name='Task-XXXX' coro=<Solarman._open_connection() done, defined at /app/solarman_logger/common.py:34> exception=ConnectionError('[HOST] Failed to connect after 3 attempts')>
  ConnectionError: [HOST] Failed to connect after 3 attempts

  (Appears for hosts 10.20.30.60, 10.20.30.61, 10.20.30.62)

reproduction: Devices go offline overnight (normal inverter sleep). On reconnection attempts from the keeper loop, _open_connection is sometimes spawned as a task but the exception is never retrieved.

started: Ongoing — happens every night during overnight device sleep cycles.

## Eliminated
<!-- APPEND only - prevents re-investigating -->

- hypothesis: Both create_task call sites are affected
  evidence: _send_receive_frame immediately awaits self._keeper (line 269 after fix), so any exception from _open_connection IS propagated to the caller. Only _keeper_loop is the problem.
  timestamp: 2026-04-02T00:01:00Z

- hypothesis: The bug is in the retry/throttle decorator wrapping _open_connection
  evidence: The traceback says "defined at common.py:34" because @throttle wraps the function — common.py:34 is the throttle wrapper. The actual unhandled raise happens at pysolarman/__init__.py:243. The decorators don't suppress the exception — they let it propagate normally. The problem is at the asyncio task creation level, not inside the function.
  timestamp: 2026-04-02T00:01:00Z

## Evidence
<!-- APPEND only - facts discovered -->

- timestamp: 2026-04-02T00:01:00Z
  checked: solarman_logger/pysolarman/__init__.py line 196-216 (_keeper_loop)
  found: At the end of _keeper_loop (after the while loop exits due to ConnectionResetError or empty data), line 216 did:
    `self._keeper = create_task(self._open_connection())`
    This created an asyncio Task for _open_connection() but never added a done_callback or stored a reference to await later.
    The result IS stored in self._keeper, but nothing ever awaits or checks self._keeper after this point unless _send_receive_frame is called — and during overnight device sleep, _send_receive_frame is NOT called because the device is unreachable.
  implication: When the device stays offline through all 3 retry attempts, _open_connection raises ConnectionError(f"[{self.host}] Failed to connect after {max_attempts} attempts"). Since the Task was created fire-and-forget from _keeper_loop (which itself is finishing), nobody retrieves this exception. Python's asyncio logs it as "Task exception was never retrieved" when the Task is garbage-collected.

- timestamp: 2026-04-02T00:01:00Z
  checked: solarman_logger/pysolarman/__init__.py line 262-269 (_send_receive_frame)
  found: Line 268: `self._keeper = create_task(self._open_connection())`
         Line 269: `await self._keeper`
    Here the task is immediately awaited, so any ConnectionError IS propagated to the caller and handled upstream.
  implication: This path is safe — the exception is retrieved. Only the _keeper_loop path is the problem.

- timestamp: 2026-04-02T00:01:00Z
  checked: solarman_logger/pysolarman/__init__.py line 226-243 (_open_connection)
  found: _open_connection raises ConnectionError in two cases:
    (a) line 240: first attempt fails AND self._last_frame is None (initial connection failure — never connected before)
    (b) line 243: all max_attempts exhausted on a reconnect (self._last_frame is not None — device was previously connected)
    Case (b) is what happens during overnight sleep and is the one leaking from _keeper_loop.
  implication: The fix handles ConnectionError from case (b) at the Task callback level, suppressing it at debug level.

- timestamp: 2026-04-02T00:01:00Z
  checked: solarman_logger/common.py line 43-44 (create_task)
  found: create_task is a thin wrapper: `asyncio.get_running_loop().create_task(coro, name=name, context=context)`
    No exception handling added here. Standard asyncio behavior: if the Task finishes with an exception and nothing retrieves it, Python logs the warning.
  implication: Fix applied at the call site in _keeper_loop, not in create_task itself.

- timestamp: 2026-04-02T00:02:00Z
  checked: Applied fix — _keeper_loop in solarman_logger/pysolarman/__init__.py
  found: Added _on_reconnect_done callback nested inside _keeper_loop, registered via .add_done_callback() immediately after create_task(). The callback:
    - Checks task.cancelled() first to skip cancelled tasks
    - If exception is ConnectionError → logs at DEBUG level (expected offline scenario)
    - If exception is any other type → logs at WARNING level (unexpected, needs visibility)
    - If no exception (success path) → no-op
  implication: The done_callback "retrieves" the exception from asyncio's perspective (task.exception() call marks it retrieved), preventing the "Task exception was never retrieved" log pollution.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: In `_keeper_loop` (line 216, pre-fix), after the connection drops the while-loop exits and `create_task(self._open_connection())` spawns a reconnection Task fire-and-forget. If `_open_connection` exhausts all 3 retry attempts (device is offline overnight), it raises `ConnectionError`. Because nothing ever awaits or adds a done_callback to this Task, asyncio logs "Task exception was never retrieved" when the Task is garbage-collected. The `_send_receive_frame` call site is safe because it immediately `await`s the task on the next line.

fix: Added a `_on_reconnect_done(task)` done_callback nested inside `_keeper_loop`. It is registered immediately after `create_task()` via `.add_done_callback()`. The callback calls `task.exception()` (which marks the exception as retrieved), logs `ConnectionError` at DEBUG level (device offline is expected), and logs other exception types at WARNING level for visibility.

verification: Code review confirmed both call sites. _send_receive_frame path (await self._keeper) is untouched and safe. _keeper_loop path now has exception handling via done_callback.

files_changed:
  - solarman_logger/pysolarman/__init__.py
