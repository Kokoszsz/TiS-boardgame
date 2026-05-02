# HexWar Engine — Project Context

Read `PROJECT_CONTEXT.md` for full architecture details. Key points below.

## What We're Building

Generic hex-based 2-player turn-based wargame engine in Python. Not one game — an **engine** supporting multiple **game systems** (rule set plugins) and **scenarios** (specific battles). Digitizing physical hex wargame series from taktykaistrategia.pl.

## Architecture: 3 Layers

```
Engine (generic)  →  System (rule set plugin)  →  Scenario (battle data)
```

- **Engine**: hex math, generic unit container, immutable game state, action dispatch, turn driver, seeded RNG. Knows nothing about specific rules.
- **System**: implements specific rule set via ABC. Defines phases, unit types, legal actions, combat resolution, victory conditions.
- **Scenario**: YAML config — map terrain, unit placement, victory conditions.

## Tech Stack

- Pure Python core engine (zero rendering deps)
- Pygame desktop client (MVP)
- FastAPI + WebSocket multiplayer (deferred)
- Hot-seat first, network later

## Core Design

- Immutable state: `apply_action(state, action) → (new_state, events)`
- System plugin via ABC: `legal_actions`, `apply_action`, `victory`
- Deterministic seeded RNG
- Unit stats as `dict[str, Any]` — system defines schema

## Package Layout

```
hexwar/
  core/       # hex.py, map.py, unit.py, state.py, actions.py, events.py, rng.py, engine.py
  systems/    # base.py (ABC), test_system.py, wb48/
  scenarios/  # *.yaml
  client/     # pygame_client/
```

## Implementation Order

1. Engine core (`hexwar/core/`) — no rules needed
2. System ABC + TestSystem — dummy system proving engine works
3. Pygame hot-seat client
4. WB-48 system plugin (needs completed `wb48_rules.md`)
5. First scenario — digitize one WB-48 battle

## Key Files

- `PROJECT_CONTEXT.md` — full architecture, System ABC interface, engine vs system ownership table
- `implementation_plan.md` — detailed step-by-step plan with substeps
- `wb48_rules.md` — extracted WB-48 rulebook (gaps marked `[DO UZUPEŁNIENIA]`)
- `instruciton images/` — photos of physical WB-48 instruction manual

## First System: WB-48

WW1 regiment-division scale. 12 phases/turn, CRT combat, ZOC, artillery, supply, disorganization.

## Development Rules

### Mandatory: Test After Every Mechanic
After implementing any new mechanic (terrain costs, ZOC, stacking, combat changes, etc.):
1. Write functional tests in `tests/` covering the mechanic + edge cases
2. Tests go through full engine pipeline: build scenario → submit actions → assert state
3. Run `python -m pytest tests/ -v` and confirm all pass before moving on
4. Use helpers from `tests/conftest.py`: `make_engine`, `make_unit`, `make_map`, `do_actions`, `assert_unit_at`, `assert_action_legal`, `assert_action_illegal`, etc.
5. Never skip this step. No mechanic is done until tests pass.

### Engine vs System Separation
- Generic mechanics (pathfinding framework, phase substeps, state management) → `hexwar/core/`
- Game-specific rules (terrain costs, CRT values, ZOC behavior) → `hexwar/systems/`
- When adding a mechanic: engine provides the framework, system provides the values/logic

## User Preferences

- Knows Python best
- Prefers concise discussion, not over-detailed brainstorming
- Pragmatic choices over theoretically optimal ones
