# HexWar Engine — Data Flow Reference

How data moves through the program when an action is submitted, and how to add a new action.

---

## Layer cake

```
┌─────────────────────────────────────────────────────────────┐
│  CLIENT (pygame_client.py)                                  │
│   - reads engine.state for rendering                        │
│   - builds Action from input (mouse/key)                    │
│   - calls engine.submit_action(action)                      │
│   - logs returned events into event_log                     │
└────────────┬────────────────────────────────────────────────┘
             │  action ↓        events ↑
┌────────────▼────────────────────────────────────────────────┐
│  ENGINE (core/engine.py)                                    │
│   submit_action(action):                                    │
│     1. check player == active_player                        │
│     2. legal = system.legal_actions(state, player)          │
│     3. validate action in legal                             │
│     4. new_state, events = system.apply_action(state, a, rng)│
│     5. self._state = new_state                              │
│     6. append HistoryEntry (for undo)                       │
│     7. check system.victory(new_state)                      │
│     8. return events                                        │
└────────────┬────────────────────────────────────────────────┘
             │  action ↓        (new_state, events) ↑
┌────────────▼────────────────────────────────────────────────┐
│  SYSTEM (systems/wb48/system.py + mixin handlers)           │
│   legal_actions(state, player) → list[Action]               │
│     - dispatch by phase → mixin builds list                 │
│   apply_action(state, action, rng) → (new_state, events)    │
│     - isinstance dispatch → mixin handler                   │
│     - handler reads state, computes new_state, emits events │
│   victory(state) → Player | None                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Data types

- **State** = immutable `GameState` dataclass. Holds units, map, `phase_index`, `active_player`, `metadata` dict (where battles live).
- **Action** = immutable dataclass. Player intent. Lives in `hexwar/core/actions.py`.
- **Event** = immutable dataclass. Past-tense fact (`UnitMoved`, `BattleResolved`). Lives in `hexwar/core/events.py`. Pure output for UI/log/replay — engine never reads them back.
- **RNG** = seeded, mutable. Only `apply_action` may touch.

---

## Golden rule

`apply_action` is pure-function shape:

```
(state, action, rng) → (new_state, events)
```

Never mutate state in place. Always `state.with_xxx(...)` or `dataclasses.replace(...)`.

---

## Add a new action — recipe

### 1. Define Action

In `hexwar/core/actions.py`:

```python
@dataclass(frozen=True, slots=True)
class FooAction(Action):
    player: Player
    unit_id: UnitId
    # ...payload
```

### 2. Define Event(s)

In `hexwar/core/events.py` for state changes worth logging:

```python
@dataclass(frozen=True, slots=True)
class FooHappened(Event):
    unit_id: UnitId
```

### 3. Add to `legal_actions`

In correct mixin/phase under `hexwar/systems/wb48/`. Engine refuses any action not in legal list.

### 4. Add handler

```python
def _apply_foo(self, state, action) -> tuple[GameState, list[Event]]:
    # read state
    # compute new_state via state.with_xxx
    # return (new_state, events)
```

### 5. Wire dispatch

In `system.apply_action` chain:

```python
if isinstance(action, FooAction):
    return self._apply_foo(state, action)
```

### 6. Wire client

In `hexwar/client/pygame_client.py`: on input, build `FooAction(...)`, call `self.engine.submit_action(action)`, append returned events to `event_log`.

### 7. Test

Write functional test in `tests/` per CLAUDE.md rule.

---

## Sequence — one click → one action

```
User clicks hex
  │
  ▼
pygame_client._handle_click(pos)
  │  builds MoveAction(player, unit_id, target)
  ▼
engine.submit_action(action)
  │  legal = system.legal_actions(state, player)   ── reads state
  │  validate
  │  new_state, events = system.apply_action(state, action, rng)
  │       │
  │       ▼
  │     system._apply_move(state, action)
  │       │  unit = state.get_unit(action.unit_id)
  │       │  new_unit = unit.with_position(action.target)
  │       │  new_state = state.with_unit(new_unit)
  │       │  events = [UnitMoved(...)]
  │       │  return (new_state, events)
  │  self._state = new_state           ── engine commits
  │  history.append(HistoryEntry)      ── for undo
  │  return events
  ▼
pygame_client logs events, re-renders from engine.state
```

---

## Where to look when lost

| Question                | File                                   |
|-------------------------|----------------------------------------|
| What state shape?       | `hexwar/core/state.py`, `unit.py`, `battle.py` |
| What actions exist?     | `hexwar/core/actions.py`               |
| What events fire?       | `hexwar/core/events.py`                |
| Engine pipeline?        | `hexwar/core/engine.py` (`submit_action`) |
| System interface (ABC)? | `hexwar/systems/base.py`               |
| WB-48 phases/dispatch?  | `hexwar/systems/wb48/system.py`        |
| Per-mechanic logic?     | `hexwar/systems/wb48/*.py` (one mixin per mechanic) |
| UI wiring?              | `hexwar/client/pygame_client.py`       |

---

## Phase advancement (separate path from regular actions)

`EndPhaseAction` takes a different route through `engine.submit_action`:

```
engine.submit_action(EndPhaseAction)
  │
  ├─ system.should_advance_phase(state) == True?
  │     │
  │     ├─ YES → engine._advance_phase()
  │     │         - system.on_phase_exit(state, current_phase)
  │     │         - increment phase_index (wrap → new turn + on_turn_start)
  │     │         - state.with_phase(next_index, next_player)
  │     │         - system.on_phase_enter(state, new_phase)
  │     │         - emit PhaseChanged event
  │     │
  │     └─ NO  → routed through normal apply_action
  │               (system handles sub-phase transitions internally)
  ▼
events returned to client
```

Use `should_advance_phase` to override when a phase has internal sub-steps (e.g. combat phase has declare → resolve → post-battle sub-phases).
