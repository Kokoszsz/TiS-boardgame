---
name: python-code
description: >
  Use when writing or editing any Python file in this project. Always-on guidelines
  for readability, type safety, structure, and cleanup. Triggers on any Python
  implementation task — new features, bug fixes, refactors.
---

# Python Code Quality Guidelines

Readability-first guidelines for all Python code. Follow as defaults — use judgment for exceptions, but default to the guideline.

Applies to **new and modified code only**. Don't auto-refactor untouched code nearby.

## Design-First Workflow

Before writing code, show design. Scale detail to change size.

**Trivial** (typo, one-liner, import fix): just do it.

**Small** (1-2 files, single concern): 3-5 bullet points — what changes, where, why. Wait for approval.

**Medium** (3-5 files, new feature): function signatures, class outlines, which files change, data flow. Wait for approval.

**Large** (new subsystem, architectural): full pseudocode-level design. File layout, class relationships, integration points. Present in sections, validate each.

## Readability

**Methods — one job each:**
- If you need a comment to explain a section inside a method, extract it into a named function instead.
- When a method has sequential steps, each step should be a call to a well-named helper.
- Prefer short methods. If a method is hard to understand in one screen, it's too long.

**Naming:**
- Function names describe what they return or what effect they have. `find_available_attackers` not `get_data`.
- Booleans read as questions: `is_exhausted`, `can_entrench`, `has_enemy_in_zoc`.
- Variables named for what they hold: `adjacent_enemies` not `filtered_list`.

**Control flow:**
- Guard clauses at top, happy path at bottom. Avoid deep else branches.
- Prefer early returns to flatten nesting. Avoid 4+ levels of indentation.
- Avoid silent failures — when validation rejects, log or emit event. Don't return empty result with no signal.

**Dead code:**
- Never leave unused functions, commented-out code, unused imports, or legacy artifacts.
- If removing a feature, remove all traces.

## Type Safety

**Enums over magic strings:**
- Phase types, combat results, sub-phases — use `Enum` or `StrEnum`.
- If a string value is compared more than once, make it a constant or enum member.

**Typed structures over dicts:**
- When a dict has a known schema (battle data, metadata sections), use `dataclass` or `TypedDict`.
- `battle.attacker_ids` over `battle["attacker_ids"]`.
- `dict[str, Any]` acceptable only at true system boundaries — config loading, external data.

**Type aliases for domain concepts:**
- Use and extend existing aliases: `UnitId`, `Player`, `CostFn`.
- Prefer `UnitId` over raw `str` in signatures.

**Annotations:**
- All public functions: fully annotated (params + return).
- Private helpers: annotate when types aren't obvious from context.
- Modern syntax: `X | None` not `Optional[X]`, `list[str]` not `List[str]`.

## Structure

**Classes — single responsibility:**
- If a class handles rendering, input, AND state — split it.
- When a class grows beyond easy comprehension, extract cohesive method groups into separate classes/modules.

**Files — one concept each:**
- If a file covers movement, combat, AND declaration — split by domain concept.
- `combat_declaration.py` not `helpers.py`.

**Separation of concerns:**
- No layer reaches into another's internals. Client never calls `system._private_method()`.
- If client needs data, engine/system exposes it through public API.
- Dependency direction: `core` ← `systems` ← `client`. No reverse imports.

**Duplication:**
- When two blocks share 80%+ structure, extract shared logic with parameters for differences.
- Don't pre-extract. Two is coincidence, three is pattern.

**Imports:**
- Organized: stdlib, third-party, local. Each group alphabetized.
- Remove unused imports immediately.

## HexWar-Specific Patterns

**Engine/System/Client separation:**
- Engine: framework (phase management, action dispatch, state transitions). Never game-specific.
- System: rules (terrain costs, combat resolution, ZOC). Never UI or rendering.
- Client: display and input. Reads state through engine's public API only.

**State immutability:**
- All changes through `with_*` methods or `dataclasses.replace()`.
- Prefer `dataclasses.replace()` over manual constructor calls.
- Never mutate state in place.

**Metadata access:**
- Systems own their metadata schema. Only combat code should know combat metadata keys.
- Client accesses game state through engine queries, not raw metadata dict reads.

**Action/Event pattern:**
- Actions = player intent. Events = what happened.
- `apply_action` returns `(new_state, events)`. Never modify state as side effect.
