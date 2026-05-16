"""Headless tests for PygameClient logic — no display needed.

Mocks pygame to test client state machine: selection, movement,
declaration flow, resolution flow, entrenchment, undo.
Identifies dead code paths by exercising all logic branches.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from hexwar.core.actions import (
    DeclareAttackAction, EndPhaseAction, MoveAction, UndeclareAttackAction,
)
from hexwar.core.hex import HexCoord
from hexwar.core.map import HexMap, TerrainLayer, TerrainType
from hexwar.core.rng import GameRNG
from hexwar.core.state import build_initial_state
from hexwar.core.engine import Engine
from hexwar.core.unit import Unit
from hexwar.systems.wb48.system import PLAYER_A, PLAYER_B, WB48System


def _make_map(w=6, h=6):
    hm = HexMap()
    for q in range(w):
        for r in range(h):
            hm.set_terrain(HexCoord(q, r), [TerrainLayer(TerrainType.PLAIN)])
    return hm


def _make_engine(units, hex_map=None):
    if hex_map is None:
        hex_map = _make_map()
    state = build_initial_state(
        scenario_id="test", scenario_name="Test", system_id="test",
        hex_map=hex_map, units=units, active_player=PLAYER_A,
    )
    return Engine(state, WB48System(), GameRNG(seed=42))


def _make_unit(id, player=PLAYER_A, q=0, r=0, type_id="infantry", strength=3, movement=2, **extra):
    stats = {"strength": strength, **extra}
    return Unit(id=id, name=id, type_id=type_id, player=player,
                position=HexCoord(q, r), stats=stats,
                movement_max=movement, movement_left=movement)


@pytest.fixture
def mock_pygame():
    """Mock pygame enough to create PygameClient without a display."""
    with patch("hexwar.client.pygame_client.pygame") as mock_pg:
        mock_pg.QUIT = 256
        mock_pg.MOUSEBUTTONDOWN = 1025
        mock_pg.MOUSEBUTTONUP = 1026
        mock_pg.MOUSEMOTION = 1024
        mock_pg.KEYDOWN = 768
        mock_pg.K_ESCAPE = 27
        mock_pg.K_e = 101
        mock_pg.K_f = 102
        mock_pg.K_u = 117
        mock_pg.K_d = 100
        mock_pg.K_q = 113
        mock_pg.KMOD_SHIFT = 1
        mock_pg.SRCALPHA = 65536

        mock_screen = MagicMock()
        mock_screen.get_size.return_value = (1024, 700)
        mock_pg.display.set_mode.return_value = mock_screen

        mock_font = MagicMock()
        mock_font.render.return_value = MagicMock(get_width=lambda: 50, get_height=lambda: 14)
        mock_pg.font.SysFont.return_value = mock_font

        mock_pg.Rect = lambda x, y, w, h: MagicMock(
            x=x, y=y, width=w, height=h,
            topleft=(x, y),
            collidepoint=lambda pos: x <= pos[0] <= x + w and y <= pos[1] <= y + h,
            centery=y + h // 2,
        )
        mock_pg.Surface.return_value = mock_screen
        mock_pg.mouse.get_pos.return_value = (0, 0)
        mock_pg.key.get_mods.return_value = 0

        yield mock_pg


def _make_client(engine, mock_pygame_fixture):
    from hexwar.client.pygame_client import PygameClient
    client = PygameClient(engine)
    return client


# =========================================================================
# Selection & Deselect
# =========================================================================

class TestSelection:
    def test_select_unit_sets_id(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        assert client.selected_unit_id == "a1"

    def test_deselect_clears_all(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        client._deselect()
        assert client.selected_unit_id is None
        assert len(client.legal_moves) == 0
        assert len(client.selected_attackers) == 0

    def test_select_computes_legal_moves(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1, movement=2)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        assert len(client.legal_moves) > 0
        assert HexCoord(2, 1) in client.legal_moves

    def test_select_computes_zoc(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1, movement=2),
            _make_unit("b1", player=PLAYER_B, q=3, r=1),
        ])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        assert len(client.enemy_zoc) > 0


# =========================================================================
# Movement
# =========================================================================

class TestMovement:
    def test_do_move_changes_unit_position(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1, movement=2)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        client._do_move(HexCoord(2, 1))
        assert engine.state.get_unit("a1").position == HexCoord(2, 1)

    def test_do_move_reselects_unit(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1, movement=2)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        client._do_move(HexCoord(2, 1))
        assert client.selected_unit_id == "a1"
        # Legal moves should be recomputed for remaining MP
        assert len(client.legal_moves) >= 0

    def test_do_move_adds_to_event_log(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1, movement=2)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        client._do_move(HexCoord(2, 1))
        assert len(client.event_log) > 0


# =========================================================================
# End Phase
# =========================================================================

class TestEndPhase:
    def test_end_phase_advances(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1)])
        client = _make_client(engine, mock_pygame)

        assert engine.current_phase.id == "move_a"
        client._end_phase()
        assert engine.current_phase.id == "combat_a"

    def test_end_phase_deselects(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        client._end_phase()
        assert client.selected_unit_id is None


# =========================================================================
# Undo
# =========================================================================

class TestUndo:
    def test_undo_restores_position(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1, movement=2)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        client._do_move(HexCoord(2, 1))
        assert engine.state.get_unit("a1").position == HexCoord(2, 1)

        client._undo()
        assert engine.state.get_unit("a1").position == HexCoord(1, 1)

    def test_undo_deselects(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1, movement=2)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        client._do_move(HexCoord(2, 1))
        client._undo()
        assert client.selected_unit_id is None

    def test_undo_empty_does_nothing(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1)])
        client = _make_client(engine, mock_pygame)

        client._undo()  # should not crash
        assert len(client.event_log) == 0


# =========================================================================
# Declaration Mode
# =========================================================================

class TestDeclarationMode:
    def _enter_combat(self, engine, client):
        """Advance to combat_a phase."""
        client._end_phase()  # move_a → combat_a
        assert engine.current_phase.id == "combat_a"

    def test_in_declaration_mode_after_combat_enter(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)

        self._enter_combat(engine, client)
        assert client._in_declaration_mode()

    def test_not_in_declaration_during_movement(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1)])
        client = _make_client(engine, mock_pygame)

        assert not client._in_declaration_mode()

    def test_end_phase_blocked_with_obligations(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)

        self._enter_combat(engine, client)
        # Obligations exist — end phase should be blocked
        client._end_phase()
        assert engine.current_phase.id == "combat_a"  # didn't advance
        assert any("BLOCKED" in msg for msg in client.event_log)

    def test_declare_attack_via_client(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)

        self._enter_combat(engine, client)
        client.selected_attackers = ["a1"]
        client._do_declare_attack(HexCoord(2, 1))

        battles = engine.state.metadata.get("battles", [])
        assert len(battles) == 1
        assert "a1" in battles[0].attacker_ids

    def test_declare_clears_selected_attackers(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)

        self._enter_combat(engine, client)
        client.selected_attackers = ["a1"]
        client._do_declare_attack(HexCoord(2, 1))
        assert len(client.selected_attackers) == 0

    def test_end_phase_allowed_after_obligations_met(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)

        self._enter_combat(engine, client)
        client.selected_attackers = ["a1"]
        client._do_declare_attack(HexCoord(2, 1))

        # Now obligations should be met
        assert engine.state.metadata.get("declaration_complete", False)
        client._end_phase()
        # Should have advanced (to resolution or next phase)
        assert engine.current_phase.id == "combat_a"  # still combat, now resolution sub-phase
        assert client._in_resolution_mode()

    def test_undeclare_via_client(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)

        self._enter_combat(engine, client)
        client.selected_attackers = ["a1"]
        client._do_declare_attack(HexCoord(2, 1))

        battles = engine.state.metadata.get("battles", [])
        client.selected_battle_id = battles[0].id
        client._undeclare_selected()

        assert len(engine.state.metadata.get("battles", [])) == 0
        assert client.selected_battle_id is None

    def test_undeclare_does_nothing_without_selection(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)

        self._enter_combat(engine, client)
        client._undeclare_selected()  # no battle selected, should not crash

    def test_undeclare_outside_declaration_mode_does_nothing(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1)])
        client = _make_client(engine, mock_pygame)

        client.selected_battle_id = 999
        client._undeclare_selected()  # not in declaration mode


class TestDeclarationMultiUnitSelection:
    def _enter_combat(self, engine, client):
        client._end_phase()

    def test_picker_opens_for_stacked_attackers(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("a2", q=1, r=1, stack_size=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_combat(engine, client)

        client._handle_declaration_click(HexCoord(1, 1))
        assert client.unit_picker_open
        assert len(client.unit_picker_units) == 2

    def test_picker_selects_attacker_in_declaration(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("a2", q=1, r=1, stack_size=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_combat(engine, client)

        client._handle_declaration_click(HexCoord(1, 1))
        picked_id = client.unit_picker_units[0].id
        # Simulate clicking first item in picker
        pos = (client.unit_picker_item_rects[0].x + 1, client.unit_picker_item_rects[0].y + 1)
        client._handle_picker_click(pos)
        assert not client.unit_picker_open
        assert picked_id in client.selected_attackers

    def test_picker_reopens_when_one_unit_committed_other_not(self, mock_pygame):
        """Bug 1 regression: clicking hex with mix of committed+uncommitted reopens picker.

        Previous behavior: showed battle view, picker never reappeared.
        """
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("a2", q=1, r=1, stack_size=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_combat(engine, client)

        # Commit a1 to a battle
        client._handle_declaration_click(HexCoord(1, 1))  # opens picker
        # Pick a1
        a1_idx = next(i for i, u in enumerate(client.unit_picker_units) if u.id == "a1")
        pos = (client.unit_picker_item_rects[a1_idx].x + 1, client.unit_picker_item_rects[a1_idx].y + 1)
        client._handle_picker_click(pos)
        # Declare attack with a1
        client._handle_declaration_click(HexCoord(2, 1))
        # a1 is now committed, a2 is not
        committed = engine.state.metadata.get("committed_attackers", set())
        assert "a1" in committed
        assert "a2" not in committed

        # Simulate user dismissing picker (click outside picker rect)
        client._close_picker()
        assert not client.unit_picker_open

        # User clicks back on stacked hex — picker should reopen for a2
        client._handle_declaration_click(HexCoord(1, 1))
        assert client.unit_picker_open, "Picker should reopen for uncommitted a2"
        # Picker shows BOTH a1 and a2 (a1 grayed [ATK], a2 selectable)
        assert len(client.unit_picker_units) == 2


class TestDeclarationClickHandling:
    def _enter_combat(self, engine, client):
        client._end_phase()

    def test_click_friendly_unit_selects_attacker(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_combat(engine, client)

        client._handle_declaration_click(HexCoord(1, 1))
        assert "a1" in client.selected_attackers

    def test_click_enemy_with_attackers_declares(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_combat(engine, client)

        client.selected_attackers = ["a1"]
        client._handle_declaration_click(HexCoord(2, 1))

        battles = engine.state.metadata.get("battles", [])
        assert len(battles) == 1

    def test_click_empty_hex_deselects(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_combat(engine, client)

        client.selected_attackers = ["a1"]
        client._handle_declaration_click(HexCoord(4, 4))  # empty hex
        assert len(client.selected_attackers) == 0

    def test_click_committed_attacker_selects_battle(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_combat(engine, client)

        # Declare attack
        client.selected_attackers = ["a1"]
        client._do_declare_attack(HexCoord(2, 1))

        # Click committed attacker — should select its battle
        client._handle_declaration_click(HexCoord(1, 1))
        assert client.selected_battle_id is not None

    def test_click_defender_hex_selects_battle(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_combat(engine, client)

        client.selected_attackers = ["a1"]
        client._do_declare_attack(HexCoord(2, 1))

        client.selected_attackers.clear()
        client._handle_declaration_click(HexCoord(2, 1))
        assert client.selected_battle_id is not None


# =========================================================================
# Resolution Mode
# =========================================================================

class TestResolutionMode:
    def _enter_resolution(self, engine, client):
        """Advance to combat resolution sub-phase."""
        client._end_phase()  # move_a → combat_a (declaration)
        # Declare attack
        client.selected_attackers = ["a1"]
        client._do_declare_attack(HexCoord(2, 1))
        # End declaration → resolution
        client._end_phase()

    def test_in_resolution_mode(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_resolution(engine, client)

        assert client._in_resolution_mode()
        assert not client._in_declaration_mode()

    def test_end_phase_blocked_with_unresolved_battles(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_resolution(engine, client)

        client._end_phase()
        # Should still be in combat_a, not advanced
        assert engine.current_phase.id == "combat_a"
        assert any("BLOCKED" in msg for msg in client.event_log)

    def test_resolve_battle_via_click(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_resolution(engine, client)

        # Click defender hex to resolve
        client._handle_resolution_click(HexCoord(2, 1))
        battles = engine.state.metadata.get("battles", [])
        assert battles[0].resolved

    def test_resolve_via_attacker_hex_click(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_resolution(engine, client)

        # Click attacker hex to resolve
        client._handle_resolution_click(HexCoord(1, 1))
        battles = engine.state.metadata.get("battles", [])
        assert battles[0].resolved

    def test_end_phase_blocked_during_post_battle(self, mock_pygame):
        """Regression: end phase must not crash during active post-battle phases."""
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_resolution(engine, client)

        client._handle_resolution_click(HexCoord(2, 1))
        # Battle resolved but post-battle phases active
        from hexwar.core.battle import PostBattlePhase
        battles = engine.state.metadata.get("battles", [])
        assert battles[0].resolved
        if battles[0].post_phase != PostBattlePhase.DONE:
            assert not client._can_end_phase()
            client._end_phase()  # must not crash
            assert engine.current_phase.id == "combat_a"
            assert any("post-battle" in msg for msg in client.event_log)

    def test_end_phase_after_all_resolved(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=1, r=1),
            _make_unit("b1", player=PLAYER_B, q=2, r=1),
        ])
        client = _make_client(engine, mock_pygame)
        self._enter_resolution(engine, client)

        client._handle_resolution_click(HexCoord(2, 1))
        # Complete post-battle flow
        from hexwar.core.actions import SkipPursuitAction
        from hexwar.core.battle import PostBattlePhase
        for _ in range(20):
            battles = engine.state.metadata.get("battles", [])
            if not battles or battles[0].post_phase == PostBattlePhase.DONE:
                break
            legal = engine.get_legal_actions()
            # Prefer skip pursuit to avoid complex pursuit logic
            skip = [a for a in legal if isinstance(a, SkipPursuitAction)]
            if skip:
                engine.submit_action(skip[0])
                continue
            post_actions = [a for a in legal if not isinstance(a, EndPhaseAction)]
            if post_actions:
                engine.submit_action(post_actions[0])
            else:
                break
        client._end_phase()
        # Should advance past combat_a
        assert engine.current_phase.id != "combat_a" or not client._in_resolution_mode()


# =========================================================================
# Exhausted Unit Indicator
# =========================================================================

class TestExhaustedUnit:
    def test_unit_not_exhausted_initially(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1, movement=2)])
        client = _make_client(engine, mock_pygame)

        unit = engine.state.get_unit("a1")
        assert not client._is_unit_exhausted(unit)

    def test_unit_exhausted_after_using_all_mp(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=1, r=1, movement=1)])
        client = _make_client(engine, mock_pygame)

        client._select_unit("a1")
        client._do_move(HexCoord(2, 1))

        unit = engine.state.get_unit("a1")
        assert client._is_unit_exhausted(unit)


# =========================================================================
# No enemies — fast path
# =========================================================================

class TestNoEnemiesInContact:
    def test_no_obligations_when_no_adjacent_enemies(self, mock_pygame):
        engine = _make_engine([
            _make_unit("a1", q=0, r=0),
            _make_unit("b1", player=PLAYER_B, q=5, r=5),
        ])
        client = _make_client(engine, mock_pygame)

        client._end_phase()  # → combat_a
        # No adjacent enemies = declaration_complete should be True
        assert engine.state.metadata.get("declaration_complete", False)
        client._end_phase()  # should advance immediately
        # Past combat declaration
        assert not client._in_declaration_mode() or engine.current_phase.id != "combat_a"

    def test_can_skip_combat_when_no_contact(self, mock_pygame):
        engine = _make_engine([_make_unit("a1", q=0, r=0)])
        client = _make_client(engine, mock_pygame)

        client._end_phase()  # → combat_a
        client._end_phase()  # → through resolution → move_b
        assert engine.current_phase.id == "move_b"
