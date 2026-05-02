# Hex Wargame Engine — Implementation Plan

## Step 1 — Engine Core (`hexwar/core/`)

No rulebook needed. Pure generic infrastructure.

### 1.1 `hex.py` — Hex Math
- `HexCoord` frozen dataclass (axial q,r + cube s property, `q + r + s = 0`)
- `neighbors(coord)` → 6 adjacent hexes (fixed direction offsets)
- `distance(a, b)` → int (max of cube coord diffs)
- `line(a, b)` → list of hexes on straight line (for LOS, supply lines)
- `ring(center, radius)` → hexes at exact distance
- `area(center, radius)` → all hexes within distance (filled circle)
- `hex_to_pixel(coord, size)` → (x, y) screen position
- `pixel_to_hex(x, y, size)` → HexCoord (click detection)
- Flat-top orientation (standard for wargames — confirm with WB-48 board)

### 1.1b `pathfinding.py` — Hex Grid Pathfinding
- Generic BFS/Dijkstra on hex grid — no game rules, pure graph algorithm
- System plugs in game-specific logic via callback functions:
  - `cost_fn(from, to) → float | None` — movement cost between adjacent hexes (None = impassable)
  - `blocked_fn(coord) → bool` — is hex blocked entirely
- `reachable_hexes(start, mp, cost_fn, blocked_fn) → dict[HexCoord, int]` — all hexes unit can reach + remaining MP
- `shortest_path(start, end, cost_fn, blocked_fn) → list[HexCoord] | None` — path for animation/display
- Client caches result per selected unit, invalidates on state change
- Will evolve as real rules expose edge cases

### 1.2 `map.py` — Hex Grid + Edge Features
Two data layers — per-hex terrain and per-edge connections:

**Per-hex terrain (one hex can have multiple terrains, e.g. "city in forest", "hill with swamp"):**
- `TerrainType` — enum (forest, plain, hill, city, swamp, marsh, etc.)
- `TerrainLayer` — dataclass (type: TerrainType + modifiers if needed)
- `dict[HexCoord, list[TerrainLayer]]` — each hex has list of terrain features
- System interprets how multiple terrains stack (e.g. movement cost = sum? worst? custom rule)

**Per-edge features (roads, rivers, railways, bridges):**
- `EdgeFeature` — dataclass (type: road/railway/river/bridge)
- `dict[FrozenSet[HexCoord], list[EdgeFeature]]` — one edge can have multiple features (e.g. bridge over river)
- Edge = pair of adjacent hexes, order doesn't matter

