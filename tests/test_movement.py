"""Functional tests for terrain-based movement costs."""

from hexwar.core.actions import EndPhaseAction, MoveAction
from hexwar.core.hex import HexCoord
from hexwar.core.map import EdgeFeature, EdgeType, HexMap, TerrainLayer, TerrainType
from hexwar.systems.test_system import PLAYER_A, PLAYER_B

from tests.conftest import (
    assert_action_illegal,
    assert_action_legal,
    assert_unit_at,
    do_actions,
    make_engine,
    make_map,
    make_unit,
)


class TestTerrainMovementCost:
    def test_plain_costs_1mp(self):
        """Unit with 2 MP can reach 2 plains away."""
        engine = make_engine(units=[make_unit("u1", q=1, r=1, movement=2)])
        move = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_legal(engine, move)

    def test_forest_costs_2mp(self):
        """Unit with 2 MP can reach adjacent forest but not go further."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.FOREST)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=2)])

        to_forest = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, to_forest)

        beyond = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_illegal(engine, beyond)

    def test_hill_costs_2mp(self):
        """Hill costs 2 MP, same as forest."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.HILL)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=2)])

        to_hill = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, to_hill)

        beyond = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_illegal(engine, beyond)

    def test_swamp_first_step_always_allowed(self):
        """Swamp costs 3 MP — unit with 2 MP can still enter as first step."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.SWAMP)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=2)])

        to_swamp = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, to_swamp)

    def test_swamp_first_step_no_further_movement(self):
        """After entering swamp as first step (cost > MP), can't move further."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.SWAMP)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=2)])

        beyond_swamp = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_illegal(engine, beyond_swamp)

    def test_swamp_reachable_with_enough_mp(self):
        """Unit with 3 MP can enter swamp."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.SWAMP)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=3)])

        to_swamp = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, to_swamp)

    def test_first_step_forest_with_1mp(self):
        """Unit with 1 MP can enter forest (cost 2) as first step."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.FOREST)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=1)])

        to_forest = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, to_forest)

    def test_first_step_does_not_apply_to_impassable(self):
        """First-step rule doesn't override impassable terrain."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.MOUNTAIN)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=5)])

        to_mountain = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_illegal(engine, to_mountain)

    def test_mountain_impassable(self):
        """Mountain is impassable — can't enter regardless of MP."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.MOUNTAIN)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=5)])

        to_mountain = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_illegal(engine, to_mountain)

    def test_water_impassable(self):
        """Water is impassable."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.WATER)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=5)])

        to_water = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_illegal(engine, to_water)

    def test_multiple_terrains_uses_worst_cost(self):
        """Hex with forest + hill takes worst cost (both 2, so 2)."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [
            TerrainLayer(TerrainType.FOREST),
            TerrainLayer(TerrainType.HILL),
        ])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=2)])

        to_hex = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, to_hex)

        beyond = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_illegal(engine, beyond)

    def test_multiple_terrains_one_impassable_blocks(self):
        """If any terrain layer is impassable, hex is impassable."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [
            TerrainLayer(TerrainType.PLAIN),
            TerrainLayer(TerrainType.WATER),
        ])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=5)])

        to_hex = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_illegal(engine, to_hex)

    def test_impassable_blocks_path_through(self):
        """Can't path through impassable hex to reach hex behind it."""
        hm = make_map(width=5, height=1)
        hm.set_terrain(HexCoord(2, 0), [TerrainLayer(TerrainType.MOUNTAIN)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=0, movement=5)])

        behind = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 0))
        assert_action_illegal(engine, behind)


class TestRoadMovement:
    def test_road_reduces_cost_to_1(self):
        """Road between hexes reduces cost to 1 regardless of terrain."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.FOREST)])
        hm.set_edge(HexCoord(1, 1), HexCoord(2, 1), [EdgeFeature(EdgeType.ROAD)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=2)])

        to_forest = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1))
        assert_action_legal(engine, to_forest)

        beyond = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_legal(engine, beyond)

    def test_road_only_applies_on_that_edge(self):
        """Road on one edge doesn't affect other edges of same hex."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.FOREST)])
        hm.set_terrain(HexCoord(2, 2), [TerrainLayer(TerrainType.FOREST)])
        hm.set_edge(HexCoord(1, 1), HexCoord(2, 1), [EdgeFeature(EdgeType.ROAD)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=2, movement=2)])

        to_forest_no_road = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 2))
        assert_action_legal(engine, to_forest_no_road)

        beyond_no_road = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 2))
        assert_action_illegal(engine, beyond_no_road)


class TestPathfindingAround:
    def test_path_around_obstacle(self):
        """Unit can path around impassable hex if enough MP."""
        hm = make_map(width=5, height=5)
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.MOUNTAIN)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=3)])

        around = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_legal(engine, around)

    def test_cannot_reach_surrounded_by_impassable(self):
        """Hex completely surrounded by mountains is unreachable."""
        hm = make_map(width=6, height=6)
        center = HexCoord(3, 2)
        for nb in center.neighbors():
            if nb in hm.all_coords():
                hm.set_terrain(nb, [TerrainLayer(TerrainType.MOUNTAIN)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=10)])

        to_center = MoveAction(player=PLAYER_A, unit_id="u1", target=center)
        assert_action_illegal(engine, to_center)


