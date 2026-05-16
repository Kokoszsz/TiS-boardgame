from __future__ import annotations

from hexwar.core.actions import Action
from hexwar.core.engine import Engine
from hexwar.core.events import Event
from hexwar.core.hex import HexCoord
from hexwar.core.map import HexMap, TerrainLayer, TerrainType
from hexwar.core.rng import GameRNG
from hexwar.core.state import build_initial_state
from hexwar.core.unit import Unit, UnitId
from hexwar.systems.base import System
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B, WB48System


def make_map(width: int = 6, height: int = 6, default_terrain: TerrainType = TerrainType.PLAIN) -> HexMap:
    hm = HexMap()
    for q in range(width):
        for r in range(height):
            hm.set_terrain(HexCoord(q, r), [TerrainLayer(default_terrain)])
    return hm


def make_unit(
    id: str,
    player: str = PLAYER_A,
    type_id: str = "infantry",
    q: int = 0,
    r: int = 0,
    strength: int = 3,
    movement: float = 2,
    **extra_stats,
) -> Unit:
    stats = {"strength": strength, **extra_stats}
    return Unit(
        id=id,
        name=id,
        type_id=type_id,
        player=player,
        position=HexCoord(q, r),
        stats=stats,
        movement_max=movement,
        movement_left=movement,
    )


def make_engine(
    hex_map: HexMap | None = None,
    units: list[Unit] | None = None,
    system: System | None = None,
    seed: int = 42,
    active_player: str = PLAYER_A,
) -> Engine:
    if hex_map is None:
        hex_map = make_map()
    if units is None:
        units = []
    if system is None:
        system = WB48System()

    state = build_initial_state(
        scenario_id="test",
        scenario_name="Test",
        system_id="test",
        hex_map=hex_map,
        units=units,
        active_player=active_player,
    )
    return Engine(state, system, GameRNG(seed=seed))


def do_actions(engine: Engine, *actions: Action) -> list[Event]:
    all_events: list[Event] = []
    for action in actions:
        events = engine.submit_action(action)
        all_events.extend(events)
    return all_events


def assert_unit_at(engine: Engine, unit_id: UnitId, q: int, r: int) -> None:
    unit = engine.state.get_unit(unit_id)
    assert unit is not None, f"Unit {unit_id} not found"
    expected = HexCoord(q, r)
    assert unit.position == expected, f"Unit {unit_id} at {unit.position}, expected {expected}"


def assert_unit_destroyed(engine: Engine, unit_id: UnitId) -> None:
    unit = engine.state.get_unit(unit_id)
    assert unit is None, f"Unit {unit_id} still exists at {unit.position}"


def assert_unit_exists(engine: Engine, unit_id: UnitId) -> None:
    unit = engine.state.get_unit(unit_id)
    assert unit is not None, f"Unit {unit_id} not found"


def assert_action_legal(engine: Engine, action: Action) -> None:
    legal = engine.get_legal_actions()
    match = any(a == action for a in legal)
    assert match, f"Action {action} not in legal actions"


def assert_action_illegal(engine: Engine, action: Action) -> None:
    legal = engine.get_legal_actions()
    match = any(a == action for a in legal)
    assert not match, f"Action {action} should be illegal but is in legal actions"
