# Hex Wargame Engine — Implementation Plan

Approach: build engine + WB-48 rules first (no abstraction between engine and "test system" — WB-48 is the system). Then scenarios, client polish, AI, multiplayer.

Status legend: ✓ done · ◐ partial · ☐ todo

---

## Step 1 — Engine Core (`hexwar/core/`)
**Status: ✓ done**

Generic infrastructure, no rules.

- `hex.py` — HexCoord, neighbors, distance, line, ring, area, pixel<->hex
- `pathfinding.py` — BFS/Dijkstra with system callbacks for costs/blocking
- `map.py` — HexMap, terrain layers, edge features (rivers, bridges)
- `unit.py` — generic Unit (dict stats), UnitTypeDef
- `state.py` — immutable GameState, `with_*` helpers, build_initial_state
- `actions.py` — Move, Attack, DeclareAttack, ResolveBattle, ChooseRetreatSplit, AssignCplLoss, RetreatUnit, Pursuit, SkipPursuit, EndPhase, Entrench, etc.
- `events.py` — UnitMoved, BattleResolved, UnitLostCpl, UnitRetreated, UnitPursued, etc.
- `rng.py` — seeded GameRNG
- `engine.py` — turn driver, action dispatch, undo, event log
- `battle.py` — Battle dataclass + PostBattlePhase enum
- `combat_results.py` — CombatResult dataclass

---

## Step 2 — WB-48 System Rules (`hexwar/systems/wb48/`)

All rules in [wb48_rules_en.md](wb48_rules_en.md). One system, fully native; not generic until proven needed.

### 2.1 Phase Structure (sec 3.0) — ◐ partial
12 phases per turn, 6 per player:
1. Air phase
2. Artillery barrage
3. Movement ✓
4. Combat ✓
5. Strategic movement
6. Supply

Currently implemented: 3, 4. Air phase + barrage + supply still missing.

### 2.2 Movement (sec 4.0) — ✓ done
Terrain costs, hex-by-hex, MP tracking, friendly stacking on path.

### 2.3 Stacking (sec 5.0) — ✓ done
3 units/hex limit (`STACK_LIMIT`). Friendly only — enemies block entry.

### 2.4 ZOC (sec 6.0) — ✓ done
6-hex projection, blocks movement (stops on entry), ZOC-to-ZOC blocked. Unit-type filter (`ZOC_UNIT_TYPES`).

### 2.5 Combat (sec 7.0) — ✓ done
Declaration sub-phase: fan-in / fan-out, must-attack rules.
Resolution sub-phase: CRT lookup, dice, results.
Post-battle pipeline: split (retreat/loss), CPL assignment, retreat movement, pursuit (rule 7.57 partial-elimination handling).

### 2.6 Strategic Movement (sec 11.0) — ☐ NEXT
- **11.11** New phase after combat
- **11.12** Eligible units: did NOT move this turn, did NOT fight, did NOT build FF, NOT in enemy ZOC, was tagged with "SM token" during movement phase
- **11.21** MP reduced by 2 during SM
- **11.22** Cannot enter enemy ZOC during SM
- **11.23** Unit performing SM cannot conduct combat afterwards (already past combat phase, so trivially enforced)

Implementation outline:
- New phase `strategic_a`/`strategic_b` in WB48System phase list
- New action `MoveStrategicAction` OR reuse `MoveAction` gated by phase
- Track unit metadata: `moved_this_turn`, `fought_this_turn`, `built_ff_this_turn`, `sm_token` flag
- New mixin `StrategicMovementMixin` in `hexwar/systems/wb48/strategic_movement.py`
- Update `_legal_move_actions` filter for SM phase: enforce eligibility + ZOC restriction
- Tests in `tests/test_strategic_movement.py`

### 2.7 Supply (sec 12.0) — ☐
- Supply lines via pathfinding (roads/rails unlimited, off-road MP-limited)
- ZOC blocks supply unless friendly unit on hex
- Supply level token (decay 0 → 1 → 2)
- Supply lack effects on combat + movement
- Supply bases per scenario

### 2.8 Disorganization (sec 14.0) — ◐ partial
`PostBattlePhase.DISORG_ROLLS` enum exists; `_initial_post_phase` returns it for some results. Missing: actual disorg roll handler, movement/combat penalties for disorganized units, recovery rules.

### 2.9 Artillery (sec 8.0) — ☐
- Independent fire (8.2)
- Supporting attack/defense (8.3, 8.4)
- Direct combat (8.5)
- Barrage phase (8.6)
- Artillery movement (8.7) — limber/unlimber