**HexMap class:**
- `get_terrain(coord)` → Terrain
- `get_edge(a, b)` → list[EdgeFeature] (what's between two hexes)
- `has_road(a, b)` → bool
- `has_river(a, b)` → bool
- `road_connections(coord)` → list[HexCoord] (neighbors connected by road)
- `is_passable(coord)` → bool
- Load from dict/YAML

**Note:** Map is static — loaded once from scenario, never changes during game. Units are NOT stored in map (they change every turn → live in GameState).

### 1.3 `unit.py` — Generic Unit

Two classes — blueprint and instance:

**`UnitType` — template (defined by System plugin):**
- `type_id`: str — e.g. `"infantry"`, `"artillery"`, `"hq"`, `"cavalry"`
- `category`: str — broad role grouping (for future subdivision, e.g. light/heavy infantry)
- `stat_schema`: list[str] — which stats units of this type must have (e.g. `["strength", "movement", "morale"]`)
- `display_info`: dict — icon, symbol, color (for renderer)
- Few per system (5-10). Never changes during game.
- System uses type_id for rule routing (artillery can bombard, HQ gives command range, etc.)

**`Unit` — individual instance on the board (defined by Scenario YAML):**
- `id`: UnitId (str) — unique identifier (`"1pp"`, `"art_3"`)
- `name`: str — display name (`"1 Pułk Piechoty"`, `"III Brygada Kawalerii"`)
- `type_id`: str — links to UnitType
- `player`: Player — which side
- `position`: HexCoord — current location
- `stats`: dict[str, Any] — **individual** values per unit, not shared from type
- Many per scenario (20-100). Stats change during game (strength loss, disorganization, etc.)

**Why stats are individual, not on UnitType:**
- Same type units have different values (two infantry regiments with different strength)
- Scenario YAML sets initial stats per unit explicitly
- UnitType defines which stat keys exist (schema), Unit stores actual values (data)

`UnitId` type alias (str)

### 1.4 `state.py` — Immutable GameState
- `GameState` frozen dataclass:
  - `scenario_id`: str — unique ID (`"tannenberg_1914"`)
  - `scenario_name`: str — display name (`"Bitwa pod Tannenbergiem"`)
  - `system_id`: str — which system (`"wb48"`, `"napoleon"`)
  - `units: FrozenDict[UnitId, Unit]`
  - `units_by_hex: FrozenDict[HexCoord, tuple[UnitId, ...]]` — reverse index, hex → units on it
  - `hex_map: HexMap`
  - `turn: int`
  - `phase_index: int`
  - `active_player: Player`
  - `active_restrictions: tuple[Restriction, ...]` — currently active scenario restrictions (some expire by turn/condition)
  - `pending_timeline: tuple[TimelineEvent, ...]` — scheduled events not yet triggered
  - `victory_points: FrozenDict[Player, int]` — if scenario uses VP scoring
  - `metadata: dict` (system can store extra state here)
- **Bidirectional unit lookup:**
  - Unit → Hex: `unit.position`
  - Hex → Units: `state.units_by_hex[coord]` (instant, no scanning)
  - Both kept in sync — when unit moves, both update in new state
- Helper methods: `get_unit(id)`, `units_at(coord)`, `units_of(player)`
- State is never mutated — `apply_action` returns new state

### 1.4b `scenario.py` — Scenario Configuration

Scenarios are complex — not just "place units, go." They have timelines, restrictions, and victory conditions.

**`ScenarioConfig` dataclass — loaded from YAML, read-only:**
- `scenario_id`: str
- `scenario_name`: str
- `system_id`: str
- `map_data`: terrain + edges definition
- `initial_units`: list of unit placements per player
- `timeline`: list[TimelineEvent] — things that happen on specific turns
- `restrictions`: list[Restriction] — conditional rules limiting actions
- `victory`: VictoryConfig — how to win

**`TimelineEvent` — scheduled scenario events:**
- `trigger`: condition (turn number, or custom condition)
- `action`: what happens — spawn units, remove restriction, show message, change terrain
- Examples: reinforcements arrive turn 3, restriction lifts turn 6, weather changes turn 8

**`Restriction` — conditional rules:**
- `id`: str — for referencing/removing
- `type`: movement_barrier, no_attack, unit_locked, area_forbidden, etc.
- `affected_units`: filter (by player, type, specific unit IDs)
- `params`: type-specific data (barrier hex line, forbidden area, etc.)
- `until`: expiry condition (turn number, event trigger, or manual removal by timeline)
- `message`: str — display reason to player
- System checks active restrictions in `legal_actions` — filtered units can't perform restricted actions

**`VictoryConfig` — complex victory conditions:**
- `type`: single or composite
- `conditions`: list — can combine multiple:
  - `control_hexes` — hold specific VP hexes, points each
  - `elimination_ratio` — destroy X% of enemy strength
  - `turn_limit` — max turns, with tiebreaker rule
  - `hold_hex_for_n_turns` — maintain control for duration
  - `exit_units_off_map` — evacuate units through edge hexes
  - System can define custom condition types
- `tiebreaker`: rule if conditions tied at turn limit

**Engine processes timeline + restrictions. System interprets what they mean mechanically.**

### 1.5 `actions.py` — Base Action Types
- `Action` base (Pydantic model): `player`, `action_type`
- Built-in types: `MoveAction`, `AttackAction`, `EndPhaseAction`, `EndTurnAction`
- Systems can define custom actions (inherit from `Action`)

### 1.6 `events.py` — Base Event Types
- `Event` base (Pydantic model): `event_type`, `timestamp`
- Built-in: `UnitMoved`, `CombatResolved`, `UnitDestroyed`, `PhaseChanged`, `TurnChanged`
- Systems extend with custom events

### 1.7 `rng.py` — Deterministic RNG
- `GameRNG` wrapping Python `random.Random` with seed
- `roll_d6()`, `roll_dice(n, sides)`
- Seed stored in GameState for replay/sync

### 1.8 `engine.py` — Turn Driver + Action Dispatch
- `Engine` class:
  - Holds current `GameState` + `System` + `GameRNG`
  - `submit_action(action)` → validates via system, applies, returns events
  - `get_legal_actions()` → delegates to system
  - Phase/turn advancement logic (reads phase list from system)
  - Action history log (for replay/undo)
- Core loop: `legal_actions → player picks → apply → events → next`

---

## Step 2 — System ABC + TestSystem

### 2.1 `systems/base.py` — Abstract System
```python
class System(ABC):
    name: str
    version: str
    phases: list[PhaseDef]        # phase sequence per player-turn
    unit_types: dict[str, UnitTypeDef]  # unit schema definitions

    @abstractmethod
    def legal_actions(self, state: GameState, player: Player) -> list[Action]: ...

    @abstractmethod
    def apply_action(self, state: GameState, action: Action, rng: GameRNG) -> tuple[GameState, list[Event]]: ...

    @abstractmethod
    def victory(self, state: GameState) -> Player | None: ...

    def on_phase_enter(self, state: GameState, phase: PhaseDef) -> tuple[GameState, list[Event]]:
        return state, []
```

- `PhaseDef`: name, allowed_action_types, auto_advance flag
- `UnitTypeDef`: stat schema (what keys must be in `stats`), display info

### 2.2 `systems/test_system.py` — Dummy System
- 2 phases: Movement, Combat
- 2 unit types: Infantry (move 2, strength 3), Tank (move 4, strength 5)
- Movement: move up to unit.stats["move_range"] hexes
- Combat: adjacent enemy, compare strength, higher wins (tie = both stay)
- Victory: eliminate all enemy units
- Purpose: validate full engine loop without real rules

---

## Step 3 — Pygame Hot-Seat Client

### 3.1 Hex Rendering
- Flat-top or pointy-top hex grid (configurable)
- `pixel_to_hex(x, y)` and `hex_to_pixel(coord)` conversion
- Camera pan + zoom
- Terrain coloring per type

### 3.2 Unit Rendering
- Unit tokens on hex (NATO symbols or simple colored shapes for MVP)
- Stack indicator when multiple units on same hex
- Player color coding

### 3.3 Interaction
- Click hex → select unit (if friendly, if current phase allows)
- Click destination → show legal moves highlighted → confirm move
- Click enemy adjacent → attack (if combat phase)
- End Phase button
- Turn/phase indicator in UI

### 3.4 Game Loop
- Init: load scenario (map + units) → create GameState → create Engine
- Each frame: render state, handle input, submit actions to engine, apply events
- Hot-seat: same screen, players alternate

### 3.5 MVP UI Elements
- Hex grid with terrain
- Unit tokens with basic info (type, strength)
- Selected unit highlight + legal move overlay
- Phase name + turn counter
- "End Phase" button
- Combat result popup (attacker, defender, roll, result)

---

## Step 4 — WB-48 System Plugin

Requires completed `wb48_rules.md`. Implements full WB-48 rules.

### 4.1 Phase Structure (12 phases per turn)
1. Faza bieżąca gracza A (admin/bookkeeping)
2. Nawała artyleryjska gracza A (artillery barrage)
3. Ruch oddziałów gracza A (movement)
4. Atak oddziałów gracza A (combat)
5. Ruch strategiczny gracza A (strategic movement)
6. Faza zaopatrzenia gracza A (supply)
7-12. Mirror for Player B

### 4.2 Unit Types
- Piechota (infantry) — p, pk, pg, etc.
- Kawaleria (cavalry) — k, kz
- Artyleria (artillery) — a, ac, ad
- Dowództwo (HQ) — D
- Each with: strength, movement, type-specific stats

### 4.3 Core Mechanics to Implement
- **Movement**: terrain costs, ZOC entry/exit rules, stacking limits (3 units/hex)
- **ZOC (Strefa Kontroli)**: 6 adjacent hexes, blocks movement, forces combat
- **CRT Combat**: force ratio → column, d6 roll → row, lookup result (De, Do, Dn, DA, OA, etc.)
- **Artillery Barrage**: range-based bombardment, separate from regular combat
- **Counterattacks**: defender can counter after surviving attack
- **Supply**: trace supply line to supply source, out-of-supply penalties
- **Disorganization**: combat result effect, movement/combat penalties
- **Strategic Movement**: double movement, no ZOC entry, no combat
- **HQ Command Range**: units must be within range of HQ for full effectiveness

### 4.4 CRT Implementation
- Ratio calculation: attacker total strength / defender total strength
- Terrain modifiers (defense bonus)
- Result table as dict/2D array
- Results: De (defender eliminated), Do (defender retreats), Dn (no effect), DA (attacker eliminated), OA (both), etc.

---

## Step 5 — First Scenario

### 5.1 Scenario Format (YAML)
```yaml
system: wb48
name: "Bitwa pod Tannenbergiem"
map:
  width: 20
  height: 15
  terrain:
    - coord: [0, 0]
      type: forest
    # ...
units:
  player_a:
    - type: infantry
      id: "1pp"
      position: [3, 5]
      stats:
        strength: 4
        movement: 3
  player_b:
    # ...
victory:
  type: elimination  # or objective_hex, turn_limit, etc.
  params: {}
special_rules: []
turn_limit: 20
```

### 5.2 Tasks
- Pick one WB-48 scenario from physical game box
- Digitize hex map (terrain per hex)
- Digitize Order of Battle (all units, positions, stats)
- Define victory conditions
- Playtest full game hot-seat

---

## Dependencies Between Steps

```
Step 1 (engine core) ──→ Step 2 (system ABC + test) ──→ Step 3 (pygame client)
                                                              │
                                              wb48_rules.md ──┤
                                                              ▼
                                                     Step 4 (WB-48 system)
                                                              │
                                                              ▼
                                                     Step 5 (first scenario)
```

- Steps 1-3: no rulebook needed, can start now
- Step 4: needs completed wb48_rules.md (especially CRT table)
- Step 5: needs physical scenario components digitized

## Estimated Scope
- Step 1: ~500-700 lines Python
- Step 2: ~200-300 lines
- Step 3: ~400-600 lines
- Step 4: ~600-1000 lines (most complex — real rules)
- Step 5: ~1 YAML file + playtesting
