

import re
from attr import dataclass


@dataclass(frozen=True)
class CombatResult:
    attacker_casualties: int = 0
    defender_casualties: int = 0
    attacker_retreat: int = 0
    defender_retreat: int = 0
    attacker_deorganized: bool = False
    defender_deorganized: bool = False
    attacker_deorganized_roll: int = 0
    defender_deorganized_roll: int = 0
    victorious_attacker: bool = False
    victorious_defender: bool = False
    victorious_tie: bool = False
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
    def determine_victory(attacker_part: str, defender_part: str) -> tuple[bool, bool, bool]:
        has_B_in_defender = "B" in defender_part
        has_A_in_attacker = "A" in attacker_part
        victorious_attacker = has_B_in_defender and not has_A_in_attacker
        victorious_defender = has_A_in_attacker and not has_B_in_defender
        victorious_tie = not has_A_in_attacker and not has_B_in_defender
        return victorious_attacker, victorious_defender, victorious_tie

    @classmethod
    def from_string(cls, result_str: str, ratio: str) -> "CombatResult":
        """Parse result string like 'A2/-' or '-1/B3D'."""
        attacker, defender = result_str.split("/")

        # Victory flags: mutually exclusive. If both sides show retreat markers,
        # neither side is marked victorious. If neither side shows a retreat
        # marker, mark the result as a tie.
        victorious_attacker, victorious_defender, victorious_tie = cls.determine_victory(attacker, defender)

        return cls(
            attacker_casualties=cls._match_casualties(attacker),
            defender_casualties=cls._match_casualties(defender),
            attacker_retreat=cls._match_retreat(attacker),
            defender_retreat=cls._match_retreat(defender),
            attacker_deorganized="D" in attacker,
            defender_deorganized="D" in defender,
            attacker_deorganized_roll=1 if "*" in attacker else 0,
            defender_deorganized_roll=1 if "*" in defender else 0,
            victorious_attacker=victorious_attacker,
            victorious_defender=victorious_defender,
            victorious_tie=victorious_tie,
            ratio=ratio,
        )
    
    def __str__(self) -> str:
        parts = []
        victory_attacker_str = " (Attacker victorious)" if self.victorious_attacker else ""
        victory_defender_str = " (Defender victorious)" if self.victorious_defender else ""
        victory_tie_str = " (Tie)" if self.victorious_tie else ""
        victory_text = victory_attacker_str + victory_defender_str + victory_tie_str
        
        attacker_parts = []
        defender_parts = []
        if self.attacker_deorganized:
            attacker_parts.append("D" if not self.attacker_deorganized_roll else "*")
        if self.defender_deorganized:
            defender_parts.append("D" if not self.defender_deorganized_roll else "*")
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

        


    