### 2.10 HQ / Command Range (sec 10.0) — ☐
- Units must be within HQ range for full effectiveness
- Combat modifier when out-of-command

### 2.11 Fortifications (sec 9.0) — ◐ partial
- Field Fortifications (FF) — ✓ build via `EntrenchAction` during movement phase, token persistence (9.13–9.16). Yellow-circle UI marker.
- Missing FF: combat column-shift (9.21 -2/-1), cumulative terrain (9.22), FF unit not forced to attack (9.23), Improved FF (9.24, red token, scenario-placed)
- Permanent Fortifications (PF) — ☐ entirely missing. Map-painted lines, halve attacker SP through PF edge (9.41), fortresses (9.42), defender PF combat option B1-B5 → CPL retain (9.44)

### 2.12 Bridges (sec 13.0) — ☐
- Destruction (small + large rivers)
- Construction (engineer units)

### 2.13 Reinforcements (sec 16.0) — ☐
- Per-turn reinforcement schedule from scenario
- Edge entry, road-only movement on entry turn

### 2.14 Airships (sec 15.0) — ☐ (defer optional)

### 2.15 CRT Audit (sec 7.4 + tables) — ◐
`hexwar/systems/wb48/crt.py` exists. Audit values + edge cases vs reference table in rules.

---

## Step 3 — Pygame Client (`hexwar/client/`)
**Status: ✓ baseline done**

Hex render, terrain coloring, unit tokens, selection, legal-move overlay, combat UI (declaration + resolution + post-battle panel), unit picker for stacked hexes, phase indicator, end-phase button.

Extensions tracked per Step 2 sub-task:
- Strategic movement UI (highlight eligible units, separate move overlay)
- Supply level token rendering
- Disorg marker on units
- Artillery range/target overlay
- FF / PF render
- HQ command range overlay
- Reinforcement entry hex markers

---

## Step 4 — Scenario YAML Format + Loader
**Status: ☐**

- `hexwar/core/scenario.py` — YAML parser, `Scenario` dataclass
- Schema: map dimensions, per-hex terrain + edges, unit roster (id, type, player, position, stats), victory conditions, supply bases, reinforcement schedule
- Validation: types, positions in-bounds, ZOC consistency
- `scenarios/*.yaml` directory

---

## Step 5 — Save / Load
**Status: ☐**

- Serialize GameState + battle history to JSON/YAML
- Resume mid-game
- Distinct from scenario format (state is dynamic, scenario is initial)

---

## Step 6 — First Scenario
**Status: ☐**

Digitize one WB-48 battle from `instruciton images/`:
- Build map YAML (terrain transcribed from physical board)
- Unit placement
- Victory conditions
- Smoke-test playable end-to-end

---

## Step 7 — Main Menu UI
**Status: ☐**

- New game (scenario picker)
- Load game (save file picker)
- Settings (input bindings, graphics)
- Quit

---

## Step 8 — Map + Scenario Editor
**Status: ☐**

- Map editor: place terrain, edges (rivers, roads, bridges), supply bases
- Scenario editor: unit placement, victory conditions, reinforcement schedule
- Export to YAML
- Standalone tool OR mode within main client

---

## Step 9 — AI Player
**Status: ☐**

Rule-based opponent (no ML). Phases:
- Movement: pathfind toward objectives, respect ZOC
- Combat: declare attacks with favorable odds
- Strategic movement: reposition after combat
- Supply: passive

Difficulty levels via heuristic tuning.

---

## Step 10 — Multiplayer (Internet)
**Status: ☐**

Per [CLAUDE.md](CLAUDE.md) tech stack: FastAPI + WebSocket.
- Lobby / matchmaking
- Authoritative server (state validation)
- Wire format spec (action + event serialization)
- Reconnect handling

---

## Step 11 — Polish
**Status: ☐**

Defer until engine complete:
- In-game rules reference (lookup 7.5x, 11.2 etc.)
- Combat preview (odds + CRT row before declaring)
- Better UI / graphics
- Sound
- Localization (PL/EN)

---

## Dependencies

```
Step 1 ✓ ──→ Step 2 (rules) ──→ Step 4 (scenario format)
                              ──→ Step 6 (first scenario)
                              ──→ Step 9 (AI)
                              ──→ Step 10 (MP)

Step 3 baseline ✓, extended per Step 2 sub-tasks

Step 4 ──→ Step 6, Step 8
Step 5 independent (any time after Step 1)
Step 7 independent
Step 11 last
```

---

## Development Rule
After every mechanic: write tests, run `python -m pytest tests/ -v`, all pass before moving on. Helpers in [tests/conftest.py](tests/conftest.py).
