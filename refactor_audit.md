# Refactor Audit — Code Smells & Mitigation Plan

Scope: `hexwar/core/` + `hexwar/systems/wb48/`.
Themes: Primitive Obsession, Poor Naming, Implicit Data Structures, Hidden Domain Logic.

---

## Audit Findings

### 1. Stringly-typed "side" (worst offender)

`pursuing_side: str`, `side: str`, raw `"attacker"`/`"defender"` literals everywhere.

Hotspots:
- [hexwar/core/battle.py:44](hexwar/core/battle.py#L44)
- [hexwar/systems/wb48/combat_resolution.py:86-90](hexwar/systems/wb48/combat_resolution.py#L86-L90)
- [hexwar/systems/wb48/combat_resolution.py:240-247](hexwar/systems/wb48/combat_resolution.py#L240-L247)
- [hexwar/systems/wb48/combat_resolution.py:314-321](hexwar/systems/wb48/combat_resolution.py#L314-L321)
- [hexwar/systems/wb48/combat_resolution.py:374-377](hexwar/systems/wb48/combat_resolution.py#L374-L377)
- [hexwar/systems/wb48/combat_resolution.py:384](hexwar/systems/wb48/combat_resolution.py#L384)
- [hexwar/systems/wb48/combat_resolution.py:440-461](hexwar/systems/wb48/combat_resolution.py#L440-L461)
- [hexwar/systems/wb48/combat_resolution.py:510-521](hexwar/systems/wb48/combat_resolution.py#L510-L521)
- [hexwar/systems/wb48/combat_resolution.py:528-549](hexwar/systems/wb48/combat_resolution.py#L528-L549)
- [hexwar/systems/wb48/combat_resolution.py:561](hexwar/systems/wb48/combat_resolution.py#L561)
- [hexwar/systems/wb48/combat_resolution.py:597-599](hexwar/systems/wb48/combat_resolution.py#L597-L599)
- [hexwar/systems/wb48/combat_resolution.py:661](hexwar/systems/wb48/combat_resolution.py#L661)
- [hexwar/core/actions.py:51](hexwar/core/actions.py#L51) — `ChooseRetreatSplitAction.side: str`

Worst pattern: `getattr(battle, f"{side}_debt", 0)` at [combat_resolution.py:260](hexwar/systems/wb48/combat_resolution.py#L260) — string-reflection on field names.

Symptom: 30+ ternaries `X if side == "attacker" else Y`. Bug magnet. Typo "attaker" → silently wrong branch.

### 2. `state.metadata: dict[str, Any]` abused as typeless namespace

Keys scattered across files. No type checks. Misspell → silent default.

Combat declaration ([combat_declaration.py:20-27](hexwar/systems/wb48/combat_declaration.py#L20-L27)):
- `"battles"`, `"next_battle_id"`, `"combat_sub_phase"`
- `"committed_attackers"`, `"committed_defenders"`
- `"obligated_attackers"`, `"obligated_enemies"`
- `"declaration_complete"`

Movement ([movement.py:157-165](hexwar/systems/wb48/movement.py#L157-L165)):
- `"entrenched"`

Refactor cost: high. Every key access untyped.

### 3. Battle = god dataclass (19 fields)

[hexwar/core/battle.py:25-45](hexwar/core/battle.py#L25-L45). Mixes:
- Declaration data (`id`, `attacker_ids`, `defender_ids`, `defender_hexes`, `combatant_origin`)
- Resolved data (`resolved`, `result`, `dice_roll`)
- Post-battle FSM (`post_phase`, `attacker_debt`, `defender_debt`, `attacker_mandatory_cpl`, `defender_mandatory_cpl`, `remaining_cpl_to_assign`, `remaining_retreat_steps`)
- Retreat tracking (`units_needing_retreat`, `retreat_paths`, `eliminated_at`)
- Pursuit tracking (`pursuing_side`, `units_pursued`)

Symmetric per-side fields (8 pairs) all named with `attacker_`/`defender_` prefix → triggers the side-string ternary explosion.

### 4. `dict[K, list[V]]` / `dict[K, V]` ad-hoc structures

Implicit relations, no name, no methods:
- `retreat_paths: dict[str, tuple[HexCoord, ...]]` — unit → retreat path
- `eliminated_at: dict[str, HexCoord]` — unit → death hex
- `combatant_origin: dict[str, HexCoord]` — unit → start hex
- `hex_to_originals: dict[HexCoord, list[str]]` — your example, line 385
- `enemy_zoc_map -> dict[HexCoord, set[str]]` — hex → units exerting ZOC
- `attacker_to_enemy_hexes: dict[str, set[HexCoord]]` — attacker → reachable enemy hexes
- `entrenched_hexes: dict[HexCoord, Player]` — hex → owner

Each begs for named type with intention-revealing methods.

### 5. CombatResult — 3 bools where 1 enum suffices

[hexwar/core/combat_results.py:17-19](hexwar/core/combat_results.py#L17-L19):
```python
victorious_attacker: bool = False
victorious_defender: bool = False
victorious_tie: bool = False
```

Invariant "exactly one true" not enforced by type. Caller checks 3 fields instead of 1 match.

Also: `attacker_deorganized_roll: int = 0` actually used as bool (0 or 1). And `deorganized` misspelled — should be `disorganized`.

### 6. `UnitId = str` plain alias

[hexwar/core/unit.py:9](hexwar/core/unit.py#L9). No mypy benefit. `UnitId` and `Player` and `str` all interchangeable. NewType gives free safety with zero runtime cost.

### 7. Sub-phase constants as strings

[hexwar/systems/wb48/combat_declaration.py:12-13](hexwar/systems/wb48/combat_declaration.py#L12-L13):
```python
SUB_PHASE_DECLARATION = "declaration"
SUB_PHASE_RESOLUTION = "resolution"
```

Enum candidate.

### 8. Repeated battle load/update boilerplate

8+ copies of this pattern in [combat_resolution.py](hexwar/systems/wb48/combat_resolution.py):
```python
battles = list(state.metadata.get("battles", []))
battle_idx = next(i for i, b in enumerate(battles) if b.id == action.battle_id)
battle = battles[battle_idx]
# ... mutate ...
battles[battle_idx] = updated
state = state.with_metadata("battles", battles)
```

Begs for `state.with_battle_updated(battle_id, fn)` helper.

### 9. Hidden domain logic

- [combat_results.py:23-63](hexwar/core/combat_results.py#L23-L63) — `CombatResult.from_string` regex-parses CRT codes (`"A2-1/-1"`, `"*-/B3D"`). Format buried in `_match_casualties`, `_match_retreat`.
- [combat_resolution.py:41-119](hexwar/systems/wb48/combat_resolution.py#L41-L119) — `_apply_resolve_battle` does 5 things: load battle, sum strengths, roll dice, apply disorg, update post phase. One function = many reasons to change.
- [combat_resolution.py:523-571](hexwar/systems/wb48/combat_resolution.py#L523-L571) — `_skip_empty_phase` is implicit FSM with goto-style `continue`s.

---

## Recommendations

### Tier 1 — High impact, low risk, mechanical

**T1. `Side` enum + symmetric accessors on Battle**
```python
class Side(Enum):
    ATTACKER = "attacker"
    DEFENDER = "defender"
    def opposite(self) -> Side: ...

# Battle gains:
def units(self, side: Side) -> tuple[UnitId, ...]
def debt(self, side: Side) -> int
def mandatory_cpl(self, side: Side) -> int
def with_debt(self, side: Side, n: int) -> Battle
```
Kills `getattr(...f"{side}_...")`. Kills 30+ ternaries.
Touches: `battle.py`, `combat_resolution.py`, `actions.py`, `events.py`.

**T2. `CombatSubPhase` enum** replaces `SUB_PHASE_*` string consts.

**T3. `BattleOutcome` enum on `CombatResult`** replaces 3 bools.
```python
class BattleOutcome(Enum):
    ATTACKER_WIN = "attacker_win"
    DEFENDER_WIN = "defender_win"
    TIE = "tie"
```
Also rename `deorganized` → `disorganized` while touching the file.

**T4. NewTypes for IDs**
```python
UnitId = NewType("UnitId", str)
BattleId = NewType("BattleId", int)
PlayerId = NewType("PlayerId", str)
```
One-line definitions. Cascades into signatures. Mypy catches "passed hex name as unit id" bugs.

**T5. `state.with_battle_updated(battle_id, fn)` helper**
Collapses 8 boilerplate blocks into one-liners. Example:
```python
state = state.with_battle_updated(action.battle_id, lambda b: b.replace(...))
```

### Tier 2 — Moderate, structural

**T6. Typed slices of `state.metadata`**
```python
@dataclass(frozen=True)
class CombatPhaseState:
    sub_phase: CombatSubPhase
    battles: tuple[Battle, ...]
    next_battle_id: BattleId
    committed: dict[Side, frozenset[UnitId]]
    obligated: dict[Side, frozenset[UnitId]]
    declaration_complete: bool
```
Stored in metadata under single key. Accessed via `state.combat_phase()` helper.
Same for entrenchment: `EntrenchmentRegistry`.

**T7. Named relation types** for the `dict[K, list[V]]` family:
- `LosersByOrigin` — your snippet's `hex_to_originals`
  - `.origin_hexes() -> set[HexCoord]`
  - `.all_eliminated_on(hex, eliminated_set) -> bool`
- `RetreatPaths` — wraps `dict[UnitId, tuple[HexCoord, ...]]`
  - `.path_of(uid) -> tuple[HexCoord, ...]`
  - `.intermediate_hexes() -> set[HexCoord]` (all hexes minus final)
- `EliminationLog` — wraps `dict[UnitId, HexCoord]`
  - `.at(uid) -> HexCoord | None`
  - `.contains(uid) -> bool`
- `ZoneOfControl` — wraps `dict[HexCoord, set[UnitId]]`
  - `.covers(hex) -> bool`
  - `.sources(hex) -> frozenset[UnitId]`

**T8. Battle decomposition** — split into:
- `Battle` (declaration data: id, attackers, defenders, origin)
- `BattleResolution` (result, dice, retreat_paths, eliminated_at, post_phase, debts...)
- `Battle.resolution: BattleResolution | None`

`resolved` becomes `resolution is not None`. Most of the 19 fields move out.

### Tier 3 — Long horizon

**T9. Post-battle FSM** extracted from `_skip_empty_phase` + `_next_phase_after_side`. Explicit transition table:
```python
PostBattleTransitions = {
    (PostBattlePhase.ATTACKER_SPLIT, condition): PostBattlePhase.ATTACKER_CPL,
    ...
}
```
Or state pattern with one class per phase.

**T10. CRT result parser** — replace regex roundtrip in `CombatResult.from_string`/`__str__` with typed `SideResult(retreat, casualties, disorg, disorg_roll)`. Parse once at table load, never string-round-trip again.

---

## Recommended Order

Start: **T4 → T1 → T2 → T3 → T5**.

Pure mechanical refactors. Each independent. Each touches small surface. Tests catch regressions immediately.

After Tier 1: re-audit. Tier 2 likely smaller than current estimate (Tier 1 removes a lot of the ad-hoc patterns indirectly).

Tier 2 + 3 wait until WB-48 mechanics complete. Architectural moves cheaper when more rules in place — current shape will reveal real seams.

---

## Cross-cutting Principles Going Forward

1. **No raw `str` for closed domains.** Enum or NewType.
2. **No `dict[K, V]` reused in 2+ places.** Make it a class with methods.
3. **No `state.metadata[key]` outside one helper per concern.** Typed slice.
4. **No `getattr(obj, f"{var}_field")`.** Use enum + accessor method.
5. **No per-side mirrored fields (`attacker_X` + `defender_X`).** Single `dict[Side, X]` or `by_side(side) -> X` method.
6. **No multi-bool "exactly one true" invariants.** Single enum field.
7. **Functions that "do 5 things" get split** — name reveals intent better than comments.
