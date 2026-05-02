"""Smoke test — runs a few turns with TestSystem to verify engine works end-to-end."""

from hexwar.core.hex import HexCoord
from hexwar.core.map import HexMap, TerrainLayer, TerrainType
from hexwar.core.unit import Unit
from hexwar.core.state import build_initial_state
from hexwar.core.rng import GameRNG
from hexwar.core.engine import Engine
from hexwar.core.actions import MoveAction, AttackAction, EndPhaseAction
from hexwar.systems.test_system import TestSystem, PLAYER_A, PLAYER_B


def build_test_map() -> HexMap:
    hm = HexMap()
    for q in range(6):
        for r in range(6):
            hm.set_terrain(HexCoord(q, r), [TerrainLayer(TerrainType.PLAIN)])
    hm.set_terrain(HexCoord(3, 3), [TerrainLayer(TerrainType.FOREST)])
    return hm


def main():
    hex_map = build_test_map()
    system = TestSystem()
    rng = GameRNG(seed=42)

    units = [
        Unit(id="inf_a1", name="1st Infantry A", type_id="infantry",
             player=PLAYER_A, position=HexCoord(1, 1), stats={"strength": 3, "movement": 2}),
        Unit(id="tank_a1", name="Tank Platoon A", type_id="tank",
             player=PLAYER_A, position=HexCoord(0, 2), stats={"strength": 5, "movement": 3}),
        Unit(id="inf_b1", name="1st Infantry B", type_id="infantry",
             player=PLAYER_B, position=HexCoord(4, 1), stats={"strength": 3, "movement": 2}),
        Unit(id="inf_b2", name="2nd Infantry B", type_id="infantry",
             player=PLAYER_B, position=HexCoord(4, 3), stats={"strength": 4, "movement": 2}),
    ]

    state = build_initial_state(
        scenario_id="test_001",
        scenario_name="Engine Test",
        system_id="test",
        hex_map=hex_map,
        units=units,
        active_player=PLAYER_A,
    )

    engine = Engine(state, system, rng)

    print("=== Engine Smoke Test ===\n")
    print(f"Scenario: {engine.state.scenario_name}")
    print(f"Turn: {engine.state.turn}")
    print(f"Phase: {engine.current_phase.name}")
    print(f"Units: {len(engine.state.units)}")
    print()

    # Player A moves infantry toward enemy
    print("--- Player A Movement Phase ---")
    legal = engine.get_legal_actions()
    print(f"Legal actions: {len(legal)}")

    move = MoveAction(player=PLAYER_A, unit_id="inf_a1", target=HexCoord(2, 1))
    events = engine.submit_action(move)
    for e in events:
        print(f"  Event: {e}")

    move2 = MoveAction(player=PLAYER_A, unit_id="tank_a1", target=HexCoord(2, 2))
    events = engine.submit_action(move2)
    for e in events:
        print(f"  Event: {e}")

    # End movement phase
    events = engine.submit_action(EndPhaseAction(player=PLAYER_A))
    for e in events:
        print(f"  Event: {e}")
    print(f"Phase now: {engine.current_phase.name}")
    print()

    # Player A combat — no adjacent enemies yet, end phase
    print("--- Player A Combat Phase ---")
    legal = engine.get_legal_actions()
    print(f"Legal attack actions: {len(legal)}")
    events = engine.submit_action(EndPhaseAction(player=PLAYER_A))
    for e in events:
        print(f"  Event: {e}")
    print(f"Phase now: {engine.current_phase.name}")
    print()

    # Player B moves infantry toward Player A
    print("--- Player B Movement Phase ---")
    move3 = MoveAction(player=PLAYER_B, unit_id="inf_b1", target=HexCoord(3, 1))
    events = engine.submit_action(move3)
    for e in events:
        print(f"  Event: {e}")

    events = engine.submit_action(EndPhaseAction(player=PLAYER_B))
    for e in events:
        print(f"  Event: {e}")
    print(f"Phase now: {engine.current_phase.name}")
    print()

    # Player B combat — check adjacency
    print("--- Player B Combat Phase ---")
    legal = engine.get_legal_actions()
    print(f"Legal attack actions: {len(legal)}")
    events = engine.submit_action(EndPhaseAction(player=PLAYER_B))
    for e in events:
        print(f"  Event: {e}")
    print(f"Turn now: {engine.state.turn}, Phase: {engine.current_phase.name}")
    print()

    # Turn 2 — move units adjacent and fight
    print("--- Turn 2: Player A moves adjacent to enemy ---")
    move4 = MoveAction(player=PLAYER_A, unit_id="tank_a1", target=HexCoord(3, 2))
    events = engine.submit_action(move4)
    for e in events:
        print(f"  Event: {e}")

    events = engine.submit_action(EndPhaseAction(player=PLAYER_A))
    for e in events:
        print(f"  Event: {e}")
    print()

    # Tank (str 5) attacks inf_b1 (str 3) — tank wins
    print("--- Turn 2: Player A attacks ---")
    attack = AttackAction(player=PLAYER_A, attacker_id="tank_a1", defender_id="inf_b1")
    events = engine.submit_action(attack)
    for e in events:
        print(f"  Event: {e}")
    print(f"Remaining units: {list(engine.state.units.keys())}")
    print()

    # Test undo
    print("--- Undo last action ---")
    engine.undo()
    print(f"Units after undo: {list(engine.state.units.keys())}")
    print()

    # History
    print(f"History entries: {len(engine.get_history())}")
    print("\n=== Smoke test complete ===")


if __name__ == "__main__":
    main()
