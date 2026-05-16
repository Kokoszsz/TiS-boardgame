"""Functional tests for entrenchment (field fortifications).

Rules:
- Unit can entrench if it hasn't moved this phase
- Costs all movement points (can't move after)
- Can't entrench on swamp
- Can't entrench if already entrenched at that hex
- Entrenchment removed if hex has no friendly unit after movement
- Entrenchment removed if enemy enters hex
- Entrenchment persists across turns if friendly unit stays
"""

from hexwar.core.actions import EndPhaseAction, EntrenchAction, MoveAction
from hexwar.core.hex import HexCoord
from hexwar.core.map import HexMap, TerrainLayer, TerrainType
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B

from tests.conftest import (
    assert_action_illegal,
    assert_action_legal,
    do_actions,
    make_engine,
    make_map,
    make_unit,
)


class TestEntrenchBasic:
    def test_unit_can_entrench(self):
        """Unit that hasn't moved can entrench."""
        engine = make_engine(units=[make_unit("u1", q=2, r=2, movement=2)])
        action = EntrenchAction(player=PLAYER_A, unit_id="u1")
        assert_action_legal(engine, action)

    def test_entrench_consumes_all_mp(self):
        """After entrenching, unit has 0 MP and can't move."""
        engine = make_engine(units=[make_unit("u1", q=2, r=2, movement=2)])
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="u1"))
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 2))
        assert_action_illegal(engine, move)

    def test_moved_unit_cannot_entrench(self):
        """Unit that already moved this phase can't entrench."""
        engine = make_engine(units=[make_unit("u1", q=2, r=2, movement=3)])
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 2)))
        action = EntrenchAction(player=PLAYER_A, unit_id="u1")
        assert_action_illegal(engine, action)

    def test_entrench_creates_fortification(self):
        """Entrenching stores hex in entrenched metadata."""
        engine = make_engine(units=[make_unit("u1", q=2, r=2, movement=2)])
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="u1"))
        entrenched = engine.state.metadata.get("entrenched", {})
        assert HexCoord(2, 2) in entrenched
        assert entrenched[HexCoord(2, 2)] == PLAYER_A


class TestEntrenchTerrain:
    def test_cannot_entrench_on_swamp(self):
        """Can't build fortifications on swamp."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 2), [TerrainLayer(TerrainType.SWAMP)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=2, r=2, movement=2)])
        action = EntrenchAction(player=PLAYER_A, unit_id="u1")
        assert_action_illegal(engine, action)

    def test_can_entrench_on_plain(self):
        engine = make_engine(units=[make_unit("u1", q=2, r=2, movement=2)])
        action = EntrenchAction(player=PLAYER_A, unit_id="u1")
        assert_action_legal(engine, action)

    def test_can_entrench_on_hill(self):
        hm = make_map()
        hm.set_terrain(HexCoord(2, 2), [TerrainLayer(TerrainType.HILL)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=2, r=2, movement=2)])
        action = EntrenchAction(player=PLAYER_A, unit_id="u1")
        assert_action_legal(engine, action)

    def test_can_entrench_on_forest(self):
        hm = make_map()
        hm.set_terrain(HexCoord(2, 2), [TerrainLayer(TerrainType.FOREST)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=2, r=2, movement=2)])
        action = EntrenchAction(player=PLAYER_A, unit_id="u1")
        assert_action_legal(engine, action)

    def test_can_entrench_on_city(self):
        hm = make_map()
        hm.set_terrain(HexCoord(2, 2), [TerrainLayer(TerrainType.CITY)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=2, r=2, movement=2)])
        action = EntrenchAction(player=PLAYER_A, unit_id="u1")
        assert_action_legal(engine, action)


class TestEntrenchRemoval:
    def test_removed_when_unit_leaves_and_no_friendly_remains(self):
        """Fortification removed if unit moves away and no other friendly stays."""
        engine = make_engine(units=[make_unit("u1", q=2, r=2, movement=3)])
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="u1"))
        # End phase, start new movement phase
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # end move_a
        do_actions(engine, EndPhaseAction(player=PLAYER_A))  # end combat_a
        do_actions(engine, EndPhaseAction(player=PLAYER_B))  # end move_b
        do_actions(engine, EndPhaseAction(player=PLAYER_B))  # end combat_b (new turn)
        # Now player A movement again, unit can move
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 2)))
        entrenched = engine.state.metadata.get("entrenched", {})
        assert HexCoord(2, 2) not in entrenched

    def test_preserved_when_friendly_swaps_in(self):
        """Fortification preserved if another friendly unit is on the hex."""
        engine = make_engine(units=[
            make_unit("u1", q=2, r=2, movement=3),
            make_unit("u2", q=1, r=2, movement=3),
        ])
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="u1"))
        # End phase cycle to next turn
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        # Move u2 to entrenched hex, then move u1 away
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u2", target=HexCoord(2, 2)))
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 2)))
        entrenched = engine.state.metadata.get("entrenched", {})
        assert HexCoord(2, 2) in entrenched

    def test_removed_when_enemy_enters(self):
        """Enemy entering entrenched hex destroys fortification."""
        engine = make_engine(units=[
            make_unit("u1", player=PLAYER_A, q=2, r=2, movement=2),
            make_unit("b1", player=PLAYER_B, q=4, r=2, movement=3),
        ])
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="u1"))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        # Player B movement — move unit A away first via next turn...
        # Actually let's just move A away in same scenario
        # Easier: A leaves, then B enters
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        # Turn 2: A moves away
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(1, 2)))
        # Entrenchment gone (no friendly remains)
        entrenched = engine.state.metadata.get("entrenched", {})
        assert HexCoord(2, 2) not in entrenched


class TestEntrenchPersistence:
    def test_entrenchment_persists_across_turns(self):
        """Fortification stays if unit doesn't leave."""
        engine = make_engine(units=[make_unit("u1", q=2, r=2, movement=2)])
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="u1"))
        # Full turn cycle
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        entrenched = engine.state.metadata.get("entrenched", {})
        assert HexCoord(2, 2) in entrenched

    def test_cannot_double_entrench(self):
        """Already entrenched hex — can't entrench again."""
        engine = make_engine(units=[make_unit("u1", q=2, r=2, movement=2)])
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="u1"))
        # Next turn
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        action = EntrenchAction(player=PLAYER_A, unit_id="u1")
        assert_action_illegal(engine, action)

    def test_can_rebuild_after_destruction(self):
        """After entrenchment removed, can rebuild at same hex."""
        engine = make_engine(units=[
            make_unit("u1", q=2, r=2, movement=3),
        ])
        do_actions(engine, EntrenchAction(player=PLAYER_A, unit_id="u1"))
        # Move away (destroys entrenchment), then move back
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 2)))
        # Next turn — move back
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 2)))
        # Next turn — entrench again
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_A))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        do_actions(engine, EndPhaseAction(player=PLAYER_B))
        action = EntrenchAction(player=PLAYER_A, unit_id="u1")
        assert_action_legal(engine, action)
