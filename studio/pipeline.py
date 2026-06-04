"""Deterministic rename rule pipeline definitions.

This module centralises the ordered rule graph that used to live implicitly in
``RenameEngine.process``.  The UI can now reorder the same steps without
changing the individual rule implementations.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PipelineStep:
    """A reusable rename rule group exposed by both engine and editor."""

    key: str
    title: str
    description: str
    accent: str


PIPELINE_STEPS: tuple[PipelineStep, ...] = (
    PipelineStep("name", "Name", "Keep, remove, fix, or reverse the base name.", "#7aa2f7"),
    PipelineStep("regex", "RegEx", "Apply Python regular-expression substitution.", "#bb9af7"),
    PipelineStep("replace", "Replace", "Plain text find/replace with case options.", "#f7768e"),
    PipelineStep("remove", "Remove", "Strip ranges, classes, accents, and whitespace.", "#e0af68"),
    PipelineStep("move_copy", "Move/Copy", "Move or copy a character range.", "#2ac3de"),
    PipelineStep("add", "Add", "Prefix, insert, or suffix text and tokens.", "#9ece6a"),
    PipelineStep("auto_date", "Auto Date", "Add creation, modified, or access dates.", "#73daca"),
    PipelineStep("numbering", "Numbering", "Add deterministic counters.", "#ff9e64"),
    PipelineStep("case", "Case", "Lower, upper, title, or sentence case.", "#c0caf5"),
    PipelineStep("extension", "Extension", "Normalize, replace, or remove file extension.", "#b4f9f8"),
)

DEFAULT_PIPELINE_ORDER: tuple[str, ...] = tuple(step.key for step in PIPELINE_STEPS)
STEP_BY_KEY: dict[str, PipelineStep] = {step.key: step for step in PIPELINE_STEPS}
DEFAULT_PIPELINE_NAME = "Factory Default"


def normalise_pipeline_order(order: Iterable[Any] | None) -> list[str]:
    """Return a deterministic, de-duplicated order containing all known steps.

    Unknown step keys are ignored so old settings/presets stay safe after
    upgrades.  Missing known steps are appended in factory-default order, which
    means partial saved pipelines remain executable.
    """

    result: list[str] = []
    seen: set[str] = set()
    for raw_key in order or ():
        key = str(raw_key)
        if key in STEP_BY_KEY and key not in seen:
            result.append(key)
            seen.add(key)

    for key in DEFAULT_PIPELINE_ORDER:
        if key not in seen:
            result.append(key)
    return result


def default_pipeline_library() -> dict[str, list[str]]:
    """Built-in named pipelines that users can copy/reorder/save."""

    return {
        DEFAULT_PIPELINE_NAME: list(DEFAULT_PIPELINE_ORDER),
        "Clean Then Number": [
            "name",
            "regex",
            "replace",
            "remove",
            "case",
            "add",
            "auto_date",
            "numbering",
            "move_copy",
            "extension",
        ],
        "Metadata Prefix First": [
            "add",
            "name",
            "regex",
            "replace",
            "remove",
            "move_copy",
            "auto_date",
            "numbering",
            "case",
            "extension",
        ],
    }
