---
name: python-tests
description: >
  Use when writing or editing test files in this project. Guidelines for
  test coverage, structure, and style. Triggers on any test implementation task.
---

# Python Test Guidelines

Guidelines for writing tests. Focus: complete coverage through systematic
case enumeration, testing behavior through full engine pipeline.

Applies alongside `python-code` skill — same readability and type safety
standards apply to test code.

## Enumerate Before Writing

Before writing tests for any mechanic, enumerate all test cases first.
Present list to user. Write tests only after case list is approved.

Think systematically:
- Happy path — basic correct usage
- Edge cases — boundaries, zero values, max limits, empty collections
- Error/illegal paths — wrong player, invalid targets, insufficient points
- Mechanic interactions — how this feature combines with others (ZOC + movement, combat + entrenchment)
- State transitions — verify before/after state changes are correct

Test behavior, not implementation. Assert observable state changes through
public API. Don't test that a private method was called — test that the
game state changed correctly.

## Test Style

**Full pipeline always.** Every test goes through engine pipeline:
build scenario → submit actions → assert state. No testing isolated
functions or internal methods directly.

**Descriptive names.** Test name describes scenario and expected outcome.
`test_unit_cannot_move_through_enemy_zoc` not `test_move_blocked`.
Name should read as a specification.

**Helpers.** Use shared `conftest.py` helpers (`make_engine`, `make_unit`,
`assert_action_legal`, etc.) when they fit. Local helpers OK when test
file has special setup needs — don't force conftest to cover everything.
Extend conftest when helper would benefit multiple test files.

**Structure.** Use class grouping or flat functions — whichever makes
the specific test file clearer. Group related scenarios when it helps
readability.

**One assertion focus per test.** Each test verifies one scenario.
Multiple asserts OK when checking different aspects of same outcome
(position changed AND movement points decreased). Not OK when testing
two unrelated behaviors.

## HexWar Test Patterns

**Scenario setup pattern:**
```python
hex_map = make_map(5, 5, "plain")
units = [
    make_unit("inf1", "player1", "infantry", q=2, r=2, strength=10, movement=4),
    make_unit("inf2", "player2", "infantry", q=3, r=2, strength=10, movement=4),
]
engine = make_engine(hex_map, units)
```

**Action-assert pattern:**
```python
engine = do_actions(engine, Action("move", unit_id="inf1", target=(3, 1)))
assert_unit_at(engine, "inf1", (3, 1))
assert_action_illegal(engine, Action("move", unit_id="inf1", target=(4, 0)))
```

**Phase transitions.** When testing mechanic that spans phases
(declaration → resolution), advance through phases explicitly.
Don't skip phases or manipulate state directly.

**Deterministic RNG.** Use seeded engine for combat tests.
When result depends on RNG, find seed that produces desired outcome
and document it: `make_engine(..., seed=42)  # produces attacker victory`.
