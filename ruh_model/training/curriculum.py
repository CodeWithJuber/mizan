"""NafsCurriculum -- progressive training curriculum based on developmental stages.

Inspired by the Quranic stages of human creation (23:12-14):
1. Nutfah  (نطفة)  -- embryonic: simple short sentences
2. Alaqah  (علقة)  -- clinging: paragraph-level comprehension
3. Mudghah (مضغة)  -- formation: document-level + reasoning
4. Khalq Akhar (خلق آخر) -- new creation: full capability

Each stage progressively increases sequence length, decreases learning rate,
and extends training duration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CurriculumStage:
    """Immutable configuration for a single curriculum stage.

    Attributes:
        name: Stage identifier (used in CLI and config lookup).
        max_seq_len: Maximum sequence length for this stage.
        lr: Learning rate for this stage.
        epochs: Number of training epochs.
        batch_size: Samples per batch.
        description: Human-readable description of the stage.
    """

    name: str
    max_seq_len: int
    lr: float
    epochs: int
    batch_size: int
    description: str


# -- Curriculum stage definitions --

_NUTFAH = CurriculumStage(
    name="nutfah",
    max_seq_len=128,
    lr=3e-4,
    epochs=5,
    batch_size=16,
    description="Embryonic: simple sentences, high LR, short sequences",
)

_ALAQAH = CurriculumStage(
    name="alaqah",
    max_seq_len=512,
    lr=1e-4,
    epochs=10,
    batch_size=8,
    description="Clinging: paragraphs, moderate LR, medium sequences",
)

_MUDGHAH = CurriculumStage(
    name="mudghah",
    max_seq_len=1024,
    lr=5e-5,
    epochs=15,
    batch_size=4,
    description="Formation: documents + reasoning, low LR, long sequences",
)

_KHALQ_AKHAR = CurriculumStage(
    name="khalq_akhar",
    max_seq_len=2048,
    lr=1e-5,
    epochs=20,
    batch_size=2,
    description="New creation: full capability, minimal LR, max sequences",
)

_STAGES_BY_NAME: dict[str, CurriculumStage] = {
    stage.name: stage
    for stage in [_NUTFAH, _ALAQAH, _MUDGHAH, _KHALQ_AKHAR]
}

_STAGES_ORDERED: list[CurriculumStage] = [
    _NUTFAH, _ALAQAH, _MUDGHAH, _KHALQ_AKHAR
]

# Valid stage names for CLI argument validation
VALID_STAGE_NAMES: list[str] = [stage.name for stage in _STAGES_ORDERED]


class NafsCurriculum:
    """Progressive training curriculum manager.

    Provides access to stage configurations by name or as a full
    ordered sequence for multi-stage training.
    """

    def get_stage(self, name: str) -> CurriculumStage:
        """Retrieve a curriculum stage by name.

        Args:
            name: Stage identifier (e.g., "nutfah", "alaqah").

        Returns:
            The corresponding CurriculumStage.

        Raises:
            KeyError: If the stage name is not recognized.
        """
        if name not in _STAGES_BY_NAME:
            valid = ", ".join(VALID_STAGE_NAMES)
            raise KeyError(
                f"Unknown curriculum stage '{name}'. Valid stages: {valid}"
            )
        return _STAGES_BY_NAME[name]

    def get_all_stages(self) -> list[CurriculumStage]:
        """Return all curriculum stages in developmental order.

        Returns:
            Ordered list from nutfah (simplest) to khalq_akhar (most complex).
        """
        return list(_STAGES_ORDERED)

    def get_stage_index(self, name: str) -> int:
        """Return the zero-based index of a stage in the progression.

        Args:
            name: Stage identifier.

        Returns:
            Index (0 = nutfah, 3 = khalq_akhar).

        Raises:
            KeyError: If the stage name is not recognized.
        """
        for idx, stage in enumerate(_STAGES_ORDERED):
            if stage.name == name:
                return idx
        valid = ", ".join(VALID_STAGE_NAMES)
        raise KeyError(
            f"Unknown curriculum stage '{name}'. Valid stages: {valid}"
        )

    def get_remaining_stages(self, from_stage: str) -> list[CurriculumStage]:
        """Return all stages from the given stage onward (inclusive).

        Useful for resuming multi-stage training from a checkpoint.

        Args:
            from_stage: Stage name to start from.

        Returns:
            List of stages from from_stage to khalq_akhar.
        """
        start_idx = self.get_stage_index(from_stage)
        return list(_STAGES_ORDERED[start_idx:])

    def summary(self) -> str:
        """Return a human-readable summary of all curriculum stages."""
        lines: list[str] = ["Nafs Curriculum Stages:"]
        for idx, stage in enumerate(_STAGES_ORDERED):
            lines.append(
                f"  {idx + 1}. {stage.name} -- "
                f"seq_len={stage.max_seq_len}, lr={stage.lr}, "
                f"epochs={stage.epochs}, batch={stage.batch_size}"
            )
            lines.append(f"     {stage.description}")
        return "\n".join(lines)
