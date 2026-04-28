"""Structured recommendation rationale.

The rationale used to be a free-text bullet block. The LLM was forced to
fabricate fields it did not have (e.g. "hours this month") so we now produce
a typed object that the UI can render as labeled chips, sections, and
warnings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Tone = Literal["positive", "neutral", "warning", "danger"]


class RationaleHighlight(BaseModel):
    label: str
    value: str
    tone: Tone = "neutral"


class Rationale(BaseModel):
    headline: str = Field(
        "", description="One-line summary, 8-14 words, plain coordinator language."
    )
    # Kept for backwards-compat with stored responses; the UI now renders
    # its own visualizations from typed fields on ScoredCandidate to avoid
    # showing the same data three different ways.
    highlights: list[RationaleHighlight] = Field(default_factory=list)
    reasons: list[str] = Field(
        default_factory=list,
        description="Insights that go BEYOND what the workload chart and fit "
        "line already convey: cross-training, recent absence, equity, tenure "
        "context. 0-3 short bullets — never repeat numeric data.",
    )
    risks: list[str] = Field(
        default_factory=list,
        description="Caveats / watch-outs the coordinator should know.",
    )