class TestRemainingMovementPoints:
    def test_unit_can_continue_moving_with_remaining_mp(self):
        """Unit with 3 MP moves 1 hex (cost 1), has 2 MP left, can move again."""
        engine = make_engine(units=[make_unit("u1", q=1, r=1, movement=3)])
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1)))
        # 2 MP remaining, can move 1 more plain
        move2 = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_legal(engine, move2)

    def test_unit_stops_when_mp_exhausted(self):
        """Unit with 2 MP moves 2 hexes (cost 1 each), 0 MP left, can't move."""
        engine = make_engine(units=[make_unit("u1", q=1, r=1, movement=2)])
        do_actions(engine,
            MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1)),
            MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1)),
        )
        move3 = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(4, 1))
        assert_action_illegal(engine, move3)

    def test_terrain_cost_reduces_remaining_mp(self):
        """Moving into forest (cost 2) from 3 MP leaves 1 MP."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.FOREST)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=3)])

        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1)))
        # 1 MP left, can move to adjacent plain
        move2 = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_legal(engine, move2)

    def test_terrain_cost_blocks_expensive_second_move(self):
        """After moving into forest (cost 2) from 3 MP, can't enter another forest (need 2, have 1)."""
        hm = make_map()
        hm.set_terrain(HexCoord(2, 1), [TerrainLayer(TerrainType.FOREST)])
        hm.set_terrain(HexCoord(3, 1), [TerrainLayer(TerrainType.FOREST)])
        engine = make_engine(hex_map=hm, units=[make_unit("u1", q=1, r=1, movement=3)])

        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1)))
        # 1 MP left, forest costs 2 — but first-step rule applies since it's a new move action
        # Actually no: first-step only applies when unit hasn't moved yet (spent == 0 in pathfinding)
        # Unit already moved, so remaining MP = 1, can't enter forest (cost 2)
        move2 = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1))
        assert_action_illegal(engine, move2)

    def test_other_unit_unaffected(self):
        """Moving one unit doesn't affect another unit's MP."""
        engine = make_engine(units=[
            make_unit("u1", q=1, r=1, movement=2),
            make_unit("u2", q=1, r=3, movement=2),
        ])
        do_actions(engine, MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1)))
        move_u2 = MoveAction(player=PLAYER_A, unit_id="u2", target=HexCoord(2, 3))
        assert_action_legal(engine, move_u2)

    def test_mp_resets_next_turn(self):
        """MP resets at start of new movement phase."""
        engine = make_engine(units=[
            make_unit("u1", q=1, r=1, movement=2),
            make_unit("u2", q=1, r=3, player=PLAYER_B, movement=2),
        ])
        do_actions(engine,
            MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(2, 1)),
            MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 1)),
            EndPhaseAction(player=PLAYER_A),  # end move_a
            EndPhaseAction(player=PLAYER_A),  # end combat_a
            MoveAction(player=PLAYER_B, unit_id="u2", target=HexCoord(2, 3)),
            EndPhaseAction(player=PLAYER_B),  # end move_b
            EndPhaseAction(player=PLAYER_B),  # end combat_b
        )
        # New turn, u1 has full 2 MP again
        move_again = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(4, 1))
        assert_action_legal(engine, move_again)


class TestEnemyBlocksPathfinding:
    def test_cannot_path_through_enemy(self):
        """Enemy unit blocks pathfinding — can't reach hex behind enemy."""
        hm = make_map(width=5, height=1)
        engine = make_engine(hex_map=hm, units=[
            make_unit("u1", q=1, r=0, movement=5),
            make_unit("e1", q=2, r=0, player=PLAYER_B),
        ])
        behind_enemy = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 0))
        assert_action_illegal(engine, behind_enemy)

    def test_can_path_around_enemy(self):
        """Can reach hex behind enemy by going around if enough MP (avoiding ZOC)."""
        hm = make_map(width=6, height=6)
        engine = make_engine(hex_map=hm, units=[
            make_unit("u1", q=0, r=3, movement=8),
            make_unit("e1", q=2, r=3, player=PLAYER_B),
        ])
        around = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(4, 3))
        assert_action_legal(engine, around)

    def test_friendly_units_dont_block_path(self):
        """Friendly units don't block pathfinding — can path through them."""
        hm = make_map(width=5, height=1)
        engine = make_engine(hex_map=hm, units=[
            make_unit("u1", q=1, r=0, movement=5),
            make_unit("u2", q=2, r=0),
        ])
        through_friendly = MoveAction(player=PLAYER_A, unit_id="u1", target=HexCoord(3, 0))
        assert_action_legal(engine, through_friendly)
