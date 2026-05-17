

import re
from enum import Enum

from attr import dataclass


class BattleOutcome(Enum):
    ATTACKER_WIN = "attacker_win"
    DEFENDER_WIN = "defender_win"
    TIE = "tie"


@dataclass(frozen=True)
class CombatResult:
    attacker_casualties: int = 0
    defender_casualties: int = 0
    attacker_retreat: int = 0
    defender_retreat: int = 0
    attacker_disorganized: bool = False
    defender_disorganized: bool = False
    attacker_disorganized_roll: int = 0
    defender_disorganized_roll: int = 0
    outcome: BattleOutcome = BattleOutcome.TIE
    ratio: str = ""

    @staticmethod
    def _match_casualties(part: str) -> int:
        match = re.search(r"-(\d+)", part)
        return int(match.group(1)) if match else 0
    @staticmethod
    def _match_retreat(part: str) -> int:
        match = re.search(r"[AB](\d+)", part)
        return int(match.group(1)) if match else 0

    @staticmethod
    def determine_victory(attacker_part: str, defender_part: str) -> BattleOutcome:
        has_B_in_defender = "B" in defender_part
        has_A_in_attacker = "A" in attacker_part
        if has_B_in_defender and not has_A_in_attacker:
            return BattleOutcome.ATTACKER_WIN
        if has_A_in_attacker and not has_B_in_defender:
            return BattleOutcome.DEFENDER_WIN
        return BattleOutcome.TIE

    @classmethod
    def from_string(cls, result_str: str, ratio: str) -> "CombatResult":
        """Parse result string like 'A2/-' or '-1/B3D'."""
        attacker, defender = result_str.split("/")

        outcome = cls.determine_victory(attacker, defender)

        return cls(
            attacker_casualties=cls._match_casualties(attacker),
            defender_casualties=cls._match_casualties(defender),
            attacker_retreat=cls._match_retreat(attacker),
            defender_retreat=cls._match_retreat(defender),
            attacker_disorganized="D" in attacker,
            defender_disorganized="D" in defender,
            attacker_disorganized_roll=1 if "*" in attacker else 0,
            defender_disorganized_roll=1 if "*" in defender else 0,
            outcome=outcome,
            ratio=ratio,
        )

    def __str__(self) -> str:
        outcome_labels = {
            BattleOutcome.ATTACKER_WIN: " (Attacker victorious)",
            BattleOutcome.DEFENDER_WIN: " (Defender victorious)",
            BattleOutcome.TIE: " (Tie)",
        }
        victory_text = outcome_labels[self.outcome]

        attacker_parts = []
        defender_parts = []
        if self.attacker_disorganized:
            attacker_parts.append("D" if not self.attacker_disorganized_roll else "*")
        if self.defender_disorganized:
            defender_parts.append("D" if not self.defender_disorganized_roll else "*")
        if self.attacker_retreat:
            attacker_parts.append(f"A{self.attacker_retreat}")
        if self.defender_retreat:
            defender_parts.append(f"B{self.defender_retreat}")
        if self.attacker_casualties:
            attacker_parts.append(f"-{self.attacker_casualties}")
        if self.defender_casualties:
            defender_parts.append(f"-{self.defender_casualties}")
        parts = ["".join(attacker_parts), "".join(defender_parts)]
        return f"{victory_text} {'/'.join(parts) if parts else '-'} (Ratio: {self.ratio})"
